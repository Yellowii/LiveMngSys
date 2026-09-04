"""Build a signed Douyin live protobuf fetch URL without launching a browser."""

import re
import urllib.parse
from typing import Iterable, Tuple

from aiohttp import ClientSession

from vendor.douyin_spider_signing import ABogusPureSigner, build_report_body, get_profile


MS_TOKEN_URL = "https://mssdk.bytedance.com/web/common?ms_appid=6383"
FETCH_URL = "https://live.douyin.com/webcast/im/fetch/"
AUDIENCE_URL = "https://live.douyin.com/webcast/ranklist/audience/"

_signer = ABogusPureSigner(fixed=False)


def signing_user_agent() -> str:
    return get_profile()["ua"]


async def request_ms_token(
    http: ClientSession,
    ttwid: str = "",
    proxy: str | None = None,
) -> str:
    profile = get_profile()
    headers = {
        "User-Agent": profile["ua"],
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://www.douyin.com",
        "Referer": "https://www.douyin.com/",
    }
    if ttwid:
        headers["Cookie"] = f"ttwid={ttwid}"

    async with http.post(
        MS_TOKEN_URL,
        data=build_report_body().encode("utf-8"),
        headers=headers,
        proxy=proxy,
    ) as response:
        await response.read()
        if response.status >= 400:
            return ""
        token = response.headers.get("x-ms-token", "")
        if token:
            return token
        cookie_token = response.cookies.get("msToken")
        if cookie_token:
            return cookie_token.value
        match = re.search(r"(?:^|[,;]\s*)msToken=([^;,]+)", response.headers.get("set-cookie", ""))
        return match.group(1) if match else ""


def _query_for_signature(params: Iterable[Tuple[str, str]]) -> str:
    return "&".join(
        f"{key}={urllib.parse.quote(str(value))}" for key, value in params
    )


def _build_signed_url(endpoint: str, params: list[Tuple[str, str]]) -> str:
    signature_query = _query_for_signature(params)
    a_bogus = _signer.sign(f"https://www.douyin.com/?{signature_query}")
    params.append(("a_bogus", a_bogus))
    return f"{endpoint}?{urllib.parse.urlencode(params)}"


def build_signed_fetch_url(room_id: str, user_unique_id: str, ms_token: str) -> str:
    profile = get_profile()
    params = [
        ("resp_content_type", "protobuf"),
        ("did_rule", "3"),
        ("device_id", ""),
        ("app_name", "douyin_web"),
        ("endpoint", "live_pc"),
        ("support_wrds", "1"),
        ("user_unique_id", str(user_unique_id)),
        ("identity", "audience"),
        ("need_persist_msg_count", "15"),
        ("insert_task_id", ""),
        ("live_reason", ""),
        ("room_id", str(room_id)),
        ("version_code", "180800"),
        ("last_rtt", "0"),
        ("live_id", "1"),
        ("aid", "6383"),
        ("fetch_rule", "1"),
        ("cursor", ""),
        ("internal_ext", ""),
        ("device_platform", "web"),
        ("cookie_enabled", "true"),
        ("screen_width", "2560"),
        ("screen_height", "1440"),
        ("browser_language", "en"),
        ("browser_platform", profile.get("platform", "Win32")),
        ("browser_name", "Mozilla"),
        ("browser_version", profile["ua"]),
        ("browser_online", "true"),
        ("tz_name", "Asia/Shanghai"),
        ("msToken", ms_token),
    ]
    return _build_signed_url(FETCH_URL, params)


def build_signed_audience_url(
    room_id: str,
    anchor_id: str,
    sec_anchor_id: str,
    ms_token: str,
) -> str:
    profile = get_profile()
    params = [
        ("aid", "6383"),
        ("app_name", "douyin_web"),
        ("live_id", "1"),
        ("device_platform", "web"),
        ("language", "zh-CN"),
        ("enter_from", "link_share"),
        ("cookie_enabled", "true"),
        ("screen_width", "1280"),
        ("screen_height", "900"),
        ("browser_language", "zh-CN"),
        ("browser_platform", profile.get("platform", "Win32")),
        ("browser_name", "Edge"),
        ("browser_version", "150.0.0.0"),
        ("os_name", "Windows"),
        ("os_version", "10"),
        ("webcast_sdk_version", "2450"),
        ("room_id", str(room_id)),
        ("anchor_id", str(anchor_id)),
        ("sec_anchor_id", str(sec_anchor_id)),
        ("ignoreToast", "true"),
        ("rank_type", "30"),
        ("msToken", ms_token),
    ]
    return _build_signed_url(AUDIENCE_URL, params)
