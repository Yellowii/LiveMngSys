"""Best-effort pronunciation and symbol annotations for display names."""

from __future__ import annotations

import re
from typing import Any

from pypinyin import Style, pinyin

try:
    import eng_to_ipa as ipa
except ImportError:
    ipa = None


_SYMBOL_NAMES = {
    "❤": "红心", "♥": "红心", "⭐": "星星", "✨": "闪亮", "🔥": "火焰",
    "🌙": "月亮", "☀": "太阳", "☁": "云", "🌤": "晴间多云", "🌥": "多云",
    "🌦": "阵雨", "🌧": "下雨", "⛈": "雷阵雨", "🌩": "雷电", "🌨": "下雪",
    "🌈": "彩虹", "❄": "雪花", "🌸": "樱花", "🌹": "玫瑰",
    "🎵": "音符", "🎶": "多个音符", "👑": "皇冠", "💎": "宝石",
    "🍀": "四叶草", "😊": "微笑", "😂": "笑哭", "🥰": "喜爱",
    "😭": "大哭", "😎": "墨镜笑脸", "👍": "点赞", "🙏": "合十",
    "👨‍👩‍👧": "一家三口", "👨‍👩‍👧‍👦": "一家四口", "👩‍👩‍👧": "家庭",
    "@": "艾特符号", "#": "井号",
}


def _is_han(char: str) -> bool:
    return bool(char) and "\u3400" <= char <= "\u9fff"


def _pinyin_candidates(char: str) -> list[str]:
    readings = pinyin(char, style=Style.TONE, heteronym=True, errors="default")
    values: list[str] = []
    for group in readings:
        for value in group:
            normalized = str(value).strip()
            if normalized and normalized not in values:
                values.append(normalized)
    return values


def _annotate_han_phrase(value: str) -> list[dict[str, Any]]:
    phrase_readings = pinyin(value, style=Style.TONE, heteronym=False, errors="default")
    annotations: list[dict[str, Any]] = []
    for index, char in enumerate(value):
        primary = str(phrase_readings[index][0] if index < len(phrase_readings) and phrase_readings[index] else char).strip()
        candidates = _pinyin_candidates(char)
        alternatives = [candidate for candidate in candidates if candidate != primary]
        annotations.append({
            "text": char,
            "annotation": primary,
            "alternatives": alternatives,
            "kind": "han",
        })
    return annotations


def _english_ipa(word: str) -> str:
    if ipa is None:
        return ""
    converted = ipa.convert(word.lower(), retrieve_all=True)
    value = " / ".join(str(item) for item in converted) if isinstance(converted, list) else str(converted or "")
    value = value.strip()
    if not value or value.endswith("*"):
        return ""
    value = value.replace("*", "")
    return value if value.startswith("/") else f"/{value}/"


def _symbol_name(value: str) -> str:
    return _SYMBOL_NAMES.get(value) or _SYMBOL_NAMES.get(value.rstrip("\ufe0f")) or ""


def _tokens(text: str) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(text):
        english = re.match(r"[A-Za-z]+(?:['-][A-Za-z]+)*", text[index:])
        if english:
            values.append(english.group(0))
            index += len(english.group(0))
            continue
        char = text[index]
        if _is_han(char):
            start = index
            index += 1
            while index < len(text) and _is_han(text[index]):
                index += 1
            values.append(text[start:index])
            continue
        if char.isspace() or char.isdigit():
            values.append(char)
            index += 1
            continue
        cluster = char
        index += 1
        if "\U0001f1e6" <= char <= "\U0001f1ff" and index < len(text) and "\U0001f1e6" <= text[index] <= "\U0001f1ff":
            cluster += text[index]
            index += 1
        while index < len(text):
            following = text[index]
            if following == "\ufe0f" or "\U0001f3fb" <= following <= "\U0001f3ff":
                cluster += following
                index += 1
                continue
            if following == "\u200d" and index + 1 < len(text):
                cluster += following + text[index + 1]
                index += 2
                continue
            break
        values.append(cluster)
    return values


def annotate_nickname(nickname: Any) -> list[dict[str, Any]]:
    """Return display tokens without changing the original nickname."""
    tokens: list[dict[str, Any]] = []
    for value in _tokens(str(nickname or "").strip()):
        if value.isspace():
            continue
        if all(_is_han(char) for char in value):
            tokens.extend(_annotate_han_phrase(value))
            continue
        elif re.fullmatch(r"[A-Za-z]+(?:['-][A-Za-z]+)*", value):
            annotation, kind = _english_ipa(value), "english"
            if not annotation:
                continue
        elif value.isdigit():
            continue
        else:
            annotation, kind = _symbol_name(value), "symbol"
            if not annotation:
                continue
        tokens.append({"text": value, "annotation": annotation, "alternatives": [], "kind": kind})
    return tokens
