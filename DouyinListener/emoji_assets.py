"""Resolve Douyin chat emoji display names to official image URLs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "emoji" / "emoji_list.json"
EMOJI_LIST_URL = "https://live.douyin.com/aweme/v1/web/emoji/list"
_emoji_map: dict[str, str] = {}


def _map_from_payload(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    result: dict[str, str] = {}
    for item in payload.get("emoji_list") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("display_name") or "").strip()
        image = item.get("emoji_url") or {}
        urls = image.get("url_list") if isinstance(image, dict) else []
        url = str(urls[0]).strip() if isinstance(urls, list) and urls else ""
        if name and url.startswith(("http://", "https://")):
            result[name] = url
    return result


def load_emoji_cache() -> dict[str, str]:
    global _emoji_map
    try:
        _emoji_map = _map_from_payload(json.loads(CACHE_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        _emoji_map = {}
    return dict(_emoji_map)


def refresh_emoji_cache() -> int:
    """Refresh the official list; retain the last valid cache on failure."""
    global _emoji_map
    try:
        request = Request(EMOJI_LIST_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        resolved = _map_from_payload(payload)
        if not resolved:
            raise ValueError("Douyin emoji list is empty")
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _emoji_map = resolved
    except Exception:
        logging.exception("Failed to refresh Douyin emoji list")
        if not _emoji_map:
            load_emoji_cache()
    return len(_emoji_map)


def emoji_url(display_name: str) -> str:
    if not _emoji_map:
        load_emoji_cache()
    return _emoji_map.get(str(display_name or "").strip(), "")


def register_emoji_url(display_name: str, url: str) -> None:
    name = str(display_name or "").strip()
    image = str(url or "").strip()
    if name and image.startswith(("http://", "https://")):
        _emoji_map[name] = image
