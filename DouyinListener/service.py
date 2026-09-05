"""Headless HTTP/WebSocket service for the Doubao listener core."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import urllib.parse
import zipfile
from collections import deque
from datetime import datetime
from copy import deepcopy
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

from Doubao.client.browser_client import (
    DouyinBrowserClient,
    browser_login_cookie_header,
    load_saved_cookie_header,
)
from Doubao.client.wss_client import ClientConfig, DouyinWssClient
from Doubao.core.parser import DoubaoParser
from event_store import EventStore
from emoji_assets import refresh_emoji_cache
from fan_database import FanDatabaseRegistry
from gift_assets import GiftAssetCatalog
from live_captions import LiveCaptionCapture
from profile_client import ProfileClient
from protocol_audit import build_protocol_audit
from room_status import RoomStatusProbe
from spark_service import SparkManager
from speech_services import DEFAULT_SPEECH_CONFIG, SpeechServiceError, SpeechServices, normalize_speech_config
from speech_model_manager import SpeechModelManager
from subtitle_pipeline import SubtitlePipeline


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "data" / "config.json"
DEFAULT_CONFIG = {
    "roomId": "190215200850",
    "roomUrl": "",
    "transport": "wss",
    "bootstrapBrowser": True,
    "monitorEnabled": True,
    "autoStart": False,
    "roomStatusPollInterval": 30,
    "browserHeadless": True,
    "browserBlockMedia": True,
    "browserVisibleFallback": False,
    "reconnect": True,
    "reconnectMax": 10,
    "reconnectDelay": 3,
    "audiencePollInterval": 15,
    "musicBot": {
        "enabled": True,
        "commandUrl": "http://127.0.0.1:7001/api/integrations/danmaku/command",
        "timeoutSeconds": 2,
    },
    "saveRaw": False,
    "saveParsed": True,
    "liveCaptions": {
        "enabled": False,
        "outputToLiveUi": True,
        "persist": False,
        "fallbackEnabled": False,
        "fallbackTimeoutSeconds": 300,
        "showIdleOnTimeout": False,
    },
    "speech": DEFAULT_SPEECH_CONFIG,
    "giftAssets": {
        "enabled": True,
        "refreshHours": 24,
        "storagePath": "data/gift_assets",
        "cacheGiftIcons": True,
        "cacheEffects": True,
    },
    "display": {
        "entryFilters": {"consumer": 0, "followers": True, "fansClub": True, "member": True, "guard": True},
        "likeMode": "aggregate",
        "giftEffects": True,
        "scoreMode": "single",
    },
}


def load_config() -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                config.update({key: value for key, value in saved.items() if key not in {"display", "liveCaptions", "giftAssets", "speech"}})
                if isinstance(saved.get("display"), dict):
                    config["display"].update(saved["display"])
                if isinstance(saved.get("liveCaptions"), dict):
                    config["liveCaptions"].update(saved["liveCaptions"])
                if isinstance(saved.get("giftAssets"), dict):
                    config["giftAssets"].update(saved["giftAssets"])
                config["speech"] = normalize_speech_config(saved.get("speech"))
        except (OSError, json.JSONDecodeError):
            logging.exception("Failed to read listener config")
    return config


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = CONFIG_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(CONFIG_PATH)


def gift_asset_storage_root(value: Any) -> Path:
    raw_path = str(value or "data/gift_assets").strip()
    if not raw_path:
        raise ValueError("Gift asset storage path cannot be empty")
    path = Path(raw_path).expanduser()
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("Gift asset storage path must be a directory")
    return resolved


SESSION_ROOT = ROOT / "data" / "sessions"
REPLAY_KINDS = {"chat", "like", "score", "enter", "follow", "gift", "membership", "fansclub", "redPacket", "luckyBag", "room", "audience"}
REPLAY_TIMELINE_LIMIT = 30000
REPLAY_METHODS = {
    "LiveMngRoomInfo", "WebcastAudioChatMessage", "WebcastExhibitionChatMessage",
    "WebcastChatMessage", "WebcastEmojiChatMessage", "ActivityEmojiGroupsMessage", "WebcastLikeMessage",
    "WebcastChatLikeMessage", "WebcastGiftMessage", "WebcastMemberMessage",
    "WebcastVipEnterMessage", "WebcastNobleEnterMessage", "WebcastRoomIntroMessage",
    "WebcastLuckyBoxMessage", "WebcastLuckyBoxRewardMessage", "WebcastLuckyBoxTempStatusMessage",
    "WebcastXGLotteryMessage",
    "WebcastLotteryEventNewMessage", "WebcastLotteryCandidateEventMessage", "WebcastLotteryDrawResultEventMessage",
    "WebcastLuckyBoxEndMessage", "WebcastPreviewCjRpMessage", "WebcastPrizeNoticeMessage",
    "WebcastSocialMessage", "WebcastProfitInteractionMessage", "WebcastFansclubMessage",
    "WebcastSubscriptionMessage", "WebcastSpecialMemberMessage",
    "WebcastMemberSpecialTipMessage", "WebcastStarGuardInfoMessage",
    "WebcastStarGuardMessage", "WebcastGuardPickUpMessage", "WebcastMemberClubEntranceMessage",
    "WebcastResidentGuestMessage", "WebcastNobleMessage", "WebcastRoomMessage",
    "WebcastRoomNotifyMessage", "WebcastNotifyEffectMessage",
    "WebcastTaskCenterEntranceMessage", "WebcastRoomDataSyncMessage",
    "WebcastRoomUserSeqMessage", "WebcastRoomRankMessage", "WebcastAudienceRankList",
    "WebcastContributionMessage", "WebcastRanklistMessage", "WebcastRoomStatsMessage",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def should_verify_room_page(status: dict, poll_interval: int, now_ms: int) -> bool:
    if str(status.get("roomState") or "unknown") != "live":
        return False
    last_event_at = int(status.get("lastEventAt") or 0)
    stale_after_ms = max(60_000, int(poll_interval) * 2_000)
    return not last_event_at or now_ms - last_event_at >= stale_after_ms


def _session_start_ms(session_id: str) -> int:
    try:
        return int(datetime.strptime(session_id[:15], "%Y%m%d_%H%M%S").timestamp() * 1000)
    except (TypeError, ValueError, OSError):
        return 0


def _replay_session_id(path: Path) -> str:
    try:
        relative = path.parent.relative_to(SESSION_ROOT)
    except ValueError:
        return path.parent.name
    parts = relative.parts
    if len(parts) <= 1:
        return path.parent.name
    return "::".join(parts)


def _replay_session_path(session_id: str) -> Path:
    if not session_id or session_id != Path(session_id).name and "::" not in session_id:
        raise ValueError("无效的回放场次")
    if "::" in session_id:
        parts = [part for part in session_id.split("::") if part]
        if not parts or any(part != Path(part).name for part in parts):
            raise ValueError("无效的回放场次")
        return SESSION_ROOT.joinpath(*parts) / "parsed.jsonl"
    return SESSION_ROOT / session_id / "parsed.jsonl"


def _iter_replay_paths() -> list[Path]:
    if not SESSION_ROOT.exists():
        return []
    return sorted(
        SESSION_ROOT.glob("**/parsed.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _scan_replay_session(path: Path, fast: bool = False) -> dict:
    session_id = _replay_session_id(path)
    methods: dict[str, int] = {}
    first_ts = 0
    last_ts = 0
    event_count = 0
    parse_errors = 0
    room_id = ""
    title = ""
    metadata = {}
    metadata_path = path.parent / "session.json"
    try:
        loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        metadata = {}
    file_size = path.stat().st_size if path.exists() else 0
    full_scan = file_size <= 5 * 1024 * 1024
    scan_limit = None if full_scan else 1200
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream):
                if scan_limit is not None and line_number >= scan_limit:
                    break
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    parse_errors += 1
                    continue
                method = str(record.get("method") or "unknown")
                methods[method] = methods.get(method, 0) + 1
                event_count += 1
                timestamp = int(record.get("ts") or 0)
                first_ts = timestamp if not first_ts else min(first_ts, timestamp)
                last_ts = max(last_ts, timestamp)
                parsed = record.get("parsed") or {}
                if isinstance(parsed, dict):
                    common = parsed.get("common") or {}
                    room_id = room_id or str(common.get("roomId") or parsed.get("roomId") or "")
                    title = title or str(parsed.get("title") or "")
                    if parsed.get("_error"):
                        parse_errors += 1
    except OSError:
        parse_errors += 1
    estimated = False
    if scan_limit is not None:
        estimated = True
        saved_count = _safe_int(metadata.get("eventCount"))
        event_count = saved_count or max(scan_limit, int(file_size / 420))
    return {
        "id": session_id,
        "roomId": room_id,
        "roomKey": str(metadata.get("roomKey") or metadata.get("secAnchorId") or metadata.get("anchorId") or room_id),
        "roomName": str(metadata.get("roomName") or metadata.get("anchor") or ""),
        "liveId": str(metadata.get("liveId") or metadata.get("sessionId") or ""),
        "title": title or str(metadata.get("roomTitle") or "未命名直播场次"),
        "sessionName": str(metadata.get("sessionName") or path.parent.name),
        "anchor": str(metadata.get("anchor") or ""),
        "startAt": first_ts or _session_start_ms(session_id),
        "endAt": last_ts or first_ts or _session_start_ms(session_id),
        "eventCount": event_count,
        "eventCountEstimated": estimated,
        "parseErrors": parse_errors,
        "methods": dict(sorted(methods.items(), key=lambda item: item[1], reverse=True)[:8]),
        "source": "parsed.jsonl",
    }


def list_replay_sessions(limit: int = 100) -> list[dict]:
    paths = _iter_replay_paths()[: max(1, min(limit, 200))]
    return [_scan_replay_session(path, fast=True) for path in paths]


def load_replay_session(session_id: str) -> dict:
    path = _replay_session_path(session_id)
    if not path.is_file():
        raise FileNotFoundError("回放场次不存在")

    store = EventStore(limit=30000)
    replay_parser = None
    timeline = deque(maxlen=REPLAY_TIMELINE_LIMIT)
    raw_event_count = 0
    parse_errors = 0
    first_ts = 0
    last_ts = 0
    summary = _scan_replay_session(path, fast=True)
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            raw_event_count += 1
            timestamp = int(record.get("ts") or 0)
            first_ts = timestamp if not first_ts else min(first_ts, timestamp)
            last_ts = max(last_ts, timestamp)
            if str(record.get("method") or "") not in REPLAY_METHODS:
                continue
            parsed = record.get("parsed")
            if str(record.get("method") or "") == "WebcastNotifyEffectMessage" and isinstance(parsed, dict):
                replay_parser = replay_parser or DoubaoParser()
                record["parsed"] = replay_parser.enrich_parsed("WebcastNotifyEffectMessage", parsed)
            event = store.apply(record)
            if event and event.get("kind") in REPLAY_KINDS:
                timeline.append(deepcopy(event))
    summary.update({
        "eventCount": raw_event_count or summary.get("eventCount", 0),
        "startAt": first_ts or summary.get("startAt", 0),
        "endAt": last_ts or summary.get("endAt", 0),
        "parseErrors": parse_errors,
        "timelineCount": len(timeline),
        "timelineTruncated": raw_event_count > len(timeline),
    })
    snapshot = store.snapshot()
    if not snapshot["room"].get("id"):
        snapshot["room"]["id"] = summary["roomId"]
    if not snapshot["room"].get("title") or snapshot["room"]["title"] == "等待连接直播间":
        snapshot["room"]["title"] = summary["title"]
    timeline = sorted(timeline, key=lambda event: int(event.get("ts") or 0))
    return {
        "session": summary,
        "room": snapshot["room"],
        "stats": snapshot["stats"],
        "events": timeline,
        "records": snapshot["records"],
    }


class ListenerManager:
    def __init__(self):
        self.config = load_config()
        self.store = EventStore()
        self.fans = FanDatabaseRegistry(ROOT / "data" / "fans")
        self.profile_client = ProfileClient()
        self.gift_assets = GiftAssetCatalog(gift_asset_storage_root(self.config["giftAssets"].get("storagePath")), lambda: self.config, lambda: self.store.room)
        self.spark = SparkManager()
        self.captions = LiveCaptionCapture(ROOT / "data" / "live_captions", self._schedule_caption_broadcast)
        self.speech = SpeechServices(ROOT, self.config.get("speech"))
        self.speech_models = SpeechModelManager(lambda: self.config, ROOT)
        self.subtitle_pipeline = SubtitlePipeline(lambda: self.config, self.speech, self._schedule_caption_broadcast)
        self.store.configure_room(self.config)
        self.client: DouyinWssClient | DouyinBrowserClient | None = None
        self.task: asyncio.Task | None = None
        self.room_probe = RoomStatusProbe()
        self.room_monitor_task: asyncio.Task | None = None
        self.room_probe_lock = asyncio.Lock()
        self.auto_start_paused = False
        saved_cookie = load_saved_cookie_header()
        self.login_task: asyncio.Task | None = None
        self.login_account_task: asyncio.Task | None = None
        self.gift_asset_sync_task: asyncio.Task | None = None
        self.login_state = {
            "state": "logged_in" if "sessionid=" in saved_cookie else "logged_out",
            "message": "已保存抖音登录态" if "sessionid=" in saved_cookie else "尚未登录抖音",
            "account": None,
            "accountLoading": "sessionid=" in saved_cookie,
        }
        self.sockets: set[web.WebSocketResponse] = set()
        self._pending_event_broadcast: dict | None = None
        self._event_broadcast_task: asyncio.Task | None = None
        self.musicbot_http: ClientSession | None = None

    def public_state(self) -> dict:
        state = self.store.snapshot()
        state["config"] = self.config
        state["login"] = self.login_state
        state["captions"] = self.captions.snapshot()
        state["speech"] = self.speech.status()
        state["speechCaptions"] = self.subtitle_pipeline.snapshot()
        state["giftAssets"] = {**self.gift_assets.public_state(), "storagePath": self.config["giftAssets"].get("storagePath", "data/gift_assets")}
        return state

    async def reconfigure_gift_assets(self, storage_path: str) -> None:
        root = gift_asset_storage_root(storage_path)
        if root == self.gift_assets.root.resolve():
            return
        if self.gift_asset_sync_task and not self.gift_asset_sync_task.done():
            self.gift_asset_sync_task.cancel()
            await asyncio.gather(self.gift_asset_sync_task, return_exceptions=True)
        await self.gift_assets.stop()
        self.gift_assets = GiftAssetCatalog(root, lambda: self.config, lambda: self.store.room)
        await self.gift_assets.start()

    def start_gift_asset_sync(self) -> tuple[bool, str]:
        if self.gift_asset_sync_task and not self.gift_asset_sync_task.done():
            return False, "礼物资产同步正在运行"

        async def runner() -> None:
            try:
                await self.gift_assets.sync()
            except Exception:
                logging.exception("Gift asset sync failed")
            finally:
                await self.broadcast({"kind": "gift_assets"})

        self.gift_asset_sync_task = asyncio.create_task(runner(), name="manual-douyin-gift-asset-sync")
        return True, "已开始同步官方礼物和特效资源"

    def _schedule_caption_broadcast(self) -> None:
        try:
            asyncio.get_running_loop().create_task(self.broadcast({"kind": "captions"}))
        except RuntimeError:
            pass

    async def broadcast(self, event: dict | None = None) -> None:
        if not self.sockets:
            return
        payload = {"type": "update", "event": event, "state": self.public_state()}
        stale = []
        for socket in self.sockets:
            try:
                await asyncio.wait_for(socket.send_json(payload), timeout=5)
            except (asyncio.TimeoutError, ConnectionResetError, RuntimeError):
                stale.append(socket)
        for socket in stale:
            self.sockets.discard(socket)

    def _schedule_event_broadcast(self, event: dict) -> None:
        """Coalesce high-frequency live events so slow clients cannot retain snapshots."""
        if not self.sockets:
            return
        self._pending_event_broadcast = event
        if self._event_broadcast_task is None or self._event_broadcast_task.done():
            self._event_broadcast_task = asyncio.create_task(
                self._drain_event_broadcasts(), name="douyin-event-broadcast"
            )

    async def _drain_event_broadcasts(self) -> None:
        while self._pending_event_broadcast is not None:
            event = self._pending_event_broadcast
            self._pending_event_broadcast = None
            await self.broadcast(event)

    def _handle_event(self, record: dict) -> None:
        event = self.store.apply(record)
        if self.client:
            configured_room_id = str(self.config.get("roomId") or "").strip()
            if configured_room_id:
                self.store.room["id"] = configured_room_id
            elif self.client.room_id:
                self.store.room["id"] = self.client.room_id
            if self.client.title:
                self.store.room["title"] = self.client.title
            if self.client.anchor:
                self.store.room["anchor"]["nickname"] = self.client.anchor
        if event:
            saver = getattr(self.client, "saver", None)
            session_id = str(getattr(saver, "session_key", "") or "")
            self.fans.get(self.store.room, self.config).observe_event(event, record, self.store.room, session_id)
            if event.get("method") == "WebcastChatMessage" and event.get("content"):
                self._schedule_musicbot_command(event)
            self._schedule_event_broadcast(event)

    def _schedule_musicbot_command(self, event: dict) -> None:
        config = self.config.get("musicBot") if isinstance(self.config.get("musicBot"), dict) else {}
        if config.get("enabled", True) is False:
            return
        if not self.musicbot_http or self.musicbot_http.closed:
            return
        user = event.get("user") if isinstance(event.get("user"), dict) else {}
        fans_club = user.get("fansClub") if isinstance(user.get("fansClub"), dict) else {}
        membership = user.get("membership") if isinstance(user.get("membership"), dict) else {}
        badges = user.get("badges") if isinstance(user.get("badges"), list) else []
        payload = {
            "text": str(event.get("content") or ""),
            "userId": str(user.get("id") or ""),
            "nickname": str(user.get("nickname") or "匿名观众"),
            "name": str(user.get("nickname") or "匿名观众"),
            "avatar": str(user.get("avatar") or ""),
            "douyinId": str(user.get("displayId") or ""),
            "roles": [role for role, enabled in (
                ("fan_group", bool(fans_club.get("level"))),
                ("member", bool(membership.get("opened"))),
                ("guardian", any(isinstance(b, dict) and b.get("type") == "guard" for b in badges)),
            ) if enabled],
            "badges": badges,
        }
        asyncio.create_task(self._send_musicbot_command(payload), name="douyin-musicbot-command")

    async def _send_musicbot_command(self, payload: dict) -> None:
        config = self.config.get("musicBot") if isinstance(self.config.get("musicBot"), dict) else {}
        url = str(config.get("commandUrl") or "").strip()
        if not url or not self.musicbot_http or self.musicbot_http.closed:
            return
        try:
            async with self.musicbot_http.post(url, json=payload) as response:
                if response.status >= 400:
                    logging.warning("MusicBot command rejected: HTTP %s", response.status)
        except Exception as error:
            logging.debug("MusicBot command delivery failed: %s", error)

    async def _probe_room_status(self) -> dict | None:
        room_id = str(self.config.get("roomId") or "").strip()
        if not room_id:
            room_url = str(self.config.get("roomUrl") or "").strip()
            room_id = room_url.rstrip("/").split("/")[-1].split("?", 1)[0]
        if not room_id:
            return None
        interval = max(10, min(300, int(self.config.get("roomStatusPollInterval", 30))))
        verify_page = should_verify_room_page(
            self.store.status,
            interval,
            int(datetime.now().timestamp() * 1000),
        )
        async with self.room_probe_lock:
            try:
                probe = await self.room_probe.probe(room_id, verify_page=verify_page)
            except Exception as error:
                logging.warning("Room status probe failed: %s", error)
                self.store.status.update({
                    "lastRoomCheckAt": int(datetime.now().timestamp() * 1000),
                    "roomStatusSource": "room_web_enter",
                })
                return None
        self.store.apply_room_status_probe(probe)
        await self.broadcast({"kind": "room_status", "state": self.store.status.get("roomState")})
        return probe

    async def ensure_room_monitor(self) -> None:
        if self.room_monitor_task and not self.room_monitor_task.done():
            return
        if not bool(self.config.get("monitorEnabled", True)):
            return
        if not (str(self.config.get("roomId") or "").strip() or str(self.config.get("roomUrl") or "").strip()):
            return
        self.room_monitor_task = asyncio.create_task(self._monitor_room_status(), name="douyin-room-status-monitor")

    async def _disable_room_monitor(self) -> None:
        self.auto_start_paused = True
        await self._stop_for_room_transition()
        await self._cancel_room_monitor_task()
        self.store.status.update({
            "state": "stopped",
            "roomState": "unknown",
            "message": "开播监控已关闭",
        })

    async def _cancel_room_monitor_task(self) -> None:
        task = self.room_monitor_task
        self.room_monitor_task = None
        if task and not task.done():
            task.cancel()
            if task is not asyncio.current_task():
                await asyncio.gather(task, return_exceptions=True)
        await self.room_probe.close()

    async def _stop_for_config_update(self) -> None:
        """Stop the old monitor and listener before applying a new live session."""
        self.auto_start_paused = True
        await self._cancel_room_monitor_task()
        await self._stop_for_room_transition()

    async def _monitor_room_status(self) -> None:
        while True:
            probe = await self._probe_room_status()
            room_state = str((probe or {}).get("roomState") or "unknown")
            if room_state in {"not_live", "ended", "not_found"} and self.task and not self.task.done():
                await self._stop_for_room_transition()
                if probe:
                    self.store.apply_room_status_probe(probe)
                    await self.broadcast({"kind": "room_status", "state": self.store.status.get("roomState")})
            elif room_state == "live" and bool(self.config.get("autoStart")) and not self.auto_start_paused:
                await self.start(skip_probe=True)
            interval = max(10, min(300, int(self.config.get("roomStatusPollInterval", 30))))
            await asyncio.sleep(interval)

    async def start(self, skip_probe: bool = False) -> tuple[bool, str]:
        if self.task and not self.task.done():
            return True, "监听已在运行"
        if not (str(self.config.get("roomId") or "").strip() or str(self.config.get("roomUrl") or "").strip()):
            return False, "请先配置直播间 URL 或房间号"

        await self.ensure_room_monitor()
        self.auto_start_paused = False
        if not skip_probe:
            probe = await self._probe_room_status()
            if probe and probe.get("roomState") != "live":
                return True, "直播间当前未开播，已开始监控"

        cfg = ClientConfig(
            room_id=str(self.config.get("roomId") or "").strip(),
            room_url=str(self.config.get("roomUrl") or "").strip(),
            output_dir=str(ROOT / "data" / "sessions"),
            save_raw=bool(self.config.get("saveRaw", False)),
            browser_headless=bool(self.config.get("browserHeadless", True)),
            browser_block_media=bool(self.config.get("browserBlockMedia", True)),
            browser_auto_visible_fallback=bool(self.config.get("browserVisibleFallback", False)),
            bootstrap_browser=bool(self.config.get("bootstrapBrowser", True)),
            reconnect=bool(self.config.get("reconnect", True)),
            reconnect_max=max(1, int(self.config.get("reconnectMax", 10))),
            reconnect_delay=max(0.5, float(self.config.get("reconnectDelay", 3))),
            audience_poll_interval=max(5, float(self.config.get("audiencePollInterval", 15))),
            deduplicate=True,
        )
        self.store.configure_room(self.config)
        self.store.set_status("connecting", "正在连接直播间")
        transport = str(self.config.get("transport") or "wss").strip().lower()
        if transport not in {"wss", "browser"}:
            transport = "wss"
        self.client = DouyinWssClient(cfg) if transport == "wss" else DouyinBrowserClient(cfg)
        self.client.on_message(self._handle_event)
        self.task = asyncio.create_task(self._run_client(), name="douyin-listener")
        await self.broadcast({"kind": "status", "state": "connecting"})
        return True, "监听启动中"

    async def _run_client(self) -> None:
        try:
            assert self.client is not None
            await self.client.connect_and_run()
            if self.store.status["state"] != "error":
                if self.store.status.get("roomState") in {"not_live", "ended"}:
                    self.store.set_status("monitoring", self.store.status.get("message") or "继续监控直播间")
                else:
                    self.store.set_status("stopped", "监听已停止")
        except asyncio.CancelledError:
            self.store.set_status("stopped", "监听已停止")
            raise
        except Exception as error:
            logging.exception("Douyin listener stopped unexpectedly")
            if self.store.status.get("roomState") in {"not_live", "ended"}:
                self.store.set_status("monitoring", self.store.status.get("message") or "继续监控直播间")
            elif self.store.status.get("roomState") == "not_found":
                self.store.set_status("error", "直播间不存在或无访问权限")
            else:
                self.store.set_status("error", str(error))
        finally:
            self.client = None
            await self.broadcast({"kind": "status", "state": self.store.status["state"]})

    async def _stop_for_room_transition(self) -> None:
        if not self.task or self.task.done():
            return
        if self.client:
            shutdown = getattr(self.client, "shutdown", None)
            if shutdown is not None:
                await shutdown()
            else:
                self.client.stop()
        try:
            await asyncio.wait_for(self.task, timeout=10)
        except asyncio.TimeoutError:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def stop(self) -> tuple[bool, str]:
        self.auto_start_paused = True
        if not self.task or self.task.done():
            self.store.set_status("stopped", "监听已停止")
            self.store.status["roomState"] = "unknown"
            return True, "监听未运行"
        await self._stop_for_room_transition()
        self.store.set_status("stopped", "监听已停止")
        self.store.status["roomState"] = "unknown"
        await self.broadcast({"kind": "status", "state": "stopped"})
        return True, "监听已停止"

    async def start_login(self) -> tuple[bool, str]:
        if self.login_task and not self.login_task.done():
            return True, "登录窗口已打开"
        if self.task and not self.task.done():
            return False, "请先停止直播监听再登录"
        self.login_state = {
            "state": "waiting",
            "message": "请在打开的浏览器中完成抖音登录",
            "account": self.login_state.get("account"),
            "accountLoading": False,
        }
        self.login_task = asyncio.create_task(self._run_login(), name="douyin-login")
        await self.broadcast({"kind": "login", "state": "waiting"})
        return True, "抖音登录窗口已打开"

    async def _run_login(self) -> None:
        try:
            cfg = ClientConfig(
                room_id=str(self.config.get("roomId") or "").strip(),
                room_url=str(self.config.get("roomUrl") or "").strip(),
            )
            await browser_login_cookie_header(cfg, timeout_sec=300)
            await self.refresh_login_account(broadcast=False)
        except asyncio.CancelledError:
            self.login_state = {
                "state": "logged_out",
                "message": "登录已取消",
                "account": None,
                "accountLoading": False,
            }
            raise
        except Exception as error:
            logging.exception("Douyin login failed")
            self.login_state = {
                "state": "error",
                "message": str(error),
                "account": self.login_state.get("account"),
                "accountLoading": False,
            }
        finally:
            await self.broadcast({"kind": "login", "state": self.login_state["state"]})

    async def refresh_login_account(self, broadcast: bool = True) -> None:
        previous_account = self.login_state.get("account")
        self.login_state = {
            "state": "logged_in",
            "message": "正在读取登录账号",
            "account": previous_account,
            "accountLoading": True,
        }
        if broadcast:
            await self.broadcast({"kind": "login", "state": "logged_in"})
        try:
            account = await self.profile_client.get_current_account()
            self.login_state = {
                "state": "logged_in",
                "message": "抖音账号已登录",
                "account": account,
                "accountLoading": False,
            }
        except Exception as error:
            logging.warning("Failed to load current Douyin account: %s", error)
            self.login_state = {
                "state": "logged_in",
                "message": "登录态可用，账号资料加载失败",
                "account": previous_account,
                "accountLoading": False,
                "accountError": str(error),
            }
        if broadcast:
            await self.broadcast({"kind": "login", "state": "logged_in"})

    def schedule_login_account_refresh(self) -> None:
        if self.login_state.get("state") != "logged_in":
            return
        if self.login_account_task and not self.login_account_task.done():
            return
        self.login_account_task = asyncio.create_task(
            self.refresh_login_account(), name="douyin-login-account"
        )

    async def cancel_login(self) -> tuple[bool, str]:
        if not self.login_task or self.login_task.done():
            return True, "当前没有进行中的登录"
        self.login_task.cancel()
        await asyncio.gather(self.login_task, return_exceptions=True)
        return True, "登录已取消"

    async def update_config(self, data: dict) -> tuple[bool, str]:
        allowed = set(DEFAULT_CONFIG)
        reset_live_data = bool(data.get("resetLiveData"))
        updated = dict(self.config)
        for key, value in data.items():
            if key in allowed:
                updated[key] = value
        updated["roomId"] = str(updated.get("roomId") or "").strip()
        updated["roomUrl"] = str(updated.get("roomUrl") or "").strip()
        updated["transport"] = "browser" if str(updated.get("transport") or "wss").lower() == "browser" else "wss"
        updated["reconnectMax"] = max(1, min(100, int(updated.get("reconnectMax", 10))))
        updated["reconnectDelay"] = max(0.5, min(60, float(updated.get("reconnectDelay", 3))))
        updated["audiencePollInterval"] = max(5, min(300, float(updated.get("audiencePollInterval", 15))))
        updated["roomStatusPollInterval"] = max(10, min(300, int(updated.get("roomStatusPollInterval", 30))))
        updated["monitorEnabled"] = bool(updated.get("monitorEnabled", True))
        musicbot_config = updated.get("musicBot") if isinstance(updated.get("musicBot"), dict) else {}
        try:
            musicbot_timeout = float(musicbot_config.get("timeoutSeconds", 2) or 2)
        except (TypeError, ValueError):
            musicbot_timeout = 2
        updated["musicBot"] = {
            "enabled": bool(musicbot_config.get("enabled", True)),
            "commandUrl": str(musicbot_config.get("commandUrl") or DEFAULT_CONFIG["musicBot"]["commandUrl"]).strip()[:2048],
            "timeoutSeconds": max(0.2, min(10, musicbot_timeout)),
        }
        caption_config = updated.get("liveCaptions") if isinstance(updated.get("liveCaptions"), dict) else {}
        try:
            fallback_timeout = int(caption_config.get("fallbackTimeoutSeconds", 300))
        except (TypeError, ValueError):
            fallback_timeout = 300
        updated["liveCaptions"] = {
            "enabled": bool(caption_config.get("enabled", False)),
            "outputToLiveUi": bool(caption_config.get("outputToLiveUi", True)),
            "persist": bool(caption_config.get("persist", False)),
            "fallbackEnabled": bool(caption_config.get("fallbackEnabled", False)),
            "fallbackTimeoutSeconds": max(5, min(3600, fallback_timeout)),
            "showIdleOnTimeout": bool(caption_config.get("showIdleOnTimeout", False)),
        }
        updated["speech"] = normalize_speech_config(updated.get("speech"))
        asset_config = updated.get("giftAssets") if isinstance(updated.get("giftAssets"), dict) else {}
        try:
            asset_refresh_hours = int(asset_config.get("refreshHours", 24) or 24)
        except (TypeError, ValueError):
            asset_refresh_hours = 24
        updated["giftAssets"] = {
            "enabled": bool(asset_config.get("enabled", True)),
            "refreshHours": max(1, min(168, asset_refresh_hours)),
            "storagePath": str(asset_config.get("storagePath") or "data/gift_assets").strip(),
            "cacheGiftIcons": bool(asset_config.get("cacheGiftIcons", True)),
            "cacheEffects": bool(asset_config.get("cacheEffects", True)),
        }
        gift_asset_storage_root(updated["giftAssets"]["storagePath"])
        connection_changed = any(
            str(updated.get(key) or "").strip() != str(self.config.get(key) or "").strip()
            for key in (
                "roomId",
                "roomUrl",
                "transport",
                "saveRaw",
                "browserHeadless",
                "browserBlockMedia",
                "browserVisibleFallback",
                "bootstrapBrowser",
                "reconnect",
                "reconnectMax",
                "reconnectDelay",
                "audiencePollInterval",
            )
        )
        should_reset = connection_changed or reset_live_data
        if should_reset:
            await self._stop_for_config_update()
        self.config = updated
        if should_reset:
            self.store.reset_live_data(updated)
        else:
            self.store.configure_room(updated)
        save_config(updated)
        await self.reconfigure_gift_assets(updated["giftAssets"]["storagePath"])
        await self.captions.configure(updated["liveCaptions"])
        if hasattr(self, "speech"):
            self.speech.configure(updated["speech"])
        if not updated["monitorEnabled"]:
            await self._disable_room_monitor()
        else:
            self.auto_start_paused = False
            await self.ensure_room_monitor()
        await self.broadcast({"kind": "config"})
        if should_reset:
            return True, "已停止旧监控和监听，已应用新配置并重新开始房间监控"
        return True, "配置已保存；显示与轮询配置已生效"


def json_response(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=lambda value: json.dumps(value, ensure_ascii=False))


async def create_app() -> web.Application:
    app = web.Application(client_max_size=25 * 1024 * 1024)
    manager = ListenerManager()
    app["manager"] = manager

    async def health(_: web.Request) -> web.Response:
        return json_response({"service": "douyin-listener", "status": "ok", "listener": manager.store.status})

    async def state(_: web.Request) -> web.Response:
        return json_response(manager.public_state())

    async def captions_state(_: web.Request) -> web.Response:
        return json_response(manager.captions.snapshot())

    async def speech_status(_: web.Request) -> web.Response:
        return json_response({"ok": True, "state": manager.speech.status(), "captions": manager.subtitle_pipeline.snapshot()})

    async def speech_options(_: web.Request) -> web.Response:
        try:
            options = await asyncio.to_thread(manager.speech.options)
            options["catalog"] = await asyncio.to_thread(manager.speech_models.catalog)
            options["downloads"] = manager.speech_models.downloads()
            return json_response({"ok": True, "options": options})
        except Exception as error:
            return json_response({"ok": False, "message": str(error)}, 503)

    async def speech_model_downloads(_: web.Request) -> web.Response:
        return json_response({"ok": True, "downloads": manager.speech_models.downloads()})

    async def speech_model_download(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            return json_response({"ok": True, "download": manager.speech_models.start(body.get("modelId"))})
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            return json_response({"ok": False, "message": str(error)}, 400)

    async def speech_model_cancel(request: web.Request) -> web.Response:
        try:
            return json_response({"ok": True, "download": manager.speech_models.cancel(request.match_info["model_id"])})
        except (ValueError, TypeError) as error:
            return json_response({"ok": False, "message": str(error)}, 400)

    async def speech_devices(_: web.Request) -> web.Response:
        try:
            return json_response({"ok": True, "devices": await manager.subtitle_pipeline.devices()})
        except Exception as error:
            return json_response({"ok": False, "message": str(error)}, 503)

    async def speech_capture_start(request: web.Request) -> web.Response:
        try:
            body = await request.json() if request.can_read_body else {}
            return json_response({"ok": True, "captions": await manager.subtitle_pipeline.start_capture(body.get("deviceId"))})
        except Exception as error:
            return json_response({"ok": False, "message": str(error)}, 503)

    async def speech_capture_stop(_: web.Request) -> web.Response:
        try:
            return json_response({"ok": True, "captions": await manager.subtitle_pipeline.stop_capture()})
        except Exception as error:
            return json_response({"ok": False, "message": str(error)}, 503)

    async def speech_asr(request: web.Request) -> web.Response:
        try:
            if request.content_type not in {"audio/wav", "audio/x-wav", "application/octet-stream"}:
                raise SpeechServiceError("unsupported_content_type", "Send a PCM WAV request body", 415)
            wav_data = await request.read()
            result = await asyncio.to_thread(manager.speech.recognize_wav, wav_data)
            return json_response({"ok": True, **result})
        except SpeechServiceError as error:
            return json_response({"ok": False, "code": error.code, "message": str(error)}, error.status)
        except Exception as error:
            logging.exception("Speech recognition failed")
            return json_response({"ok": False, "code": "asr_failed", "message": str(error)}, 500)

    async def speech_tts(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise SpeechServiceError("invalid_request", "Request must be a JSON object")
            wav_data, metadata = await asyncio.to_thread(
                manager.speech.synthesize, body.get("text"), body.get("speakerId"), body.get("speed")
            )
            return web.Response(body=wav_data, content_type="audio/wav", headers={
                "X-Sample-Rate": str(metadata["sampleRate"]),
                "X-Speaker-Id": str(metadata["speakerId"]),
                "X-Speech-Speed": str(metadata["speed"]),
            })
        except (json.JSONDecodeError, TypeError):
            return json_response({"ok": False, "code": "invalid_request", "message": "Request must be valid JSON"}, 400)
        except SpeechServiceError as error:
            return json_response({"ok": False, "code": error.code, "message": str(error)}, error.status)
        except Exception as error:
            logging.exception("Speech synthesis failed")
            return json_response({"ok": False, "code": "tts_failed", "message": str(error)}, 500)

    async def speech_translate(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise SpeechServiceError("invalid_request", "Request must be a JSON object")
            result = await asyncio.to_thread(
                manager.speech.translate, body.get("text"), body.get("sourceLanguage", ""), body.get("targetLanguage", "")
            )
            return json_response({"ok": True, **result})
        except (json.JSONDecodeError, TypeError):
            return json_response({"ok": False, "code": "invalid_request", "message": "Request must be valid JSON"}, 400)
        except SpeechServiceError as error:
            return json_response({"ok": False, "code": error.code, "message": str(error)}, error.status)
        except Exception as error:
            logging.exception("Translation failed")
            return json_response({"ok": False, "code": "translation_failed", "message": str(error)}, 500)

    async def get_config(_: web.Request) -> web.Response:
        return json_response(manager.config)

    async def put_config(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("配置必须是 JSON 对象")
            ok, message = await manager.update_config(body)
            return json_response({"ok": ok, "message": message, "config": manager.config, "state": manager.public_state()})
        except (json.JSONDecodeError, ValueError, TypeError) as error:
            return json_response({"ok": False, "message": str(error)}, 400)

    async def start_listener(_: web.Request) -> web.Response:
        ok, message = await manager.start()
        return json_response({"ok": ok, "message": message, "state": manager.public_state()}, 200 if ok else 400)

    async def stop_listener(_: web.Request) -> web.Response:
        ok, message = await manager.stop()
        return json_response({"ok": ok, "message": message, "state": manager.public_state()})

    async def login_status(_: web.Request) -> web.Response:
        if manager.login_state.get("state") == "logged_in" and not manager.login_state.get("account"):
            manager.schedule_login_account_refresh()
        return json_response({"ok": True, "login": manager.login_state})

    async def start_login(_: web.Request) -> web.Response:
        ok, message = await manager.start_login()
        return json_response({"ok": ok, "message": message, "login": manager.login_state}, 200 if ok else 400)

    async def cancel_login(_: web.Request) -> web.Response:
        ok, message = await manager.cancel_login()
        return json_response({"ok": ok, "message": message, "login": manager.login_state})

    async def records(request: web.Request) -> web.Response:
        kind = request.query.get("type", "all")
        available = manager.public_state()["records"]
        if kind == "redpacket":
            return json_response({"redPackets": available["redPackets"]})
        if kind == "luckybag":
            return json_response({"luckyBags": available["luckyBags"]})
        return json_response(available)

    async def fans(request: web.Request) -> web.Response:
        try:
            database = manager.fans.get(manager.store.room, manager.config)
            result = database.list_fans(
                query=request.query.get("q", ""),
                mystery=request.query.get("mystery", "all"),
                min_level=int(request.query.get("minLevel", "0")),
                member_status=request.query.get("memberStatus", ""),
                guardian_status=request.query.get("guardianStatus", ""),
                sort=request.query.get("sort", "recent"),
                limit=int(request.query.get("limit", "100")),
                offset=int(request.query.get("offset", "0")),
            )
            return json_response({"ok": True, "database": database.metadata(), **result})
        except (TypeError, ValueError) as error:
            return json_response({"ok": False, "message": str(error)}, 400)

    async def fan_detail(request: web.Request) -> web.Response:
        database = manager.fans.get(manager.store.room, manager.config)
        detail = database.fan_detail(request.match_info["identity"])
        if detail is None:
            return json_response({"ok": False, "message": "粉丝记录不存在"}, 404)
        return json_response({"ok": True, **detail})

    async def gift_assets_state(_: web.Request) -> web.Response:
        return json_response({"ok": True, "state": manager.public_state()["giftAssets"]})

    async def gift_assets_sync(_: web.Request) -> web.Response:
        ok, message = manager.start_gift_asset_sync()
        return json_response({"ok": ok, "message": message, "state": manager.public_state()["giftAssets"]}, 202 if ok else 409)

    async def gift_assets_logs(request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "6"))
        except ValueError:
            limit = 6
        return json_response({"ok": True, "runs": await asyncio.to_thread(manager.gift_assets.recent_runs, limit)})

    async def gift_assets_catalog(request: web.Request) -> web.Response:
        try:
            result = await asyncio.to_thread(
                manager.gift_assets.list_gifts,
                request.query.get("q", ""),
                int(request.query.get("limit", "48")),
                int(request.query.get("offset", "0")),
            )
            return json_response({"ok": True, **result})
        except (TypeError, ValueError) as error:
            return json_response({"ok": False, "message": str(error)}, 400)

    async def gift_assets_cache(request: web.Request) -> web.StreamResponse:
        kind = request.match_info["kind"]
        role = request.match_info["role"]
        if kind not in {"gift", "effect"} or role not in {"icon", "image", "webp", "standard", "format265"}:
            raise web.HTTPNotFound()
        path = await asyncio.to_thread(manager.gift_assets.cached_resource_path, kind, request.match_info["source_id"], role)
        if not path:
            raise web.HTTPNotFound()
        content_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".mp4": "video/mp4", ".webm": "video/webm", ".zip": "application/zip"}
        return web.FileResponse(path, headers={"Cache-Control": "public, max-age=86400", "Content-Type": content_types.get(path.suffix.lower(), "application/octet-stream")})

    async def gift_effect_preview(request: web.Request) -> web.StreamResponse:
        try:
            result = await asyncio.to_thread(manager.gift_assets.effect_preview_path, request.match_info["effect_id"])
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            return json_response({"ok": False, "message": str(error)}, 422)
        if not result:
            raise web.HTTPNotFound()
        path, _ = result
        return web.FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

    async def gift_effect_preview_info(request: web.Request) -> web.Response:
        try:
            result = await asyncio.to_thread(manager.gift_assets.effect_preview_path, request.match_info["effect_id"])
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            return json_response({"ok": False, "message": str(error)}, 422)
        if not result:
            return json_response({"ok": False, "message": "官方资源包不含可播放的视频特效"}, 422)
        path, config = result
        return json_response({
            "ok": True,
            "previewUrl": f"/api/livemngsys/live/gift-assets/effects/{urllib.parse.quote(request.match_info['effect_id'], safe='')}/preview?v={path.stat().st_mtime_ns}",
            "portrait": config.get("portrait") if isinstance(config, dict) else {},
        })

    async def user_profile(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            supplied = body.get("user") if isinstance(body, dict) else {}
            supplied = supplied if isinstance(supplied, dict) else {}
            identity = str(supplied.get("secUid") or supplied.get("id") or supplied.get("displayId") or "")
            live_user = manager.store.find_user(identity) or supplied
            sec_uid = str(live_user.get("secUid") or supplied.get("secUid") or "")
            profile = await manager.profile_client.get_profile(sec_uid)
            if not profile.get("signature") and live_user.get("signature"):
                profile["signature"] = live_user.get("signature")
            profile.update({
                "badges": live_user.get("badges") or [],
                "fansClub": live_user.get("fansClub") or {},
                "anchorFollowStatus": live_user.get("anchorFollowStatus"),
                "anchorRelation": live_user.get("anchorRelation") or "",
                "membership": live_user.get("membership") or {
                    "opened": bool(live_user.get("subscribeStatus")),
                    "label": "已开通" if live_user.get("subscribeStatus") else "未开通",
                },
            })
            return json_response({"ok": True, "profile": profile})
        except (json.JSONDecodeError, ValueError, TypeError) as error:
            return json_response({"ok": False, "message": str(error)}, 400)
        except Exception as error:
            logging.exception("Douyin profile lookup failed")
            return json_response({"ok": False, "message": str(error)}, 502)

    async def protocol_audit(_: web.Request) -> web.Response:
        try:
            report = await asyncio.to_thread(build_protocol_audit, ROOT / "data" / "sessions")
            return json_response({"ok": True, "report": report})
        except Exception as error:
            logging.exception("Protocol audit failed")
            return json_response({"ok": False, "message": str(error)}, 500)

    async def replay_sessions(request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "100"))
        except ValueError:
            limit = 100
        return json_response({"ok": True, "sessions": await asyncio.to_thread(list_replay_sessions, limit)})

    async def replay_session(request: web.Request) -> web.Response:
        try:
            result = await asyncio.to_thread(load_replay_session, request.match_info["session_id"])
            return json_response({"ok": True, **result})
        except FileNotFoundError as error:
            return json_response({"ok": False, "message": str(error)}, 404)
        except (ValueError, OSError) as error:
            return json_response({"ok": False, "message": str(error)}, 400)
        except Exception as error:
            logging.exception("Replay session load failed")
            return json_response({"ok": False, "message": str(error)}, 500)

    async def spark_status(request: web.Request) -> web.Response:
        if request.query.get("refresh") == "1":
            await manager.spark.check_login()
        return json_response({"ok": True, "state": manager.spark.public_state()})

    async def spark_login_start(_: web.Request) -> web.Response:
        ok, message = await manager.spark.start_login()
        return json_response({"ok": ok, "message": message, "state": manager.spark.public_state()}, 200 if ok else 400)

    async def spark_login_cancel(_: web.Request) -> web.Response:
        ok, message = await manager.spark.cancel_login()
        return json_response({"ok": ok, "message": message, "state": manager.spark.public_state()})

    async def spark_friends(_: web.Request) -> web.Response:
        try:
            return json_response({"ok": True, "friends": await manager.spark.list_friends()})
        except Exception as error:
            return json_response({"ok": False, "message": str(error)}, 502)

    async def spark_copywriting(request: web.Request) -> web.Response:
        try:
            kind = request.query.get("type", "random")
            count = int(request.query.get("count", "1"))
            items = await manager.spark.generate_copywriting(kind, count)
            return json_response({"ok": True, "items": items})
        except (TypeError, ValueError) as error:
            return json_response({"ok": False, "message": str(error)}, 400)

    async def spark_start(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("请求必须是 JSON 对象")
            ok, message = await manager.spark.start_batch(body)
            return json_response({"ok": ok, "message": message, "state": manager.spark.public_state()}, 200 if ok else 400)
        except (json.JSONDecodeError, ValueError, TypeError) as error:
            return json_response({"ok": False, "message": str(error)}, 400)

    async def spark_stop(_: web.Request) -> web.Response:
        ok, message = await manager.spark.stop_batch()
        return json_response({"ok": ok, "message": message, "state": manager.spark.public_state()})

    async def websocket(request: web.Request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse(heartbeat=20)
        await socket.prepare(request)
        manager.sockets.add(socket)
        await socket.send_json({"type": "state", "state": manager.public_state()})
        try:
            async for message in socket:
                if message.type == WSMsgType.TEXT and message.data == "ping":
                    await socket.send_str("pong")
                elif message.type == WSMsgType.ERROR:
                    break
        finally:
            manager.sockets.discard(socket)
        return socket

    app.router.add_get("/health", health)
    app.router.add_get("/api/livemngsys/live/state", state)
    app.router.add_get("/api/livemngsys/live/captions", captions_state)
    app.router.add_get("/api/livemngsys/live/speech/status", speech_status)
    app.router.add_get("/api/livemngsys/live/speech/options", speech_options)
    app.router.add_get("/api/livemngsys/live/speech/models/downloads", speech_model_downloads)
    app.router.add_post("/api/livemngsys/live/speech/models/download", speech_model_download)
    app.router.add_post("/api/livemngsys/live/speech/models/download/{model_id}/cancel", speech_model_cancel)
    app.router.add_get("/api/livemngsys/live/speech/devices", speech_devices)
    app.router.add_post("/api/livemngsys/live/speech/capture/start", speech_capture_start)
    app.router.add_post("/api/livemngsys/live/speech/capture/stop", speech_capture_stop)
    app.router.add_post("/api/livemngsys/live/speech/asr", speech_asr)
    app.router.add_post("/api/livemngsys/live/speech/tts", speech_tts)
    app.router.add_post("/api/livemngsys/live/speech/translate", speech_translate)
    app.router.add_get("/api/livemngsys/live/config", get_config)
    app.router.add_put("/api/livemngsys/live/config", put_config)
    app.router.add_post("/api/livemngsys/live/start", start_listener)
    app.router.add_post("/api/livemngsys/live/stop", stop_listener)
    app.router.add_get("/api/livemngsys/live/login/status", login_status)
    app.router.add_post("/api/livemngsys/live/login/start", start_login)
    app.router.add_post("/api/livemngsys/live/login/cancel", cancel_login)
    app.router.add_get("/api/livemngsys/live/records", records)
    app.router.add_get("/api/livemngsys/live/fans", fans)
    app.router.add_get("/api/livemngsys/live/fans/{identity}", fan_detail)
    app.router.add_get("/api/livemngsys/live/gift-assets/catalog", gift_assets_catalog)
    app.router.add_get("/api/livemngsys/live/gift-assets/cache/{kind}/{source_id}/{role}", gift_assets_cache)
    app.router.add_get("/api/livemngsys/live/gift-assets/effects/{effect_id}/preview-info", gift_effect_preview_info)
    app.router.add_get("/api/livemngsys/live/gift-assets/effects/{effect_id}/preview", gift_effect_preview)
    app.router.add_get("/api/livemngsys/live/gift-assets", gift_assets_state)
    app.router.add_get("/api/livemngsys/live/gift-assets/logs", gift_assets_logs)
    app.router.add_post("/api/livemngsys/live/gift-assets/sync", gift_assets_sync)
    app.router.add_post("/api/livemngsys/live/users/profile", user_profile)
    app.router.add_get("/api/livemngsys/live/protocol/audit", protocol_audit)
    app.router.add_get("/api/livemngsys/live/replay/sessions", replay_sessions)
    app.router.add_get("/api/livemngsys/live/replay/sessions/{session_id}", replay_session)
    app.router.add_get("/api/livemngsys/live/spark/status", spark_status)
    app.router.add_post("/api/livemngsys/live/spark/login/start", spark_login_start)
    app.router.add_post("/api/livemngsys/live/spark/login/cancel", spark_login_cancel)
    app.router.add_get("/api/livemngsys/live/spark/friends", spark_friends)
    app.router.add_get("/api/livemngsys/live/spark/copywriting", spark_copywriting)
    app.router.add_post("/api/livemngsys/live/spark/start", spark_start)
    app.router.add_post("/api/livemngsys/live/spark/stop", spark_stop)
    app.router.add_get("/live-ws", websocket)

    async def startup(_: web.Application) -> None:
        musicbot_config = manager.config.get("musicBot") if isinstance(manager.config.get("musicBot"), dict) else {}
        manager.musicbot_http = ClientSession(timeout=ClientTimeout(total=float(musicbot_config.get("timeoutSeconds", 2) or 2)))
        asyncio.create_task(asyncio.to_thread(refresh_emoji_cache), name="douyin-emoji-cache-refresh")
        manager.schedule_login_account_refresh()
        asyncio.create_task(manager.spark.check_login(), name="douyin-spark-login-check")
        await manager.captions.configure(manager.config.get("liveCaptions") or {})
        await manager.subtitle_pipeline.start()
        await manager.gift_assets.start()
        await manager.ensure_room_monitor()

    async def cleanup(_: web.Application) -> None:
        await manager._cancel_room_monitor_task()
        if manager._event_broadcast_task and not manager._event_broadcast_task.done():
            manager._event_broadcast_task.cancel()
            await asyncio.gather(manager._event_broadcast_task, return_exceptions=True)
        await manager.spark.close()
        await manager.gift_assets.stop()
        if manager.gift_asset_sync_task and not manager.gift_asset_sync_task.done():
            manager.gift_asset_sync_task.cancel()
            await asyncio.gather(manager.gift_asset_sync_task, return_exceptions=True)
        await manager.captions.stop()
        await manager.subtitle_pipeline.stop()
        await manager.speech_models.close()
        await manager.cancel_login()
        if manager.login_account_task and not manager.login_account_task.done():
            manager.login_account_task.cancel()
            await asyncio.gather(manager.login_account_task, return_exceptions=True)
        await manager.stop()
        if manager.musicbot_http and not manager.musicbot_http.closed:
            await manager.musicbot_http.close()

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="LiveMngSys Douyin listener service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7002)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
    web.run_app(create_app(), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
