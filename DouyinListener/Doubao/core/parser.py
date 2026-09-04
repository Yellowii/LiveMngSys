"""
Doubao 抖音直播间 protobuf 解析核心
用法:
    from Doubao.core.parser import DoubaoParser
    p = DoubaoParser()
    for msg in p.parse_wss_frame(ws_bytes):
        print(msg["method"], msg["data"])
"""
from __future__ import annotations
import base64, gzip, inspect, json, os, re
from google.protobuf import json_format
from google.protobuf.message import DecodeError

# 动态加载 proto 编译产物；为方便未编译场景，同时支持纯 dict 路由（字段映射字典）
_HERE = os.path.dirname(os.path.abspath(__file__))
_DICT_PATH = os.path.join(_HERE, "..", "dict", "field_mapping.json")
PBResponse = None
PBMessage = None


def _load_mapping():
    with open(_DICT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_varint(data: bytes, pos: int):
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _sanitize_proto_strings(data: bytes) -> bytes:
    """Recursively walk protobuf binary and replace invalid UTF-8 in string fields
    (wire type 2) with Unicode replacement characters so ParseFromString succeeds."""
    out = bytearray()
    pos = 0
    while pos < len(data):
        tag_start = pos
        try:
            tag, pos = _read_varint(data, pos)
        except (ValueError, IndexError):
            out.extend(data[tag_start:])
            break
        wire_type = tag & 0x7
        if wire_type == 0:  # varint
            try:
                _, pos = _read_varint(data, pos)
            except (ValueError, IndexError):
                out.extend(data[tag_start:])
                break
            out.extend(data[tag_start:pos])
        elif wire_type == 1:  # 64-bit
            take = min(8, len(data) - pos)
            out.extend(data[tag_start:pos + take])
            pos += take
        elif wire_type == 2:  # length-delimited
            try:
                length, pos_after_len = _read_varint(data, pos)
            except (ValueError, IndexError):
                out.extend(data[tag_start:])
                break
            end = pos_after_len + length
            if end > len(data):
                out.extend(data[tag_start:])
                break
            payload = data[pos_after_len:end]
            try:
                payload.decode('utf-8')
                # Valid UTF-8 string - keep as-is
                out.extend(data[tag_start:end])
            except UnicodeDecodeError:
                # Not valid UTF-8 - could be a sub-message (recurse) or a bad string
                sanitized_sub = _sanitize_proto_strings(payload)
                # After recursion, if it's still not valid UTF-8, treat as string with replacements
                try:
                    sanitized_sub.decode('utf-8')
                    fixed = sanitized_sub
                except UnicodeDecodeError:
                    fixed = payload.decode('utf-8', errors='replace').encode('utf-8')
                # Write tag + new length + fixed payload
                out.extend(data[tag_start:pos])  # tag bytes only (up to start of length varint)
                l = len(fixed)
                while l > 0x7f:
                    out.append((l & 0x7f) | 0x80)
                    l >>= 7
                out.append(l)
                out.extend(fixed)
            pos = end
        elif wire_type == 5:  # 32-bit
            take = min(4, len(data) - pos)
            out.extend(data[tag_start:pos + take])
            pos += take
        else:
            out.extend(data[tag_start:])
            break
    return bytes(out)


class DoubaoParser:
    """抖音直播 WSS 消息解析器（框架）。

    职责：
        1. 拆帧：解析 WebcastResponse 外壳，迭代每条 Message；
        2. 解压：若 Message.compressed 为真则 gzip 解压 payload；
        3. 派发：按 method 通过 METHOD_DISPATCH 路由到对应 proto 类；
        4. 归一化：把 proto 对象转成 dict，并补充字段元数据说明。
    """

    # 方法到 proto 类名的映射（编译后由 _build_class_index 填充）
    _class_index = {}

    def __init__(self, mapping: dict | None = None):
        self.mapping = mapping or _load_mapping()
        self.dispatch = self.mapping.get("METHOD_DISPATCH", {})
        self._build_class_index()

    # --------------------------------------------------
    # 反射：尝试 import 已编译的 pb2
    # --------------------------------------------------
    def _build_class_index(self):
        try:
            import sys
            gen_dir = os.path.join(_HERE, "gen")
            sys.path.insert(0, gen_dir)  # 让 extra_pb2 能 import douyin_live_pb2
            import douyin_live_pb2, douyin_extra_pb2  # type: ignore
            for mod in (douyin_live_pb2, douyin_extra_pb2):
                for name, obj in inspect.getmembers(mod, inspect.isclass):
                    if getattr(obj, "DESCRIPTOR", None) is not None:
                        self._class_index[name] = obj
            # 外层 Response/Message（proto 中分别叫 Response / Message）
            if hasattr(douyin_live_pb2, "Response"):
                self._class_index["WebcastResponse"] = douyin_live_pb2.Response
                globals()["PBResponse"] = douyin_live_pb2.Response
            if hasattr(douyin_live_pb2, "Message"):
                self._class_index["WebcastMessage"] = douyin_live_pb2.Message
                globals()["PBMessage"] = douyin_live_pb2.Message
        except Exception as e:
            # 未编译时退化为仅方法派发（payload 原样返回）
            import traceback; traceback.print_exc()
            pass

    # --------------------------------------------------
    # 拆帧 & 派发
    # --------------------------------------------------
    def parse_wss_frame(self, frame: bytes):
        """解析完整 WSS push 帧，自动兼容 PushFrame / Response 两种外壳。

        抖音直播间 WSS 的二进制帧有两层：
          1) PushFrame  —— 外层信封，payload 经 gzip 压缩；
          2) Response   —— 内层响应，包含 messages[] 列表（每条对应一个业务消息）。
        """
        if not self._class_index.get("WebcastResponse"):
            yield {"_error": "pb2 not compiled; please compile .proto first"}
            return

        resp_cls = self._class_index["WebcastResponse"]
        pf_cls = self._class_index.get("PushFrame")

        payload = frame
        cursor = ""
        # 外层若是 PushFrame：解压
        if pf_cls is not None:
            pf = pf_cls()
            try:
                pf.ParseFromString(frame)
                if pf.payload:
                    payload = pf.payload
                    try:
                        payload = gzip.decompress(payload)
                    except Exception:
                        pass
                    cursor = getattr(pf, "cursor", "") or getattr(pf, "logId", "") or ""
            except DecodeError:
                payload = frame  # 不是 PushFrame，当 Response 解

        resp = resp_cls()
        try:
            resp.ParseFromString(payload)
        except DecodeError as e:
            yield {"_error": f"decode WebcastResponse: {e}"}
            return
        if not cursor:
            cursor = getattr(resp, "cursor", "") or getattr(resp, "internalExt", "") or ""
        for m in getattr(resp, "messages", []):
            mp = getattr(m, "payload", b"") or b""
            if getattr(m, "compressed", False):
                try:
                    mp = gzip.decompress(mp)
                except Exception:
                    pass
            method = getattr(m, "method", "")
            parsed = self._dispatch(method, mp)
            yield {
                "method": method,
                "msgId": getattr(m, "msg_id", 0) or getattr(m, "msgId", 0),
                "sendTime": getattr(m, "send_time", 0) or getattr(m, "sendTime", 0),
                "isHistory": getattr(m, "is_history", False) or getattr(m, "isHistory", False),
                "cursor": cursor,
                "data": parsed,
                "_meta": self.dispatch.get(method, {}),
            }

    def _dispatch(self, method: str, payload: bytes):
        cls = self._class_index.get(method)
        if cls is None:
            return {"_raw": payload, "_note": "no proto class, raw bytes"}
        obj = cls()
        try:
            obj.ParseFromString(payload)
        except DecodeError as e:
            # UTF-8 strict mode may fail on emoji/binary strings; try sanitizing
            if "bad UTF-8" in str(e) or "UTF-8" in str(e):
                try:
                    sanitized = _sanitize_proto_strings(payload)
                    obj2 = cls()
                    obj2.ParseFromString(sanitized)
                    obj = obj2
                except Exception:
                    return {"_error": f"decode {method}: {e}"}
            else:
                return {"_error": f"decode {method}: {e}"}
        # 转 dict
        parsed = json_format.MessageToDict(
            obj,
            preserving_proto_field_name=True,
            use_integers_for_enums=True,
        )
        # 所有消息都做 Image.urlList 切分（含 EmojiChat 表情图、User 徽章、礼物横幅等）
        return self.enrich_parsed(method, parsed)

    def enrich_parsed(self, method: str, parsed: dict) -> dict:
        """Add structured data hidden in bytes fields without changing the wire schema."""
        if method == "WebcastNotifyEffectMessage":
            effect_payload = parsed.get("payload") if isinstance(parsed.get("payload"), dict) else {}
            template_data = effect_payload.get("templateData") if isinstance(effect_payload.get("templateData"), dict) else {}
            content = template_data.get("content") if isinstance(template_data.get("content"), dict) else {}
            embedded = self._decode_embedded_text(content.get("contentData"))
            if embedded:
                parsed["embeddedDisplayText"] = embedded
                parsed.setdefault("displayText", embedded)
        self._normalize_embedded_image_urls(parsed)
        self._attach_badge_summary(parsed)
        return parsed

    def _decode_embedded_text(self, value):
        if not value:
            return {}
        try:
            raw = base64.b64decode(value, validate=True) if isinstance(value, str) else bytes(value)
            text_cls = self._class_index.get("Text")
            if not raw or text_cls is None:
                return {}
            text = text_cls()
            text.ParseFromString(raw)
            return json_format.MessageToDict(
                text,
                preserving_proto_field_name=True,
                use_integers_for_enums=True,
            )
        except (DecodeError, TypeError, ValueError):
            return {}

    @staticmethod
    def _normalize_embedded_image_urls(value):
        """递归把 Image.urlList 中粘连的多 URL 字符串拆成独立项。"""
        if isinstance(value, dict):
            urls = value.get("urlList")
            if isinstance(urls, list) and len(urls) == 1 and isinstance(urls[0], str):
                found = re.findall(r"https?://[^\x00-\x20\x12\x1a\*\"']+", urls[0])
                if found and len(found) > 1:
                    value["urlList"] = found
            for child in value.values():
                DoubaoParser._normalize_embedded_image_urls(child)
        elif isinstance(value, list):
            for child in value:
                DoubaoParser._normalize_embedded_image_urls(child)

    # 用户各类徽章字段标签（proto 中定义在 User 消息上）
    _USER_BADGE_FIELDS = {
        "avatarBorder":      "头像框",
        "medal":             "主播勋章",
        "specialBadge":      "专属会员徽章",
        "nobleLevel":        "贵族徽章",
        "starGuard":         "星守护徽章",
        "subscriptionInfo":  "订阅徽章",
        "liveStarBadge":     "直播之星徽章",
    }

    @classmethod
    def _attach_badge_summary(cls, parsed):
        """遍历 parsed 中所有 user 子节点，补一个 _badges 列表（徽章名 -> uri）。"""
        if isinstance(parsed, dict):
            # 识别 User 节点（含 id + nickname）
            if ("id" in parsed or "shortId" in parsed) and (
                "nickname" in parsed or "nickName" in parsed
            ):
                badges = []
                for f, label in cls._USER_BADGE_FIELDS.items():
                    v = parsed.get(f)
                    if isinstance(v, dict) and v.get("uri"):
                        badges.append({"label": label, "uri": v.get("uri"),
                                       "urls": v.get("urlList", [])})
                # badgeList (field 61): 复合徽章列表
                for img in (parsed.get("badgeList") or []):
                    if isinstance(img, dict) and img.get("uri"):
                        badges.append({"label": "徽章", "uri": img.get("uri"),
                                       "urls": img.get("urlList", [])})
                if badges:
                    parsed["_badges"] = badges
            # EmojiStruct 节点：把 image 标为表情图
            if "emoji" in parsed and "image" in parsed:
                img = parsed.get("image")
                if isinstance(img, dict):
                    img["_role"] = "emoji_image"
            for child in parsed.values():
                cls._attach_badge_summary(child)
        elif isinstance(parsed, list):
            for child in parsed:
                cls._attach_badge_summary(child)

    # --------------------------------------------------
    # 便捷工具
    # --------------------------------------------------
    def explain(self, method: str) -> dict:
        """返回某 method 的字段映射字典（方便上层 UI 渲染）。"""
        return self.mapping.get(method, {})

    def summarize(self, parsed_msg: dict) -> str:
        """把已解析消息转成可读摘要文本。"""
        method = parsed_msg.get("method", "")
        data = parsed_msg.get("data", {})
        common = data.get("common", {})

        if method == "WebcastChatMessage":
            return f"[弹幕] {data.get('user', {}).get('nickName', '')}: {data.get('content', '')}"
        if method == "WebcastEmojiChatMessage":
            u = data.get("user", {})
            return f"[表情弹幕] {u.get('nickname', u.get('nickName', ''))}: {data.get('content', '[表情]')}"
        if method == "WebcastGiftMessage":
            g = data.get("gift", {})
            return (f"[礼物] {data.get('user', {}).get('nickName', '')} 送出 "
                    f"{g.get('name', '')} x{data.get('comboCount', data.get('count', ''))} "
                    f"({g.get('diamondCount', 0) * data.get('count', 0)}钻)")
        if method == "WebcastLikeMessage":
            return f"[点赞] {data.get('user', {}).get('nickName', '')} x{data.get('count', '')}"
        if method == "WebcastMemberMessage":
            return f"[进场] {data.get('user', {}).get('nickName', '')}"
        if method == "WebcastSocialMessage":
            return f"[社交] {data.get('user', {}).get('nickName', '')} action={data.get('action')}"
        if method == "WebcastResidentGuestMessage":
            return (f"[星守护榜单] 守护人数={data.get('guestNum')} "
                    f"更新类型={data.get('updateType')} 最新={len(data.get('latestGuestUser', []))}")
        if method == "WebcastStarGuardMessage":
            return (f"[星守护入场] {data.get('user', {}).get('nickname', '')} "
                    f"lv={data.get('guardLevel')} {data.get('guardName', '')}")
        if method == "WebcastSpecialMemberMessage":
            return (f"[专属会员] {data.get('user', {}).get('nickname', '')} "
                    f"lv={data.get('memberLevel')} {data.get('memberName', '')}")
        if method == "WebcastSubscriptionMessage":
            return (f"[订阅] {data.get('user', {}).get('nickname', '')} "
                    f"lv={data.get('subscribeLevel')} action={data.get('action')}")
        if method == "WebcastNobleMessage":
            return (f"[贵族] {data.get('nobleName', '')} lv={data.get('nobleLevel')} "
                    f"{data.get('user', {}).get('nickname', '')}")
        if method == "WebcastRanklistHourEntranceMessage":
            return f"[小时榜入口] {data.get('title', '')} hour={data.get('hour')}"
        if method == "WebcastHourRankListMessage":
            return (f"[小时榜] type={data.get('rankType')} "
                    f"hour={data.get('hour')} 上榜={len(data.get('items', []))}")
        if method == "WebcastFansRankMessage":
            return (f"[粉丝榜] period={data.get('periodType')} "
                    f"上榜={len(data.get('items', []))} 自身={data.get('ownRank')}")
        if method == "WebcastRanklistMessage":
            return (f"[全量榜单] {data.get('title', '')} type={data.get('rankType')} "
                    f"scope={data.get('rankScope')} 上榜={len(data.get('items', []))}")
        if method == "WebcastRoomStatsMessage":
            return (f"[统计] 在线={data.get('roomUserCount')} 累计={data.get('totalUser')} "
                    f"点赞={data.get('likeCount')} 礼物钻={data.get('giftDiamondCount')}")
        if method == "WebcastRoomNotifyMessage":
            return f"[房间通知] type={data.get('notifyType')} {data.get('content', '')}"
        if method == "WebcastControlMessage":
            return f"[控制] status={data.get('status')} action={data.get('action')}"
        if method == "WebcastTeamPlayTeamInfoMessage":
            return (f"[团战状态] battle={data.get('battleIdStr')} "
                    f"status={data.get('status')} ts={data.get('timestamp')}")
        return f"[{method}] msgId={parsed_msg.get('msgId')}"


if __name__ == "__main__":
    import sys
    p = DoubaoParser()
    print(f"Loaded {len(p.dispatch)} methods; class_index={len(p._class_index)}")
