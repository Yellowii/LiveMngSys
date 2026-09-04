"""Normalize Doubao events into the stable state consumed by LiveMngSys."""

from __future__ import annotations

import base64
import json
import re
import time
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Any

from emoji_assets import emoji_url, register_emoji_url


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


BADGE_CONFIG_PATH = Path(__file__).resolve().parent / "Doubao" / "dict" / "badge_urls.json"
BADGE_KIND_ALIASES = {
    "fans_club": "fans",
    "pay_grade": "consumer",
}
BADGE_DISPLAY_ORDER = {
    "consumer": 10,
    "live_star": 20,
    "badge": 20,
    "vip": 20,
    "top_vip": 20,
    "medal": 20,
    "avatar_border": 20,
    "fans": 30,
    "guard": 30,
    "member": 40,
    "annual_member": 40,
    "subscribe": 40,
    "admin": 50,
}


def _load_badge_rules() -> tuple[list[dict], dict]:
    fallback = {"kind": "badge", "label": "徽章", "bg_color": "#555555", "fg_color": "#cccccc"}
    try:
        data = json.loads(BADGE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], fallback
    rules = [rule for rule in data.get("categories", []) if isinstance(rule, dict)]
    rules.sort(key=lambda rule: -_number(rule.get("priority")))
    default = data.get("default") if isinstance(data.get("default"), dict) else fallback
    return rules, {**fallback, **default}


BADGE_RULES, BADGE_DEFAULT = _load_badge_rules()


def _first_http_url(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"https?://[^\x00-\x20\"'<>]+", text)
    return match.group(0) if match else text


def _image_url(image: Any) -> str:
    if isinstance(image, str):
        return _first_http_url(image)
    if not isinstance(image, dict):
        return ""
    urls = image.get("urlList") or image.get("url_list") or []
    if isinstance(urls, list) and urls:
        return _first_http_url(urls[0])
    return _first_http_url(image.get("url") or image.get("uri") or "")


def _badge_image_url(image: Any) -> str:
    url = _image_url(image)
    return url if url.startswith(("http://", "https://")) else ""


def _image_uri(image: Any) -> str:
    if not isinstance(image, dict):
        return ""
    return str(image.get("uri") or "")


def _image_identity(image: Any) -> str:
    if not isinstance(image, dict):
        return str(image or "").lower()
    urls = image.get("urlList") or image.get("url_list") or []
    values = [image.get("uri"), image.get("url")]
    if isinstance(urls, list):
        values.extend(urls)
    return " ".join(str(value) for value in values if value).lower()


def _classify_badge(image: Any) -> tuple[str, str, str, str]:
    identity = _image_identity(image)
    image_type = _number((image or {}).get("imageType") or (image or {}).get("image_type")) if isinstance(image, dict) else 0
    if "ranklist_fansclub" in identity and "advanced_badge_" in identity:
        if "ranklist_fansclub_pop_" not in identity and (image_type == 51 or "_xmp" in identity):
            return "guard", "星守护", "#b37feb", "#ffffff"
        return "fans_club", "粉丝团", "#ff6b35", "#ffffff"
    for rule in BADGE_RULES:
        if any(str(token).lower() in identity for token in rule.get("match", [])):
            kind = str(rule.get("kind") or "badge")
            label = str(rule.get("label") or "徽章")
            regex = rule.get("extract_level_regex")
            label_format = rule.get("label_format")
            if regex and label_format:
                match = re.search(str(regex), identity)
                if match:
                    level = next((group for group in match.groups() if group), "")
                    if level:
                        label = str(label_format).replace("{level}", level)
            return kind, label, str(rule.get("bg_color") or ""), str(rule.get("fg_color") or "")
    if image_type == 59:
        return "member", "会员", "#c0392b", "#f5d76e"
    return (
        str(BADGE_DEFAULT.get("kind") or "badge"),
        str(BADGE_DEFAULT.get("label") or "徽章"),
        str(BADGE_DEFAULT.get("bg_color") or ""),
        str(BADGE_DEFAULT.get("fg_color") or ""),
    )


def _badge_level_from_filename(kind: str, image: Any) -> int:
    filename = (_image_uri(image) or _image_url(image)).split("?", 1)[0].split("~", 1)[0].lower().rsplit("/", 1)[-1]
    if not filename:
        return 0
    if kind == "pay_grade":
        match = re.search(r"(?:level_v\d+_|grade_level_v\d+_)(\d+)", filename)
        return int(match.group(1)) if match else 0
    if kind in {"fans_club", "guard"}:
        match = re.search(r"(?:level_v\d+_|badge_)(\d+)", filename)
        return int(match.group(1)) if match else 0
    return 0


def _emoji_image_url(payload: dict) -> str:
    emoji = payload.get("emoji") or {}
    for image in (
        payload.get("emojiImage"), payload.get("emoji_image"),
        emoji.get("image") if isinstance(emoji, dict) else None,
        emoji.get("icon") if isinstance(emoji, dict) else None,
    ):
        url = _image_url(image)
        if url:
            return url

    display = payload.get("displayText") or (payload.get("common") or {}).get("displayText") or {}
    if isinstance(display, dict):
        pieces = (display.get("pieces") or []) + (display.get("piecesV2") or display.get("pieces_v2") or [])
        for piece in pieces:
            if isinstance(piece, dict):
                url = _image_url(piece.get("imageValue") or piece.get("image_value"))
                if url:
                    return url

    content = payload.get("content")
    if isinstance(content, str) and content:
        try:
            raw = base64.b64decode(content, validate=True)
        except (ValueError, TypeError):
            raw = b""
        match = re.search(rb"https?://[^\x00-\x20]+", raw)
        if match:
            return match.group(0).decode("ascii", errors="ignore")
    return ""


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    if value.get("defaultPattern"):
        return str(value["defaultPattern"])
    pieces = []
    for piece in (value.get("pieces") or []) + (value.get("piecesV2") or value.get("pieces_v2") or []):
        if not isinstance(piece, dict):
            continue
        pieces.append(str(piece.get("stringValue") or piece.get("text") or ""))
    return "".join(pieces)


def _display_text_render(value: Any) -> str:
    """Render display-text pieces without exposing the protocol template."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    rendered = []
    values = []
    for piece in (value.get("pieces") or []) + (value.get("piecesV2") or value.get("pieces_v2") or []):
        if not isinstance(piece, dict):
            values.append("")
            continue
        user_value = piece.get("userValue")
        user = _first_dict(
            piece.get("user"),
            user_value.get("user") if isinstance(user_value, dict) else user_value,
        )
        if user:
            nickname = str(user.get("nickname") or user.get("userName") or "").strip()
            values.append(nickname)
            if nickname:
                rendered.append(nickname)
            continue
        text = str(piece.get("stringValue") or piece.get("text") or "").strip()
        values.append(text)
        if text:
            rendered.append(text)
    pattern = str(value.get("defaultPattern") or "")
    if pattern:
        return re.sub(
            r"\{(\d+):[^}]+\}",
            lambda match: values[int(match.group(1))] if int(match.group(1)) < len(values) else "",
            pattern,
        ).strip()
    return "".join(rendered)


def _content_segments(content: str) -> list[dict[str, str]]:
    """Split normal chat text using the same [display_name] convention as Douyin web."""
    if not content:
        return []
    segments: list[dict[str, str]] = []
    cursor = 0
    matched = False
    for match in re.finditer(r"(\[[^\[\]\r\n]{1,32}\])", content):
        if match.start() > cursor:
            segments.append({"type": "text", "text": content[cursor:match.start()]})
        token = match.group(1)
        image = emoji_url(token)
        if image:
            segments.append({"type": "emoji", "text": token, "name": token[1:-1], "image": image})
            matched = True
        else:
            segments.append({"type": "text", "text": token})
        cursor = match.end()
    if cursor < len(content):
        segments.append({"type": "text", "text": content[cursor:]})
    return segments if matched else []


def _register_activity_emoji_groups(payload: dict) -> int:
    registered = 0
    effective_groups = payload.get("activityEmojiGroups") or payload.get("activity_emoji_groups") or []
    for effective in effective_groups:
        if not isinstance(effective, dict):
            continue
        group = effective.get("emojiGroup") or effective.get("emoji_group") or {}
        if not isinstance(group, dict):
            continue
        group_name = str(group.get("name") or "").strip()
        if not group_name:
            continue
        for item in group.get("emojiList") or group.get("emoji_list") or []:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("name") or "").strip()
            image = _image_url(item.get("emoji"))
            if item_name and image:
                register_emoji_url(f"[{group_name}_{item_name}]", image)
                registered += 1
    return registered


def _first_dict(*values: Any) -> dict:
    return next((value for value in values if isinstance(value, dict) and value), {})


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, bytes):
        candidates = [value]
        try:
            candidates.append(base64.b64decode(value, validate=True))
        except (ValueError, TypeError):
            pass
    elif isinstance(value, str) and value.strip():
        candidates = [value.encode("utf-8")]
        try:
            candidates.append(base64.b64decode(value, validate=True))
        except (ValueError, TypeError):
            pass
    else:
        return {}
    for candidate in candidates:
        try:
            parsed = json.loads(candidate.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _protobuf_varint_fields(value: Any) -> dict[int, int]:
    if isinstance(value, str):
        try:
            data = base64.b64decode(value, validate=True)
        except (ValueError, TypeError):
            return {}
    elif isinstance(value, bytes):
        data = value
    else:
        return {}

    def read_varint(position: int) -> tuple[int, int]:
        result = shift = 0
        while position < len(data):
            current = data[position]
            position += 1
            result |= (current & 0x7F) << shift
            if not current & 0x80:
                return result, position
            shift += 7
        raise ValueError("truncated protobuf varint")

    values: dict[int, int] = {}
    position = 0
    try:
        while position < len(data):
            tag, position = read_varint(position)
            number, wire_type = tag >> 3, tag & 7
            if wire_type == 0:
                values[number], position = read_varint(position)
            elif wire_type == 1:
                position += 8
            elif wire_type == 2:
                length, position = read_varint(position)
                position += length
            elif wire_type == 5:
                position += 4
            else:
                return {}
            if position > len(data):
                return {}
    except ValueError:
        return {}
    return values


def _protobuf_varint_field(value: Any, field_number: int) -> int:
    return _protobuf_varint_fields(value).get(field_number, 0)


def _first_value(mapping: dict, *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _merge_dicts(*values: Any) -> dict:
    result: dict = {}
    for value in values:
        if isinstance(value, dict):
            result.update(value)
    return result


def normalize_user(user: Any) -> dict:
    user = user if isinstance(user, dict) else {}
    uid = (
        user.get("id") or user.get("idStr") or user.get("shortId")
        or user.get("openId") or user.get("secUid") or ""
    )
    gender_value = _number(user.get("gender"))
    gender = "male" if gender_value == 1 else "female" if gender_value == 2 else "unknown"
    avatar = ""
    for key in ("avatarThumb", "avatarMedium", "avatarLarge", "avatar_thumb", "avatar"):
        avatar = _image_url(user.get(key))
        if avatar:
            break

    badges = []

    def add_badge(badge_type: str, label: str, image: Any = None, level: int = 0, source: str = "", bg_color: str = "", fg_color: str = "") -> None:
        api_type = BADGE_KIND_ALIASES.get(badge_type, badge_type)
        icon = _badge_image_url(image)
        uri = _image_uri(image)
        for existing in badges:
            if existing.get("type") == api_type and existing.get("label") == label:
                if icon and not existing.get("icon"):
                    existing["icon"] = icon
                if uri and not existing.get("uri"):
                    existing["uri"] = uri
                if bg_color and not existing.get("bgColor"):
                    existing["bgColor"] = bg_color
                if fg_color and not existing.get("fgColor"):
                    existing["fgColor"] = fg_color
                return
        badge = {"type": api_type, "kind": badge_type, "label": label, "level": level or 0}
        if icon:
            badge["icon"] = icon
        if uri:
            badge["uri"] = uri
        if source:
            badge["source"] = source
        if bg_color:
            badge["bgColor"] = bg_color
        if fg_color:
            badge["fgColor"] = fg_color
        badges.append(badge)

    pay_grade = user.get("payGrade") or {}
    pay_level = _number(pay_grade.get("level")) if isinstance(pay_grade, dict) else 0
    pay_icon = pay_grade.get("newImIconWithLevel") or pay_grade.get("newLiveIcon") if isinstance(pay_grade, dict) else None
    pay_icon = pay_icon or user.get("badgeImageList")
    if pay_level:
        add_badge("pay_grade", f"消费Lv{pay_level}", pay_icon, pay_level, "payGrade")

    fans_data = ((user.get("fansClub") or {}).get("data") or {}) if isinstance(user.get("fansClub"), dict) else {}
    fans_level = _number(fans_data.get("level"))
    fans_name = str(fans_data.get("clubName") or fans_data.get("name") or "")
    fans_status = _number(fans_data.get("userFansClubStatus") or fans_data.get("status"))
    if fans_level:
        add_badge("fans_club", f"粉丝团Lv{fans_level}", None, fans_level, "fansClub")

    subscribe_status = _number(user.get("subscribeStatus"))

    club_icons = ((fans_data.get("badge") or {}).get("icons") or {}) if isinstance(fans_data.get("badge"), dict) else {}
    for key, item in club_icons.items():
        if str(key) == "2" or not isinstance(item, dict):
            continue
        badge_type, label, bg_color, fg_color = _classify_badge(item)
        level = _badge_level_from_filename(badge_type, item)
        if badge_type == "fans_club" and fans_level:
            label = f"粉丝团Lv{fans_level}"
            level = fans_level
        elif badge_type == "guard" and fans_level:
            label = f"星守护Lv{fans_level}"
            level = fans_level
        add_badge(badge_type, label, item, level, f"fansClub.badge.icons.{key}", bg_color, fg_color)

    for item in user.get("badgeList") or []:
        if not isinstance(item, dict):
            continue
        badge_type, fallback_label, bg_color, fg_color = _classify_badge(item)
        label = _text(item.get("displayText")) or str(item.get("name") or item.get("description") or fallback_label)
        level = _badge_level_from_filename(badge_type, item)
        if badge_type == "pay_grade" and pay_level:
            label = f"消费Lv{pay_level}"
            level = pay_level
        elif badge_type == "fans_club" and fans_level:
            label = f"粉丝团Lv{fans_level}"
            level = fans_level
        elif badge_type == "guard" and fans_level:
            label = f"星守护Lv{fans_level}"
            level = fans_level
        add_badge(badge_type, label, item.get("image") or item.get("icon") or item, level, "badgeList", bg_color, fg_color)

    # Some payloads expose only badgeImageList. Keep it as a fallback image source.
    if not any(badge.get("icon") for badge in badges):
        image = user.get("badgeImageList")
        if isinstance(image, dict) and _badge_image_url(image):
            badge_type, label, bg_color, fg_color = _classify_badge(image)
            level = _badge_level_from_filename(badge_type, image)
            if badge_type == "pay_grade" and pay_level:
                label = f"消费Lv{pay_level}"
                level = pay_level
            elif badge_type == "fans_club" and fans_level:
                label = f"粉丝团Lv{fans_level}"
                level = fans_level
            add_badge(badge_type, label, image, level, "badgeImageList", bg_color, fg_color)

    for field_name, badge_type, badge_label in (
        ("starGuard", "guard", "星守护"),
        ("liveStarBadge", "live_star", "直播之星"),
        ("subscriptionInfo", "member", "会员"),
        ("specialBadge", "member", "会员"),
        ("avatarBorder", "avatar_border", "头像框"),
        ("medal", "medal", "勋章"),
        ("newLiveImMedal", "medal", "勋章"),
        ("topVipBadge", "top_vip", "TopVIP"),
        ("nobleLevel", "vip", "贵族"),
    ):
        image = user.get(field_name)
        if isinstance(image, dict) and _badge_image_url(image):
            kind, fallback_label, bg_color, fg_color = _classify_badge(image)
            add_badge(badge_type, badge_label or fallback_label, image, _badge_level_from_filename(kind, image), field_name, bg_color, fg_color)

    for source in ("realTimeIcons", "newRealTimeIcons"):
        for image in user.get(source) or []:
            if isinstance(image, dict) and (_badge_image_url(image) or _image_uri(image)):
                badge_type, label, bg_color, fg_color = _classify_badge(image)
                add_badge(badge_type, label, image, _badge_level_from_filename(badge_type, image), source, bg_color, fg_color)

    top_vip_no = _number(user.get("topVipNo"))
    if top_vip_no:
        add_badge("top_vip", f"TopVIP {top_vip_no}", None, 0, "topVipNo", "#d4a017", "#1a1a2e")

    if fans_name:
        for badge in badges:
            if badge.get("type") == "guard" or badge.get("kind") == "guard":
                badge["clubName"] = fans_name
    if isinstance(user.get("badges"), list):
        badges = _merge_badges(badges, user["badges"])
    badges = _merge_badges(badges)

    follow_info = user.get("followInfo") or user.get("follow_info") or {}
    if not isinstance(follow_info, dict):
        follow_info = {}
    has_anchor_relation = "followStatus" in follow_info or "follow_status" in follow_info
    follow_value = follow_info.get("followStatus", follow_info.get("follow_status"))
    if follow_value is None:
        has_anchor_relation = "followStatus" in user or "follow_status" in user
        follow_value = user.get("followStatus", user.get("follow_status"))
    anchor_follow_status = _number(follow_value) if follow_value is not None else None
    # Douyin FollowInfo: 0=not following, 1=following, 2=mutual follow.
    # Keep 3 as a compatibility alias for archived payloads from the old mapping.
    anchor_relation = {1: "粉丝", 2: "互关", 3: "互关"}.get(anchor_follow_status, "")

    membership_opened = any(badge.get("type") in {"member", "annual_member"} for badge in badges)
    nickname = str(user.get("nickname") or user.get("nickName") or "匿名观众")
    nickname_key = nickname.strip().lower()
    is_anonymous = bool(user.get("isAnonymous") or user.get("is_anonym") or user.get("anonymous"))
    is_anonymous = is_anonymous or nickname_key in {"匿名", "匿名.", "匿名用户", "匿名观众", "anonymous"}
    is_mystery = bool(user.get("isMystery") or user.get("isMysteryUser") or user.get("is_mystery") or user.get("mysteryUser"))
    is_mystery = is_mystery or "神秘人" in nickname or "mystery" in nickname_key
    privacy_label = "匿名" if is_anonymous else "神秘人" if is_mystery else ""
    return {
        "id": str(uid),
        "nickname": nickname,
        "isAnonymous": is_anonymous,
        "isMystery": is_mystery,
        "privacyLabel": privacy_label,
        "avatar": avatar,
        "gender": gender,
        "signature": str(user.get("signature") or user.get("signatureText") or user.get("description") or ""),
        "badges": badges[:8],
        "secUid": str(user.get("secUid") or user.get("sec_uid") or ""),
        # Room-enter responses name the public Douyin ID `unique_id`, while
        # websocket user messages normally use `displayId`.
        "displayId": str(
            user.get("displayId") or user.get("display_id")
            or user.get("uniqueId") or user.get("unique_id") or ""
        ),
        "followStatus": _number(user.get("followStatus")),
        "followerCount": _number(follow_info.get("followerCount") or follow_info.get("follower_count") or user.get("followerCount") or user.get("follower_count")),
        "followingCount": _number(follow_info.get("followingCount") or follow_info.get("following_count")),
        "anchorFollowStatus": anchor_follow_status,
        "anchorRelation": anchor_relation,
        "hasAnchorRelation": has_anchor_relation,
        "anchorRelationSource": "",
        "subscribeStatus": subscribe_status,
        "fansClub": {"name": fans_name, "level": fans_level, "status": fans_status},
        "membership": {"opened": membership_opened, "label": "已开通" if membership_opened else "未开通"},
    }


def _display_text(payload: dict) -> dict:
    common = payload.get("common") if isinstance(payload.get("common"), dict) else {}
    display = payload.get("displayText") or common.get("displayText") or {}
    return display if isinstance(display, dict) else {}


def _display_text_user(payload: dict) -> dict:
    display = _display_text(payload)
    pieces = (display.get("pieces") or []) + (display.get("piecesV2") or display.get("pieces_v2") or [])
    for piece in pieces:
        if not isinstance(piece, dict):
            continue
        user_value = piece.get("userValue")
        user = _first_dict(piece.get("user"), user_value.get("user") if isinstance(user_value, dict) else user_value)
        if user:
            return user
    return {}


def _display_text_strings(payload: dict) -> list[str]:
    display = _display_text(payload)
    pieces = (display.get("pieces") or []) + (display.get("piecesV2") or display.get("pieces_v2") or [])
    return [str(piece.get("stringValue") or piece.get("text") or "").strip() for piece in pieces if isinstance(piece, dict) and str(piece.get("stringValue") or piece.get("text") or "").strip()]


def _template_vars(payload: dict) -> dict[str, str]:
    result = {}
    for item in payload.get("vars") or []:
        if isinstance(item, dict) and item.get("key"):
            result[str(item["key"])] = str(item.get("value") or "")
    return result


def _membership_purchase_signal(method: str, payload: dict) -> tuple[bool, str, int]:
    """Return whether this message is an actual purchase, its operation and duration."""
    display = _display_text(payload)
    display_key = str(display.get("key") or "").lower()
    template = payload.get("template") if isinstance(payload.get("template"), dict) else {}
    template_key = str(template.get("key") or "").lower()
    variables = _template_vars(payload)
    strings = " ".join(_display_text_strings(payload))
    evidence = " ".join((display_key, template_key, _text(display), strings, json.dumps(variables, ensure_ascii=False))).lower()

    if method == "WebcastResidentGuestMessage":
        update_type = _number(payload.get("updateType"))
        operation = {1: "open", 2: "renew", 3: "cancel", 4: "update", 5: "open"}.get(update_type, "")
        return bool(operation and payload.get("latestGuestUser")), operation, 0
    if method == "WebcastStarGuardMessage":
        if any(token in evidence for token in ("续费星守护", "renew")):
            operation = "renew"
        elif any(token in evidence for token in ("星守护过期", "取消星守护", "expired", "cancel")):
            operation = "cancel"
        elif any(token in evidence for token in ("成为星守护", "点亮星守护")):
            operation = "open"
        else:
            operation = ""
        return bool(operation), operation, 0
    if method == "WebcastNotifyEffectMessage":
        explicit = template_key == "subscribe_purchase_tip" or display_key == "subscribe_purchase_tip"
    elif method in {"WebcastRoomMessage", "WebcastRoomNotifyMessage"}:
        member_purchase = "subscribe_anchor_mvp" in display_key
        star_guard_purchase = (
            display_key == "live_signal_msg_special_key"
            and any(token in evidence for token in ("成为星守护", "点亮星守护", "续费星守护"))
        )
        explicit = member_purchase or star_guard_purchase
    else:
        explicit = True
    if not explicit:
        return False, "", 0

    purchase_type = variables.get("purchase_type", "").lower()
    if purchase_type == "renew" or any(token in evidence for token in ("续费", "renew", "renewal")):
        operation = "renew"
    elif purchase_type in {"cancel", "expire", "expired"} or any(token in evidence for token in ("取消", "过期", "cancel", "expired")):
        operation = "cancel"
    else:
        operation = "open"

    subscribe_type = variables.get("subscribe_type", "").lower()
    months = 12 if subscribe_type in {"year", "annual", "yearly"} or any(token in evidence for token in ("年度", "年费", "annual", "yearly")) else 1
    return True, operation, months


def _event_raw_user(payload: dict) -> dict:
    common = payload.get("common") if isinstance(payload.get("common"), dict) else {}
    candidates = [payload.get("user"), common.get("user"), _display_text_user(payload)]
    fallback = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if not fallback:
            fallback = candidate
        nickname = str(candidate.get("nickname") or candidate.get("nickName") or "").strip()
        identity = str(candidate.get("id") or candidate.get("secUid") or candidate.get("displayId") or "").strip()
        if nickname and nickname not in {"匿名", "匿名.", "匿名用户", "匿名观众"} and identity:
            return candidate
    return fallback


def _event_user(payload: dict) -> dict:
    user = normalize_user(_event_raw_user(payload))
    if user.get("hasAnchorRelation"):
        user["anchorRelationSource"] = "interaction"
    return user


def _badge_from_image(kind: str, label: str, image: Any, level: int = 0, source: str = "") -> dict | None:
    if not isinstance(image, dict) or not (_badge_image_url(image) or _image_uri(image)):
        return None
    classified_kind, fallback_label, bg_color, fg_color = _classify_badge(image)
    raw_kind = kind or classified_kind
    api_type = BADGE_KIND_ALIASES.get(raw_kind, raw_kind)
    badge = {
        "type": api_type,
        "kind": raw_kind,
        "label": label or fallback_label,
        "level": level or _badge_level_from_filename(classified_kind, image),
    }
    icon = _badge_image_url(image)
    uri = _image_uri(image)
    if icon:
        badge["icon"] = icon
    if uri:
        badge["uri"] = uri
    if source:
        badge["source"] = source
    if bg_color:
        badge["bgColor"] = bg_color
    if fg_color:
        badge["fgColor"] = fg_color
    return badge


def _badge_asset_key(icon: str, uri: str) -> str:
    value = str(uri or "").strip().lower()
    if not value:
        value = str(icon or "").split("?", 1)[0].split("~", 1)[0].lower()
        marker = "/img/"
        if marker in value:
            value = value.split(marker, 1)[1]
    return value.lstrip("/")


def _badge_dedupe_key(badge_type: str, badge: dict, icon: str, uri: str) -> tuple[str, str]:
    """Keep one badge per known visual category while retaining unknown assets."""
    kind = str(badge.get("kind") or "")
    if badge_type in {"consumer", "fans", "guard", "member", "annual_member", "top_vip"}:
        return badge_type, ""
    if badge_type == "vip":
        # VIP, noble and seat assets can coexist only when they are distinct sources.
        source = str(badge.get("source") or kind or icon or uri)
        return badge_type, source
    return badge_type, _badge_asset_key(icon, uri) or str(badge.get("label") or "")


def _merge_badges(*groups: Any) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for group in groups:
        if not isinstance(group, list):
            continue
        for badge in group:
            if not isinstance(badge, dict):
                continue
            badge_type = str(badge.get("type") or BADGE_KIND_ALIASES.get(str(badge.get("kind") or ""), str(badge.get("kind") or "badge")))
            label = str(badge.get("label") or "徽章")
            icon = str(badge.get("icon") or badge.get("url") or "")
            uri = str(badge.get("uri") or "")
            key = _badge_dedupe_key(badge_type, badge, icon, uri)
            if key not in merged:
                normalized = {
                    **badge,
                    "type": badge_type,
                    "label": label,
                    "icon": icon,
                }
                if not normalized.get("kind"):
                    normalized["kind"] = badge_type
                merged[key] = normalized
            else:
                current = merged[key]
                incoming_level = _number(badge.get("level"))
                current_level = _number(current.get("level"))
                if incoming_level >= current_level:
                    current["label"] = label
                    current["level"] = incoming_level
                    if icon:
                        current["icon"] = icon
                    if uri:
                        current["uri"] = uri
                    if badge.get("source"):
                        current["source"] = badge.get("source")
                elif icon and not current.get("icon"):
                    current["icon"] = icon
                if uri and not current.get("uri"):
                    current["uri"] = uri
                if badge.get("bgColor") and not current.get("bgColor"):
                    current["bgColor"] = badge.get("bgColor")
                if badge.get("fgColor") and not current.get("fgColor"):
                    current["fgColor"] = badge.get("fgColor")
                if badge.get("clubName") and (incoming_level >= current_level or not current.get("clubName")):
                    current["clubName"] = badge.get("clubName")
    badges = list(merged.values())
    if any(badge.get("type") == "guard" or badge.get("kind") == "guard" for badge in badges):
        badges = [badge for badge in badges if badge.get("type") != "fans" and badge.get("kind") != "fans_club"]
    return [badge for _, badge in sorted(
        enumerate(badges),
        key=lambda entry: (BADGE_DISPLAY_ORDER.get(str(entry[1].get("type") or entry[1].get("kind") or "badge"), 20), entry[0]),
    )][:8]


def _merge_session_badges(*groups: Any) -> list[dict]:
    """Keep historical badge states; live rendering may intentionally hide overlaps."""
    merged: dict[tuple[str, str], dict] = {}
    for group in groups:
        if not isinstance(group, list):
            continue
        for badge in group:
            if not isinstance(badge, dict):
                continue
            badge_type = str(badge.get("type") or badge.get("kind") or "badge")
            label = str(badge.get("label") or "徽章")
            key = (badge_type, label)
            current = merged.get(key)
            if current is None:
                merged[key] = deepcopy(badge)
                continue
            if _number(badge.get("level")) >= _number(current.get("level")):
                merged[key] = {**current, **badge}
    return list(merged.values())[:16]


def _merge_fans_club(incoming: Any, previous: Any) -> dict:
    incoming = incoming if isinstance(incoming, dict) else {}
    previous = previous if isinstance(previous, dict) else {}
    return {
        "name": str(incoming.get("name") or incoming.get("clubName") or previous.get("name") or previous.get("clubName") or ""),
        "level": _number(incoming.get("level"), _number(previous.get("level"))),
        "status": _number(incoming.get("status"), _number(previous.get("status"))),
    }


def _has_anchor_relation(user: Any) -> bool:
    if not isinstance(user, dict):
        return False
    if "hasAnchorRelation" in user:
        return bool(user.get("hasAnchorRelation"))
    return user.get("anchorFollowStatus") is not None


def _anchor_relation_priority(user: Any) -> int:
    if not _has_anchor_relation(user):
        return 0
    return 2 if str(user.get("anchorRelationSource") or "") == "interaction" else 1


def _merge_anchor_relation(incoming: Any, previous: Any) -> dict:
    incoming = incoming if isinstance(incoming, dict) else {}
    previous = previous if isinstance(previous, dict) else {}
    incoming_priority = _anchor_relation_priority(incoming)
    previous_priority = _anchor_relation_priority(previous)
    source = incoming if incoming_priority >= previous_priority and incoming_priority else previous
    return {
        "anchorFollowStatus": source.get("anchorFollowStatus"),
        "anchorRelation": str(source.get("anchorRelation") or ""),
        "hasAnchorRelation": _has_anchor_relation(source),
        "anchorRelationSource": str(source.get("anchorRelationSource") or ""),
    }


def extract_event_badges(method: str, payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    badges: list[dict] = []

    def add(kind: str, label: str, image: Any, level: Any = 0, source: str = "") -> None:
        badge = _badge_from_image(kind, label, image, _number(level), source)
        if badge:
            badges.append(badge)

    if method == "WebcastSubscriptionMessage":
        level = payload.get("subscriptionLevel") or payload.get("level") or payload.get("memberLevel")
        add("member", "订阅", payload.get("subscriberBadge") or payload.get("badge"), level, "subscriberBadge")
    elif method == "WebcastSpecialMemberMessage":
        level = payload.get("memberLevel")
        name = str(payload.get("memberName") or "专属会员")
        add("member", name, payload.get("badge"), level, "specialMember.badge")
        add("member", name, payload.get("background"), level, "specialMember.background")
    elif method == "WebcastMemberSpecialTipMessage":
        level = payload.get("memberLevel")
        name = str(payload.get("memberName") or "会员")
        member_type = _number(payload.get("memberType"))
        kind = "guard" if member_type == 4 or "守护" in name else "member"
        add(kind, name, payload.get("memberBadge"), level, "memberBadge")
        for index, image in enumerate(payload.get("tags") or []):
            add(kind, name, image, level, f"tags.{index}")
    elif method == "WebcastVipEnterMessage":
        add("vip", "VIP", payload.get("vipIcon"), payload.get("vipLevel"), "vipIcon")
        add("vip", "贵族", payload.get("nobleIcon"), payload.get("nobleLevel"), "nobleIcon")
        add("vip", "座驾", payload.get("seatBadge"), 0, "seatBadge")
    elif method == "WebcastNobleMessage":
        label = str(payload.get("nobleName") or "贵族")
        add("vip", label, payload.get("nobleBadge"), payload.get("nobleLevel"), "nobleBadge")
        add("vip", label, payload.get("nobleIcon"), payload.get("nobleLevel"), "nobleIcon")
    elif method == "WebcastNobleEnterMessage":
        label = str(payload.get("seatName") or payload.get("nobleName") or "贵族")
        add("vip", label, payload.get("seatBadge"), payload.get("nobleLevel"), "seatBadge")
    elif method == "WebcastStarGuardMessage":
        level = payload.get("guardLevel")
        name = str(payload.get("guardName") or "星守护")
        add("guard", name, payload.get("guardBadge") or payload.get("guardIcon"), level, "starGuard")
    elif method == "WebcastStarGuardInfoMessage":
        add("guard", "星守护", payload.get("guardBadge"), payload.get("guardLevel"), "starGuardInfo")
    elif method == "WebcastResidentGuestMessage":
        level = payload.get("guestLevel") or payload.get("guardLevel")
        name = str(payload.get("guestTitle") or payload.get("guardName") or "星守护")
        add("guard", name, payload.get("badge") or payload.get("lightUpBadge"), level, "residentGuest.badge")
        add("guard", name, payload.get("levelIcon"), level, "residentGuest.levelIcon")

    return _merge_badges(badges)


def _rank_entry(item: Any, index: int, trusted_score: bool = True) -> dict | None:
    if not isinstance(item, dict):
        return None
    user = normalize_user(_first_dict(item.get("user"), item.get("userInfo"), item.get("account"), item))
    if not user["id"] and user["nickname"] == "匿名观众":
        return None
    score_fields = (
        "score", "rankScore", "exactlyScore", "exactly_score",
        "scoreDescription", "score_description", "value", "contribution",
    )
    score_key = next((key for key in score_fields if key in item and item.get(key) not in (None, "")), None)
    has_contribution = bool(trusted_score and score_key is not None)
    return {
        **user,
        "rank": _number(item.get("rank"), index + 1),
        "contribution": _number(item.get(score_key)) if has_contribution else 0,
        "hasContribution": has_contribution,
    }


def _user_identity_keys(user: dict) -> tuple[str, ...]:
    values = []
    for key in ("id", "secUid", "displayId"):
        value = str(user.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    return tuple(values)


class EventStore:
    AUDIENCE_LIMIT = 300
    SESSION_WATCH_GAP_LIMIT_MS = 5 * 60 * 1000

    def __init__(self, limit: int = 160):
        self.limit = limit
        self.configured_room_id = ""
        self.status = {
            "state": "stopped",
            "roomState": "unknown",
            "message": "监听服务已就绪",
            "lastEventAt": 0,
            "eventCount": 0,
            "lastRoomCheckAt": 0,
            "lastLiveAt": 0,
            "lastOfflineAt": 0,
            "roomStatusSource": "",
            "rawRoomStatus": 0,
            "pageRoomState": "unknown",
            "pageStatusMessage": "",
            "hasLiveSession": False,
        }
        self.room = {
            "id": "",
            "url": "",
            "roomKey": "",
            "roomName": "",
            "sessionId": "",
            "sessionName": "",
            "title": "等待连接直播间",
            "description": "配置房间号后启动监听",
            "liveId": "",
            "cover": "",
            "status": 0,
            "createTime": 0,
            "startTime": 0,
            "anchorId": "",
            "secAnchorId": "",
            "anchor": normalize_user({"nickname": "未连接主播"}),
        }
        self.stats = {"online": 0, "likes": 0, "giftValue": 0}
        self.session_memory = self._new_session_memory()
        self.memberships = deque(maxlen=40)
        self.gifts = deque(maxlen=limit)
        self.interactions = deque(maxlen=limit)
        self.audience: list[dict] = []
        self.audience_scores: dict[str, int] = {}
        self.audience_status = {
            "lastRankRefreshAt": 0,
            "lastPushAt": 0,
            "lastUpdatedAt": 0,
            "rankCount": 0,
            "source": "",
            "revision": 0,
        }
        self.records = {
            # Activity records are part of the current session archive, not a live feed.
            "redPackets": deque(),
            "luckyBags": deque(),
        }
        self._activity_state = {
            "redPacket": {"mergeKey": "", "ts": 0},
            "luckyBag": {"mergeKey": "", "ts": 0},
        }
        self._seen_record_keys: set[str] = set()
        self._seen_record_order: deque[str] = deque(maxlen=2048)
        self._gift_streams: dict[str, dict] = {}
        self._membership_transactions: dict[tuple[str, str, str, int], dict] = {}

    def _new_session_memory(self, session_id: str = "", timestamp: int = 0) -> dict:
        return {
            "sessionId": str(session_id or ""),
            "roomId": str(self.room.get("id") or self.configured_room_id or ""),
            "startedAt": _number(timestamp),
            "lastUpdatedAt": _number(timestamp),
            "summary": {
                "totalLikes": 0,
                "totalGiftCount": 0,
                "totalGiftValue": 0,
                "giftMessageValue": 0,
                "rankGiftValue": 0,
                "giftValueSource": "gift_messages",
                "rankSnapshotCount": 0,
                "rankContributorCount": 0,
                "redPacketCount": 0,
                "luckyBagCount": 0,
                "participantCount": 0,
                "winnerCount": 0,
                "userCount": 0,
            },
            "users": {},
        }

    def _ensure_session_memory(self, timestamp: int, session_id: str = "") -> None:
        session_id = str(session_id or "").strip()
        current_id = str(self.session_memory.get("sessionId") or "")
        if session_id and current_id and session_id != current_id:
            self.session_memory = self._new_session_memory(session_id, timestamp)
        elif session_id and not current_id:
            self.session_memory["sessionId"] = session_id
        if not self.session_memory.get("startedAt"):
            self.session_memory["startedAt"] = _number(timestamp)
        self.session_memory["roomId"] = str(self.room.get("id") or self.configured_room_id or self.session_memory.get("roomId") or "")
        self.session_memory["lastUpdatedAt"] = max(_number(self.session_memory.get("lastUpdatedAt")), _number(timestamp))

    @staticmethod
    def _session_identity(user: dict) -> str:
        keys = _user_identity_keys(user)
        return keys[0] if keys else ""

    def _observe_session_user(
        self,
        user: dict,
        timestamp: int,
        *,
        likes: int = 0,
        gift_count: int = 0,
        gift_value: int = 0,
        contribution: int | None = None,
        profit_score: int = 0,
        participant: bool = False,
        winner: bool = False,
    ) -> None:
        if not isinstance(user, dict):
            return
        self._ensure_session_memory(timestamp, self.room.get("sessionId"))
        identity = self._session_identity(user)
        if not identity:
            return
        users = self.session_memory["users"]
        existing = users.get(identity)
        if not isinstance(existing, dict):
            for existing_identity, candidate in users.items():
                if not isinstance(candidate, dict):
                    continue
                same_alias = any(
                    str(user.get(key) or "").strip()
                    and str(user.get(key) or "").strip() == str(candidate.get(key) or "").strip()
                    for key in ("id", "secUid", "displayId")
                )
                if same_alias:
                    identity = existing_identity
                    existing = candidate
                    break
        if not isinstance(existing, dict):
            existing = {
                "identity": identity,
                "id": "",
                "secUid": "",
                "displayId": "",
                "nickname": "",
                "avatar": "",
                "isAnonymous": False,
                "isMystery": False,
                "privacyLabel": "",
                "badges": [],
                "firstSeenAt": _number(timestamp),
                "lastSeenAt": _number(timestamp),
                "watchDurationMs": 0,
                "likes": 0,
                "giftCount": 0,
                "giftValue": 0,
                "contribution": 0,
                "profitScore": 0,
                "participated": False,
                "won": False,
            }
            users[identity] = existing
        previous_seen = _number(existing.get("lastSeenAt"))
        if previous_seen and timestamp > previous_seen:
            existing["watchDurationMs"] += min(timestamp - previous_seen, self.SESSION_WATCH_GAP_LIMIT_MS)
        existing["lastSeenAt"] = max(previous_seen, _number(timestamp))
        for key in ("id", "secUid", "displayId", "nickname", "avatar"):
            if user.get(key) not in (None, ""):
                existing[key] = str(user[key]) if key != "avatar" else user[key]
        for key in ("isAnonymous", "isMystery", "privacyLabel"):
            if user.get(key):
                existing[key] = user[key]
        existing["badges"] = _merge_session_badges(existing.get("badges"), user.get("badges"))
        existing["likes"] += max(0, _number(likes))
        existing["giftCount"] += max(0, _number(gift_count))
        existing["giftValue"] += max(0, _number(gift_value))
        existing["profitScore"] += max(0, _number(profit_score))
        if contribution is not None:
            existing["contribution"] = max(_number(existing.get("contribution")), _number(contribution))
        if participant:
            existing["participated"] = True
        if winner:
            existing["won"] = True

    def _observe_session_event(self, event: dict, timestamp: int) -> None:
        if not isinstance(event, dict):
            return
        kind = str(event.get("kind") or "")
        user = event.get("user")
        gift_count = _number(event.get("increment")) or _number(event.get("count"))
        gift_value = _number(event.get("unitValue")) * gift_count or _number(event.get("value"))
        if isinstance(user, dict):
            self._observe_session_user(
                user,
                timestamp,
                likes=_number(event.get("count")) if kind == "like" else 0,
                gift_count=gift_count if kind == "gift" else 0,
                gift_value=gift_value if kind == "gift" else 0,
                contribution=max(_number(event.get("contribution")), _number(event.get("totalScore"))) if kind == "score" else None,
                profit_score=_number(event.get("score")) if kind == "score" else 0,
            )
        for key, flag in (("sender", False),):
            sender = event.get(key)
            if isinstance(sender, dict) and sender is not user:
                self._observe_session_user(sender, timestamp, participant=flag)
        for key, flag in (("participants", True), ("winners", True)):
            for item in event.get(key) or []:
                if isinstance(item, dict):
                    self._observe_session_user(item, timestamp, participant=key == "participants", winner=key == "winners")

        summary = self.session_memory["summary"]
        if kind == "like":
            summary["totalLikes"] += max(0, _number(event.get("count")))
        elif kind == "gift":
            summary["totalGiftCount"] += max(0, gift_count)
            summary["giftMessageValue"] += max(0, gift_value)
            if not _number(summary.get("rankSnapshotCount")):
                summary["totalGiftValue"] = summary["giftMessageValue"]
                summary["giftValueSource"] = "gift_messages"
        summary["userCount"] = len(self.session_memory["users"])

    def _refresh_rank_gift_value(self) -> int:
        summary = self.session_memory["summary"]
        contributors = [
            user for user in self.session_memory["users"].values()
            if _number(user.get("contribution")) > 0
        ]
        rank_total = sum(_number(user.get("contribution")) for user in contributors)
        summary["rankGiftValue"] = rank_total
        summary["rankContributorCount"] = len(contributors)
        if _number(summary.get("rankSnapshotCount")):
            summary["totalGiftValue"] = rank_total
            summary["giftValueSource"] = "rank"
            self.stats["giftValue"] = rank_total
        else:
            summary["totalGiftValue"] = _number(summary.get("giftMessageValue"))
            summary["giftValueSource"] = "gift_messages"
        return _number(summary.get("totalGiftValue"))

    def _refresh_session_summary(self) -> None:
        summary = self.session_memory["summary"]
        self._refresh_rank_gift_value()
        summary["redPacketCount"] = len(self.records["redPackets"])
        summary["luckyBagCount"] = len(self.records["luckyBags"])
        summary["participantCount"] = sum(1 for user in self.session_memory["users"].values() if user.get("participated"))
        summary["winnerCount"] = sum(1 for user in self.session_memory["users"].values() if user.get("won"))
        summary["userCount"] = len(self.session_memory["users"])

    def _session_memory_snapshot(self) -> dict:
        self._refresh_session_summary()
        users = list(self.session_memory["users"].values())
        users.sort(key=lambda item: (-_number(item.get("contribution")), -_number(item.get("lastSeenAt")), str(item.get("identity") or "")))
        return {
            "sessionId": self.session_memory.get("sessionId", ""),
            "roomId": self.session_memory.get("roomId", ""),
            "startedAt": self.session_memory.get("startedAt", 0),
            "lastUpdatedAt": self.session_memory.get("lastUpdatedAt", 0),
            "summary": deepcopy(self.session_memory["summary"]),
            "users": deepcopy(users),
            "activities": {
                "redPackets": deepcopy(list(self.records["redPackets"])),
                "luckyBags": deepcopy(list(self.records["luckyBags"])),
            },
        }

    def configure_room(self, config: dict) -> None:
        room_id = str(config.get("roomId") or "").strip()
        room_url = str(config.get("roomUrl") or "").strip()
        self.configured_room_id = room_id
        self.room["id"] = room_id
        self.room["url"] = room_url or (f"https://live.douyin.com/{room_id}" if room_id else "")

    def reset_live_data(self, config: dict, message: str = "直播间配置已切换，等待连接") -> None:
        """Discard runtime data before a new room configuration takes effect."""
        self.room = {
            "id": "",
            "url": "",
            "roomKey": "",
            "roomName": "",
            "sessionId": "",
            "sessionName": "",
            "title": "等待连接直播间",
            "description": "配置房间号后启动监听",
            "liveId": "",
            "cover": "",
            "status": 0,
            "createTime": 0,
            "startTime": 0,
            "anchorId": "",
            "secAnchorId": "",
            "anchor": normalize_user({"nickname": "未连接主播"}),
        }
        self.stats = {"online": 0, "likes": 0, "giftValue": 0}
        self.session_memory = self._new_session_memory()
        self.memberships.clear()
        self.gifts.clear()
        self.interactions.clear()
        self.audience = []
        self.audience_scores.clear()
        self.audience_status = {
            "lastRankRefreshAt": 0,
            "lastPushAt": 0,
            "lastUpdatedAt": 0,
            "rankCount": 0,
            "source": "",
            "revision": 0,
        }
        for records in self.records.values():
            records.clear()
        for state in self._activity_state.values():
            state["mergeKey"] = ""
            state["ts"] = 0
        self._seen_record_keys.clear()
        self._seen_record_order.clear()
        self._gift_streams.clear()
        self._membership_transactions.clear()
        self.configure_room(config)
        self.status.update({
            "state": "stopped", "roomState": "unknown", "message": message, "lastEventAt": 0, "eventCount": 0,
            "lastRoomCheckAt": 0, "lastLiveAt": 0, "lastOfflineAt": 0, "roomStatusSource": "",
            "rawRoomStatus": 0, "pageRoomState": "unknown", "pageStatusMessage": "", "hasLiveSession": False,
        })

    def _remember_audience_score(self, user: dict, score: int) -> None:
        for identity in _user_identity_keys(user):
            self.audience_scores[identity] = _number(score)

    def _resolve_audience_score(self, user: dict) -> tuple[int, bool]:
        for identity in _user_identity_keys(user):
            if identity in self.audience_scores:
                return self.audience_scores[identity], True
        return 0, False

    def set_status(self, state: str, message: str = "") -> None:
        self.status["state"] = state
        if message:
            self.status["message"] = message

    def apply_room_status_probe(self, probe: dict) -> None:
        if not isinstance(probe, dict):
            return
        checked_at = _number(probe.get("checkedAt"), int(time.time() * 1000))
        room_state = str(probe.get("roomState") or "unknown")
        self.status.update({
            "lastRoomCheckAt": checked_at,
            "roomStatusSource": "room_web_enter_and_page" if probe.get("pageChecked") else "room_web_enter",
            "rawRoomStatus": _number(probe.get("rawStatus")),
            "pageRoomState": str(probe.get("pageState") or "unknown"),
            "pageStatusMessage": str(probe.get("pageStatusMessage") or ""),
        })
        for key, source in (("id", "roomId"), ("sessionId", "sessionId"), ("title", "title"), ("anchorId", "anchorId"), ("secAnchorId", "secAnchorId")):
            if key == "id" and self.configured_room_id:
                self.room["id"] = self.configured_room_id
                continue
            value = str(probe.get(source) or "")
            if value:
                self.room[key] = value
        if probe.get("anchor"):
            self.room["anchor"]["nickname"] = str(probe["anchor"])
            self.room["roomName"] = str(probe["anchor"])
        for key, source in (("id", "anchorId"), ("secUid", "secAnchorId"), ("displayId", "anchorDisplayId")):
            value = str(probe.get(source) or "")
            if value:
                self.room["anchor"][key] = value
        if room_state == "live":
            self.status["roomState"] = "live"
            self.status["lastLiveAt"] = checked_at
            self.status["hasLiveSession"] = True
            if self.status.get("state") not in {"connected", "connecting", "reconnecting", "ranking"}:
                self.set_status("monitoring", "检测到直播，等待自动监听")
        elif room_state == "not_live":
            was_live = bool(self.status.get("hasLiveSession"))
            page_ended = self.status.get("pageStatusMessage") == "直播已结束"
            self.status["roomState"] = "ended" if was_live or page_ended else "not_live"
            self.status["lastOfflineAt"] = checked_at
            self.set_status("monitoring", "直播已下播，继续监控开播" if was_live or page_ended else "直播间未开播，继续监控")
        elif room_state == "not_found":
            self.status.update({"roomState": "not_found", "message": "直播间不存在或无访问权限"})

    def _settle_expired_activities(self) -> None:
        now = int(time.time() * 1000)
        for records in self.records.values():
            for record in records:
                if not isinstance(record, dict):
                    continue
                activity = record.get("activity")
                if not isinstance(activity, dict):
                    continue
                draw_at = _number(activity.get("endAt"))
                if not draw_at or draw_at > now or activity.get("status") in {"ended", "won"}:
                    continue
                activity["status"] = "ended"
                if record.get("method") == "WebcastRoomDataSyncMessage":
                    record["content"] = "福袋开奖状态同步" if activity.get("type") == "lucky_bag" else "红包活动结束"
                for update in reversed(record.get("updates") or []):
                    if isinstance(update, dict) and update.get("method") == "WebcastRoomDataSyncMessage":
                        update["status"] = "ended"
                        update["content"] = record["content"]
                        break

    def snapshot(self) -> dict:
        self._settle_expired_activities()
        return {
            "status": deepcopy(self.status),
            "room": deepcopy(self.room),
            "stats": deepcopy(self.stats),
            "memberships": list(self.memberships),
            "gifts": list(self.gifts),
            "interactions": list(self.interactions),
            "audience": deepcopy(self.audience),
            "audienceStatus": deepcopy(self.audience_status),
            "records": {key: list(value) for key, value in self.records.items()},
            "sessionMemory": self._session_memory_snapshot(),
        }

    def find_user(self, identity: str) -> dict | None:
        identity = str(identity or "").strip()
        if not identity:
            return None
        users = [self.room.get("anchor") or {}]
        users.extend(self.audience)
        for collection in (self.memberships, self.gifts, self.interactions):
            users.extend(item.get("user") or {} for item in collection if isinstance(item, dict))
        users.extend(
            user
            for user in (self.session_memory.get("users") or {}).values()
            if isinstance(user, dict)
        )
        result: dict | None = None
        for user in users:
            if not isinstance(user, dict):
                continue
            values = {str(user.get(key) or "") for key in ("id", "secUid", "displayId")}
            if identity in values:
                if result is None:
                    result = deepcopy(user)
                    continue
                for key, value in user.items():
                    if value not in (None, "", [], {}):
                        result[key] = deepcopy(value)
        return result

    def apply(self, record: dict) -> dict | None:
        method = str(record.get("method") or "")
        if method in ("WebcastHeartbeat", "WebcastHeartbeatResponse"):
            return None
        payload = record.get("parsed") or {}
        if not isinstance(payload, dict):
            payload = {}
        record_key = self._record_key(record, method, payload)
        if record_key and record_key in self._seen_record_keys:
            return None
        if record_key:
            self._seen_record_keys.add(record_key)
            self._seen_record_order.append(record_key)
            while len(self._seen_record_keys) > self._seen_record_order.maxlen:
                self._seen_record_keys.discard(self._seen_record_order.popleft())
        timestamp = _number(record.get("ts"), int(time.time() * 1000))
        rank_only = method == "WebcastAudienceRankList" and self.status["state"] in {"connecting", "ranking"}
        self.status.update({"lastEventAt": timestamp, "eventCount": self.status["eventCount"] + 1})
        if method != "LiveMngRoomInfo" and self.status.get("roomState") not in {"not_live", "ended", "not_found"}:
            self.status.update({
                "state": "connecting" if rank_only else "connected",
                "roomState": "live",
                "message": "已获取观众榜，正在连接弹幕流" if rank_only else "弹幕流已连接",
            })

        event = self._apply_event(method, payload, timestamp)
        self._ensure_session_memory(timestamp, self.room.get("sessionId"))
        if event:
            for user_key in ("user", "sender"):
                user = event.get(user_key)
                if isinstance(user, dict):
                    identity = next(iter(_user_identity_keys(user)), "")
                    known = self.find_user(identity) if identity else None
                    if known:
                        enriched = deepcopy(known)
                        for key, value in user.items():
                            if value not in (None, "", [], {}):
                                enriched[key] = deepcopy(value)
                        event[user_key] = user = enriched
                    self._sync_audience_user(user)
            self._observe_session_event(event, timestamp)

        if method == "LiveMngRoomInfo":
            if self._room_is_missing(payload):
                self.status.update({"state": "error", "roomState": "not_found", "message": "直播间不存在或无访问权限"})
            elif self._room_is_not_live(payload):
                self.status.update({"state": "connected", "roomState": "not_live", "message": "直播间未开播"})
            elif self.status.get("roomState") not in {"live"}:
                self.status.update({"state": "connecting", "roomState": "unknown", "message": "已获取直播间信息，正在连接弹幕流"})
        return event or {"kind": "state", "method": method, "ts": timestamp}

    @staticmethod
    def _room_is_missing(payload: dict) -> bool:
        if payload.get("roomExists") is False or payload.get("room_exists") is False:
            return True
        code = _number(payload.get("statusCode") or payload.get("status_code"))
        return code not in (0, 200) and not bool(payload.get("roomInfo") or payload.get("room") or payload.get("liveId"))

    @staticmethod
    def _room_is_not_live(payload: dict) -> bool:
        if payload.get("isLive") is False or payload.get("is_live") is False:
            return True
        value = str(payload.get("roomState") or payload.get("room_state") or payload.get("liveStatus") or payload.get("live_status") or "").strip().lower()
        if value in {"offline", "not_live", "notlive", "ended"}:
            return True
        return False

    def _base(self, kind: str, method: str, payload: dict, timestamp: int) -> dict:
        return {"kind": kind, "method": method, "ts": timestamp, "user": _event_user(payload)}

    @staticmethod
    def _record_key(record: dict, method: str, payload: dict) -> str:
        message_id = _first_value(
            record,
            "msg_id", "msgId", "message_id", "messageId",
        )
        common = payload.get("common") if isinstance(payload.get("common"), dict) else {}
        message_id = message_id or _first_value(common, "msgId", "msg_id", "messageId", "message_id")
        if message_id not in (None, "", 0, "0"):
            return f"{method}:id:{message_id}"
        stable_id = _first_value(payload, "logId", "log_id", "eventId", "event_id", "id")
        if stable_id not in (None, "", 0, "0"):
            return f"{method}:stable:{stable_id}"
        return ""

    def _apply_event(self, method: str, payload: dict, timestamp: int) -> dict | None:
        if method == "LiveMngRoomInfo":
            self.room["id"] = self.configured_room_id or str(payload.get("roomId") or self.room["id"])
            self.room["sessionId"] = str(payload.get("liveId") or payload.get("sessionId") or self.room.get("sessionId") or "")
            self.room["title"] = str(payload.get("title") or self.room["title"])
            self.room["roomName"] = str(payload.get("roomName") or payload.get("anchor") or self.room.get("roomName") or "")
            self.room["description"] = str(payload.get("description") or self.room["description"])
            self.room["liveId"] = str(payload.get("liveId") or payload.get("sessionId") or self.room.get("liveId") or "")
            self.room["cover"] = str(payload.get("cover") or self.room.get("cover") or "")
            self.room["status"] = _number(payload.get("status") or self.room.get("status"))
            self.room["createTime"] = _number(payload.get("createTime") or self.room.get("createTime"))
            self.room["startTime"] = _number(payload.get("startTime") or self.room.get("startTime"))
            self.room["anchorId"] = str(payload.get("anchorId") or self.room.get("anchorId") or "")
            self.room["secAnchorId"] = str(payload.get("secAnchorId") or self.room.get("secAnchorId") or "")
            self.room["roomKey"] = str(
                payload.get("roomKey") or self.room.get("secAnchorId")
                or self.room.get("anchorId") or self.room.get("id") or ""
            )
            self.room["sessionName"] = str(
                payload.get("sessionName") or self.room.get("sessionId")
                or self.room.get("liveId") or self.room.get("id") or ""
            )
            anchor_payload = payload.get("anchorInfo") or payload.get("anchor") or {}
            if isinstance(anchor_payload, dict):
                anchor_user = normalize_user(anchor_payload)
                self.room["anchor"].update(anchor_user)
            else:
                self.room["anchor"].update({
                    "id": str(payload.get("anchorId") or self.room["anchor"].get("id") or ""),
                    "secUid": str(payload.get("secAnchorId") or self.room["anchor"].get("secUid") or ""),
                    "nickname": str(payload.get("anchor") or self.room["anchor"]["nickname"]),
                    "avatar": str(payload.get("avatar") or self.room["anchor"]["avatar"]),
                })
            return {"kind": "room", "method": method, "ts": timestamp}

        if method == "WebcastAudioChatMessage":
            event = self._base("chat", method, payload, timestamp)
            event["content"] = str(payload.get("content") or _text(payload.get("displayText")) or "语音弹幕")
            event["audioUrl"] = str(payload.get("audioUrl") or "")
            event["durationMs"] = _number(payload.get("durationMs"))
            self.interactions.append(event)
            return event

        if method == "ActivityEmojiGroupsMessage":
            _register_activity_emoji_groups(payload)
            return None

        if method == "WebcastExhibitionChatMessage":
            event = self._base("chat", method, payload, timestamp)
            if not _event_raw_user(payload):
                event["systemEvent"] = True
                event["user"] = normalize_user({"nickname": "直播间"})
            event["content"] = str(
                payload.get("giftName")
                or _display_text_render(payload.get("displayText") or (payload.get("common") or {}).get("displayText"))
                or "展览弹幕"
            )
            event["giftId"] = _number(payload.get("giftId"))
            event["comboCount"] = _number(payload.get("comboCount"))
            event["count"] = _number(payload.get("count"))
            self.interactions.append(event)
            return event

        if method in ("WebcastChatMessage", "WebcastEmojiChatMessage"):
            event = self._base("chat", method, payload, timestamp)
            if method == "WebcastEmojiChatMessage":
                emoji = payload.get("emoji") or {}
                event["content"] = str(
                    _text(payload.get("displayText"))
                    or (emoji.get("describe") if isinstance(emoji, dict) else "")
                    or "[会员表情]"
                )
                event["emojiImage"] = _emoji_image_url(payload)
            else:
                event["content"] = str(payload.get("content") or _text(payload.get("displayText")) or "")
                segments = _content_segments(event["content"])
                if segments:
                    event["contentSegments"] = segments
            self.interactions.append(event)
            return event

        if method in ("WebcastLikeMessage", "WebcastChatLikeMessage"):
            event = self._base("like", method, payload, timestamp)
            count = _number(payload.get("count"))
            if method == "WebcastChatLikeMessage":
                count = sum(_number((entry.get("meta") or {}).get("count"), 1) for entry in payload.get("likes") or [] if isinstance(entry, dict))
            event.update({"count": count, "content": f"点赞了直播间 x{count or 1}"})
            self.stats["likes"] = max(self.stats["likes"] + count, _number(payload.get("total")))
            self.interactions.append(event)
            return event

        if method == "WebcastGiftMessage":
            gift = payload.get("gift") or {}
            user = _event_user(payload)
            gift_id = _number(payload.get("giftId") or gift.get("id") or gift.get("giftId"))
            group_id = _number(payload.get("groupId"))
            combo_id = str(payload.get("comboId") or payload.get("combo_id") or "")
            repeat_count = _number(payload.get("repeatCount"))
            combo_count = _number(payload.get("comboCount"))
            group_count = _number(payload.get("groupCount") or payload.get("group_count"))
            batch_compose = bool(payload.get("batchCompose") or payload.get("batch_compose"))
            total_diamond_count = _number(
                payload.get("totalDiamondCount") or payload.get("total_diamond_count")
            )
            cumulative = max(repeat_count, combo_count, 1)
            combo_enabled = bool(gift.get("combo")) or bool(combo_id) or group_id > 0 or cumulative > 1
            stream_key = ""
            if combo_enabled:
                identity = next(iter(_user_identity_keys(user)), "anonymous")
                stream_key = ":".join((
                    str(self.room.get("id") or payload.get("roomId") or ""),
                    identity,
                    str(gift_id),
                    combo_id or str(group_id),
                ))
            stream = self._gift_streams.get(stream_key) if stream_key else None
            previous_count = _number(stream.get("repeatCount")) if stream else 0
            repeat_end = _number(payload.get("repeatEnd"))
            if stream and cumulative <= previous_count:
                if repeat_end:
                    self._gift_streams.pop(stream_key, None)
                return None
            if stream_key:
                count = cumulative - previous_count
                if group_count > count:
                    count = group_count
            else:
                count = max(
                    1,
                    group_count,
                    _number(payload.get("count") or payload.get("giftCount") or payload.get("batchGiftNum"), 1),
                )
            unit_value = _number(payload.get("diamondCount") or gift.get("diamondCount"))
            event = self._base("gift", method, payload, timestamp)
            event.update({
                "gift": str(gift.get("name") or gift.get("describe") or "未知礼物"),
                "giftIcon": _image_url(gift.get("image") or gift.get("icon")),
                "count": count,
                "value": unit_value * count,
                "unitValue": unit_value,
                "repeatCount": cumulative,
                "comboCount": combo_count,
                "comboId": combo_id,
                "groupId": group_id,
                "groupCount": group_count,
                "batchCompose": batch_compose,
                "giftId": gift_id,
                "combo": combo_enabled,
                "repeatEnd": repeat_end,
                "merged": bool(stream),
                "increment": count,
                "totalCount": cumulative,
                "totalValue": total_diamond_count or unit_value * cumulative,
                "totalDiamondCount": total_diamond_count,
                "effect": None,
            })
            if stream:
                merged_event = stream["event"]
                merged_event.update({
                    "ts": timestamp,
                    "count": _number(merged_event.get("count")) + count,
                    "value": _number(merged_event.get("value")) + event["value"],
                    "repeatCount": cumulative,
                    "comboCount": max(combo_count, _number(merged_event.get("comboCount"))),
                    "groupCount": group_count,
                    "batchCompose": batch_compose or bool(merged_event.get("batchCompose")),
                    "totalCount": cumulative,
                    "totalValue": total_diamond_count or unit_value * cumulative,
                    "totalDiamondCount": total_diamond_count or _number(merged_event.get("totalDiamondCount")),
                    "increment": count,
                    "merged": True,
                    "repeatEnd": repeat_end,
                })
                event = merged_event
            else:
                self.gifts.append(event)
            if not _number(self.session_memory.get("summary", {}).get("rankSnapshotCount")):
                self.stats["giftValue"] += event["value"] if not stream else unit_value * count
            if stream_key:
                self._gift_streams[stream_key] = {"repeatCount": cumulative, "event": event}
                if repeat_end:
                    self._gift_streams.pop(stream_key, None)
            return deepcopy(event)

        if method in ("WebcastMemberMessage", "WebcastVipEnterMessage", "WebcastNobleEnterMessage"):
            event = self._base("enter", method, payload, timestamp)
            event["content"] = "进入直播间"
            self.interactions.append(event)
            return event

        if method == "WebcastRoomIntroMessage":
            intro = str(payload.get("intro") or _text(payload.get("displayText")) or "")
            cover = payload.get("cover") or {}
            if intro:
                self.room["description"] = intro
            if isinstance(cover, dict):
                cover_url = _image_url(cover)
                if cover_url:
                    self.room["cover"] = cover_url
            return {"kind": "room", "method": method, "ts": timestamp}

        if method == "WebcastLuckyBoxEndMessage":
            return self._apply_activity("luckyBag", method, payload, timestamp, "福袋开奖")

        if method == "WebcastLuckyBoxMessage":
            return self._apply_activity("luckyBag", method, payload, timestamp, "福袋发放中")

        if method == "WebcastLuckyBoxRewardMessage":
            return self._apply_activity("luckyBag", method, payload, timestamp, "福袋参与")

        if method == "WebcastLuckyBoxTempStatusMessage":
            return self._apply_activity("luckyBag", method, payload, timestamp, "福袋状态同步")

        if method == "WebcastXGLotteryMessage":
            lottery = payload.get("lotteryInfo") if isinstance(payload.get("lotteryInfo"), dict) else {}
            if lottery:
                return self._apply_activity(
                    "luckyBag",
                    method,
                    {
                        **payload,
                        **lottery,
                        "winners": lottery.get("luckyUsers") or [],
                        "candidateTotalCount": lottery.get("candidateNum") or 0,
                    },
                    timestamp,
                    "福袋开奖",
                )

        if method == "WebcastLotteryEventNewMessage":
            lottery_id = str(_first_value(payload, "lotteryId", "lottery_id") or "")
            lottery_status = _number(_first_value(payload, "lotteryStatus", "lottery_status"))
            start_time = _number(_first_value(payload, "lotteryStartTime", "lottery_start_time"))
            draw_time = _number(_first_value(payload, "lotteryDrawTime", "lottery_draw_time"))
            current_time = _number(_first_value(payload, "lotteryCurrentTime", "lottery_current_time"))
            prize_count = _number(_first_value(payload, "prizeCount", "prize_count"))
            lucky_count = _number(_first_value(payload, "luckyCount", "lucky_count"))
            status = "active" if lottery_status == 1 else "ended" if lottery_status == 2 else "unknown"
            if draw_time and max(current_time * 1000, timestamp) >= draw_time * 1000:
                status = "ended"
            return self._apply_activity(
                "luckyBag",
                method,
                {
                    **payload,
                    "lotteryId": lottery_id,
                    "_activityTitle": "福袋活动",
                    "content": "福袋活动发起" if status != "ended" else "福袋开奖状态同步",
                    "status": status,
                    "startTime": start_time * 1000 if start_time and start_time < 10_000_000_000 else start_time,
                    "endTime": draw_time * 1000 if draw_time and draw_time < 10_000_000_000 else draw_time,
                    "currentTime": current_time * 1000 if current_time and current_time < 10_000_000_000 else current_time,
                    "prizeCount": prize_count,
                    "luckyCount": lucky_count,
                    "totalCount": lucky_count,
                    "amount": prize_count,
                    "currency": "钻石" if prize_count else "",
                    "prize": {
                        "name": str(_first_value(payload, "awardName", "award_name") or "钻石福袋" if prize_count else ""),
                        "amount": prize_count,
                        "count": prize_count,
                        "currency": "钻石" if prize_count else "",
                        "description": str(_first_value(payload, "awardDescription", "award_description") or ""),
                    },
                },
                timestamp,
            )

        if method == "WebcastLotteryCandidateEventMessage":
            lottery_id = str(_first_value(payload, "lotteryId", "lottery_id") or "")
            success = bool(_first_value(payload, "participateSuccess", "participate_success"))
            user_id = _first_value(payload, "userId", "user_id", "userOpenid", "user_openid")
            return self._apply_activity(
                "luckyBag",
                method,
                {
                    **payload,
                    "lotteryId": lottery_id,
                    "_activityTitle": "福袋活动",
                    "content": "福袋参与" if success else "福袋参与失败",
                    "status": "active",
                    "participants": [user_id] if success and user_id else [],
                },
                timestamp,
            )

        if method == "WebcastLotteryDrawResultEventMessage":
            lottery_id = str(_first_value(payload, "lotteryId", "lottery_id") or "")
            winners = _first_value(payload, "userIds", "user_ids") or _first_value(payload, "userOpenids", "user_openids") or []
            return self._apply_activity(
                "luckyBag",
                method,
                {
                    **payload,
                    "lotteryId": lottery_id,
                    "_activityTitle": "福袋活动",
                    "content": "福袋开奖结果",
                    "status": "ended",
                    "winners": winners,
                    "winnerCount": len(winners) if isinstance(winners, list) else 0,
                    "claimedCount": len(winners) if isinstance(winners, list) else 0,
                    "luckyCount": len(winners) if isinstance(winners, list) else 0,
                },
                timestamp,
            )

        if method == "WebcastPreviewCjRpMessage":
            return self._apply_activity("redPacket", method, payload, timestamp, "超级红包发放中")

        if method == "WebcastPrizeNoticeMessage":
            prize_notice_extra = _merge_dicts(
                payload,
                _json_object(payload.get("jsonPayload")),
                _json_object(payload.get("data")),
                _json_object(payload.get("extra")),
            )
            winner = prize_notice_extra.get("winner") if isinstance(prize_notice_extra.get("winner"), dict) else {}
            labels = " ".join(
                str(prize_notice_extra.get(key) or "")
                for key in ("prizeName", "title", "activityName", "name", "content", "schemaUrl", "bizExtra")
            ).lower()
            has_red_packet = bool(_first_value(prize_notice_extra, "rpId", "redPacketId")) or any(
                token in labels for token in ("红包", "redpacket", "red_packet", "cash red packet")
            )
            has_lucky_bag = bool(_first_value(
                prize_notice_extra, "luckyBoxId", "luckyBoxIdStr", "lotteryId", "lottery_id", "activityId", "activity_id"
            )) or any(token in labels for token in ("福袋", "luckybox", "lucky_box", "lottery"))
            if not has_red_packet and not has_lucky_bag:
                event = self._base("room", method, payload, timestamp)
                if not _event_raw_user(payload):
                    event["systemEvent"] = True
                    event["user"] = normalize_user({"nickname": "直播间"})
                event["content"] = _text(payload.get("displayText")) or "中奖通知"
                event["prizeNotice"] = {
                    "winner": self._activity_user(winner) if winner else {},
                    "prizeId": str(_first_value(prize_notice_extra, "prizeId") or ""),
                    "prizeName": str(_first_value(prize_notice_extra, "prizeName") or ""),
                    "prizeCount": _number(_first_value(prize_notice_extra, "prizeCount")),
                    "lotteryId": str(_first_value(prize_notice_extra, "lotteryId") or ""),
                }
                self.interactions.append(event)
                return event
            return self._apply_activity("redPacket" if has_red_packet else "luckyBag", method, payload, timestamp, "中奖通知")
        if method == "WebcastSocialMessage":
            event = self._base("follow", method, payload, timestamp)
            display = _display_text(payload)
            display_key = str(display.get("key") or "").lower()
            display_pattern = _text(display).lower()
            if _number(payload.get("shareTime")) or "share" in display_key or "分享" in display_pattern:
                event["content"] = "分享了直播间"
            elif payload.get("follow") or "follow" in display_key or "关注" in display_pattern:
                event["content"] = "关注了主播"
            else:
                event["content"] = "完成了互动"
            self.interactions.append(event)
            return event

        if method == "WebcastFansclubMessage":
            return self._apply_fansclub(payload, timestamp)

        if method == "WebcastProfitInteractionMessage":
            event = self._base("score", method, payload, timestamp)
            user_id = str(payload.get("userId") or "")
            if user_id and not event["user"].get("id"):
                event["user"]["id"] = user_id
            display_content = "".join(_display_text_strings(payload))
            event.update({
                "action": str(payload.get("interactionName") or payload.get("interactionType") or "profit"),
                "score": _number(payload.get("profitScore")),
                "totalScore": _number(payload.get("totalScore")),
                "interactionType": _number(payload.get("interactionType")),
                "interactionName": str(payload.get("interactionName") or ""),
                "anchorId": str(payload.get("anchorId") or ""),
                "roomId": str(payload.get("roomId") or ""),
                "content": display_content or _text(payload.get("displayText")) or str(payload.get("interactionName") or "互动加分"),
            })
            self.interactions.append(event)
            return event

        if method in {
            "WebcastStarGuardInfoMessage", "WebcastMemberSpecialTipMessage",
            "WebcastGuardPickUpMessage", "WebcastMemberClubEntranceMessage",
        }:
            return self._apply_membership_snapshot(method, payload, timestamp)

        if method == "WebcastStarGuardMessage" and not _membership_purchase_signal(method, payload)[0]:
            return self._apply_membership_snapshot(method, payload, timestamp)

        if method in {
            "WebcastSubscriptionMessage", "WebcastSpecialMemberMessage",
            "WebcastStarGuardMessage",
            "WebcastResidentGuestMessage", "WebcastNobleMessage",
            "WebcastNotifyEffectMessage",
        }:
            return self._apply_membership(method, payload, timestamp)

        if method == "WebcastRoomMessage":
            display = payload.get("displayText") or (payload.get("common") or {}).get("displayText") or {}
            content = _text(display) or str(payload.get("title") or "")
            key = str(display.get("key") or "") if isinstance(display, dict) else ""
            pattern = str(display.get("defaultPattern") or "") if isinstance(display, dict) else ""
            if key == "live_signal_msg_special_key" and pattern == "{0:user} 为主播加了 {1:string}分":
                score = _number("".join(_display_text_strings(payload)))
                event = self._base("score", method, payload, timestamp)
                event.update({
                    "action": "room_signal_score",
                    "score": score,
                    "totalScore": 0,
                    "interactionType": 0,
                    "interactionName": "直播间互动加分",
                    "anchorId": "",
                    "roomId": str(payload.get("roomId") or (payload.get("common") or {}).get("roomId") or ""),
                    "content": f"为主播加了 {score} 分" if score else "为主播加分",
                })
                self.interactions.append(event)
                return event
            if _membership_purchase_signal(method, payload)[0]:
                return self._apply_membership(method, payload, timestamp, content)

        if method in ("WebcastRoomUserSeqMessage", "WebcastRoomRankMessage", "WebcastAudienceRankList", "WebcastContributionMessage", "WebcastRanklistMessage"):
            return self._apply_rank(method, payload, timestamp)

        if method == "WebcastRoomStatsMessage":
            self.stats["online"] = _number(payload.get("onlineUser") or payload.get("onlineUserCount"), self.stats["online"])
            total_likes = _number(payload.get("likeCount") or payload.get("totalLike"))
            total_gift_value = _number(payload.get("giftCount") or payload.get("giftValue"))
            self.stats["likes"] = max(self.stats["likes"], total_likes)
            if not _number(self.session_memory["summary"].get("rankSnapshotCount")):
                self.stats["giftValue"] = max(self.stats["giftValue"], total_gift_value)
            self._ensure_session_memory(timestamp, self.room.get("sessionId"))
            self.session_memory["summary"]["totalLikes"] = max(self.session_memory["summary"]["totalLikes"], total_likes)
            summary = self.session_memory["summary"]
            summary["giftMessageValue"] = max(_number(summary.get("giftMessageValue")), total_gift_value)
            if not _number(summary.get("rankSnapshotCount")):
                summary["totalGiftValue"] = summary["giftMessageValue"]
            return {"kind": "stats", "method": method, "ts": timestamp}

        if method == "WebcastRoomNotifyMessage":
            if _membership_purchase_signal(method, payload)[0]:
                return self._apply_membership(method, payload, timestamp, _text(_display_text(payload)))
            notify_type = _number(payload.get("notifyType"))
            if notify_type in (2, 3):
                return self._apply_activity("redPacket" if notify_type == 2 else "luckyBag", method, payload, timestamp)

        if method in ("WebcastTaskCenterEntranceMessage", "WebcastRoomDataSyncMessage"):
            data_type = str(payload.get("dataType") or "")
            if data_type == "LotteryInfoSyncData":
                lottery = _protobuf_varint_fields(payload.get("data"))
                lottery_id = lottery.get(1, 0)
                room_id = str(payload.get("roomId") or (payload.get("common") or {}).get("roomId") or "")
                start_at = lottery.get(7, 0) * 1000
                draw_at = lottery.get(8, 0) * 1000
                prize_count = lottery.get(6, 0)
                lucky_count = lottery.get(2, 0)
                candidate_total_count = lottery.get(3, 0)
                is_ended = bool(draw_at and max(timestamp, int(time.time() * 1000)) >= draw_at)
                sync_payload = {
                    **payload,
                    "lotteryId": str(lottery_id) if lottery_id else "",
                    "_activityTitle": "福袋活动",
                    "content": "福袋开奖状态同步" if is_ended else "福袋活动状态同步",
                    "status": "ended" if is_ended else "active",
                    "startTime": start_at,
                    "endTime": draw_at,
                    "luckyCount": lucky_count,
                    "candidateTotalCount": candidate_total_count,
                    "lotteryType": lottery.get(5, 0),
                    "prizeCount": prize_count,
                    "totalCount": lucky_count,
                    "claimedCount": candidate_total_count,
                    "amount": prize_count,
                    "currency": "钻石" if prize_count else "",
                    "prize": {
                        "name": "钻石福袋" if prize_count else "",
                        "amount": prize_count,
                        "currency": "钻石" if prize_count else "",
                    },
                    "_activityFallbackKey": f"lottery-sync:{room_id or 'room'}",
                }
                return self._apply_activity("luckyBag", method, sync_payload, timestamp)
            activity_data = _merge_dicts(
                _json_object(payload.get("jsonPayload")),
                _json_object(payload.get("data")),
                _json_object(payload.get("extra")),
            )
            content = " ".join((
                str(payload.get("dataType") or ""),
                str(payload.get("jsonPayload") or ""),
                str(payload.get("extra") or ""),
                json.dumps(activity_data, ensure_ascii=False),
            ))
            lowered = content.lower()
            if any(token in content for token in ("福袋", "LotteryInfoSyncData", "LuckyBox")) or "lucky" in lowered:
                return self._apply_activity("luckyBag", method, payload, timestamp)
            if "红包" in content or "redpacket" in lowered or "red_packet" in lowered or "lottery" in lowered:
                return self._apply_activity("redPacket", method, payload, timestamp)
        return None

    def _apply_fansclub(self, payload: dict, timestamp: int) -> dict:
        raw_user = _event_raw_user(payload)
        normalized_user = normalize_user(raw_user)
        fans_data = raw_user.get("fansClub") if isinstance(raw_user.get("fansClub"), dict) else {}
        fans_data = fans_data.get("data") if isinstance(fans_data.get("data"), dict) else fans_data
        display_strings = _display_text_strings(payload)
        club_name = str(_first_value(
            payload, "clubName", "fansclubName", "fansClubName",
        ) or _first_value(fans_data, "clubName", "name") or (display_strings[-1] if display_strings else ""))
        level = _number(_first_value(payload, "fansclubLevel", "level", "fansLevel") or _first_value(fans_data, "level"))
        action_code = _number(_first_value(payload, "action", "type", "operateType"))
        display = _text(_display_text(payload))
        source_content = str(payload.get("content") or display or "").strip()
        lowered = source_content.lower()
        if any(token in source_content for token in ("升级", "升级到")) or "upgrade" in lowered:
            action_type, action_label = "upgrade", "升级了"
        elif any(token in source_content for token in ("点亮", "续灯", "续费")) or "light" in lowered:
            action_type, action_label = "light", "点亮了"
        elif any(token in source_content for token in ("加入", "入团")) or "join" in lowered:
            action_type, action_label = "join", "加入了"
        elif "type" in payload and "action" not in payload:
            # SourceCodeDouyinBarrageGrab's normalized Type uses 1=upgrade, 2=join.
            action_type, action_label = ("upgrade", "升级了") if action_code == 1 else ("join", "加入了")
        else:
            # DmProto's current action uses 1=join, 2=light, 3=upgrade.
            action_type, action_label = {
                1: ("join", "加入了"),
                2: ("light", "点亮了"),
                3: ("upgrade", "升级了"),
            }.get(action_code, ("activity", "进行了粉丝团互动"))
        if club_name:
            normalized_user["fansClub"] = {
                **(normalized_user.get("fansClub") or {}),
                "name": club_name,
                "level": level or _number((normalized_user.get("fansClub") or {}).get("level")),
                "status": 1,
            }
        if action_type == "upgrade":
            content = f"升级了「{club_name or '粉丝团'}」粉丝团"
            if level:
                content += f"至 Lv{level}"
        elif action_type == "light":
            content = f"点亮了「{club_name or '粉丝团'}」灯牌"
            if level:
                content += f" · Lv{level}"
        elif action_type == "join":
            content = f"加入了「{club_name or '粉丝团'}」粉丝团"
        else:
            content = source_content or f"{action_label}{club_name or '粉丝团'}"
        event = {
            "kind": "fansclub",
            "method": "WebcastFansclubMessage",
            "ts": timestamp,
            "user": normalized_user,
            "action": action_type,
            "actionCode": action_code,
            "clubId": str(_first_value(payload, "clubId", "fansClubId") or ""),
            "clubName": club_name,
            "level": level,
            "content": content,
            "rawContent": source_content,
            "isMembershipLightOn": bool(payload.get("isMembershipLightOn")),
            "intimacyScore": _number(payload.get("intimacyScore")),
            "lightUpDays": _number(payload.get("lightUpDays")),
        }
        self.interactions.append(event)
        return event

    def _apply_membership_snapshot(self, method: str, payload: dict, timestamp: int) -> dict:
        raw_user = _event_raw_user(payload)
        member_type = _number(payload.get("memberType"))
        is_guard = (
            "Guard" in method
            or member_type == 4
            or "守护" in _text(_display_text(payload))
            or "守护" in str(payload.get("guardName") or payload.get("memberName") or "")
        )
        event = {
            "kind": "membership_snapshot",
            "method": method,
            "ts": timestamp,
            "membership": "星守护" if is_guard else "会员",
            "active": bool(payload.get("isGuard")) if "isGuard" in payload else None,
            "level": _number(payload.get("guardLevel") or payload.get("memberLevel")),
            "memberType": member_type,
            "guardName": str(payload.get("guardName") or payload.get("memberName") or ""),
            "content": _text(_display_text(payload)) or _text(payload.get("welcomeText")),
        }
        if raw_user:
            event["user"] = normalize_user(raw_user)
        return event

    def _apply_membership(self, method: str, payload: dict, timestamp: int, content: str = "") -> dict | None:
        users = []
        if method == "WebcastResidentGuestMessage":
            # This is a roster snapshot. Only its explicit latest list represents
            # a new event; a count-only snapshot must never create an anonymous row.
            for item in payload.get("latestGuestUser") or []:
                if isinstance(item, dict):
                    users.append((item.get("user") or {}, item))
        if not users:
            user = _first_dict(payload.get("user"), (payload.get("common") or {}).get("user"), _display_text_user(payload))
            if user:
                users = [(user, payload)]
        if not users:
            return {"kind": "membership_snapshot", "method": method, "ts": timestamp}

        display = _display_text(payload)
        purchase_signal, signal_operation, signal_months = _membership_purchase_signal(method, payload)
        if method in {"WebcastNotifyEffectMessage", "WebcastRoomMessage", "WebcastRoomNotifyMessage", "WebcastStarGuardMessage"} and not purchase_signal:
            return {"kind": "membership_snapshot", "method": method, "ts": timestamp}
        display_text = _text(display)
        display_strings = " ".join(_display_text_strings(payload))
        template_vars = _template_vars(payload)
        welcome_text = _text(payload.get("welcomeText"))
        raw_content = " ".join(part for part in (
            content, display_text, display_strings, " ".join(template_vars.values()), welcome_text,
            str(payload.get("guardName") or ""), str(payload.get("memberName") or ""),
        ) if part).strip()
        subscribe_state = _number(payload.get("subscribeState"))
        action_code = _number(payload.get("action") or payload.get("operateType"))
        update_type = _number(payload.get("updateType"))
        member_type = _number(payload.get("memberType"))
        is_new = bool(payload.get("isNew"))
        is_auto_renew = bool(payload.get("isAutoRenew"))
        guard = (
            any(token in method for token in ("Guard", "ResidentGuest"))
            or member_type == 4
            or "守护" in raw_content
            or "star_guard" in raw_content.lower()
        )
        state = subscribe_state or action_code or update_type
        cancel = subscribe_state == 3 or update_type == 3 or signal_operation == "cancel" or any(token in raw_content.lower() for token in ("取消", "cancel", "expired", "expire"))
        renew = bool(payload.get("isRenew")) or subscribe_state == 2 or update_type == 2 or signal_operation == "renew" or (method == "WebcastSubscriptionMessage" and state in (2, 4)) or any(token in raw_content.lower() for token in ("续费", "renew", "continue", "renewal"))
        update = signal_operation == "update"
        if guard:
            membership_label = "星守护"
            if cancel:
                action = "星守护过期"
            elif renew:
                action = "续费星守护"
            elif update:
                action = "星守护等级变更"
            elif method == "WebcastResidentGuestMessage" and update_type == 1:
                action = "加入星守护"
            else:
                action = "点亮星守护"
        elif method == "WebcastSpecialMemberMessage":
            membership_label = "专属会员"
            action = "取消专属会员" if cancel else "续费专属会员" if renew else "开通专属会员"
        elif method == "WebcastSubscriptionMessage":
            membership_label = "会员"
            action = "取消会员" if cancel else "续费会员" if renew else "开通会员"
        elif method == "WebcastMemberSpecialTipMessage":
            membership_label = {1: "VIP", 2: "高级会员", 3: "贵族", 4: "星守护"}.get(member_type, "会员")
            action = "取消" + membership_label if cancel else "续费" + membership_label if renew else "开通" + membership_label
        elif method == "WebcastNobleMessage":
            membership_label = "贵族"
            action = "取消贵族" if cancel else "续费贵族" if renew else "开通贵族"
        else:
            membership_label = "会员"
            action = "取消会员" if cancel else "续费会员" if renew else "开通会员"
        months = _number(
            payload.get("subscriptionMonths") or payload.get("subscribeMonths")
            or payload.get("months"),
            0,
        )
        if method == "WebcastResidentGuestMessage" and months <= 0:
            months = _number(payload.get("residentCount") or payload.get("guestDays") or payload.get("continueWeeks"))
        if months <= 0:
            months = signal_months or (12 if any(token in raw_content for token in ("年", "年度", "annual", "year")) else 1)
        last_event = None
        duplicate_only = False
        extra_badges = extract_event_badges(method, payload)
        for raw_user, detail in users:
            detail = detail if isinstance(detail, dict) else {}
            level = _number(detail.get("guardLevel") or detail.get("guestLevel") or detail.get("memberLevel") or payload.get("guardLevel") or payload.get("memberLevel"))
            expire_at = _number(detail.get("expireTimestamp") or payload.get("expireTime") or payload.get("expireTimestamp"))
            guard_type = _number(detail.get("guardType") or payload.get("guardType"))
            guest_days = _number(detail.get("guestDays") or payload.get("guestDays"))
            continue_weeks = _number(detail.get("continueWeeks") or payload.get("continueWeeks"))
            resident_count = _number(detail.get("residentCount") or payload.get("residentCount"))
            light_up_status = _number(detail.get("lightUpStatus") or payload.get("lightUpStatus"))
            event_content = action
            normalized_user = normalize_user(raw_user)
            if normalized_user.get("hasAnchorRelation"):
                normalized_user["anchorRelationSource"] = "interaction"
            normalized_user["badges"] = _merge_badges(normalized_user.get("badges"), extra_badges)
            event = {
                "kind": "membership",
                "method": method,
                "ts": timestamp,
                "user": normalized_user,
                "membership": membership_label,
                "action": action,
                "operation": "cancel" if cancel else "renew" if renew else "update" if update else "open",
                "months": months,
                "level": level,
                "content": event_content,
                "rawContent": raw_content,
                "state": state,
                "isNew": is_new,
                "isAutoRenew": is_auto_renew,
                "expireAt": expire_at,
                "anchorId": str(_first_value(detail, "anchorId") or _first_value(payload, "anchorId") or ""),
                "guardType": guard_type,
                "guestDays": guest_days,
                "continueWeeks": continue_weeks,
                "residentCount": resident_count,
                "lightUpStatus": light_up_status,
                "memberType": member_type,
                "guardianPeriod": {1: "weekly", 2: "monthly", 3: "quarterly", 4: "yearly"}.get(guard_type, ""),
                "guardianPeriodLabel": {1: "周守护", 2: "月守护", 3: "季守护", 4: "年守护"}.get(guard_type, ""),
                "sourceMethods": [method],
                "displayKey": str(display.get("key") or ""),
                "templateKey": str((payload.get("template") or {}).get("key") or "") if isinstance(payload.get("template"), dict) else "",
            }
            if method == "WebcastSubscriptionMessage":
                event["subscriptionLevel"] = _number(_first_value(payload, "subscribeLevel", "subscriptionLevel") or level)
                event["subscribeTime"] = _number(payload.get("subscribeTime"))
                event["subscribeState"] = subscribe_state
            if method == "WebcastSpecialMemberMessage":
                event["memberName"] = str(payload.get("memberName") or "")
            if method in ("WebcastStarGuardMessage", "WebcastStarGuardInfoMessage", "WebcastResidentGuestMessage"):
                event["guardName"] = str(payload.get("guardName") or payload.get("guestTitle") or "")
                event["guardDuration"] = _number(payload.get("guardDuration") or detail.get("continueWeeks"))
                event["totalGuardCount"] = _number(payload.get("totalGuardCount") or payload.get("totalGuards") or payload.get("guestNum"))
            if method in {"WebcastSubscriptionMessage", "WebcastNotifyEffectMessage", "WebcastRoomMessage", "WebcastRoomNotifyMessage", "WebcastStarGuardMessage", "WebcastResidentGuestMessage"}:
                identity = next(iter(_user_identity_keys(normalized_user)), normalized_user.get("nickname") or "anonymous")
                transaction_key = (str(identity), event["operation"], membership_label, months)
                existing = self._membership_transactions.get(transaction_key)
                if existing and timestamp - _number(existing.get("ts")) <= 10_000 and method not in existing.get("methods", set()):
                    existing_event = existing["event"]
                    existing["methods"].add(method)
                    existing_event["sourceMethods"] = sorted(existing["methods"])
                    if raw_content and raw_content not in str(existing_event.get("rawContent") or ""):
                        existing_event["rawContent"] = " | ".join(filter(None, (existing_event.get("rawContent"), raw_content)))
                    duplicate_only = True
                    continue
                self._membership_transactions[transaction_key] = {
                    "ts": timestamp,
                    "methods": {method},
                    "event": event,
                }
                for key, transaction in list(self._membership_transactions.items()):
                    if timestamp - _number(transaction.get("ts")) > 30_000:
                        self._membership_transactions.pop(key, None)
            self.memberships.append(event)
            last_event = event
        if last_event:
            return last_event
        if duplicate_only:
            return None
        return {"kind": "membership", "method": method, "ts": timestamp}

    def _apply_rank(self, method: str, payload: dict, timestamp: int) -> dict:
        data = payload.get("data") or payload
        if method == "WebcastRoomRankMessage":
            items = data.get("audienceRanks") or data.get("ranks") or []
        else:
            items = data.get("ranks") or data.get("audienceRanks") or data.get("rankList") or data.get("seats") or data.get("items") or []
        trusted_score = method != "WebcastAudienceRankList"
        ranking = [entry for index, item in enumerate(items) if (entry := _rank_entry(item, index, trusted_score=trusted_score))]
        has_rank_scores = any(entry.get("hasContribution") for entry in ranking)
        for entry in ranking:
            if entry.get("hasAnchorRelation"):
                entry["anchorRelationSource"] = "http" if method == "WebcastAudienceRankList" else "rank"
            self._observe_session_user(
                entry,
                timestamp,
                contribution=_number(entry.get("contribution")) if entry.get("hasContribution") else None,
            )
        if has_rank_scores:
            self.session_memory["summary"]["rankSnapshotCount"] += 1
            rank_gift_value = self._refresh_rank_gift_value()
        else:
            rank_gift_value = _number(self.session_memory["summary"].get("totalGiftValue"))
        if method == "WebcastAudienceRankList":
            self._replace_audience(ranking)
            self.audience_status.update({
                "lastRankRefreshAt": timestamp,
                "lastUpdatedAt": timestamp,
                "rankCount": len(self.audience),
                "source": method,
                "revision": self.audience_status["revision"] + 1,
            })
        else:
            self._map_audience_scores(ranking)
            self.audience_status.update({
                "lastPushAt": timestamp,
                "lastUpdatedAt": timestamp,
                "source": method,
            })
        visible_total = len(ranking)
        invisible_total = _number(data.get("invisible_total") or data.get("invisibleTotal"))
        total = _number(data.get("total") or payload.get("onlineUserCount") or payload.get("total"))
        self.stats["online"] = total or (visible_total + invisible_total) or self.stats["online"]
        return {
            "kind": "audience",
            "method": method,
            "ts": timestamp,
            "count": len(self.audience),
            "giftValue": rank_gift_value,
            "giftValueSource": "rank" if has_rank_scores else "",
        }

    def _replace_audience(self, ranking: list[dict]) -> None:
        previous_by_identity = {}
        for audience_item in self.audience:
            for identity in _user_identity_keys(audience_item):
                previous_by_identity.setdefault(identity, audience_item)

        next_audience = []
        for incoming in ranking[: self.AUDIENCE_LIMIT]:
            item = deepcopy(incoming)
            previous = next(
                (previous_by_identity.get(identity) for identity in _user_identity_keys(item)
                 if previous_by_identity.get(identity) is not None),
                None,
            )
            if previous:
                if not item.get("hasContribution") and previous.get("hasContribution"):
                    item["contribution"] = previous.get("contribution", item.get("contribution", 0))
                    item["hasContribution"] = True
                item["badges"] = _merge_badges(previous.get("badges"), item.get("badges"))
                item.update(_merge_anchor_relation(item, previous))
                for key in ("avatar", "gender", "secUid", "displayId", "fansClub", "membership"):
                    if key == "fansClub":
                        item[key] = _merge_fans_club(item.get(key), previous.get(key))
                        continue
                    if item.get(key) in (None, "", [], {}) and previous.get(key) not in (None, "", [], {}):
                        item[key] = deepcopy(previous[key])
            remembered, found = self._resolve_audience_score(item)
            if found and not item.get("hasContribution"):
                item["contribution"] = remembered
                item["hasContribution"] = True
            if item.get("hasContribution"):
                self._remember_audience_score(item, item.get("contribution", 0))
            next_audience.append(item)
        self.audience = next_audience

    def _map_audience_scores(self, ranking: list[dict]) -> None:
        if not ranking:
            return
        if not self.audience:
            for incoming in ranking:
                if incoming.get("hasContribution"):
                    self._remember_audience_score(incoming, incoming["contribution"])
            return
        audience_by_identity = {}
        for audience_item in self.audience:
            for identity in _user_identity_keys(audience_item):
                audience_by_identity.setdefault(identity, audience_item)

        updated = set()
        changed = False
        for incoming in ranking:
            if not incoming.get("hasContribution"):
                continue
            target = next(
                (audience_by_identity.get(identity) for identity in _user_identity_keys(incoming)
                 if audience_by_identity.get(identity) is not None),
                None,
            )
            if target is None or id(target) in updated:
                if incoming.get("hasContribution"):
                    self._remember_audience_score(incoming, incoming["contribution"])
                continue
            target["badges"] = _merge_badges(target.get("badges"), incoming.get("badges"))
            target.update(_merge_anchor_relation(incoming, target))
            for key in ("avatar", "gender", "secUid", "displayId", "fansClub", "membership"):
                if key == "fansClub":
                    target[key] = _merge_fans_club(incoming.get(key), target.get(key))
                    continue
                if incoming.get(key) not in (None, "", [], {}):
                    target[key] = deepcopy(incoming[key])
            target["contribution"] = incoming["contribution"]
            target["hasContribution"] = True
            self._remember_audience_score(target, incoming["contribution"])
            updated.add(id(target))
            changed = True
        if changed:
            self.audience_status["revision"] += 1

    def _sync_audience_user(self, user: dict) -> None:
        if not self.audience or not _user_identity_keys(user):
            return
        for item in self.audience:
            if not set(_user_identity_keys(item)).intersection(_user_identity_keys(user)):
                continue
            item["badges"] = _merge_badges(item.get("badges"), user.get("badges"))
            item.update(_merge_anchor_relation(user, item))
            for key in ("avatar", "gender", "secUid", "displayId", "fansClub", "membership", "signature"):
                if key == "fansClub":
                    item[key] = _merge_fans_club(user.get(key), item.get(key))
                    continue
                if user.get(key) not in (None, "", [], {}):
                    item[key] = deepcopy(user[key])
            self.audience_status["revision"] += 1
            self.audience_status["lastUpdatedAt"] = self.status["lastEventAt"]
            return

    def _apply_activity(self, kind: str, method: str, payload: dict, timestamp: int, fallback_content: str = "") -> dict:
        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        extra = _merge_dicts(
            payload,
            _json_object(payload.get("jsonPayload")),
            _json_object(payload.get("data")),
            _json_object(payload.get("extra")),
            info,
        )
        if method == "WebcastLuckyBoxEndMessage":
            extra = {
                **extra,
                "luckyBoxId": str(payload.get("luckyBoxIdStr") or payload.get("luckyBoxId") or ""),
            }
        if method == "WebcastPrizeNoticeMessage":
            extra = {
                **extra,
                "winner": payload.get("winner") or {},
                "prizeId": payload.get("prizeId"),
                "prizeName": payload.get("prizeName"),
                "prizeIcon": payload.get("prizeIcon"),
                "prizeCount": payload.get("prizeCount"),
                "lotteryId": payload.get("lotteryId"),
            }
        kind = self._activity_kind(kind, extra)
        participants = _first_value(extra, "participants", "joinUsers", "participantUsers", "participantList", "userIds") or []
        winners = []
        for key in (
            "winners", "winnerUsers", "winnerList", "winningUsers", "luckyUsers",
            "rewardedUsers", "rewardedDetails", "rewardedUserIds", "rewardedUserId",
            "winnerUserIds",
        ):
            value = extra.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, (list, tuple, set)):
                winners.extend(value)
            else:
                winners.append(value)
        if method == "WebcastLuckyBoxRewardMessage":
            participants = _first_value(extra, "participants", "joinUsers", "participantUsers", "userIds") or []
            winners = []
            for key in ("winnerUserIds", "rewardedUsers", "rewardedDetails", "rewardedUserIds", "rewardedUserId"):
                value = extra.get(key)
                if value in (None, "", [], {}):
                    continue
                if isinstance(value, (list, tuple, set)):
                    winners.extend(value)
                else:
                    winners.append(value)
        if method == "WebcastLotteryCandidateEventMessage":
            winners = []
            participants = extra.get("participants") or []
        if method == "WebcastLotteryDrawResultEventMessage":
            participants = []
            winners = extra.get("winners") or _first_value(extra, "userIds", "userOpenids", "user_ids", "user_openids") or []
        if isinstance(extra.get("winner"), dict):
            winners = [extra["winner"]]
        prize = _first_value(extra, "prize", "reward", "prizeInfo")
        if not isinstance(prize, dict):
            prize = {
                "name": str(_first_value(extra, "prizeName", "title", "name") or ""),
                "amount": _first_value(extra, "amount", "money", "rewardAmount", "diamondCount", "totalDiamondCount") or "",
                "count": _number(_first_value(extra, "prizeCount", "totalCount", "count")),
                "currency": str(_first_value(extra, "currency", "unit") or ""),
                "icon": _image_url(_first_value(extra, "prizeIcon", "icon", "iconUrl")),
            }
            red_packet_id = str(_first_value(extra, "rpId", "redPacketId") or "")
            if red_packet_id:
                prize["redPacketId"] = red_packet_id
        if method == "WebcastLuckyBoxEndMessage" and not prize.get("name"):
            prize["luckyBoxId"] = extra.get("luckyBoxId") or ""
        if isinstance(prize, dict) and not any(value not in (None, "", 0, [], {}) for value in prize.values()):
            prize = {}
        if kind == "luckyBag":
            activity_id = str(_first_value(extra, "luckyBoxId", "luckyBoxIdStr", "lotteryId", "activityId", "activity_id") or "")
        else:
            activity_id = str(_first_value(
                extra, "rpId", "redPacketId", "luckyBoxId", "luckyBoxIdStr", "lotteryId", "activityId", "activity_id"
            ) or "")
        merge_key = activity_id or str(extra.get("_activityMergeKey") or "")
        fallback_key = str(extra.get("_activityFallbackKey") or "")
        title = str(_first_value(extra, "title", "activityName", "name", "_activityTitle", "prizeName") or "")
        if not title:
            title = "福袋" if kind == "luckyBag" else "红包"
        activity = {
            "id": activity_id,
            "mergeKey": merge_key,
            "fallbackKey": fallback_key,
            "type": "lucky_bag" if kind == "luckyBag" else "red_packet",
            "status": str(_first_value(extra, "status", "state", "activityStatus") or "unknown"),
            "title": title,
            "startAt": _number(_first_value(extra, "startTime", "start_at", "beginTime")),
            "endAt": _number(_first_value(extra, "endTime", "end_at", "finishTime")),
            "totalCount": _number(_first_value(extra, "totalCount", "totalNum", "count")),
            "claimedCount": _number(_first_value(extra, "claimedCount", "receiveCount", "winnerCount")),
            "luckyCount": _number(_first_value(extra, "luckyCount")),
            "candidateTotalCount": _number(_first_value(extra, "candidateTotalCount")),
            "currency": str(_first_value(extra, "currency", "unit") or prize.get("currency") or ""),
            "amount": _first_value(extra, "amount", "money", "rewardAmount", "diamondCount", "totalDiamondCount") or prize.get("amount") or "",
            "schemaUrl": str(_first_value(extra, "schemaUrl", "schema", "url") or ""),
            "requirement": _first_value(extra, "requirement", "condition", "joinCondition") or "",
        }
        if method == "WebcastLuckyBoxEndMessage":
            activity["status"] = "ended"
        if method == "WebcastLuckyBoxMessage" and activity["status"] == "unknown":
            activity["status"] = "active"
        if method == "WebcastLuckyBoxRewardMessage" and winners:
            activity["status"] = "ended"
        if method == "WebcastLuckyBoxRewardMessage" and activity["status"] == "unknown":
            activity["status"] = "participating"
        if method == "WebcastLuckyBoxRewardMessage" and winners and not activity.get("claimedCount"):
            activity["claimedCount"] = len(winners)
        if method == "WebcastLuckyBoxTempStatusMessage" and activity["status"] == "unknown":
            activity["status"] = "active"
        if method == "WebcastRoomDataSyncMessage" and activity["status"] == "unknown":
            activity["status"] = "active"
        if method == "WebcastPrizeNoticeMessage":
            activity["status"] = "won"
        if method == "WebcastXGLotteryMessage" and winners:
            activity["status"] = "ended"
        if method == "WebcastLotteryEventNewMessage" and activity["status"] == "unknown":
            activity["status"] = "active"
        if method == "WebcastLotteryCandidateEventMessage":
            activity["status"] = "active"
        if method == "WebcastLotteryDrawResultEventMessage":
            activity["status"] = "ended"
            if winners and not activity.get("claimedCount"):
                activity["claimedCount"] = len(winners)
        content = str(payload.get("content") or _text(payload.get("displayText")) or payload.get("dataType") or fallback_content or "活动记录")
        if method == "WebcastLuckyBoxEndMessage" and content == "\u798f\u888b\u5f00\u5956" and kind == "redPacket":
            content = "\u7ea2\u5305\u5f00\u5956"
        if title not in {"福袋", "红包"} and content in {"活动记录", "中奖通知", "超级红包发放中", "福袋开奖"}:
            content = f"{title}：{content}"
        sender_value = _first_value(extra, "sender", "user", "anchor")
        sender = self._activity_user(sender_value) if sender_value else _event_user(payload)
        event = {
            "kind": kind,
            "method": method,
            "ts": timestamp,
            "sender": sender,
            "content": content,
            "participants": self._activity_users(participants),
            "winners": self._activity_users(winners),
            "activity": activity,
            "prize": prize or "待协议补全",
            "raw": extra,
            "updates": [{"method": method, "ts": timestamp, "content": content, "status": activity["status"]}],
        }
        if not event["sender"].get("id") and event["winners"]:
            event["sender"] = deepcopy(event["winners"][0])
        target = self.records["redPackets" if kind == "redPacket" else "luckyBags"]
        other_target = self.records["luckyBags" if kind == "redPacket" else "redPackets"]
        merge_key = str((event.get("activity") or {}).get("mergeKey") or "")
        fallback_key = str((event.get("activity") or {}).get("fallbackKey") or "")
        if not merge_key and not fallback_key and kind == "luckyBag" and method == "WebcastLuckyBoxTempStatusMessage":
            for previous in reversed(target):
                if not isinstance(previous, dict):
                    continue
                previous_activity = previous.get("activity") if isinstance(previous.get("activity"), dict) else {}
                previous_key = str((previous_activity or {}).get("mergeKey") or (previous_activity or {}).get("id") or "")
                previous_status = str((previous_activity or {}).get("status") or "")
                if not previous_key or previous_status in {"ended", "won"}:
                    continue
                if timestamp - _number(previous.get("ts")) > 300000:
                    continue
                fallback_key = str((previous_activity or {}).get("fallbackKey") or previous_key)
                break
        if merge_key:
            for index, previous in enumerate(other_target):
                previous_activity = previous.get("activity") if isinstance(previous, dict) else {}
                previous_key = str((previous_activity or {}).get("mergeKey") or (previous_activity or {}).get("id") or "")
                if previous_key != merge_key:
                    continue
                migrated = deepcopy(previous)
                migrated["kind"] = kind
                migrated_activity = dict(previous_activity or {})
                migrated_activity["type"] = "red_packet" if kind == "redPacket" else "lucky_bag"
                migrated["activity"] = migrated_activity
                del other_target[index]
                target.append(migrated)
                break
        if merge_key or fallback_key:
            for index, previous in enumerate(target):
                previous_activity = previous.get("activity") if isinstance(previous, dict) else {}
                previous_key = str((previous_activity or {}).get("mergeKey") or (previous_activity or {}).get("id") or "")
                if merge_key and previous_key != merge_key:
                    continue
                if not merge_key and (
                    fallback_key not in {
                        str((previous_activity or {}).get("fallbackKey") or ""),
                        previous_key,
                    }
                    or timestamp - _number(previous.get("ts")) > 120000
                ):
                    continue
                merged = deepcopy(previous)
                merged_activity = dict(previous_activity or {})
                for key, value in (event.get("activity") or {}).items():
                    if value not in (None, "", 0, [], {}):
                        if (
                            key == "title"
                            and value in {"红包", "福袋", "红包活动", "福袋活动"}
                            and merged_activity.get("title") not in (None, "", "红包", "福袋", "红包活动", "福袋活动")
                        ):
                            continue
                        if key != "status" or value != "unknown" or not merged_activity.get("status"):
                            merged_activity[key] = value
                merged["activity"] = merged_activity
                merged["method"] = method
                merged["ts"] = timestamp
                if event.get("content") and method != "WebcastRoomDataSyncMessage":
                    merged["content"] = event["content"]
                if event.get("sender", {}).get("id") and not merged.get("sender", {}).get("id"):
                    merged["sender"] = event["sender"]
                for key in ("participants", "winners"):
                    users = []
                    seen_users = set()
                    for user in (merged.get(key) or []) + (event.get(key) or []):
                        if not isinstance(user, dict):
                            continue
                        identity = next(iter(_user_identity_keys(user)), "")
                        identity = identity or json.dumps(user, ensure_ascii=False, sort_keys=True)
                        if identity in seen_users:
                            continue
                        seen_users.add(identity)
                        users.append(user)
                    merged[key] = users
                previous_prize = merged.get("prize")
                current_prize = event.get("prize")
                if isinstance(previous_prize, dict) and isinstance(current_prize, dict):
                    merged["prize"] = {**previous_prize, **current_prize}
                elif current_prize not in (None, "", "待协议补全"):
                    merged["prize"] = current_prize
                merged["raw"] = _merge_dicts(merged.get("raw"), event.get("raw"))
                updates = list(merged.get("updates") or [])
                if method == "WebcastRoomDataSyncMessage":
                    updates = [item for item in updates if not isinstance(item, dict) or item.get("method") != method]
                if not any(item.get("method") == method and item.get("ts") == timestamp for item in updates if isinstance(item, dict)):
                    updates.append({"method": method, "ts": timestamp, "content": content, "status": activity["status"]})
                merged["updates"] = updates
                target[index] = merged
                if merge_key:
                    self._activity_state["redPacket" if kind == "redPacket" else "luckyBag"]["mergeKey"] = merge_key
                    self._activity_state["redPacket" if kind == "redPacket" else "luckyBag"]["ts"] = timestamp
                return deepcopy(merged)
        target.append(event)
        if merge_key:
            self._activity_state["redPacket" if kind == "redPacket" else "luckyBag"]["mergeKey"] = merge_key
            self._activity_state["redPacket" if kind == "redPacket" else "luckyBag"]["ts"] = timestamp
        return event

    def _activity_kind(self, kind: str, extra: dict) -> str:
        if kind != "luckyBag":
            return kind
        red_packet_id = str(_first_value(extra, "rpId", "redPacketId") or "")
        if red_packet_id:
            return "redPacket"
        labels = " ".join(
            str(extra.get(key) or "")
            for key in ("title", "activityName", "name", "_activityTitle", "prizeName", "content", "schemaUrl", "bizExtra")
        ).lower()
        if "\u7ea2\u5305" in labels or "redpacket" in labels or "red_packet" in labels:
            return "redPacket"
        activity_id = str(_first_value(
            extra, "luckyBoxId", "luckyBoxIdStr", "rpId", "redPacketId", "lotteryId", "activityId", "activity_id"
        ) or "")
        if activity_id:
            for record_kind, records in (("redPacket", self.records["redPackets"]), ("luckyBag", self.records["luckyBags"])):
                for record in records:
                    activity = record.get("activity") if isinstance(record, dict) else {}
                    record_id = str((activity or {}).get("mergeKey") or (activity or {}).get("id") or "")
                    if record_id == activity_id:
                        return record_kind
        return kind

    def _activity_users(self, values: Any) -> list[dict]:
        if isinstance(values, (dict, str, int)):
            values = [values]
        if not isinstance(values, (list, tuple, set)):
            return []
        users = []
        for value in values:
            if isinstance(value, str):
                decoded = _json_object(value)
                if decoded:
                    value = decoded
            if isinstance(value, (dict, str, int)):
                users.append(self._activity_user(value))
        return users

    def _activity_user(self, value: Any) -> dict:
        raw_user = value.get("user") or value if isinstance(value, dict) else {"id": str(value)}
        if isinstance(raw_user, dict) and raw_user.get("userId") and not raw_user.get("id"):
            raw_user = {
                **raw_user,
                "id": str(raw_user.get("userIdStr") or raw_user.get("userId") or ""),
                "nickname": str(raw_user.get("userName") or raw_user.get("nickname") or ""),
                "avatar": raw_user.get("avatarUrl") or raw_user.get("avatar") or "",
                "secUid": str(raw_user.get("secUserId") or raw_user.get("secUid") or ""),
            }
        user = normalize_user(raw_user)
        if user.get("id"):
            known = self.find_user(user["id"])
            if known:
                return deepcopy(known)
        return user


