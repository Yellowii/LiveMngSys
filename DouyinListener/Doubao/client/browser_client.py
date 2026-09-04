"""Browser-backed Douyin listener.

This client lets a real browser page perform login, signing, and WebSocket
handshake, then feeds received binary frames into the Doubao protobuf parser.
It does not depend on danmu-server.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
import urllib.parse
from pathlib import Path
from typing import Dict, Optional

from Doubao.client.auth_qr import SAVE_COOKIES_TO
from Doubao.client.wss_client import ClientConfig, DouyinWssClient, SessionSaver, _extract_room_enter_info

_log = logging.getLogger("Doubao.browser_client")

BROWSER_PROFILE_DIR = Path(__file__).resolve().parent.parent / "browser_profile"
MEDIA_EXT_RE = re.compile(r"\.(?:m3u8|flv|mp4|webm|m4s|ts)(?:[?#]|$)", re.I)
AUDIENCE_RANK_PATH = "/webcast/ranklist/audience/"
ROOM_ENTER_PATH = "/webcast/room/web/enter/"


def _parse_cookie_header(header: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in (header or "").split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            if k:
                out[k] = v
    return out


def _cookies_to_header(cookies) -> str:
    pairs = []
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        domain = c.get("domain", "")
        if name and value is not None and "douyin.com" in domain:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def load_saved_cookie_header() -> str:
    if not SAVE_COOKIES_TO.exists():
        return ""
    try:
        data = json.loads(SAVE_COOKIES_TO.read_text(encoding="utf-8"))
    except Exception:
        return ""
    cookies = data.get("cookies") or {}
    if not isinstance(cookies, dict):
        return ""
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if k and v is not None)


async def _launch_persistent_context(playwright, user_data_dir: Path, headless: bool = False):
    user_data_dir.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--window-size=1280,900",
        ],
    }
    try:
        return await playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            channel="msedge",
            **kwargs,
        )
    except Exception:
        return await playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            **kwargs,
        )


async def browser_login_cookie_header(cfg: Optional[ClientConfig] = None, timeout_sec: int = 180) -> str:
    """Open an independent browser profile and wait until Douyin session cookies exist."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError("缂哄皯 playwright锛氳杩愯 pip install playwright") from e

    cfg = cfg or ClientConfig()
    async with async_playwright() as p:
        context = None
        try:
            context = await _launch_persistent_context(p, BROWSER_PROFILE_DIR, headless=False)
            if cfg.cookie:
                await _add_cookie_header_to_context(context, cfg.cookie)
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://live.douyin.com/", wait_until="domcontentloaded", timeout=60000)
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                header = _cookies_to_header(await context.cookies())
                if "sessionid=" in header:
                    _save_cookie_header(header)
                    return header
                await asyncio.sleep(1.0)
        finally:
            if context is not None:
                with contextlib.suppress(Exception):
                    await context.close()
    raise RuntimeError("browser login timed out: complete Douyin login in the opened browser")


async def _add_cookie_header_to_context(context, header: str):
    cookies = []
    for name, value in _parse_cookie_header(header).items():
        cookies.append({
            "name": name,
            "value": value,
            "domain": ".douyin.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "Lax",
        })
    if cookies:
        await context.add_cookies(cookies)


def _save_cookie_header(header: str):
    cookies = _parse_cookie_header(header)
    if not cookies:
        return
    SAVE_COOKIES_TO.parent.mkdir(parents=True, exist_ok=True)
    SAVE_COOKIES_TO.write_text(json.dumps({
        "saved_at": int(time.time()),
        "source": "Doubao browser profile",
        "cookies": cookies,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


async def _route_without_media(route):
    request = route.request
    url = request.url
    if request.resource_type == "media" or MEDIA_EXT_RE.search(url):
        await route.abort()
        return
    await route.continue_()


class DouyinBrowserClient(DouyinWssClient):
    """Use a real browser WebSocket and Doubao parsing/storage."""

    def __init__(self, cfg: ClientConfig):
        super().__init__(cfg)
        self._context = None
        self._page = None
        self._context_lock = asyncio.Lock()
        self._seen_ws = set()
        self._ws_ready = None
        self._last_ws_frame = 0.0
        self._last_wss_url = ""
        self._last_fetch_url = ""
        self._last_audience_url = ""
        self._last_audience_emit = 0.0

    def _emit_audience_rank(self, data, url: str):
        self._last_audience_url = url
        self._last_audience_emit = time.time()
        payload = data.get("data") if isinstance(data, dict) else {}
        ranks = payload.get("ranks") if isinstance(payload, dict) else []
        rec = {
            "ts": int(time.time() * 1000),
            "seq": self.seq,
            "method": "WebcastAudienceRankList",
            "msg_id": "",
            "url": url,
            "parsed": data,
        }
        self._emit(rec)
        _log.info(
            "audience_rank_list ranks=%s invisible=%s",
            len(ranks or []),
            payload.get("invisible_total") if isinstance(payload, dict) else "",
        )

    def _emit_room_info_from_response(self, data, url: str):
        if not isinstance(data, dict):
            return
        info = _extract_room_enter_info(data, self.room_id or self.cfg.room_id)
        if info.get("title"):
            self.title = info["title"]
        if info.get("anchor"):
            self.anchor = info["anchor"]
        self.live_id = info.get("liveId") or self.live_id
        self.cover = info.get("cover") or self.cover
        self.anchor_id = info.get("anchorId") or self.anchor_id
        self.sec_anchor_id = info.get("secAnchorId") or self.sec_anchor_id
        self.anchor_avatar = info.get("avatar") or self.anchor_avatar
        if self.saver is None and (self.room_id or self.cfg.room_id):
            self.saver = SessionSaver(self.cfg, self.room_id or self.cfg.room_id, self.title, self.live_id, self.anchor)
            _log.info("session dir=%s", self.saver.session_dir)
        rec = {
            "ts": int(time.time() * 1000),
            "seq": self.seq,
            "method": "LiveMngRoomInfo",
            "msg_id": "",
            "url": url,
            "parsed": {
                **info,
                "roomId": self.room_id or self.cfg.room_id,
                "title": self.title,
                "anchor": self.anchor,
                "avatar": self.anchor_avatar,
                "anchorId": self.anchor_id,
                "secAnchorId": self.sec_anchor_id,
                "liveId": self.live_id,
                "cover": self.cover,
            },
        }
        self._emit(rec)

    async def _emit_room_info(self):
        if not self._page or self._page.is_closed():
            return
        try:
            info = await self._page.evaluate(
                """() => {
                    const meta = (name) => document.querySelector(
                        'meta[name="' + name + '"],meta[property="' + name + '"]'
                    )?.content || '';
                    const text = (selectors) => {
                        for (const selector of selectors) {
                            const value = document.querySelector(selector)?.textContent?.trim();
                            if (value) return value;
                        }
                        return '';
                    };
                    const image = (selectors) => {
                        for (const selector of selectors) {
                            const node = document.querySelector(selector);
                            const value = node?.currentSrc || node?.src || '';
                            if (value) return value;
                        }
                        return '';
                    };
                    const bodyText = document.body?.innerText || '';
                    const roomMissing = /\u623f\u95f4\u4e0d\u5b58\u5728|\u76f4\u64ad\u95f4\u4e0d\u5b58\u5728/.test(bodyText);
                    const notLive = /\u6682\u672a\u5f00\u64ad|\u4e3b\u64ad\u6682\u672a\u5f00\u64ad|\u76f4\u64ad\u5df2\u7ed3\u675f|\u4e3b\u64ad\u4f11\u606f\u4e2d/.test(bodyText);
                    return {
                        title: meta('og:title') || text(['h1']) || document.title.replace(/\\s*-\\s*鎶栭煶鐩存挱.*$/, ''),
                        description: meta('description') || meta('og:description'),
                        anchor: text(['[class*="anchor"] [class*="name"]', '[class*="author"] [class*="name"]']),
                        avatar: image(['[class*="anchor"] img', '[class*="author"] img', 'img[alt*="涓绘挱"]', 'img[alt*="澶村儚"]']),
                        roomExists: !roomMissing,
                        roomState: roomMissing ? 'not_found' : notLive ? 'not_live' : 'unknown',
                        isLive: notLive ? false : null,
                    };
                }"""
            )
        except Exception as error:
            _log.debug("room metadata extraction failed: %s", error)
            return
        if not isinstance(info, dict):
            return
        self.title = info.get("title") or self.title
        self.anchor = info.get("anchor") or self.anchor
        if self.saver is None and (self.room_id or self.cfg.room_id):
            self.saver = SessionSaver(self.cfg, self.room_id or self.cfg.room_id, self.title, self.live_id, self.anchor)
            _log.info("session dir=%s", self.saver.session_dir)
        self._emit({
            "ts": int(time.time() * 1000),
            "seq": self.seq,
            "method": "LiveMngRoomInfo",
            "msg_id": "",
            "parsed": {
                "roomId": self.room_id or self.cfg.room_id,
                "liveId": self.live_id,
                "title": self.title,
                "description": info.get("description") or "",
                "cover": self.cover,
                "anchor": self.anchor,
                "avatar": info.get("avatar") or "",
                "roomExists": info.get("roomExists"),
                "roomState": info.get("roomState") or "unknown",
                "isLive": info.get("isLive"),
            },
        })

    def _target_url(self) -> str:
        if self.cfg.room_url:
            return self.cfg.room_url
        if self.cfg.room_id:
            return f"https://live.douyin.com/{self.cfg.room_id}"
        raise RuntimeError("璇峰～鍐欑洿鎾棿 URL 鎴栨埧闂村彿")

    def _payload_to_bytes(self, payload) -> Optional[bytes]:
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, str):
            try:
                import base64
                return base64.b64decode(payload, validate=True)
            except Exception:
                try:
                    return payload.encode("latin1")
                except Exception:
                    return None
        return None

    async def _handle_browser_frame(self, payload):
        raw = self._payload_to_bytes(payload)
        if not raw:
            return
        self._last_ws_frame = time.time()
        decoded = False
        for resp in self._decode_responses(raw):
            decoded = True
            self._handle_response(resp)
        if not decoded:
            _log.debug("skip browser websocket frame len=%s", len(raw))

    def _on_websocket(self, ws):
        url = ws.url
        if "/webcast/im/push/v2/" not in url:
            return
        self._last_wss_url = url
        self._seen_ws.add(id(ws))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        stream_session_id = (q.get("room_id") or [""])[0]
        configured_room_id = str(self.cfg.room_id or "").strip()
        # The page WebSocket uses room_id for the long live-session identifier.
        # Keep the configured short room number as the archive room identity.
        self.room_id = self.room_id or configured_room_id or stream_session_id
        if stream_session_id and stream_session_id != self.room_id and not self.live_id:
            self.live_id = stream_session_id
        if self.saver is None:
            self.saver = SessionSaver(self.cfg, self.room_id or "unknown", self.title, self.live_id, self.anchor)
            _log.info("session dir=%s", self.saver.session_dir)
        _log.info("browser websocket attached host=%s room_id=%s", urllib.parse.urlparse(url).netloc, self.room_id)
        if self._ws_ready and not self._ws_ready.is_set():
            self._ws_ready.set()
        self._last_ws_frame = time.time()

        def on_frame(payload):
            try:
                asyncio.create_task(self._handle_browser_frame(payload))
            except Exception as e:
                _log.warning("websocket frame handler error: %s", e)

        ws.on("framereceived", on_frame)

    async def _handle_browser_response(self, response):
        url = response.url
        if "/webcast/im/fetch/" in url:
            self._last_fetch_url = url
        if ROOM_ENTER_PATH in url or "/webcast/room/enter/" in url:
            try:
                data = await response.json()
            except Exception as e:
                _log.debug("room enter response parse failed: %s", e)
            else:
                self._emit_room_info_from_response(data, url)
        if AUDIENCE_RANK_PATH not in url:
            return
        now = time.time()
        if url == self._last_audience_url and now - self._last_audience_emit < 0.5:
            return
        try:
            data = await response.json()
        except Exception as e:
            _log.debug("audience rank response parse failed: %s", e)
            return
        self._emit_audience_rank(data, url)

    async def _poll_audience_rank_list(self):
        if not self._last_audience_url or not self._page or self._page.is_closed():
            return False
        before = self._last_audience_emit
        try:
            data = await self._page.evaluate(
                """async (url) => {
                    const resp = await fetch(url, {
                        credentials: 'include',
                        cache: 'no-store',
                    });
                    return await resp.json();
                }""",
                self._last_audience_url,
            )
        except Exception as e:
            _log.debug("audience rank active poll failed: %s", e)
            return False
        if self._last_audience_emit == before:
            self._emit_audience_rank(data, self._last_audience_url)
        return True

    async def _nudge_audience_panel(self):
        if not self._page or self._page.is_closed():
            return
        try:
            count = await self._page.evaluate(
                """() => {
                    const selectors = [
                        '.vYlYuXg3', '.axSXNioG', '.P3Zz1HOZ', '.sDE_n_gz',
                        'div[class*="audience"]', 'button', 'a', '[role="tab"]', '[role="button"]'
                    ];
                    const seen = new Set();
                    const items = [];
                    for (const selector of selectors) {
                        document.querySelectorAll(selector).forEach((el) => {
                            if (!seen.has(el)) {
                                seen.add(el);
                                items.push(el);
                            }
                        });
                    }
                    document.querySelectorAll('div,span,button,a,[role="tab"],[role="button"]').forEach((el) => {
                        const text = (el.textContent || '').trim();
                        if (text.length > 0 && text.length < 30 && /瑙備紬|鍦ㄧ嚎|鎺掑悕/.test(text) && !seen.has(el)) {
                            seen.add(el);
                            items.push(el);
                        }
                    });
                    for (const el of items.slice(0, 20)) {
                        const r = el.getBoundingClientRect();
                        const x = Math.max(1, r.left + Math.min(10, Math.max(1, r.width / 2)));
                        const y = Math.max(1, r.top + Math.min(10, Math.max(1, r.height / 2)));
                        for (const type of ['mouseenter', 'mouseover', 'mousemove']) {
                            el.dispatchEvent(new MouseEvent(type, {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                                clientX: x,
                                clientY: y
                            }));
                        }
                    }
                    return items.length;
                }"""
            )
            if count and not self._last_audience_url:
                _log.info("audience panel hover triggered candidates=%s", count)
        except Exception as e:
            _log.debug("audience panel hover trigger failed: %s", e)

    async def _close_context(self):
        async with self._context_lock:
            context = self._context
            page = self._page
            self._context = None
            self._page = None
        if not context:
            return
        browser = None
        try:
            browser = context.browser
        except Exception:
            browser = None
        try:
            if page and not page.is_closed():
                await asyncio.wait_for(page.close(), timeout=5)
        except asyncio.TimeoutError:
            _log.debug("ignore browser page close timeout")
        except Exception as e:
            _log.debug("ignore browser page close error: %s", e)
        try:
            await asyncio.wait_for(context.close(), timeout=10)
        except asyncio.TimeoutError:
            _log.debug("ignore browser context close timeout")
        except Exception as e:
            _log.debug("ignore browser context close error: %s", e)
        if browser:
            try:
                await asyncio.wait_for(browser.close(), timeout=5)
            except asyncio.TimeoutError:
                _log.debug("ignore browser close timeout")
            except Exception as e:
                _log.debug("ignore browser close error: %s", e)

    async def _launch_context(self, playwright, headless: bool):
        async with self._context_lock:
            if self._context is not None:
                raise RuntimeError("browser context already active")
            self._context = await _launch_persistent_context(playwright, BROWSER_PROFILE_DIR, headless=headless)
            return self._context

    async def shutdown(self):
        self._stop = True
        if self._ws_ready and not self._ws_ready.is_set():
            self._ws_ready.set()
        await self._close_context()

    async def _run_browser_session(self, playwright, headless: bool):
        self._seen_ws.clear()
        self._ws_ready = asyncio.Event()
        _log.info("browser mode=%s profile=%s", "headless" if headless else "visible", BROWSER_PROFILE_DIR)
        self._context = await self._launch_context(playwright, headless=headless)
        if bool(getattr(self.cfg, "browser_block_media", True)):
            await self._context.route("**/*", _route_without_media)
            _log.info("browser media requests blocked")
        if self.cfg.cookie:
            await _add_cookie_header_to_context(self._context, self.cfg.cookie)
        self._context.on("page", lambda page: (
            page.on("websocket", self._on_websocket),
            page.on("response", lambda response: asyncio.create_task(self._handle_browser_response(response))),
        ))
        for page in self._context.pages:
            page.on("websocket", self._on_websocket)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        await self._page.set_viewport_size({"width": 1280, "height": 900})
        self._page.on("websocket", self._on_websocket)
        self._page.on("response", lambda response: asyncio.create_task(self._handle_browser_response(response)))
        self._page.on("close", lambda: _log.warning("browser page closed before/while listening"))
        self._page.on("crash", lambda: _log.error("browser page crashed"))
        _log.info("__STATUS__:connected")
        await self._page.goto(self._target_url(), wait_until="commit", timeout=30000)
        timeout = float(getattr(self.cfg, "browser_wss_timeout", 25.0) or 25.0)
        try:
            await asyncio.wait_for(self._ws_ready.wait(), timeout=timeout)
        except asyncio.TimeoutError as e:
            raise RuntimeError(
                f"{timeout:.0f}s without a live websocket; check login, room id, or visible browser mode"
            ) from e
        if self._stop:
            return
        await asyncio.sleep(1.0)
        await self._emit_room_info()
        while not self._stop:
            if not self._context or not self._page or self._page.is_closed():
                raise RuntimeError("browser context or page closed")
            await asyncio.sleep(1.0)
            now = time.time()
            # Refresh the page if no websocket frames arrive for a while.
            if self._last_ws_frame and now - self._last_ws_frame > 30:
                _log.warning("WSS stalled for %ss; refreshing the page", int(now - self._last_ws_frame))
                self._seen_ws.clear()
                self._last_ws_frame = 0
                try:
                    await self._page.reload(wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(3)
                except Exception as e:
                    _log.warning("椤甸潰鍒锋柊澶辫触: %s", e)

    async def _run_browser_session_loop(self, playwright, headless: bool):
        attempt = 0
        current_headless = headless
        fallback_used = False
        while not self._stop:
            try:
                attempt += 1
                await self._run_browser_session(playwright, headless=current_headless)
                return
            except Exception as e:
                await self._close_context()
                if self._stop:
                    return
                fallback = (
                    current_headless
                    and bool(getattr(self.cfg, "browser_auto_visible_fallback", True))
                    and not fallback_used
                    and not self._seen_ws
                )
                if fallback:
                    fallback_used = True
                    current_headless = False
                    _log.warning("headless 鏈缓绔嬬洿鎾斁娴侊紝鍒囨崲鍙绐楀彛閲嶈瘯: %s", e)
                    continue
                if not bool(getattr(self.cfg, "reconnect", True)):
                    _log.warning("browser session stopped: %s", e)
                    return
                max_retry = int(getattr(self.cfg, "reconnect_max", 10) or 10)
                if attempt > max_retry:
                    _log.warning("browser session exceeded retry limit (%s/%s): %s", attempt, max_retry, e)
                    return
                delay = float(getattr(self.cfg, "reconnect_delay", 3.0) or 3.0)
                _log.warning("browser connect loop error (%s/%s): %s", attempt, max_retry, e)
                _log.info("__STATUS__:reconnect")
                await asyncio.sleep(delay)

    async def connect_and_run(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError("缂哄皯 playwright锛氳杩愯 pip install playwright") from e

        try:
            async with async_playwright() as p:
                headless = bool(getattr(self.cfg, "browser_headless", True))
                if not self.cfg.cookie:
                    self.cfg.cookie = load_saved_cookie_header()
                await self._run_browser_session_loop(p, headless=headless)
        finally:
            self._stop = True
            if self.saver:
                self.saver.close()
                self.saver = None
            await self._close_context()
            _log.info("__STATUS__:stopped")
