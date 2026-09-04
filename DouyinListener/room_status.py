"""Signed room-status probe used independently from the barrage transport."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import urllib.parse
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from Doubao.client.browser_client import load_saved_cookie_header
from Doubao.client.signed_fetch import request_ms_token, signing_user_agent
from profile_client import _cookies
from vendor.douyin_spider_signing import ABogusPureSigner


ROOM_ENTER_URL = "https://live.douyin.com/webcast/room/web/enter/"
LIVE_ROOM_STATUSES = {2}
OFFLINE_ROOM_STATUSES = {0, 1, 3, 4}


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _room_entry(response: dict) -> dict:
    data = response.get("data") if isinstance(response, dict) else {}
    items = data.get("data") if isinstance(data, dict) else data if isinstance(data, list) else []
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return {}
    return items[0]


def _response_data(response: dict) -> dict:
    data = response.get("data") if isinstance(response, dict) else {}
    return data if isinstance(data, dict) else {}


def classify_room_response(response: dict, checked_at: int | None = None, web_rid: str = "") -> dict:
    """Normalize room/web/enter responses without treating failed probes as offline."""
    checked_at = checked_at or int(time.time() * 1000)
    code = _integer(response.get("status_code") or response.get("statusCode") or response.get("code"))
    message = str(response.get("status_msg") or response.get("statusMessage") or response.get("message") or "")
    item = _room_entry(response)
    raw_status = _integer(item.get("status") or (item.get("room") or {}).get("status"))
    explicit_live = item.get("is_live", item.get("isLive"))
    if not isinstance(explicit_live, bool):
        explicit_live = (item.get("room") or {}).get("is_live", (item.get("room") or {}).get("isLive"))

    text = message.lower()
    if any(token in message for token in ("不存在", "已注销", "无访问权限")) or "not found" in text:
        room_state = "not_found"
    elif not item:
        room_state = "unknown"
    elif explicit_live is True or raw_status in LIVE_ROOM_STATUSES:
        room_state = "live"
    elif explicit_live is False or raw_status in OFFLINE_ROOM_STATUSES:
        room_state = "not_live"
    else:
        room_state = "unknown"

    data = _response_data(response)
    room = item.get("room") if isinstance(item.get("room"), dict) else item
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else room.get("owner") if isinstance(room.get("owner"), dict) else data.get("user") if isinstance(data.get("user"), dict) else {}
    return {
        "roomState": room_state,
        "isLive": room_state == "live",
        "checkedAt": checked_at,
        "statusCode": code,
        "statusMessage": message,
        "rawStatus": raw_status,
        "roomId": str(web_rid or item.get("web_rid") or ""),
        "sessionId": str(item.get("id_str") or item.get("id") or room.get("id_str") or room.get("id") or ""),
        "liveId": str(item.get("live_id") or room.get("live_id") or ""),
        "title": str(item.get("title") or room.get("title") or ""),
        "anchorId": str(item.get("owner_user_id_str") or owner.get("id_str") or owner.get("id") or ""),
        "secAnchorId": str(owner.get("sec_uid") or owner.get("secUid") or ""),
        "anchorDisplayId": str(owner.get("display_id") or owner.get("displayId") or owner.get("unique_id") or owner.get("uniqueId") or owner.get("short_id") or owner.get("shortId") or ""),
        "anchor": str(owner.get("nickname") or owner.get("nick_name") or ""),
    }


class RoomStatusProbe:
    def __init__(self) -> None:
        self._browser_lock = asyncio.Lock()

    async def _open_page(self):
        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()
        browser = None
        try:
            try:
                browser = await playwright.chromium.launch(
                    channel="msedge",
                    headless=True,
                    args=["--disable-background-networking", "--disable-component-update"],
                )
            except Exception:
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=["--disable-background-networking", "--disable-component-update"],
                )
            page = await browser.new_page(viewport={"width": 1280, "height": 900})

            async def block_media(route):
                if route.request.resource_type in {"media", "image", "font", "stylesheet"}:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", block_media)
            return playwright, browser, page
        except BaseException:
            if browser is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(browser.close(), timeout=8)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(playwright.stop(), timeout=8)
            raise

    async def _close_page(self, playwright, browser, page) -> None:
        if page is not None:
            with contextlib.suppress(Exception):
                if not page.is_closed():
                    await asyncio.wait_for(page.close(), timeout=5)
        if browser is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(browser.close(), timeout=8)
        if playwright is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(playwright.stop(), timeout=8)

    async def close(self) -> None:
        return None

    async def _probe_page_state(self, web_rid: str) -> dict:
        """Read the rendered room state because room/web/enter can retain a closed session."""
        try:
            import playwright.async_api  # noqa: F401
        except ImportError:
            return {"pageState": "unknown", "pageStatusMessage": "浏览器状态探测不可用"}

        async with self._browser_lock:
            playwright = browser = page = None
            try:
                playwright, browser, page = await self._open_page()
                try:
                    await page.goto(f"https://live.douyin.com/{web_rid}", wait_until="commit", timeout=10000)
                    await page.wait_for_function(
                        """() => /\\u76f4\\u64ad\\u5df2\\u7ed3\\u675f|\\u6682\\u672a\\u5f00\\u64ad|\\u4e3b\\u64ad\\u4f11\\u606f\\u4e2d|\\u76f4\\u64ad\\u95f4\\u4e0d\\u5b58\\u5728/.test(document.body?.innerText || '')""",
                        timeout=3000,
                    )
                except Exception:
                    pass
                result = await page.evaluate(
                    """() => {
                        const text = document.body?.innerText || '';
                        if (/\\u76f4\\u64ad\\u95f4\\u4e0d\\u5b58\\u5728|\\u623f\\u95f4\\u4e0d\\u5b58\\u5728/.test(text)) return { pageState: 'not_found', pageStatusMessage: '\\u76f4\\u64ad\\u95f4\\u4e0d\\u5b58\\u5728' };
                        if (/\\u76f4\\u64ad\\u5df2\\u7ed3\\u675f/.test(text)) return { pageState: 'not_live', pageStatusMessage: '\\u76f4\\u64ad\\u5df2\\u7ed3\\u675f' };
                        if (/\\u6682\\u672a\\u5f00\\u64ad|\\u4e3b\\u64ad\\u4f11\\u606f\\u4e2d/.test(text)) return { pageState: 'not_live', pageStatusMessage: '\\u6682\\u672a\\u5f00\\u64ad' };
                        return { pageState: 'unknown', pageStatusMessage: '' };
                    }"""
                )
                return result if isinstance(result, dict) else {"pageState": "unknown", "pageStatusMessage": ""}
            except asyncio.CancelledError:
                raise
            except Exception as error:
                return {"pageState": "unknown", "pageStatusMessage": f"页面状态探测失败: {error}"}
            finally:
                await self._close_page(playwright, browser, page)

    async def probe(self, room_id: str, verify_page: bool = True) -> dict:
        web_rid = str(room_id or "").strip()
        if not web_rid:
            raise ValueError("请先配置直播间房间号")
        cookie_header = load_saved_cookie_header()
        cookie_values = _cookies(cookie_header)
        params = [
            ("aid", "6383"), ("app_name", "douyin_web"), ("live_id", "1"),
            ("device_platform", "web"), ("language", "zh-CN"), ("enter_from", "web_live"),
            ("cookie_enabled", "true"), ("screen_width", "1920"), ("screen_height", "1080"),
            ("browser_language", "zh-CN"), ("browser_platform", "Win32"),
            ("browser_name", "Edge"), ("browser_version", "150.0.0.0"),
            ("os_name", "Windows"), ("os_version", "10"), ("web_rid", web_rid),
            ("enter_source", ""), ("is_need_double_stream", "false"),
            ("insert_task_id", ""), ("live_reason", ""),
        ]
        timeout = ClientTimeout(total=20)
        async with ClientSession(timeout=timeout) as http:
            ms_token = await request_ms_token(http, cookie_values.get("ttwid", ""))
            params.append(("msToken", ms_token))
            query = "&".join(f"{key}={urllib.parse.quote(str(value))}" for key, value in params)
            params.append(("a_bogus", ABogusPureSigner(fixed=False).sign(f"https://live.douyin.com/?{query}")))
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Cookie": cookie_header,
                "Referer": f"https://live.douyin.com/{web_rid}",
                "User-Agent": signing_user_agent(),
            }
            async with http.get(ROOM_ENTER_URL, params=params, headers=headers) as response:
                raw = await response.read()
                if response.status >= 400:
                    raise RuntimeError(f"直播间状态接口返回 HTTP {response.status}")
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as error:
            raise RuntimeError("直播间状态接口返回了无效数据") from error
        if not isinstance(payload, dict):
            raise RuntimeError("直播间状态接口返回了无效结构")
        result = classify_room_response(payload, web_rid=web_rid)
        if not verify_page or result.get("roomState") not in {"live", "unknown"}:
            result.update({
                "pageChecked": False,
                "pageState": "not_checked",
                "pageStatusMessage": "",
            })
            return result
        page_state = await self._probe_page_state(web_rid)
        page_state["pageChecked"] = True
        result.update(page_state)
        if page_state.get("pageState") in {"not_live", "not_found"}:
            result["roomState"] = page_state["pageState"]
            result["isLive"] = False
            result["statusMessage"] = page_state.get("pageStatusMessage") or result.get("statusMessage") or ""
        return result
