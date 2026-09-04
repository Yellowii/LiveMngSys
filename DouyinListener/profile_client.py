"""Authenticated Douyin web profile lookup using the listener login state."""

from __future__ import annotations

import time
import urllib.parse
import json
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from Doubao.client.browser_client import load_saved_cookie_header
from Doubao.client.signed_fetch import request_ms_token, signing_user_agent
from nickname_annotation import annotate_nickname
from vendor.douyin_spider_signing import ABogusPureSigner


PROFILE_URL = "https://www.douyin.com/aweme/v1/web/user/profile/other/"
CURRENT_ACCOUNT_URL = "https://live.douyin.com/webcast/user/me/"


def _cookies(header: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in header.split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            result[key] = value
    return result


def _image_url(image: Any) -> str:
    if not isinstance(image, dict):
        return ""
    urls = image.get("url_list") or image.get("urlList") or []
    return str(urls[0]) if isinstance(urls, list) and urls else ""


def _normalize_current_account(response: Any) -> dict:
    if not isinstance(response, dict) or int(response.get("status_code") or 0) != 0:
        message = response.get("status_msg") if isinstance(response, dict) else ""
        raise RuntimeError(str(message or "当前登录账号信息获取失败"))
    user = response.get("data") or {}
    if not isinstance(user, dict) or not (user.get("id") or user.get("id_str") or user.get("sec_uid")):
        raise RuntimeError("抖音当前账号接口未返回用户资料")
    sec_uid = str(user.get("sec_uid") or "")
    return {
        "uid": str(user.get("id_str") or user.get("id") or ""),
        "secUid": sec_uid,
        "displayId": str(user.get("display_id") or user.get("short_id") or ""),
        "nickname": str(user.get("nickname") or "抖音用户"),
        "avatar": _image_url(user.get("avatar_medium") or user.get("avatar_large") or user.get("avatar_thumb")),
        "profileUrl": f"https://www.douyin.com/user/{sec_uid}" if sec_uid else "",
    }


class ProfileClient:
    CACHE_SECONDS = 600

    def __init__(self) -> None:
        self._signer = ABogusPureSigner(fixed=False)
        self._cache: dict[str, tuple[float, dict]] = {}

    async def get_current_account(self, cookie_header: str | None = None) -> dict:
        if cookie_header is None:
            cookie_header = load_saved_cookie_header()
        cookie_values = _cookies(cookie_header)
        if "sessionid" not in cookie_values:
            raise RuntimeError("请先完成抖音登录")

        timeout = ClientTimeout(total=20)
        async with ClientSession(timeout=timeout) as http:
            ms_token = await request_ms_token(http, cookie_values.get("ttwid", ""))
            params = [
                ("aid", "6383"), ("app_name", "douyin_web"), ("live_id", "1"),
                ("device_platform", "web"), ("language", "zh-CN"),
                ("enter_from", "web_live"), ("cookie_enabled", "true"),
                ("screen_width", "1920"), ("screen_height", "1080"),
                ("browser_language", "zh-CN"), ("browser_platform", "Win32"),
                ("browser_name", "Edge"), ("browser_version", "150.0.0.0"),
                ("os_name", "Windows"), ("os_version", "10"),
                ("room_id", "0"), ("msToken", ms_token),
            ]
            query = "&".join(f"{key}={urllib.parse.quote(str(value))}" for key, value in params)
            params.append(("a_bogus", self._signer.sign(f"https://live.douyin.com/?{query}")))
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Cookie": cookie_header,
                "Referer": "https://live.douyin.com/",
                "User-Agent": signing_user_agent(),
            }
            async with http.get(CURRENT_ACCOUNT_URL, params=params, headers=headers) as response:
                raw_body = await response.read()
                data = json.loads(raw_body.decode("utf-8", errors="replace"))
                if response.status >= 400:
                    raise RuntimeError(f"抖音当前账号接口返回 HTTP {response.status}")
        return _normalize_current_account(data)

    async def get_profile(self, sec_uid: str) -> dict:
        sec_uid = str(sec_uid or "").strip()
        if not sec_uid:
            raise ValueError("当前消息没有可用于查询主页的 sec_uid")
        cached = self._cache.get(sec_uid)
        if cached and time.time() - cached[0] < self.CACHE_SECONDS:
            return cached[1]

        cookie_header = load_saved_cookie_header()
        cookie_values = _cookies(cookie_header)
        if "sessionid" not in cookie_values:
            raise RuntimeError("请先在实时弹幕配置页完成抖音登录")

        verify_fp = cookie_values.get("s_v_web_id", "")
        timeout = ClientTimeout(total=20)
        async with ClientSession(timeout=timeout) as http:
            ms_token = await request_ms_token(http, cookie_values.get("ttwid", ""))
            params = [
                ("device_platform", "webapp"), ("aid", "6383"),
                ("channel", "channel_pc_web"), ("sec_user_id", sec_uid),
                ("publish_video_strategy_type", "2"), ("source", "channel_pc_web"),
                ("personal_center_strategy", "1"), ("update_version_code", "170400"),
                ("pc_client_type", "1"), ("pc_libra_divert", "Windows"),
                ("version_code", "170400"), ("version_name", "17.4.0"),
                ("cookie_enabled", "true"), ("screen_width", "1920"),
                ("screen_height", "1080"), ("browser_language", "zh-CN"),
                ("browser_platform", "Win32"), ("browser_name", "Edge"),
                ("browser_version", signing_user_agent()), ("browser_online", "true"),
                ("engine_name", "Blink"), ("os_name", "Windows"), ("os_version", "10"),
                ("cpu_core_num", "16"), ("device_memory", "8"), ("platform", "PC"),
                ("downlink", "10"), ("effective_type", "4g"), ("round_trip_time", "50"),
                ("webid", cookie_values.get("passport_csrf_token", "")),
                ("verifyFp", verify_fp), ("fp", verify_fp), ("msToken", ms_token),
            ]
            query = "&".join(f"{key}={urllib.parse.quote(str(value))}" for key, value in params)
            params.append(("a_bogus", self._signer.sign(f"https://www.douyin.com/?{query}")))
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Cookie": cookie_header,
                "Referer": f"https://www.douyin.com/user/{sec_uid}",
                "User-Agent": signing_user_agent(),
            }
            async with http.get(PROFILE_URL, params=params, headers=headers) as response:
                raw_body = await response.read()
                data = json.loads(raw_body.decode("utf-8", errors="replace"))
                if response.status >= 400:
                    raise RuntimeError(f"抖音主页接口返回 HTTP {response.status}")

        if not isinstance(data, dict) or int(data.get("status_code") or 0) != 0:
            raise RuntimeError(str(data.get("status_msg") or "主页信息获取失败"))
        user = data.get("user") or {}
        nickname = str(user.get("nickname") or "未知用户")
        location = str(user.get("ip_location") or "").replace("IP属地：", "").replace("IP属地:", "").strip()
        result = {
            "secUid": str(user.get("sec_uid") or sec_uid),
            "uid": str(user.get("uid") or ""),
            "uniqueId": str(user.get("unique_id") or user.get("short_id") or ""),
            "nickname": nickname,
            "nicknameAnnotation": annotate_nickname(nickname),
            "avatar": _image_url(user.get("avatar_larger") or user.get("avatar_medium") or user.get("avatar_thumb")),
            "signature": str(user.get("signature") or ""),
            "gender": int(user.get("gender") or 0),
            "followers": int(user.get("follower_count") or 0),
            "following": int(user.get("following_count") or 0),
            "likes": int(user.get("total_favorited") or 0),
            "works": int(user.get("aweme_count") or 0),
            "ipLocation": location,
            "profileUrl": f"https://www.douyin.com/user/{sec_uid}",
        }
        self._cache[sec_uid] = (time.time(), result)
        return result
