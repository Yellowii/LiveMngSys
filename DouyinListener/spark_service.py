"""Browser-backed private-message batch sender for spark renewal workflows."""

from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from Doubao.client.browser_client import _launch_persistent_context
from profile_client import ProfileClient


CHAT_URL = "https://www.douyin.com/chat"
CHAT_PROFILE_DIR = Path(__file__).resolve().parent / "Doubao" / "chat_profile"
CONVERSATION_LIST_SELECTOR = ".conversationConversationListwrapper"
CONVERSATION_ROW_SELECTOR = ".conversationConversationItemwrapper"
MAX_CONVERSATION_SCAN_STEPS = 240
SEARCH_SELECTORS = [
    'input.semi-input[placeholder="搜索"][type="text"]',
    'input[placeholder="搜索"]',
    '.searchSearchInputinput_box input',
    '.LeftPanelHeadersearch input',
]
SEARCH_RESULT_ITEM_SELECTOR = ".SearchPanelitembox"
SEARCH_RESULT_ACTION_SELECTOR = ".SearchPanelitemchat_btn"
EDITOR_SELECTORS = ['div[data-slate-editor="true"][contenteditable="true"]', 'div[contenteditable="true"]']
CHAT_LOGIN_TIMEOUT = 15000
CHAT_UI_TIMEOUT = 45000
GROUP_AVATAR_HOST = "aweme-im-img.byteimg.com"
HITOKOTO_API_URL = "https://v1.hitokoto.cn/"
COPYWRITING_TYPES = {
    "random": ("d", "i", "k"),
    "literature": ("d",),
    "poetry": ("i",),
    "philosophy": ("k",),
}
HITOKOTO_TIMEOUT = 3
FALLBACK_QUOTES = (
    "日子缓缓，愿你心里有光。",
    "把寻常日子，过成喜欢的模样。",
    "愿每一次相遇，都恰逢其时。",
    "心有热爱，奔赴山海。",
    "生活明朗，万物可爱。",
    "愿你的今天，比昨天更温柔。",
)


def _cookie_header(cookies: list[dict]) -> str:
    values = {}
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        if name:
            values[name] = str(cookie.get("value") or "")
    return "; ".join(f"{name}={value}" for name, value in values.items())


def _is_group_avatar(avatar: str) -> bool:
    """Return whether a chat avatar uses Douyin's observed group-image host."""
    try:
        hostname = (urlparse(avatar).hostname or "").lower()
    except (TypeError, ValueError):
        return False
    return hostname == GROUP_AVATAR_HOST or hostname.endswith(f"-{GROUP_AVATAR_HOST}")


def _normalize_recipients(value: Any) -> list[dict[str, str]]:
    if isinstance(value, str):
        value = [{"name": line.strip()} for line in value.splitlines() if line.strip()]
    if not isinstance(value, list):
        return []

    result = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            recipient_id = str(item.get("id") or item.get("conversationId") or name).strip()
            avatar = str(item.get("avatar") or "").strip()
            is_group = bool(item.get("isGroup")) or _is_group_avatar(avatar)
            try:
                list_offset = max(0, int(item.get("listOffset") or 0))
            except (TypeError, ValueError):
                list_offset = 0
        else:
            name = str(item or "").strip()
            recipient_id = name
            avatar = ""
            is_group = False
            list_offset = 0
        if not name or not recipient_id or recipient_id in seen:
            continue
        seen.add(recipient_id)
        recipient = {"id": recipient_id, "name": name}
        if avatar:
            recipient["avatar"] = avatar
        if is_group:
            recipient["isGroup"] = True
        if list_offset:
            recipient["listOffset"] = list_offset
        result.append(recipient)
        if len(result) == 200:
            break
    return result


def _normalize_spark_conversation(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    name = str(value.get("name") or "").strip()
    avatar = str(value.get("avatar") or "").strip()
    try:
        list_offset = max(0, int(value.get("listOffset") or 0))
    except (TypeError, ValueError):
        list_offset = 0
    spark = value.get("spark") or {}
    if not isinstance(spark, dict):
        return None
    label = str(spark.get("label") or "").strip()
    if not name or not label:
        return None
    state = str(spark.get("state") or "active")
    if state not in {"active", "inactive", "reigniting"}:
        state = "active"
    result = {
        "id": str(value.get("id") or f"{name}|{avatar}"),
        "name": name,
        "avatar": avatar,
        "isGroup": bool(value.get("isGroup")) or _is_group_avatar(avatar),
        "spark": {
            "label": label,
            "state": state,
            "icon": str(spark.get("icon") or ""),
        },
    }
    if list_offset:
        result["listOffset"] = list_offset
    return result


def _fetch_hitokoto_quote(categories: tuple[str, ...], opener=urlopen) -> str:
    query = urlencode([("c", category) for category in categories])
    request = Request(
        f"{HITOKOTO_API_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "LiveMngSys/1.0"},
    )
    with opener(request, timeout=HITOKOTO_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    quote = " ".join(str(payload.get("hitokoto") or "").split())
    if not quote:
        raise ValueError("一言接口未返回有效内容")
    return quote[:80]


class SparkManager:
    def __init__(self, profile_client: ProfileClient | None = None) -> None:
        self.login_task: asyncio.Task | None = None
        self.batch_task: asyncio.Task | None = None
        self._batch_lock = asyncio.Lock()
        self._context = None
        self._browser_lock = asyncio.Lock()
        self._recent_friends: list[dict] = []
        self.profile_client = profile_client or ProfileClient()
        self.status = {
            "state": "idle", "login": "unknown", "message": "请先检查私信登录状态",
            "account": None, "accountLoading": False, "accountError": "",
            "current": 0, "total": 0, "completed": 0, "failed": 0,
            "results": [], "updatedAt": int(time.time() * 1000),
        }

    def public_state(self) -> dict:
        return dict(self.status, results=list(self.status["results"]))

    def _set(self, **values: Any) -> None:
        self.status.update(values)
        self.status["updatedAt"] = int(time.time() * 1000)

    @staticmethod
    async def _first_visible(page, selectors: list[str], timeout: int = 10000):
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            for selector in selectors:
                locator = page.locator(selector).first
                try:
                    if await locator.is_visible(timeout=300):
                        return locator
                except Exception:
                    pass
            await asyncio.sleep(0.25)
        return None

    @staticmethod
    async def _logged_in(page, timeout: int = CHAT_LOGIN_TIMEOUT) -> bool:
        if "/login" in page.url:
            return False
        body = await page.locator("body").inner_text(timeout=min(timeout, 5000))
        if any(text in body for text in ("扫码登录", "验证码登录", "登录后即可聊天")):
            return False
        return bool(await SparkManager._first_visible(page, SEARCH_SELECTORS, timeout=timeout))

    async def _refresh_account(self, context) -> bool:
        previous_account = self.status.get("account")
        self._set(accountLoading=True, accountError="")
        try:
            cookies = await context.cookies(["https://www.douyin.com", "https://live.douyin.com"])
            account = await self.profile_client.get_current_account(_cookie_header(cookies))
            self._set(account=account, accountLoading=False, accountError="")
            return True
        except Exception as error:
            self._set(account=previous_account, accountLoading=False, accountError=str(error))
            return False

    async def check_login(self) -> dict:
        if self.login_task and not self.login_task.done():
            return self.public_state()
        previous_login = self.status.get("login")
        try:
            from playwright.async_api import async_playwright
            async with self._browser_lock:
                async with async_playwright() as playwright:
                    context = await _launch_persistent_context(playwright, CHAT_PROFILE_DIR, headless=True)
                    try:
                        page = context.pages[0] if context.pages else await context.new_page()
                        await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=60000)
                        chat_ready = await self._logged_in(page)
                        account_ready = await self._refresh_account(context)
                        if chat_ready or account_ready:
                            self._set(login="logged_in", message="私信已登录")
                        elif previous_login == "logged_in":
                            self._set(login="logged_in", message="私信登录检查暂时失败，保留当前登录态")
                        else:
                            self._set(login="logged_out", message="私信尚未登录", account=None, accountLoading=False)
                    finally:
                        await context.close()
        except Exception as error:
            if previous_login == "logged_in":
                self._set(login="logged_in", message="私信登录检查暂时失败，保留当前登录态", accountLoading=False, accountError=str(error))
            else:
                self._set(login="error", message=f"登录检查失败：{error}", account=None, accountLoading=False)
        return self.public_state()

    async def start_login(self) -> tuple[bool, str]:
        if self.login_task and not self.login_task.done():
            return True, "私信登录窗口已打开"
        if self.batch_task and not self.batch_task.done():
            return False, "批量任务运行中，不能切换登录状态"
        self._set(login="waiting", message="请在打开的浏览器中完成抖音登录", account=None, accountLoading=False, accountError="")
        self.login_task = asyncio.create_task(self._run_login(), name="douyin-spark-login")
        return True, "私信登录窗口已打开"

    async def _run_login(self) -> None:
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as playwright:
                self._context = await _launch_persistent_context(playwright, CHAT_PROFILE_DIR, headless=False)
                page = self._context.pages[0] if self._context.pages else await self._context.new_page()
                await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=60000)
                deadline = time.monotonic() + 300
                while time.monotonic() < deadline:
                    if await self._logged_in(page):
                        self._set(login="logged_in", message="私信登录成功")
                        await self._refresh_account(self._context)
                        return
                    await asyncio.sleep(1)
                self._set(login="error", message="私信登录超时")
        except asyncio.CancelledError:
            self._set(login="logged_out", message="私信登录已取消", account=None, accountLoading=False)
            raise
        except Exception as error:
            self._set(login="error", message=f"私信登录失败：{error}", account=None, accountLoading=False)
        finally:
            if self._context:
                await self._context.close()
                self._context = None

    async def cancel_login(self) -> tuple[bool, str]:
        if self.login_task and not self.login_task.done():
            self.login_task.cancel()
            await asyncio.gather(self.login_task, return_exceptions=True)
        return True, "私信登录已取消"

    async def _collect_spark_conversations(self, page) -> list[dict]:
        conversation_list = page.locator(CONVERSATION_LIST_SELECTOR).first
        if not await conversation_list.is_visible(timeout=CHAT_LOGIN_TIMEOUT):
            raise RuntimeError("未找到私信会话列表，抖音页面结构可能已变化")

        collected: dict[str, dict] = {}
        for _ in range(MAX_CONVERSATION_SCAN_STEPS):
            rows = await conversation_list.evaluate("""(list, rowSelector) => [...list.querySelectorAll(rowSelector)].map(row => {
                const nameNode = row.querySelector('[class*="item-header-name-"], .conversationConversationItemtitle');
                const streakNode = row.querySelector('.commonStreakstreakContainer');
                const streakIcon = row.querySelector('.commonStreakicon');
                const avatar = [...row.querySelectorAll('img')].find(image => !image.classList.contains('commonStreakicon'));
                const name = (nameNode && nameNode.textContent || '').trim();
                const label = (streakNode && streakNode.textContent || '').trim();
                const icon = streakIcon && streakIcon.getAttribute('src') || '';
                const typeHints = [
                    row.getAttribute('data-conversation-type'),
                    row.getAttribute('data-chat-type'),
                    row.className,
                    ...[...row.querySelectorAll('[class], [aria-label], [title]')].map(node =>
                        `${node.className || ''} ${node.getAttribute('aria-label') || ''} ${node.getAttribute('title') || ''}`
                    )
                ].filter(Boolean).join(' ');
                return {
                    name,
                    avatar: avatar && avatar.getAttribute('src') || '',
                    listOffset: list.scrollTop,
                    isGroup: /(group|群聊|群组)/i.test(typeHints)
                        || Boolean(avatar && avatar.classList.contains('commonConversationIconnoDrag') && /群/.test(name)),
                    spark: label ? {
                        label,
                        icon,
                        state: label.includes('\u91cd\u71c3\u4e2d') ? 'reigniting' : icon.includes('/gray_') ? 'inactive' : 'active'
                    } : null
                };
            })""", CONVERSATION_ROW_SELECTOR)
            for row in rows:
                conversation = _normalize_spark_conversation(row)
                if conversation:
                    collected.setdefault(conversation["id"], conversation)

            position = await conversation_list.evaluate("list => ({ top: list.scrollTop, height: list.scrollHeight, client: list.clientHeight })")
            next_top = min(position["top"] + max(int(position["client"] * 0.82), 1), max(position["height"] - position["client"], 0))
            if next_top <= position["top"]:
                break
            await conversation_list.evaluate("(list, top) => { list.scrollTop = top; }", next_top)
            await asyncio.sleep(0.08)

        await conversation_list.evaluate("list => { list.scrollTop = 0; }")
        return list(collected.values())

    async def list_friends(self) -> list[dict]:
        try:
            from playwright.async_api import async_playwright
            async with self._browser_lock:
                async with async_playwright() as playwright:
                    context = await _launch_persistent_context(playwright, CHAT_PROFILE_DIR, headless=True)
                    try:
                        page = context.pages[0] if context.pages else await context.new_page()
                        await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=60000)
                        if not await self._logged_in(page):
                            raise RuntimeError("请先登录抖音私信")
                        result = await self._collect_spark_conversations(page)
                        self._recent_friends = result
                        return list(result)
                    finally:
                        await context.close()
        except Exception:
            if self._recent_friends:
                return list(self._recent_friends)
            raise

    async def generate_copywriting(self, kind: str, count: int) -> list[str]:
        categories = COPYWRITING_TYPES.get(kind)
        if not categories:
            raise ValueError("不支持的文案类型")
        count = max(1, min(5, count))
        responses = await asyncio.gather(
            *(asyncio.to_thread(_fetch_hitokoto_quote, categories) for _ in range(count)),
            return_exceptions=True,
        )
        quotes = []
        for response in responses:
            if isinstance(response, str) and response not in quotes:
                quotes.append(response)
        for quote in random.sample(FALLBACK_QUOTES, len(FALLBACK_QUOTES)):
            if len(quotes) >= count:
                break
            if quote not in quotes:
                quotes.append(quote)
        return quotes[:count]

    async def start_batch(self, payload: dict) -> tuple[bool, str]:
        recipients = _normalize_recipients(payload.get("recipients"))
        message = str(payload.get("message") or "").strip()
        if not recipients:
            return False, "请从最近会话列表选择至少一位接收人"
        if not message:
            return False, "消息内容不能为空"
        interval = max(2.0, min(30.0, float(payload.get("interval") or 3)))
        options = {
            "recipients": recipients, "message": message, "interval": interval,
            "linkMode": bool(payload.get("linkMode")), "dryRun": bool(payload.get("dryRun")),
        }
        async with self._batch_lock:
            if self.batch_task and not self.batch_task.done():
                return False, "已有批量任务正在运行"
            self.batch_task = None
            self._set(state="queued", message="批量任务已排队", current=0, total=len(recipients), completed=0, failed=0, results=[])
            self.batch_task = asyncio.create_task(self._run_batch(options), name="douyin-spark-batch")
            return True, "批量任务已启动"

    @staticmethod
    def _same_avatar(left: str, right: str) -> bool:
        return left.split("?", 1)[0] == right.split("?", 1)[0]

    async def _find_search_result(self, page, recipient: dict[str, str]):
        name = recipient["name"]
        expected_avatar = str(recipient.get("avatar") or "")
        deadline = time.monotonic() + CHAT_UI_TIMEOUT / 1000
        fallback = None
        while time.monotonic() < deadline:
            items = page.locator(SEARCH_RESULT_ITEM_SELECTOR)
            count = await items.count()
            for index in range(count):
                item = items.nth(index)
                try:
                    if not await item.is_visible(timeout=250):
                        continue
                    title = (await item.locator(".SearchPanelitemtitle").first.inner_text(timeout=500)).strip()
                    if title != name:
                        continue
                    fallback = fallback or item
                    if not expected_avatar:
                        return item
                    avatar = await item.locator("img").first.get_attribute("src")
                    if avatar and self._same_avatar(expected_avatar, avatar):
                        return item
                except Exception:
                    continue
            if fallback:
                return fallback
            await asyncio.sleep(0.35)
        return None

    async def _open_from_conversation_list(self, page, recipient: dict[str, str]):
        conversation_list = page.locator(CONVERSATION_LIST_SELECTOR).first
        try:
            await conversation_list.wait_for(state="visible", timeout=CHAT_UI_TIMEOUT)
        except Exception:
            return None

        name = recipient["name"]
        expected_avatar = str(recipient.get("avatar") or "")
        try:
            list_offset = max(0, int(recipient.get("listOffset") or 0))
        except (TypeError, ValueError):
            list_offset = 0
        fallback = None
        try:
            await conversation_list.evaluate("(list, top) => { list.scrollTop = top; }", list_offset)
            await asyncio.sleep(1.2)
            for _ in range(MAX_CONVERSATION_SCAN_STEPS):
                rows = conversation_list.locator(CONVERSATION_ROW_SELECTOR)
                count = await rows.count()
                for index in range(count):
                    row = rows.nth(index)
                    try:
                        title = (await row.locator('[class*="item-header-name-"], .conversationConversationItemtitle').first.inner_text(timeout=400)).strip()
                        if title != name:
                            continue
                        fallback = fallback or row
                        avatar = await row.locator("img").evaluate_all("images => { const image = images.find(item => !item.classList.contains('commonStreakicon')); return image && image.getAttribute('src') || ''; }")
                        if expected_avatar and (not avatar or not self._same_avatar(expected_avatar, avatar)):
                            continue
                        await row.click()
                        return await self._first_visible(page, EDITOR_SELECTORS, timeout=CHAT_UI_TIMEOUT)
                    except Exception:
                        continue

                position = await conversation_list.evaluate("list => ({ top: list.scrollTop, height: list.scrollHeight, client: list.clientHeight })")
                next_top = min(position["top"] + max(int(position["client"] * 0.82), 1), max(position["height"] - position["client"], 0))
                if next_top <= position["top"]:
                    break
                await conversation_list.evaluate("(list, top) => { list.scrollTop = top; }", next_top)
                await asyncio.sleep(0.35)

            if fallback:
                await fallback.click()
                return await self._first_visible(page, EDITOR_SELECTORS, timeout=CHAT_UI_TIMEOUT)
            return None
        finally:
            await conversation_list.evaluate("list => { list.scrollTop = 0; }")

    async def _open_conversation(self, page, recipient: dict[str, str]):
        name = recipient["name"]
        if recipient.get("isGroup"):
            editor = await self._open_from_conversation_list(page, recipient)
            if editor:
                return editor
        search = await self._first_visible(page, SEARCH_SELECTORS, timeout=CHAT_UI_TIMEOUT)
        if not search:
            editor = await self._open_from_conversation_list(page, recipient)
            if editor:
                return editor
            raise RuntimeError("未找到私信搜索框或会话列表，抖音页面结构可能已变化")
        await search.fill(name)
        result = await self._find_search_result(page, recipient)
        if result:
            action = result.locator(SEARCH_RESULT_ACTION_SELECTOR).first
            if await action.is_visible(timeout=1000):
                await action.click()
            else:
                await result.click()
            editor = await self._first_visible(page, EDITOR_SELECTORS, timeout=CHAT_UI_TIMEOUT)
            if editor:
                return editor

        await search.fill("")
        await page.keyboard.press("Escape")
        editor = await self._open_from_conversation_list(page, recipient)
        if editor:
            return editor
        raise RuntimeError("搜索结果和会话列表中均未找到该会话")

    async def _run_batch(self, options: dict) -> None:
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as playwright:
                self._context = await _launch_persistent_context(playwright, CHAT_PROFILE_DIR, headless=True)
                page = self._context.pages[0] if self._context.pages else await self._context.new_page()
                await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=60000)
                if not await self._logged_in(page):
                    raise RuntimeError("私信登录已失效，请重新登录")
                self._set(state="running", login="logged_in", message="正在执行批量续火花")
                for index, recipient in enumerate(options["recipients"], start=1):
                    recipient_name = recipient["name"]
                    self._set(current=index, message=f"正在处理 {recipient_name}")
                    try:
                        editor = await self._open_conversation(page, recipient)
                        await editor.click()
                        await page.keyboard.press("Control+A")
                        await page.keyboard.press("Backspace")
                        content = options["message"]
                        await page.keyboard.insert_text(content)
                        if options["linkMode"]:
                            await asyncio.sleep(2)
                        if not options["dryRun"]:
                            await page.keyboard.press("Enter")
                        result = {"recipient": recipient_name, "recipientId": recipient["id"], "content": content, "ok": True, "status": "预演完成" if options["dryRun"] else "已发送"}
                        self.status["completed"] += 1
                    except Exception as error:
                        result = {"recipient": recipient_name, "recipientId": recipient["id"], "ok": False, "status": str(error)}
                        self.status["failed"] += 1
                    self.status["results"].append(result)
                    self.status["results"] = self.status["results"][-200:]
                    self._set()
                    if index < len(options["recipients"]):
                        await asyncio.sleep(options["interval"])
                self._set(state="completed", message=f"任务完成：成功 {self.status['completed']}，失败 {self.status['failed']}")
        except asyncio.CancelledError:
            self._set(state="stopped", message="批量任务已停止")
            raise
        except Exception as error:
            self._set(state="error", message=str(error))
        finally:
            if self._context:
                await self._context.close()
                self._context = None

    async def stop_batch(self) -> tuple[bool, str]:
        async with self._batch_lock:
            task = self.batch_task
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if self.batch_task is task:
                self.batch_task = None
            self._set(state="stopped", message="批量任务已停止")
            return True, "批量任务已停止"

    async def close(self) -> None:
        await self.cancel_login()
        await self.stop_batch()
