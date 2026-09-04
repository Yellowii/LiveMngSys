"""抖音直播 WebSocket 客户端（基于 protobuf push 流）。

连接流程：
1. GET https://live.douyin.com/<room_id>  -> 抓 Set-Cookie 拿到 ttwid
2. 从直播页或本地参数构造 wss://.../webcast/im/push/v2/ 入口
3. 建立 wss 连接 -> 循环收发 Response/PayloadInIm，并发送 heartbeat/ACK 保活
"""
import asyncio
import base64
import contextlib
import html as html_lib
import json
import logging
import re
import ssl
import sys
import time
import urllib.parse
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional

import aiohttp
import websockets
from aiohttp import ClientSession
from google.protobuf import json_format, message_factory

# 兼容从子目录直接运行：把项目根加入 sys.path
_THIS_DIR = Path(__file__).resolve().parent
_PROJ_ROOT = _THIS_DIR.parent.parent  # d:\Proj\DmProto
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

from Doubao.core.frame import (  # noqa: E402
    parse_wss_message,
    build_heartbeat_frame,
    build_ack_frame,
    unzip_response,
)
from Doubao.core.parser import DoubaoParser  # noqa: E402
from Doubao.core.parser import _sanitize_proto_strings  # noqa: E402
from Doubao.client.auth_qr import QrLogin, interactive_login  # noqa: E402
from Doubao.client.signed_fetch import (  # noqa: E402
    build_signed_audience_url,
    build_signed_fetch_url,
    request_ms_token,
    signing_user_agent,
)

_log = logging.getLogger('Doubao.wss_client')

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _short(s, n=60):
    s = str(s or "")
    return s if len(s) <= n else s[:n] + "…"


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first_image_url(image) -> str:
    if not isinstance(image, dict):
        return ''
    urls = image.get('url_list') or image.get('urlList') or []
    return str(urls[0]) if isinstance(urls, list) and urls else ''


def _safe_path_part(value: str, fallback: str = 'unknown') -> str:
    text = str(value or '').strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text)
    text = text.strip(' .')
    return text or fallback


def _extract_room_enter_info(data: dict, fallback_room_id: str = '') -> dict:
    payload = data.get('data') if isinstance(data, dict) else {}
    if isinstance(payload, dict):
        items = payload.get('data') or payload.get('list') or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    room_data = items[0] if items and isinstance(items[0], dict) else {}
    nested_room = room_data.get('room') or room_data.get('room_info') or room_data.get('roomInfo')
    room = nested_room if isinstance(nested_room, dict) else room_data
    owner = room_data.get('owner') or room_data.get('owner_info') or room_data.get('anchor_info') or room.get('owner') or {}
    if not isinstance(room, dict):
        room = {}
    if not isinstance(owner, dict):
        owner = {}

    cover = room.get('cover') or room_data.get('cover') or {}
    avatar = owner.get('avatar_thumb') or owner.get('avatar_medium') or owner.get('avatar_large') or owner.get('avatar') or {}
    intro = room_data.get('live_intro') or room_data.get('description') or room.get('description') or room.get('introduction') or ''
    response_code = _to_int(data.get('status_code') or data.get('statusCode') or data.get('code')) if isinstance(data, dict) else 0
    response_message = str((data.get('status_msg') or data.get('statusMessage') or data.get('message') or '') if isinstance(data, dict) else '')
    raw_status = _to_int(room_data.get('status') or room.get('status'))
    is_live = room.get('is_live', room.get('isLive', room_data.get('is_live', room_data.get('isLive'))))
    if not isinstance(is_live, bool):
        is_live = True if raw_status == 2 else False if raw_status in {0, 1, 3, 4} else None
    room_state = 'live' if is_live is True else 'not_live' if is_live is False else 'unknown'

    return {
        'roomExists': bool(room_data or room),
        'statusCode': response_code,
        'statusMessage': response_message,
        'isLive': is_live,
        'roomState': room_state,
        # web_rid identifies the stable room URL; id_str identifies this live session.
        'roomId': str(room_data.get('web_rid') or room.get('web_rid') or fallback_room_id or ''),
        'sessionId': str(room_data.get('id_str') or room.get('id_str') or room_data.get('room_id') or room.get('id') or ''),
        'liveId': str(room.get('live_id') or room_data.get('live_id') or room_data.get('liveId') or room_data.get('session_id') or room_data.get('sessionId') or ''),
        'title': str(room.get('title') or room_data.get('title') or ''),
        'description': str(intro or ''),
        'cover': _first_image_url(cover),
        'status': raw_status,
        'createTime': _to_int(room.get('create_time') or room_data.get('create_time') or room_data.get('createTime')),
        'startTime': _to_int(room.get('start_time') or room_data.get('start_time') or room_data.get('startTime')),
        'anchorId': str(owner.get('id_str') or owner.get('id') or room_data.get('anchor_id') or ''),
        'secAnchorId': str(owner.get('sec_uid') or owner.get('secUid') or room_data.get('sec_uid') or ''),
        'anchor': str(owner.get('nickname') or owner.get('nick_name') or room_data.get('anchor') or ''),
        'avatar': _first_image_url(avatar),
        'anchorInfo': owner,
        'roomInfo': room,
    }


def _iter_wire_fields(data):
    """Yield top-level protobuf fields without interpreting opaque length fields."""
    pos = 0
    while pos < len(data):
        tag = 0
        shift = 0
        while pos < len(data):
            byte = data[pos]
            pos += 1
            tag |= (byte & 0x7f) << shift
            if not byte & 0x80:
                break
            shift += 7
        field_number, wire_type = tag >> 3, tag & 7
        if not field_number:
            raise ValueError('invalid protobuf field number')
        if wire_type == 0:
            value = 0
            shift = 0
            while pos < len(data):
                byte = data[pos]
                pos += 1
                value |= (byte & 0x7f) << shift
                if not byte & 0x80:
                    break
                shift += 7
        elif wire_type == 1:
            value = data[pos:pos + 8]
            pos += 8
        elif wire_type == 2:
            length = 0
            shift = 0
            while pos < len(data):
                byte = data[pos]
                pos += 1
                length |= (byte & 0x7f) << shift
                if not byte & 0x80:
                    break
                shift += 7
            value = data[pos:pos + length]
            pos += length
        elif wire_type == 5:
            value = data[pos:pos + 4]
            pos += 4
        else:
            raise ValueError(f'unsupported protobuf wire type {wire_type}')
        yield field_number, wire_type, value


def _parse_emoji_fallback(pb_cls, data):
    """Parse emoji messages whose nested emoji field contains opaque bytes."""
    parsed = {}
    urls = []
    fields = pb_cls.DESCRIPTOR.fields_by_number
    for field_number, wire_type, value in _iter_wire_fields(data):
        field = fields.get(field_number)
        if field is None:
            continue
        if wire_type == 0:
            parsed[field.name] = value
            continue
        if wire_type != 2:
            continue
        if field_number == 4:
            parsed[field.name] = base64.b64encode(value).decode('ascii')
            urls.extend(match.decode('ascii', errors='ignore') for match in re.findall(rb'https?://[^\x00-\x20]+', value))
            continue
        if field.message_type is None:
            continue
        try:
            nested_cls = message_factory.GetMessageClass(field.message_type)
            nested = nested_cls()
            nested.ParseFromString(value)
            parsed[field.name] = json_format.MessageToDict(
                nested, preserving_proto_field_name=True, use_integers_for_enums=True,
            )
        except Exception:
            if field_number == 3:
                urls.extend(match.decode('ascii', errors='ignore') for match in re.findall(rb'https?://[^\x00-\x20]+', value))
    if urls:
        parsed['emoji'] = {'image': {'urlList': list(dict.fromkeys(urls))}}
    return parsed


@dataclass
class ClientConfig:
    room_id: str = ''
    room_url: str = ''
    cookie: str = ''
    user_unique_id: str = ''
    output_dir: str = 'Doubao/sessions'
    save_raw: bool = True
    heartbeat_interval: float = 10.0
    audience_poll_interval: float = 15.0
    reconnect: bool = True
    reconnect_max: int = 10
    reconnect_delay: float = 3.0
    log_level: str = 'INFO'
    auto_login: bool = True
    browser_headless: bool = True
    browser_block_media: bool = True
    browser_auto_visible_fallback: bool = True
    browser_wss_timeout: float = 25.0
    bootstrap_browser: bool = True
    deduplicate: bool = True
    dedup_cache_size: int = 300
    ws_proxy: str = ''
    http_proxy: str = ''

    @classmethod
    def from_file(cls, path: str) -> 'ClientConfig':
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: str) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding='utf-8'
        )


class SessionSaver:
    """Persist raw proto and parsed JSON by room/session."""

    def __init__(
        self,
        cfg: ClientConfig,
        room_id: str,
        room_title: str = '',
        live_id: str = '',
        anchor: str = '',
        anchor_id: str = '',
        sec_anchor_id: str = '',
    ):
        self.cfg = cfg
        self.room_id = str(room_id or '')
        self.live_id = str(live_id or '')
        self.anchor_id = str(anchor_id or '')
        self.sec_anchor_id = str(sec_anchor_id or '')
        self.session_key = self.live_id or f'{time.strftime("%Y%m%d_%H%M%S")}_{self.room_id}'
        self.room_key = self.sec_anchor_id or self.anchor_id or self.room_id
        room_name = anchor or room_title or self.room_id or 'unknown'
        room_label = _safe_path_part(f'{room_name}的直播间_{self.room_key}' if self.room_key else f'{room_name}的直播间')
        session_label = _safe_path_part(f'场次{self.session_key}')
        self.session_dir = Path(cfg.output_dir) / room_label / session_label
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = self.session_dir / 'proto'
        self.json_dir = self.session_dir / 'json'
        if cfg.save_raw:
            self.raw_dir.mkdir(exist_ok=True)
        self.json_dir.mkdir(exist_ok=True)
        self._parsed_fp = open(self.session_dir / 'parsed.jsonl', 'a', encoding='utf-8', buffering=1)
        self._index_fp = open(self.session_dir / 'raw_proto_index.jsonl', 'a', encoding='utf-8', buffering=1)
        meta_path = self.session_dir / 'session.json'
        created_at = _now_ms()
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                metadata = {}
        else:
            metadata = {}
        metadata.update({
            'roomId': self.room_id,
            'roomKey': self.room_key,
            'liveId': self.live_id,
            'roomTitle': room_title or metadata.get('roomTitle') or '',
            'roomName': room_name,
            'anchor': anchor or metadata.get('anchor') or '',
            'anchorId': self.anchor_id,
            'secAnchorId': self.sec_anchor_id,
            'sessionId': self.session_key,
            'sessionName': f'{time.strftime("%Y-%m-%d %H:%M:%S")} · {room_title or "未命名直播"}',
            'createdAt': metadata.get('createdAt') or created_at,
            'archive': {
                'format': 'livedash-compatible-session-v1',
                'parsedJsonl': 'parsed.jsonl',
                'jsonDirectory': 'json',
                'rawProtoDirectory': 'proto',
                'rawProtoIndex': 'raw_proto_index.jsonl',
                'rawProtoEnabled': bool(cfg.save_raw),
            },
        })
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')

    def _stem(self, method: str, msg_id: int, seq: int) -> str:
        ts_str = time.strftime('%Y%m%d_%H%M%S_') + str(seq % 1000).zfill(3)
        return f'{ts_str}_{method}_{msg_id}'

    def save_raw(self, method: str, msg_id: int, seq: int, payload: bytes) -> str:
        if not self.cfg.save_raw:
            return ''
        stem = self._stem(method, msg_id, seq)
        rel = f'proto/{stem}.bin'
        (self.raw_dir / f'{stem}.bin').write_bytes(payload)
        self._index_fp.write(json.dumps({
            'ts': _now_ms(), 'seq': seq, 'method': method,
            'msg_id': msg_id, 'file': rel,
        }, ensure_ascii=False) + '\n')
        return rel

    def save_json(self, method: str, msg_id: int, seq: int, rec: dict) -> str:
        stem = self._stem(method, msg_id, seq)
        rel = f'json/{stem}.json'
        (self.json_dir / f'{stem}.json').write_text(
            json.dumps(rec, ensure_ascii=False, indent=2, default=str),
            encoding='utf-8',
        )
        return rel

    def save_parsed(self, rec: dict):
        self._parsed_fp.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')

    def flush_events(self):
        self._parsed_fp.flush()
        self._index_fp.flush()

    def close(self):
        self.flush_events()
        self._parsed_fp.close()
        self._index_fp.close()


class DouyinWssClient:

    def __init__(self, cfg: ClientConfig):
        self.cfg = cfg
        self._parser = DoubaoParser()
        self._response_cls = self._parser._class_index.get("WebcastResponse")
        self._push_frame_cls = self._parser._class_index.get("PushFrame")
        self._payload_in_im_cls = self._parser._class_index.get("PayloadInIm")
        self._ws = None
        self._stop = False
        self._hb_task = None
        self._audience_task = None
        self._cookies: Dict[str, str] = {}
        self.room_id = ''
        self.live_id = ''
        self.anchor = ''
        self.anchor_id = ''
        self.sec_anchor_id = ''
        self.anchor_avatar = ''
        self.cover = ''
        self.title = ''
        self.description = ''
        self.seq = 0
        self._cursor = ''
        self._internal_ext = ''
        self._msg_counter = 0
        self.saver: Optional[SessionSaver] = None
        self._listeners: List[Callable[[dict], None]] = []
        self._seen_msg_ids: Dict[str, List[int]] = {}
        self._bootstrap_attempted = False
        logging.basicConfig(
            level=getattr(logging, cfg.log_level.upper(), logging.INFO),
            format='[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S',
        )

    def on_message(self, fn):
        self._listeners.append(fn)
        return fn

    def _emit(self, rec):
        for fn in list(self._listeners):
            try:
                fn(rec)
            except Exception as e:
                _log.debug('listener error: %s', e)

    def _is_duplicate_message(self, method: str, msg_id: int) -> bool:
        if not getattr(self.cfg, 'deduplicate', True) or not msg_id:
            return False
        msg_ids = self._seen_msg_ids.setdefault(method, [])
        if msg_id in msg_ids:
            return True
        msg_ids.append(msg_id)
        max_size = int(getattr(self.cfg, 'dedup_cache_size', 300) or 300)
        max_size = max(max_size, 1)
        if len(msg_ids) > max_size:
            del msg_ids[:-max_size]
        return False

    # ---------- cookies ----------
    def _cookie_header(self) -> str:
        if self.cfg.cookie:
            return self.cfg.cookie
        return '; '.join(f'{k}={v}' for k, v in self._cookies.items())

    def _parse_cookies(self, header: str):
        for part in header.split(';'):
            if '=' in part:
                k, v = part.strip().split('=', 1)
                self._cookies[k.strip()] = v.strip()

    def _cookie_value(self, name: str) -> str:
        if name in self._cookies:
            return self._cookies[name]
        cookie = self.cfg.cookie or ''
        m = re.search(r'(?:^|;\s*)' + re.escape(name) + r'=([^;]+)', cookie)
        return m.group(1) if m else ''

    def _user_unique_id(self) -> str:
        if self.cfg.user_unique_id:
            return self.cfg.user_unique_id
        for name in ('webcast_did', 'ttwid'):
            val = self._cookie_value(name)
            m = re.search(r'(\d{16,})', urllib.parse.unquote(val))
            if m:
                return m.group(1)
        if not self.cfg.user_unique_id:
            self.cfg.user_unique_id = str(int(time.time() * 1000))
        return self.cfg.user_unique_id

    @staticmethod
    def _extract_room_id_from_html(html: str) -> str:
        unescaped = html.replace('\\"', '"').replace('\\u0026', '&')
        for pat in (
            r'"roomId"\s*:\s*"?(\d{10,})',
            r'"room_id"\s*:\s*"?(\d{10,})',
        ):
            m = re.search(pat, unescaped)
            if m:
                return m.group(1)
        for pat in (
            r'room_id["\']?\s*[:=]\s*["\']?(\d{10,})',
            r'roomId["\']?\s*[:=]\s*["\']?(\d{10,})',
            r'web_rid["\']?\s*[:=]\s*["\']?(\d{6,})',
        ):
            m = re.search(pat, unescaped)
            if m:
                return m.group(1)
        return ''

    @staticmethod
    def _extract_user_unique_id_from_html(html: str) -> str:
        unescaped = html.replace('\\"', '"').replace('\\u0026', '&')
        for pattern in (
            r'"user_unique_id"\s*:\s*"?(\d{10,})',
            r'user_unique_id["\']?\s*[:=]\s*["\']?(\d{10,})',
        ):
            match = re.search(pattern, unescaped)
            if match:
                return match.group(1)
        return ''

    @staticmethod
    def _extract_room_metadata_from_html(html: str) -> dict:
        text = html.replace('\\"', '"').replace('\\u0026', '&')
        metadata = {}
        title = re.search(
            r'"roomInfo"\s*:\s*\{"room"\s*:\s*\{[^{}]{0,500}?"title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
            text,
        )
        if title:
            metadata['title'] = html_lib.unescape(title.group(1))

        anchor = re.search(
            r'"anchor"\s*:\s*\{"id_str"\s*:\s*"(\d+)"\s*,\s*"sec_uid"\s*:\s*"([^"]+)"\s*,\s*"nickname"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
            text,
        )
        if anchor:
            metadata.update({
                'anchor_id': anchor.group(1),
                'sec_anchor_id': anchor.group(2),
                'anchor': html_lib.unescape(anchor.group(3)),
            })
            avatar_scope = text[anchor.end():anchor.end() + 2500]
            avatar = re.search(r'"avatar_thumb"\s*:\s*\{"url_list"\s*:\s*\["([^"]+)"', avatar_scope)
            if avatar:
                metadata['avatar'] = html_lib.unescape(avatar.group(1))

        description = re.search(
            r'<meta\s+(?:name|property)=["\'](?:description|og:description)["\'][^>]*content=["\']([^"\']+)',
            html,
            re.IGNORECASE,
        )
        if description:
            metadata['description'] = html_lib.unescape(description.group(1))
        return metadata

    @staticmethod
    def _extract_wss_from_html(html: str) -> str:
        text = html.replace('\\u0026', '&').replace('\\/', '/').replace('\\"', '"')
        m = re.search(r'wss://[^"\'<>\s]+/webcast/im/push/v2/\?[^"\'<>\s]+', text)
        return m.group(0) if m else ''

    def _build_direct_wss_url(self, signature: str = '') -> str:
        now_ms = _now_ms()
        user_unique_id = self._user_unique_id()
        params = {
            'app_name': 'douyin_web',
            'version_code': '180800',
            'webcast_sdk_version': '1.0.15',
            'update_version_code': '1.0.15',
            'compress': 'gzip',
            'device_platform': 'web',
            'cookie_enabled': 'true',
            'screen_width': '1920',
            'screen_height': '1080',
            'browser_language': 'zh-CN',
            'browser_platform': 'Win32',
            'browser_name': 'Mozilla',
            'browser_version': USER_AGENT,
            'browser_online': 'true',
            'tz_name': 'Asia/Shanghai',
            'cursor': self._cursor,
            'internal_ext': self._internal_ext,
            'host': 'https://live.douyin.com',
            'aid': '6383',
            'live_id': '1',
            'did_rule': '3',
            'endpoint': 'live_pc',
            'support_wrds': '1',
            'user_unique_id': user_unique_id,
            'im_path': '/webcast/im/fetch/',
            'identity': 'audience',
            'need_persist_msg_count': '15',
            'insert_task_id': '',
            'live_reason': '',
            'room_id': self.room_id,
            'heartbeatDuration': '0',
        }
        if not params['cursor']:
            params['cursor'] = f't-{now_ms}_r-1_d-1_u-1_h-1'
        if not params['internal_ext']:
            params['internal_ext'] = (
                f'internal_src:dim|wss_push_room_id:{self.room_id}|'
                f'wss_push_did:{user_unique_id}|first_req_ms:{now_ms}|'
                f'fetch_time:{now_ms}|seq:1|wss_info:0-{now_ms}-0-0'
            )
        if signature:
            params['signature'] = signature
        return 'wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/?' + urllib.parse.urlencode(params)

    # ---------- room/init ----------
    async def _ensure_login(self, http: ClientSession):
        cookie = (self.cfg.cookie or '').strip()
        if cookie and 'sessionid=' in cookie:
            self._parse_cookies(cookie)
            return
        cached = QrLogin.load_cached_cookies()
        if cached and cached.get('sessionid'):
            self._cookies.update(cached)
            _log.info('使用本地缓存 cookie（sessionid=%s…）', cached.get('sessionid', '')[:8])
            return
        if not self.cfg.auto_login:
            raise RuntimeError('没有有效的 sessionid，且自动登录未启用')
        _log.info('未检测到登录态，开始二维码登录…')
        cookie_str = await interactive_login(proxy=self.cfg.http_proxy or None)
        self._parse_cookies(cookie_str)

    async def _resolve_room(self, http: ClientSession) -> str:
        if self.cfg.room_id and self.cfg.room_id.isdigit():
            return self.cfg.room_id
        url = self.cfg.room_url
        if url:
            headers = {'User-Agent': USER_AGENT, 'Cookie': self._cookie_header()}
            async with http.get(url, headers=headers,
                                proxy=self.cfg.http_proxy or None) as r:
                html = await r.text()
            room_id = self._extract_room_id_from_html(html)
            if room_id:
                return room_id
            if 'live.douyin.com/' in url:
                tail = url.rstrip('/').split('/')[-1].split('?')[0]
                if tail.isdigit():
                    return tail
        raise RuntimeError('无法解析 room_id，请直接填写直播间数字 ID')

    async def _fetch_wss_url(self, http: ClientSession):
        page_url = f'https://live.douyin.com/{self.room_id}'
        hdrs = {'User-Agent': USER_AGENT, 'Cookie': self._cookie_header()}
        async with http.get(page_url, headers=hdrs,
                            proxy=self.cfg.http_proxy or None,
                            allow_redirects=True) as r:
            for ck in r.cookies.values():
                self._cookies[ck.key] = ck.value
            text = await r.text()

        parsed_room = self._extract_room_id_from_html(text)
        if parsed_room and parsed_room != self.room_id:
            _log.info('页面解析到真实 room_id=%s（原输入=%s）', parsed_room, self.room_id)
            self.room_id = parsed_room

        parsed_user_id = self._extract_user_unique_id_from_html(text)
        if parsed_user_id:
            self.cfg.user_unique_id = parsed_user_id

        metadata = self._extract_room_metadata_from_html(text)
        self.title = metadata.get('title') or self.title
        self.description = metadata.get('description') or self.description
        self.anchor = metadata.get('anchor') or self.anchor
        self.anchor_id = metadata.get('anchor_id') or self.anchor_id
        self.sec_anchor_id = metadata.get('sec_anchor_id') or self.sec_anchor_id
        self.anchor_avatar = metadata.get('avatar') or self.anchor_avatar
        if metadata:
            self._emit({
                'ts': _now_ms(),
                'seq': self.seq,
                'method': 'LiveMngRoomInfo',
                'msg_id': '',
                'parsed': {
                    'roomId': self.room_id,
                    'liveId': self.live_id,
                    'title': self.title,
                    'description': self.description,
                    'cover': self.cover,
                    'anchor': self.anchor,
                    'avatar': self.anchor_avatar,
                    'anchorId': self.anchor_id,
                    'secAnchorId': self.sec_anchor_id,
                },
            })

        wss_url = self._extract_wss_from_html(text)
        if not wss_url:
            sig = ''
            m = re.search(r'["\']signature["\']\s*[:=]\s*["\']([^"\']+)["\']', text)
            if m:
                sig = m.group(1)
            wss_url = self._build_direct_wss_url(sig)

        title, anchor = self.title, self.anchor
        _log.info('wss host=%s', urllib.parse.urlparse(wss_url).netloc)
        return wss_url, title, anchor

    async def _fetch_room_info(self, http: ClientSession):
        url = (
            'https://live.douyin.com/webcast/room/web/enter/?'
            'aid=6383&app_name=douyin_web&live_id=1&device_platform=web&'
            'language=zh-CN&enter_from=web_live&room_id=' + self.room_id
        )
        hdrs = {'User-Agent': USER_AGENT, 'Cookie': self._cookie_header(),
                'Referer': f'https://live.douyin.com/{self.room_id}'}
        try:
            async with http.get(url, headers=hdrs,
                                proxy=self.cfg.http_proxy or None, timeout=5) as r:
                data = await r.json(content_type=None)
            info = _extract_room_enter_info(data, self.room_id)
            if not info.get('roomExists') and info.get('statusCode'):
                _log.debug('room_info request rejected status=%s; waiting for signed room monitor', info.get('statusCode'))
                return
            if info.get('title'):
                self.title = info['title']
            if info.get('description'):
                self.description = info['description']
            self.live_id = info.get('liveId') or self.live_id
            self.cover = info.get('cover') or self.cover
            self.anchor = info.get('anchor') or self.anchor
            self.anchor_id = info.get('anchorId') or self.anchor_id
            self.sec_anchor_id = info.get('secAnchorId') or self.sec_anchor_id
            self.anchor_avatar = info.get('avatar') or self.anchor_avatar
            self._emit({
                'ts': _now_ms(),
                'seq': self.seq,
                'method': 'LiveMngRoomInfo',
                'msg_id': '',
                'parsed': {
                    **info,
                    'roomId': self.room_id,
                    'title': self.title,
                    'description': self.description,
                    'anchor': self.anchor,
                    'avatar': self.anchor_avatar,
                    'anchorId': self.anchor_id,
                    'secAnchorId': self.sec_anchor_id,
                    'liveId': self.live_id,
                    'cover': self.cover,
                },
            })
        except Exception as e:
            _log.debug('获取 room_info 失败（忽略）：%s', e)

    async def _fetch_signed_urls(self, http: ClientSession) -> tuple[str, str]:
        ms_token = await request_ms_token(
            http,
            ttwid=self._cookie_value('ttwid'),
            proxy=self.cfg.http_proxy or None,
        )
        if not ms_token:
            _log.warning('pure signing did not return an msToken; using compatibility transport')
            return '', ''
        fetch_url = build_signed_fetch_url(
            room_id=self.room_id,
            user_unique_id=self._user_unique_id(),
            ms_token=ms_token,
        )
        audience_url = ''
        if self.anchor_id and self.sec_anchor_id:
            audience_url = build_signed_audience_url(
                room_id=self.room_id,
                anchor_id=self.anchor_id,
                sec_anchor_id=self.sec_anchor_id,
                ms_token=ms_token,
            )
        return fetch_url, audience_url

    async def _fetch_audience_rank(self, http: ClientSession, audience_url: str) -> None:
        headers = self._build_headers()
        headers['User-Agent'] = signing_user_agent()
        async with http.get(
            audience_url,
            headers=headers,
            proxy=self.cfg.http_proxy or None,
        ) as response:
            data = await response.json(content_type=None)
            if not isinstance(data, dict):
                raise RuntimeError('audience endpoint returned an invalid response')
            if response.status >= 400 or data.get('status_code') not in (None, 0):
                raise RuntimeError(f'audience endpoint returned HTTP {response.status}')
        self._emit({
            'ts': _now_ms(),
            'seq': self.seq,
            'method': 'WebcastAudienceRankList',
            'msg_id': '',
            'url': 'https://live.douyin.com/webcast/ranklist/audience/',
            'parsed': data,
        })
        ranks = (data.get('data') or {}).get('ranks') or []
        _log.info('audience_rank_list ranks=%s via signed fetch', len(ranks))

    async def _poll_audience_rank(self, audience_url: str) -> None:
        interval = max(5.0, float(self.cfg.audience_poll_interval or 15.0))
        current_url = audience_url
        timeout = aiohttp.ClientTimeout(total=20, connect=8)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            while not self._stop:
                await asyncio.sleep(interval)
                if self._stop:
                    break
                try:
                    await self._fetch_audience_rank(http, current_url)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    _log.warning('audience rank poll failed; refreshing signature: %s', error)
                    try:
                        _, refreshed_url = await self._fetch_signed_urls(http)
                        if not refreshed_url:
                            continue
                        current_url = refreshed_url
                        await self._fetch_audience_rank(http, current_url)
                    except asyncio.CancelledError:
                        raise
                    except Exception as retry_error:
                        _log.warning('audience rank poll retry failed: %s', retry_error)

    # ---------- wss ----------
    def _build_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': USER_AGENT,
            'Cookie': self._cookie_header(),
            'Origin': 'https://live.douyin.com',
            'Referer': f'https://live.douyin.com/{self.room_id}',
            'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
        }

    async def _send_heartbeat_loop(self):
        while not self._stop:
            try:
                if self._ws is not None:
                    await self._ws.send(build_heartbeat_frame())
            except Exception as e:
                _log.debug('心跳发送失败: %s', e)
            await asyncio.sleep(self.cfg.heartbeat_interval)

    async def _send_ack(self, internal_ext: str):
        if self._ws is None or not internal_ext:
            return
        try:
            await self._ws.send(build_ack_frame(internal_ext))
        except Exception:
            pass

    async def _bootstrap_dynamic_transport(self) -> tuple[str, str]:
        """Resolve current browser-generated transport values, then close the browser."""
        if self._bootstrap_attempted or not self.cfg.bootstrap_browser:
            return '', ''
        self._bootstrap_attempted = True
        try:
            from Doubao.client.browser_client import DouyinBrowserClient
        except ImportError:
            _log.warning('browser compatibility client is unavailable; direct WSS cannot bootstrap dynamic parameters')
            return '', ''

        bootstrap_cfg = ClientConfig(**asdict(self.cfg))
        bootstrap_cfg.reconnect = False
        bootstrap_cfg.browser_headless = True
        bootstrap_cfg.browser_block_media = False
        bootstrap_cfg.browser_auto_visible_fallback = False
        bootstrap_cfg.browser_wss_timeout = 10
        bootstrap = DouyinBrowserClient(bootstrap_cfg)

        def forward(record):
            if record.get('method') == 'WebcastAudienceRankList':
                query = urllib.parse.parse_qs(urllib.parse.urlparse(record.get('url') or '').query)
                rank_room_id = (query.get('room_id') or [''])[0]
                if rank_room_id:
                    self.room_id = rank_room_id
            self._emit(record)

        bootstrap.on_message(forward)
        try:
            await asyncio.wait_for(bootstrap.connect_and_run(), timeout=22)
        except asyncio.TimeoutError:
            pass
        except Exception as error:
            _log.info('headless transport bootstrap ended: %s', error)
        finally:
            wss_url = getattr(bootstrap, '_last_wss_url', '')
            fetch_url = getattr(bootstrap, '_last_fetch_url', '')
            self.room_id = bootstrap.room_id or self.room_id
            self.title = bootstrap.title or self.title
            self.anchor = bootstrap.anchor or self.anchor
            await bootstrap.shutdown()
        if wss_url:
            _log.info('resolved dynamic WSS host=%s', urllib.parse.urlparse(wss_url).netloc)
        if fetch_url:
            _log.info('resolved dynamic fetch endpoint host=%s', urllib.parse.urlparse(fetch_url).netloc)
        return wss_url, fetch_url

    def _decode_response(self, raw_resp: bytes):
        """gzip 解压后解析 Response protobuf。"""
        data = unzip_response(raw_resp)
        if not data or self._response_cls is None:
            return None
        resp = self._response_cls()
        try:
            resp.ParseFromString(data)
        except Exception:
            # 某些数据帧没有经过 gzip 且本身不是 Response（可能是嵌套 PushFrame）
            return None
        return resp

    def _decode_responses(self, raw: bytes):
        resp = self._decode_response(raw)
        if resp is not None:
            yield resp
            return

        if self._push_frame_cls is not None:
            frame = self._push_frame_cls()
            try:
                frame.ParseFromString(raw)
            except Exception:
                frame = None
            if frame is not None and getattr(frame, 'payload', b''):
                payload = getattr(frame, 'payload', b'') or b''
                resp = self._decode_response(payload)
                if resp is not None:
                    yield resp
                    return
                yield from self._decode_payload_in_im(payload)

        yield from self._decode_payload_in_im(raw)

    def _decode_payload_in_im(self, raw: bytes):
        if self._payload_in_im_cls is None:
            return
        data = unzip_response(raw)
        obj = self._payload_in_im_cls()
        try:
            obj.ParseFromString(data)
        except Exception:
            return
        payloads = getattr(obj, 'payloads', {}) or {}
        for payload in payloads.values():
            resp = self._decode_response(payload)
            if resp is not None:
                yield resp

    def _handle_response(self, resp):
        if getattr(resp, 'cursor', ''):
            self._cursor = resp.cursor
        ie = getattr(resp, 'internalExt', '') or ''
        if ie:
            self._internal_ext = ie
            asyncio.ensure_future(self._send_ack(ie))
        for msg in resp.messages:
            method = msg.method
            payload = msg.payload
            msg_id = int(getattr(msg, 'msgId', 0) or 0)
            if self._is_duplicate_message(method, msg_id):
                _log.debug('skip duplicate %s msg_id=%s', method, msg_id)
                continue
            self.seq += 1
            raw_file = ''
            if self.saver:
                raw_file = self.saver.save_raw(method, msg_id, self.seq, payload)
            parsed = self._parse_message(method, payload)
            rec = {
                'ts': _now_ms(),
                'seq': self.seq, 'method': method, 'msg_id': msg_id,
                'parsed': parsed,
            }
            if self.saver:
                if raw_file:
                    rec['rawproto_file'] = raw_file
                rec['json_file'] = self.saver.save_json(method, msg_id, self.seq, rec)
                self.saver.save_parsed(rec)
            self._emit(rec)
            brief = self._brief(rec)
            if brief:
                _log.info(brief)

    def _parse_message(self, method: str, payload: bytes):
        pb_cls = self._parser._class_index.get(method)
        if pb_cls is None:
            return {'_raw_len': len(payload), '_unknown': True}
        # 处理 gzip 压缩的 payload
        data = payload
        if data[:2] == b"\x1f\x8b":
            try:
                import gzip as _gzip
                data = _gzip.decompress(data)
            except Exception:
                data = payload
        try:
            msg = pb_cls()
            msg.ParseFromString(data)
            parsed = json_format.MessageToDict(
                msg, preserving_proto_field_name=True,
                use_integers_for_enums=True,
            )
            # 统一处理图片 URL 粘连切分
            self._parser._normalize_embedded_image_urls(parsed)
            # 补充徽章摘要
            self._parser._attach_badge_summary(parsed)
            return parsed
        except Exception as e:
            err_str = str(e)
            if 'bad UTF-8' in err_str or 'UTF-8' in err_str:
                try:
                    sanitized = _sanitize_proto_strings(data)
                    msg2 = pb_cls()
                    msg2.ParseFromString(sanitized)
                    parsed = json_format.MessageToDict(
                        msg2, preserving_proto_field_name=True,
                        use_integers_for_enums=True,
                    )
                    self._parser._normalize_embedded_image_urls(parsed)
                    self._parser._attach_badge_summary(parsed)
                    return parsed
                except Exception:
                    pass
            if method == 'WebcastEmojiChatMessage':
                try:
                    parsed = _parse_emoji_fallback(pb_cls, data)
                    self._parser._normalize_embedded_image_urls(parsed)
                    self._parser._attach_badge_summary(parsed)
                    return parsed
                except Exception:
                    pass
            return {'_raw_len': len(payload), '_error': str(e)}

    @staticmethod
    def _normalize_embedded_image_urls(value):
        if isinstance(value, dict):
            urls = value.get('urlList')
            if isinstance(urls, list) and len(urls) == 1 and isinstance(urls[0], str):
                found = re.findall(r'https?://[^\x00-\x20\x12\x1a\*]+', urls[0])
                if found:
                    value['urlList'] = found
            for child in value.values():
                DouyinWssClient._normalize_embedded_image_urls(child)
        elif isinstance(value, list):
            for child in value:
                DouyinWssClient._normalize_embedded_image_urls(child)

    @staticmethod
    def _brief(rec: dict):
        method = rec.get('method', '')
        p = rec.get('parsed') or {}
        if p.get('_error'):
            return f'- {method} parse_error={p["_error"]}'
        if method == 'WebcastChatMessage':
            u = p.get('user') or {}
            return f'chat {u.get("nickname", u.get("nickName", "?"))}: {p.get("content", "")}'
        if method == 'WebcastEmojiChatMessage':
            u = p.get('user') or {}
            return f'emoji_chat {u.get("nickname", u.get("nickName", "?"))}: {p.get("content", "[表情]")}'
        if method == 'WebcastLikeMessage':
            return f'like x{p.get("count", 0)}'
        if method == 'WebcastGiftMessage':
            g = p.get('gift') or {}
            gs = p.get('giftStruct') or {}
            u = p.get('user') or {}
            combo = p.get('comboCount') or p.get('repeatCount') or 1
            name = g.get("name") or gs.get("name") or "?"
            return f'gift {u.get("nickname", u.get("nickName", "?"))} -> {name} x{combo}'
        if method == 'WebcastMemberMessage':
            u = p.get('user') or {}
            return f'enter {u.get("nickname", u.get("nickName", "?"))}'
        if method == 'WebcastRoomRankMessage':
            return (
                f'room_rank ranks={len(p.get("ranks") or [])} '
                f'audience={len(p.get("audienceRanks") or [])}'
            )
        if method == 'WebcastRoomUserSeqMessage':
            return f'room_user_seq online={p.get("total") or p.get("onlineUserForAnchor") or 0} ranks={len(p.get("ranks") or [])}'
        if method == 'WebcastSocialMessage':
            u = p.get('user') or {}
            share = p.get('shareType', 0)
            action = 'share' if share else f'action={p.get("action", 0)}'
            return f'social {u.get("nickname", u.get("nickName", "?"))} {action}'
        if method == 'WebcastChatLikeMessage':
            cnt = sum(
                _to_int((entry.get('meta') or {}).get('count'), 1)
                for entry in (p.get('likes') or [])
                if isinstance(entry, dict)
            )
            return f'chat_like bulk={len(p.get("likes") or [])} total={cnt}'
        if method == 'WebcastRoomDataSyncMessage':
            return f'room_sync type={p.get("dataType", "")}'
        if method == 'WebcastRoomStatsMessage':
            return (f'stats online={p.get("roomUserCount", 0)} '
                    f'total={p.get("totalUser", 0)} like={p.get("likeCount", 0)}')
        if method == 'WebcastFansclubMessage':
            u = p.get('user') or {}
            return f'fansclub {u.get("nickname", u.get("nickName", "?"))} Lv{p.get("level", 0)}'
        if method == 'WebcastInRoomBannerMessage':
            return f'banner {_short(p.get("title", ""), 40)}'
        if method == 'WebcastGiftBannerMessage':
            return f'gift_banner {_short(p.get("title", ""), 40)}'
        if method == 'WebcastTeamPlayTeamInfoMessage':
            return (f'team_play battle={p.get("battleIdStr", "")} '
                    f'status={p.get("status", 0)}')
        if method == 'WebcastGameIntroduceMessage':
            return f'game_intro {_short(p.get("gameName", ""), 40)}'
        if method == 'WebcastGameCPBaseMessage':
            return f'game_cp cpType={p.get("cpType", 0)}'
        if method == 'WebcastRanklistHourEntranceMessage':
            return f'rank_entrance {_short(p.get("title", ""), 40)}'
        if method == 'WebcastTaskCenterEntranceMessage':
            return f'task_center payload={len(p.get("jsonPayload", "") or "")} bytes'
        if method == 'WebcastNotifyEffectMessage':
            tpl = ((p.get('template') or {}).get('key', '')
                   if isinstance(p.get('template'), dict) else '')
            return f'notify_effect {_short(tpl, 40)}'
        if method == 'WebcastEffectInteractMessage':
            return f'effect_interact type={p.get("effectType", 0)}'
        return f'{method} msg_id={rec.get("msg_id")}'

    async def _handle_ws_bytes(self, raw: bytes):
        decoded = False
        for payload, ptype, _compression in parse_wss_message(raw):
            if ptype == 'hb':
                continue
            if ptype not in ('resp', 'push', 'unknown'):
                continue
            for resp in self._decode_responses(payload):
                decoded = True
                self._handle_response(resp)
        if not decoded:
            for resp in self._decode_responses(raw):
                decoded = True
                self._handle_response(resp)
        if not decoded:
            _log.debug('skip non-response websocket frame len=%s', len(raw))

    async def _consume_wss(self, wss_url: str):
        ssl_ctx = ssl.create_default_context()
        headers = self._build_headers()
        connect_kwargs = {
            'extra_headers': headers,
            'ssl': ssl_ctx,
            'ping_interval': None,
            'max_size': None,
            'compression': None,
        }
        if self.cfg.ws_proxy:
            _log.warning('ws_proxy is configured but websockets does not expose a stable proxy option here; ignoring it')

        async with websockets.connect(wss_url, **connect_kwargs) as ws:
            self._ws = ws
            self._hb_task = asyncio.create_task(self._send_heartbeat_loop())
            _log.info('__STATUS__:connected')
            _log.info('connected room=%s title=%s anchor=%s', self.room_id, self.title, self.anchor)
            try:
                async for raw in ws:
                    if self._stop:
                        break
                    if isinstance(raw, str):
                        _log.debug('text frame len=%s', len(raw))
                        continue
                    await self._handle_ws_bytes(raw)
            finally:
                if self._hb_task:
                    self._hb_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._hb_task
                self._hb_task = None
                self._ws = None

    async def _consume_fetch(self, fetch_url: str, fail_fast: bool = False):
        """Consume the browser page's protobuf long-poll endpoint without a browser."""
        parsed = urllib.parse.urlparse(fetch_url)
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        headers = self._build_headers()
        timeout = aiohttp.ClientTimeout(total=35, connect=10)
        connected = False
        async with aiohttp.ClientSession(timeout=timeout) as http:
            while not self._stop:
                query = urllib.parse.urlencode(params, doseq=True)
                url = urllib.parse.urlunparse(parsed._replace(query=query))
                try:
                    async with http.get(url, headers=headers, proxy=self.cfg.http_proxy or None) as response:
                        body = await response.read()
                        if response.status >= 400:
                            raise RuntimeError(f'fetch endpoint returned HTTP {response.status}')
                    if fail_fast and not connected and not body:
                        raise RuntimeError('signed fetch endpoint returned an empty response')
                    if body:
                        if not connected:
                            _log.info('__STATUS__:connected')
                            _log.info('connected via signed fetch room=%s', self.room_id)
                        connected = True
                        await self._handle_ws_bytes(body)
                        if self._cursor:
                            params['cursor'] = [self._cursor]
                        if self._internal_ext:
                            params['internal_ext'] = [self._internal_ext]
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    if self._stop:
                        break
                    if fail_fast and not connected:
                        raise
                    _log.warning('fetch poll error: %s', error)
                    await asyncio.sleep(self.cfg.reconnect_delay)
                else:
                    await asyncio.sleep(0.1)

    async def _run_once(self):
        timeout = aiohttp.ClientTimeout(total=30)
        signed_fetch_url = ''
        signed_audience_url = ''
        async with aiohttp.ClientSession(timeout=timeout) as http:
            await self._ensure_login(http)
            self.room_id = await self._resolve_room(http)
            await self._fetch_room_info(http)
            wss_url, title, anchor = await self._fetch_wss_url(http)
            self.title = title or self.title
            self.anchor = anchor or self.anchor
            try:
                signed_fetch_url, signed_audience_url = await self._fetch_signed_urls(http)
                if signed_audience_url:
                    await self._fetch_audience_rank(http, signed_audience_url)
            except Exception as error:
                _log.warning('pure signed fetch setup failed: %s', error)

        self.saver = SessionSaver(
            self.cfg, self.room_id, self.title, self.live_id, self.anchor,
            self.anchor_id, self.sec_anchor_id,
        )
        _log.info('session dir=%s', self.saver.session_dir)
        if signed_audience_url and self.cfg.audience_poll_interval > 0:
            self._audience_task = asyncio.create_task(
                self._poll_audience_rank(signed_audience_url),
                name='douyin-audience-rank-poll',
            )

        try:
            if signed_fetch_url:
                try:
                    await self._consume_fetch(signed_fetch_url, fail_fast=True)
                    return
                except Exception as error:
                    _log.warning('pure signed fetch unavailable; using compatibility transport: %s', error)

            try:
                await self._consume_wss(wss_url)
            except Exception as error:
                if 'HTTP 200' not in str(error) or self._bootstrap_attempted:
                    raise
                fallback_wss, fallback_fetch = await self._bootstrap_dynamic_transport()
                if fallback_wss:
                    await self._consume_wss(fallback_wss)
                    return
                if fallback_fetch:
                    await self._consume_fetch(fallback_fetch)
                    return
                if not fallback_wss and not fallback_fetch:
                    raise
        finally:
            if self._audience_task:
                self._audience_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._audience_task
                self._audience_task = None

    async def connect_and_run(self):
        attempt = 0
        self._bootstrap_attempted = False
        try:
            while not self._stop:
                try:
                    await self._run_once()
                    if not self.cfg.reconnect or self._stop:
                        break
                    attempt = 0
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    attempt += 1
                    if not self.cfg.reconnect or attempt > self.cfg.reconnect_max:
                        raise
                    _log.warning('connect loop error (%s/%s): %s', attempt, self.cfg.reconnect_max, e)
                    _log.info('__STATUS__:reconnect')
                    await asyncio.sleep(self.cfg.reconnect_delay)
        finally:
            self._stop = True
            if self.saver:
                self.saver.close()
                self.saver = None
            _log.info('__STATUS__:stopped')

    def stop(self):
        self._stop = True


def main():
    import argparse

    ap = argparse.ArgumentParser(description='Doubao Douyin live WSS listener')
    ap.add_argument('--config', default='', help='path to config json')
    ap.add_argument('--room-id', default='', help='numeric live room id')
    ap.add_argument('--room-url', default='', help='live.douyin.com room url')
    ap.add_argument('--cookie', default='', help='Cookie header')
    ap.add_argument('--output-dir', default='', help='session output directory')
    ap.add_argument('--no-auto-login', action='store_true', help='disable QR login fallback')
    args = ap.parse_args()

    cfg = ClientConfig.from_file(args.config) if args.config else ClientConfig()
    if args.room_id:
        cfg.room_id = args.room_id
    if args.room_url:
        cfg.room_url = args.room_url
    if args.cookie:
        cfg.cookie = args.cookie
    if args.output_dir:
        cfg.output_dir = args.output_dir
    if args.no_auto_login:
        cfg.auto_login = False

    client = DouyinWssClient(cfg)
    asyncio.run(client.connect_and_run())


if __name__ == '__main__':
    main()


