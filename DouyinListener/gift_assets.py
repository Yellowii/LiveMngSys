"""Daily catalog sync and local cache for Douyin gift icons and effect packages."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import time
import urllib.parse
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from aiohttp import ClientSession, ClientTimeout

from Doubao.client.browser_client import load_saved_cookie_header
from Doubao.client.signed_fetch import request_ms_token, signing_user_agent
from vendor.douyin_spider_signing import ABogusPureSigner


GIFT_LIST_URL = "https://live.douyin.com/webcast/gift/list/"
EFFECTS_URL = "https://live.douyin.com/webcast/assets/effects/"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _cookies(header: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in header.split(";"):
        if "=" in item:
            key, value = item.strip().split("=", 1)
            result[key] = value
    return result


def _urls(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    entries = value.get("url_list") or value.get("urlList") or []
    return [_text(item) for item in entries if _text(item)] if isinstance(entries, list) else []


def _fingerprint(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class GiftAssetCatalog:
    """Stores complete official catalog snapshots and caches only changed resources."""

    def __init__(self, root: Path, config_provider: Callable[[], dict] | None = None, room_provider: Callable[[], dict] | None = None):
        self.root = Path(root)
        self.snapshots = self.root / "snapshots"
        self.icons_dir = self.root / "cache" / "gift_icons"
        self.effects_dir = self.root / "cache" / "effects"
        self.preview_dir = self.root / "cache" / "effect_previews"
        self.db_path = self.root / "gift_assets.sqlite3"
        self.config_provider = config_provider or (lambda: {})
        self.room_provider = room_provider or (lambda: {})
        self._signer = ABogusPureSigner(fixed=False)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._status: dict[str, Any] = {
            "state": "idle", "message": "Waiting for gift asset sync", "lastAttemptAt": 0,
            "lastSuccessAt": 0, "lastError": "", "giftCount": 0, "effectCount": 0,
            "cachedIcons": 0, "cachedEffects": 0, "lastResult": {},
        }
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshots.mkdir(parents=True, exist_ok=True)
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        self.effects_dir.mkdir(parents=True, exist_ok=True)
        self.preview_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._load_status()

    @contextmanager
    def _db(self):
        connection = sqlite3.connect(self.db_path, timeout=12)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 12000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._db() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS gift_catalog (
                    gift_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', diamond_count INTEGER NOT NULL DEFAULT 0,
                    primary_effect_id TEXT NOT NULL DEFAULT '', asset_ids_json TEXT NOT NULL DEFAULT '[]',
                    icon_urls_json TEXT NOT NULL DEFAULT '[]', image_urls_json TEXT NOT NULL DEFAULT '[]',
                    webp_urls_json TEXT NOT NULL DEFAULT '[]', payload_hash TEXT NOT NULL, first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL, changed_at INTEGER NOT NULL, source_snapshot TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS effect_catalog (
                    effect_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', resource_type TEXT NOT NULL DEFAULT '',
                    md5 TEXT NOT NULL DEFAULT '', resource_urls_json TEXT NOT NULL DEFAULT '[]',
                    format_265_urls_json TEXT NOT NULL DEFAULT '[]', payload_hash TEXT NOT NULL, first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL, changed_at INTEGER NOT NULL, source_snapshot TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS asset_cache (
                    asset_kind TEXT NOT NULL, source_id TEXT NOT NULL, role TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
                    local_path TEXT NOT NULL DEFAULT '', content_sha256 TEXT NOT NULL DEFAULT '', size_bytes INTEGER NOT NULL DEFAULT 0,
                    first_seen_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL, downloaded_at INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending', last_error TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(asset_kind, source_id, role)
                );
                CREATE TABLE IF NOT EXISTS catalog_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, started_at INTEGER NOT NULL, completed_at INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'running', gift_snapshot TEXT NOT NULL DEFAULT '', effect_snapshot TEXT NOT NULL DEFAULT '',
                    new_gifts INTEGER NOT NULL DEFAULT 0, changed_gifts INTEGER NOT NULL DEFAULT 0,
                    new_effects INTEGER NOT NULL DEFAULT 0, changed_effects INTEGER NOT NULL DEFAULT 0,
                    downloaded_icons INTEGER NOT NULL DEFAULT 0, downloaded_effects INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_asset_cache_status ON asset_cache(status, last_seen_at DESC);
                """
            )

    def _load_status(self) -> None:
        with self._db() as db:
            run = db.execute("SELECT * FROM catalog_runs ORDER BY id DESC LIMIT 1").fetchone()
            gifts = db.execute("SELECT COUNT(*) FROM gift_catalog").fetchone()[0]
            effects = db.execute("SELECT COUNT(*) FROM effect_catalog").fetchone()[0]
            icons = db.execute("SELECT COUNT(*) FROM asset_cache WHERE asset_kind='gift' AND status='ready'").fetchone()[0]
            cached_effects = db.execute("SELECT COUNT(*) FROM asset_cache WHERE asset_kind='effect' AND status='ready'").fetchone()[0]
        self._status.update({"giftCount": gifts, "effectCount": effects, "cachedIcons": icons, "cachedEffects": cached_effects})
        if run:
            if run["status"] == "running":
                self._status.update({"state": "waiting", "message": "Resuming incomplete gift asset sync", "lastAttemptAt": 0, "lastSuccessAt": 0, "lastError": ""})
            else:
                self._status.update({"lastAttemptAt": run["started_at"], "lastSuccessAt": run["completed_at"] if run["status"] == "success" else 0, "lastError": run["error"]})

    def public_state(self) -> dict:
        return dict(self._status)

    def recent_runs(self, limit: int = 6) -> list[dict]:
        limit = max(1, min(20, _number(limit) or 6))
        with self._db() as db:
            rows = db.execute(
                "SELECT id,started_at,completed_at,status,new_gifts,changed_gifts,new_effects,changed_effects,downloaded_icons,downloaded_effects,error "
                "FROM catalog_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"], "startedAt": row["started_at"], "completedAt": row["completed_at"], "status": row["status"],
                "newGifts": row["new_gifts"], "changedGifts": row["changed_gifts"], "newEffects": row["new_effects"],
                "changedEffects": row["changed_effects"], "downloadedIcons": row["downloaded_icons"],
                "downloadedEffects": row["downloaded_effects"], "error": row["error"],
            }
            for row in rows
        ]

    def list_gifts(self, query: str = "", limit: int = 48, offset: int = 0) -> dict:
        query = _text(query)
        limit = max(1, min(120, _number(limit) or 48))
        offset = max(0, _number(offset))
        with self._db() as db:
            if query:
                pattern = f"%{query}%"
                total = db.execute("SELECT COUNT(*) FROM gift_catalog WHERE gift_id LIKE ? OR name LIKE ?", (pattern, pattern)).fetchone()[0]
                rows = db.execute("SELECT * FROM gift_catalog WHERE gift_id LIKE ? OR name LIKE ? ORDER BY diamond_count DESC, gift_id LIMIT ? OFFSET ?", (pattern, pattern, limit, offset)).fetchall()
            else:
                total = db.execute("SELECT COUNT(*) FROM gift_catalog").fetchone()[0]
                rows = db.execute("SELECT * FROM gift_catalog ORDER BY diamond_count DESC, gift_id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            gift_ids = [row["gift_id"] for row in rows]
            cache_rows = self._cache_rows(db, "gift", gift_ids)
            effect_ids = []
            for row in rows:
                effect_ids.extend([_text(row["primary_effect_id"]), *self._stored_values(row["asset_ids_json"])])
            effect_ids = list(dict.fromkeys(item for item in effect_ids if item))
            effect_rows = self._effect_rows(db, effect_ids)
            effect_cache = self._cache_rows(db, "effect", effect_ids)
        items = []
        for row in rows:
            gift_id = row["gift_id"]
            asset_cache = cache_rows.get(gift_id, {})
            effect = None
            for effect_id in [_text(row["primary_effect_id"]), *self._stored_values(row["asset_ids_json"])]:
                if effect_id in effect_rows:
                    effect = dict(effect_rows[effect_id])
                    effect_cache_info = effect_cache.get(effect_id, {})
                    effect["cached"] = any(item.get("status") == "ready" for item in effect_cache_info.values())
                    effect["previewable"] = self.effect_preview_available(effect_id) if effect["cached"] else False
                    effect["previewMessage"] = "" if effect["previewable"] else "官方资源包不含可播放的视频特效"
                    effect["previewUrl"] = f"/api/livemngsys/live/gift-assets/effects/{urllib.parse.quote(effect_id, safe='')}/preview"
                    break
            items.append({
                "id": gift_id,
                "name": row["name"],
                "diamondCount": row["diamond_count"],
                "primaryEffectId": row["primary_effect_id"],
                "assetIds": self._stored_values(row["asset_ids_json"]),
                "assets": {
                    role: f"/api/livemngsys/live/gift-assets/cache/gift/{urllib.parse.quote(gift_id, safe='')}/{role}"
                    for role in ("icon", "image", "webp")
                    if asset_cache.get(role, {}).get("status") == "ready"
                },
                "effect": effect,
            })
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def cached_resource_path(self, kind: str, source_id: str, role: str) -> Path | None:
        with self._db() as db:
            row = db.execute("SELECT local_path, status FROM asset_cache WHERE asset_kind=? AND source_id=? AND role=?", (kind, source_id, role)).fetchone()
        if not row or row["status"] != "ready":
            return None
        path = self._safe_path(row["local_path"])
        return path if path and path.is_file() else None

    def _effect_preview_source(self, effect_id: str) -> tuple[Path, str, str] | None:
        for role in ("standard", "format265"):
            source = self.cached_resource_path("effect", _text(effect_id), role)
            if not source or source.suffix.lower() not in {".zip", ".mp4", ".webm"}:
                continue
            if source.suffix.lower() in {".mp4", ".webm"}:
                return source, role, ""
            try:
                with zipfile.ZipFile(source) as archive:
                    video_name = next((name for name in archive.namelist() if name.lower().endswith((".mp4", ".webm"))), "")
            except (OSError, zipfile.BadZipFile):
                continue
            if video_name:
                return source, role, video_name
        return None

    def effect_preview_available(self, effect_id: str) -> bool:
        return self._effect_preview_source(effect_id) is not None

    def effect_preview_path(self, effect_id: str) -> tuple[Path, dict] | None:
        preview_source = self._effect_preview_source(effect_id)
        if not preview_source:
            return None
        source, role, video_name = preview_source
        if not video_name:
            return source, {"portrait": {}}
        extension = Path(video_name).suffix.lower()
        output = self.preview_dir / f"{re.sub(r'[^A-Za-z0-9_-]', '_', _text(effect_id))}_{role}{extension}"
        config = {}
        with zipfile.ZipFile(source) as archive:
            info_name = next((name for name in archive.namelist() if name.lower().endswith("config.json")), "")
            if info_name:
                try:
                    config = json.loads(archive.read(info_name).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    config = {}
            if not output.exists() or output.stat().st_mtime_ns < source.stat().st_mtime_ns:
                info = archive.getinfo(video_name)
                if info.file_size > 160 * 1024 * 1024:
                    raise ValueError("Effect preview is too large")
                temporary = output.with_suffix(".tmp")
                temporary.write_bytes(archive.read(video_name))
                temporary.replace(output)
        return output, config

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._daily_loop(), name="douyin-gift-asset-sync")

    async def stop(self) -> None:
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _daily_loop(self) -> None:
        while not self._stop.is_set():
            config = self.config_provider().get("giftAssets") or {}
            enabled = bool(config.get("enabled", True))
            due_after = max(1, min(168, _number(config.get("refreshHours") or 24))) * 3600 * 1000
            previous = max(_number(self._status.get("lastAttemptAt")), _number(self._status.get("lastSuccessAt")))
            waiting_for_room = self._status.get("state") == "waiting" or "room metadata is incomplete" in _text(self._status.get("lastError"))
            if enabled and (waiting_for_room or not previous or _now_ms() - previous >= due_after):
                try:
                    await self.sync()
                except Exception:
                    pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=5 if enabled and self._status.get("state") == "waiting" else 60)
            except asyncio.TimeoutError:
                continue

    async def sync(self) -> dict:
        if self._lock.locked():
            raise RuntimeError("Gift asset sync is already running")
        async with self._lock:
            context = self._catalog_context()
            if context is None:
                self._status.update({"state": "waiting", "message": "Waiting for current room metadata", "lastAttemptAt": 0, "lastError": ""})
                return {"skipped": "room_metadata"}
            started = _now_ms()
            self._status.update({"state": "syncing", "message": "Fetching official gift and effect catalogs", "lastAttemptAt": started, "lastError": ""})
            run_id = self._start_run(started)
            try:
                gifts_payload, effects_payload = await self._fetch_catalogs(context)
                result = await self.ingest_snapshot(gifts_payload, effects_payload, download=True)
                self._finish_run(run_id, "success", result, "")
                self._status.update({"state": "idle", "message": "Gift asset catalog is up to date", "lastSuccessAt": _now_ms(), "lastResult": result})
                self._load_status()
                return result
            except Exception as error:
                message = str(error)
                self._finish_run(run_id, "error", {}, message)
                self._status.update({"state": "error", "message": "Gift asset sync failed", "lastError": message})
                raise

    async def ingest_snapshot(self, gifts_payload: dict, effects_payload: dict, download: bool = False) -> dict:
        """Store supplied official payloads. Public for deterministic tests and offline imports."""
        timestamp = _now_ms()
        gift_snapshot = self._write_snapshot("gift_list", gifts_payload, timestamp)
        effect_snapshot = self._write_snapshot("effects", effects_payload, timestamp)
        gifts = self._parse_gifts(gifts_payload)
        effects = self._parse_effects(effects_payload)
        changes = self._upsert_catalogs(gifts, effects, gift_snapshot, effect_snapshot, timestamp)
        downloaded = {"icons": 0, "effects": 0, "failed": 0}
        if download:
            self._load_status()
            downloaded = await self._download_changed_resources(changes)
        return {"gifts": len(gifts), "effects": len(effects), **changes, "downloaded": downloaded, "giftSnapshot": gift_snapshot, "effectSnapshot": effect_snapshot}

    def _catalog_context(self) -> tuple[str, str] | None:
        room = self.room_provider() or {}
        room_id = _text(room.get("id"))
        anchor = room.get("anchor") if isinstance(room.get("anchor"), dict) else {}
        sec_anchor_id = _text(room.get("secAnchorId") or anchor.get("secUid"))
        return (room_id, sec_anchor_id) if room_id and sec_anchor_id else None

    async def _fetch_catalogs(self, context: tuple[str, str]) -> tuple[dict, dict]:
        header = load_saved_cookie_header()
        cookies = _cookies(header)
        if "sessionid" not in cookies:
            raise RuntimeError("Please log in to Douyin before synchronizing gift assets")
        room_id, sec_anchor_id = context
        timeout = ClientTimeout(total=45)
        async with ClientSession(timeout=timeout) as http:
            ms_token = await request_ms_token(http, cookies.get("ttwid", ""))
            common = [
                ("aid", "6383"), ("app_name", "douyin_web"), ("live_id", "1"), ("device_platform", "web"),
                ("language", "zh-CN"), ("enter_from", "web_live"), ("cookie_enabled", "true"), ("screen_width", "1920"),
                ("screen_height", "1080"), ("browser_language", "zh-CN"), ("browser_platform", "Win32"),
                ("browser_name", "Edge"), ("browser_version", "150.0.0.0"), ("os_name", "Windows"),
                ("os_version", "10"), ("browser_online", "true"), ("engine_name", "Blink"), ("engine_version", "150.0.0.0"),
                ("cpu_core_num", "16"), ("device_memory", "16"), ("platform", "PC"), ("downlink", "10"),
                ("effective_type", "4g"), ("round_trip_time", "0"), ("channel", "channel_pc_web"),
                ("room_id", room_id), ("sec_anchor_id", sec_anchor_id), ("msToken", ms_token),
            ]
            gifts = await self._signed_get(http, GIFT_LIST_URL, [*common, ("to_room_id", room_id), ("sec_to_user_id", sec_anchor_id), ("gift_scene", "1"), ("to_episode_id", "0"), ("fetch_giftlist_from", "3")], header)
            effects = await self._signed_get(http, EFFECTS_URL, [*common, ("is_living", "true"), ("download_assets_from", "3")], header)
        return gifts, effects

    async def _signed_get(self, http: ClientSession, url: str, params: list[tuple[str, str]], cookie_header: str) -> dict:
        query = "&".join(f"{key}={urllib.parse.quote(str(value))}" for key, value in params)
        signed = [*params, ("a_bogus", self._signer.sign(f"https://live.douyin.com/?{query}"))]
        headers = {"Accept": "application/json, text/plain, */*", "Accept-Language": "zh-CN,zh;q=0.9", "Cookie": cookie_header, "Referer": "https://live.douyin.com/", "User-Agent": signing_user_agent()}
        async with http.get(url, params=signed, headers=headers) as response:
            raw = await response.read()
            if response.status >= 400:
                raise RuntimeError(f"Catalog endpoint returned HTTP {response.status}")
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError as error:
                raise RuntimeError("Catalog endpoint did not return JSON") from error
        if not isinstance(payload, dict) or int(payload.get("status_code") or 0) != 0:
            raise RuntimeError(_text(payload.get("status_msg") if isinstance(payload, dict) else "Catalog request failed"))
        return payload

    def _write_snapshot(self, kind: str, payload: dict, timestamp: int) -> str:
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(timestamp / 1000))
        directory = self.snapshots / time.strftime("%Y-%m-%d", time.localtime(timestamp / 1000))
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{kind}_{stamp}_{timestamp % 1000:03d}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path.relative_to(self.root)).replace("\\", "/")

    @staticmethod
    def _parse_gifts(payload: dict) -> list[dict]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        raw = [item for item in (data.get("gifts") or []) if isinstance(item, dict)]
        for page in data.get("pages") or []:
            if isinstance(page, dict):
                raw.extend(item for item in (page.get("gifts") or []) if isinstance(item, dict))
        info = data.get("gifts_info") or data.get("giftsInfo") or {}
        if isinstance(info, dict):
            raw.extend(item for item in (info.get("gift_list") or info.get("giftList") or []) if isinstance(item, dict))
        result: dict[str, dict] = {}
        for item in raw:
            gift_id = _text(item.get("id"))
            if not gift_id:
                continue
            result[gift_id] = {
                "id": gift_id, "name": _text(item.get("name")), "diamondCount": _number(item.get("diamond_count") or item.get("diamondCount")),
                "primaryEffectId": _text(item.get("primary_effect_id") or item.get("primaryEffectId")), "assetIds": item.get("asset_ids") or item.get("assetIds") or [],
                "iconUrls": _urls(item.get("icon")), "imageUrls": _urls(item.get("image")), "webpUrls": _urls(item.get("webp_image") or item.get("webpImage")),
            }
        return list(result.values())

    @staticmethod
    def _stored_values(value: Any) -> list[str]:
        try:
            parsed = json.loads(_text(value))
        except json.JSONDecodeError:
            return []
        return [_text(item) for item in parsed if _text(item)] if isinstance(parsed, list) else []

    @staticmethod
    def _cache_rows(db: sqlite3.Connection, kind: str, source_ids: list[str]) -> dict[str, dict[str, dict]]:
        if not source_ids:
            return {}
        placeholders = ",".join("?" for _ in source_ids)
        rows = db.execute(f"SELECT source_id, role, local_path, status FROM asset_cache WHERE asset_kind=? AND source_id IN ({placeholders})", (kind, *source_ids)).fetchall()
        result: dict[str, dict[str, dict]] = {}
        for row in rows:
            result.setdefault(row["source_id"], {})[row["role"]] = dict(row)
        return result

    @staticmethod
    def _effect_rows(db: sqlite3.Connection, effect_ids: list[str]) -> dict[str, dict]:
        if not effect_ids:
            return {}
        placeholders = ",".join("?" for _ in effect_ids)
        rows = db.execute(f"SELECT effect_id, name, resource_type, md5 FROM effect_catalog WHERE effect_id IN ({placeholders})", effect_ids).fetchall()
        return {row["effect_id"]: {"id": row["effect_id"], "name": row["name"], "resourceType": row["resource_type"], "md5": row["md5"]} for row in rows}

    def _safe_path(self, relative: str) -> Path | None:
        root = self.root.resolve()
        path = (self.root / relative).resolve()
        return path if path.is_relative_to(root) else None

    @staticmethod
    def _parse_effects(payload: dict) -> list[dict]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        result: dict[str, dict] = {}
        for item in data.get("assets") or []:
            if not isinstance(item, dict):
                continue
            effect_id = _text(item.get("id"))
            if effect_id:
                format_265 = item.get("format_265_resource") or item.get("format265Resource") or {}
                result[effect_id] = {"id": effect_id, "name": _text(item.get("name")), "resourceType": _text(item.get("resource_type") or item.get("resourceType")), "md5": _text(item.get("md5")), "resourceUrls": _urls(item.get("resource_url") or item.get("resourceUrl")), "format265Urls": _urls(format_265.get("resource_url") or format_265.get("resourceUrl")) if isinstance(format_265, dict) else []}
        return list(result.values())

    def _upsert_catalogs(self, gifts: list[dict], effects: list[dict], gift_snapshot: str, effect_snapshot: str, timestamp: int) -> dict:
        result = {"newGifts": 0, "changedGifts": 0, "newEffects": 0, "changedEffects": 0, "giftResources": [], "effectResources": []}
        with self._db() as db:
            for gift in gifts:
                payload_hash = _fingerprint(gift)
                old = db.execute("SELECT payload_hash FROM gift_catalog WHERE gift_id=?", (gift["id"],)).fetchone()
                is_new = old is None
                changed = not is_new and old["payload_hash"] != payload_hash
                if is_new:
                    result["newGifts"] += 1
                elif changed:
                    result["changedGifts"] += 1
                db.execute("""INSERT INTO gift_catalog (gift_id,name,diamond_count,primary_effect_id,asset_ids_json,icon_urls_json,image_urls_json,webp_urls_json,payload_hash,first_seen_at,last_seen_at,changed_at,source_snapshot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(gift_id) DO UPDATE SET name=excluded.name,diamond_count=excluded.diamond_count,primary_effect_id=excluded.primary_effect_id,asset_ids_json=excluded.asset_ids_json,icon_urls_json=excluded.icon_urls_json,image_urls_json=excluded.image_urls_json,webp_urls_json=excluded.webp_urls_json,payload_hash=excluded.payload_hash,last_seen_at=excluded.last_seen_at,changed_at=CASE WHEN gift_catalog.payload_hash<>excluded.payload_hash THEN excluded.changed_at ELSE gift_catalog.changed_at END,source_snapshot=excluded.source_snapshot""", (gift["id"],gift["name"],gift["diamondCount"],gift["primaryEffectId"],json.dumps(gift["assetIds"],ensure_ascii=False),json.dumps(gift["iconUrls"],ensure_ascii=False),json.dumps(gift["imageUrls"],ensure_ascii=False),json.dumps(gift["webpUrls"],ensure_ascii=False),payload_hash,timestamp,timestamp,timestamp,gift_snapshot))
                if is_new or changed:
                    result["giftResources"].extend((gift["id"], role, urls) for role, urls in (("icon", gift["iconUrls"]), ("image", gift["imageUrls"]), ("webp", gift["webpUrls"])) if urls)
            for effect in effects:
                payload_hash = _fingerprint(effect)
                old = db.execute("SELECT payload_hash FROM effect_catalog WHERE effect_id=?", (effect["id"],)).fetchone()
                is_new = old is None
                changed = not is_new and old["payload_hash"] != payload_hash
                if is_new:
                    result["newEffects"] += 1
                elif changed:
                    result["changedEffects"] += 1
                db.execute("""INSERT INTO effect_catalog (effect_id,name,resource_type,md5,resource_urls_json,format_265_urls_json,payload_hash,first_seen_at,last_seen_at,changed_at,source_snapshot) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(effect_id) DO UPDATE SET name=excluded.name,resource_type=excluded.resource_type,md5=excluded.md5,resource_urls_json=excluded.resource_urls_json,format_265_urls_json=excluded.format_265_urls_json,payload_hash=excluded.payload_hash,last_seen_at=excluded.last_seen_at,changed_at=CASE WHEN effect_catalog.payload_hash<>excluded.payload_hash THEN excluded.changed_at ELSE effect_catalog.changed_at END,source_snapshot=excluded.source_snapshot""", (effect["id"],effect["name"],effect["resourceType"],effect["md5"],json.dumps(effect["resourceUrls"],ensure_ascii=False),json.dumps(effect["format265Urls"],ensure_ascii=False),payload_hash,timestamp,timestamp,timestamp,effect_snapshot))
                if is_new or changed:
                    result["effectResources"].extend((effect["id"], role, urls) for role, urls in (("standard", effect["resourceUrls"]), ("format265", effect["format265Urls"])) if urls)
        return result

    async def _download_changed_resources(self, changes: dict) -> dict:
        config = self.config_provider().get("giftAssets") or {}
        downloads = []
        if bool(config.get("cacheGiftIcons", True)):
            downloads.extend(("gift", *item) for item in self._catalog_resources("gift"))
        if bool(config.get("cacheEffects", True)):
            downloads.extend(("effect", *item) for item in self._catalog_resources("effect"))
        result = {"icons": 0, "effects": 0, "failed": 0}
        if downloads:
            self._status.update({"state": "syncing", "message": f"Caching {len(downloads)} gift and effect resources"})
        timeout = ClientTimeout(total=180)
        async with ClientSession(timeout=timeout, headers={"User-Agent": signing_user_agent(), "Referer": "https://live.douyin.com/"}) as http:
            for start in range(0, len(downloads), 8):
                outcomes = await asyncio.gather(*(
                    self._cache_resource(http, kind, source_id, role, urls)
                    for kind, source_id, role, urls in downloads[start:start + 8]
                ))
                for (kind, _, _, _), downloaded in zip(downloads[start:start + 8], outcomes):
                    if downloaded == "ready":
                        result["icons" if kind == "gift" else "effects"] += 1
                    elif downloaded == "error":
                        result["failed"] += 1
        return result

    def _catalog_resources(self, kind: str) -> list[tuple[str, str, list[str]]]:
        resources: list[tuple[str, str, list[str]]] = []
        with self._db() as db:
            if kind == "gift":
                rows = db.execute("SELECT gift_id, icon_urls_json, image_urls_json, webp_urls_json FROM gift_catalog").fetchall()
                columns = (("icon", "icon_urls_json"), ("image", "image_urls_json"), ("webp", "webp_urls_json"))
                for row in rows:
                    for role, column in columns:
                        resources.append((row["gift_id"], role, self._stored_urls(row[column])))
            elif kind == "effect":
                rows = db.execute("SELECT effect_id, resource_urls_json, format_265_urls_json FROM effect_catalog").fetchall()
                columns = (("standard", "resource_urls_json"), ("format265", "format_265_urls_json"))
                for row in rows:
                    for role, column in columns:
                        resources.append((row["effect_id"], role, self._stored_urls(row[column])))
        return [item for item in resources if item[2]]

    @staticmethod
    def _stored_urls(value: Any) -> list[str]:
        try:
            parsed = json.loads(_text(value))
        except json.JSONDecodeError:
            return []
        return [_text(item) for item in parsed if _text(item)] if isinstance(parsed, list) else []

    async def _cache_resource(self, http: ClientSession, kind: str, source_id: str, role: str, urls: list[str]) -> str:
        url = urls[0] if urls else ""
        if not url:
            return "skipped"
        extension = Path(urllib.parse.urlparse(url).path).suffix or (".zip" if kind == "effect" else ".png")
        safe_role = re.sub(r"[^A-Za-z0-9_-]", "_", role)
        relative = Path("cache") / ("effects" if kind == "effect" else "gift_icons") / f"{source_id}_{safe_role}{extension}"
        path = self.root / relative
        timestamp = _now_ms()
        with self._db() as db:
            existing = db.execute("SELECT url, local_path, status FROM asset_cache WHERE asset_kind=? AND source_id=? AND role=?", (kind, source_id, role)).fetchone()
            if existing and existing["url"] == url and existing["status"] == "ready" and (self.root / existing["local_path"]).exists():
                db.execute("UPDATE asset_cache SET last_seen_at=? WHERE asset_kind=? AND source_id=? AND role=?", (timestamp, kind, source_id, role))
                return "skipped"
        try:
            payload = b""
            last_error = ""
            for candidate in urls:
                try:
                    async with http.get(candidate) as response:
                        if response.status < 400:
                            payload = await response.read()
                            if payload:
                                url = candidate
                                break
                        last_error = f"HTTP {response.status}"
                except Exception as error:
                    last_error = str(error)
            if not payload:
                raise RuntimeError(last_error or "empty resource response")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            with self._db() as db:
                db.execute("""INSERT INTO asset_cache (asset_kind,source_id,role,url,local_path,content_sha256,size_bytes,first_seen_at,last_seen_at,downloaded_at,status,last_error) VALUES (?,?,?,?,?,?,?,?,?,?,?,'') ON CONFLICT(asset_kind,source_id,role) DO UPDATE SET url=excluded.url,local_path=excluded.local_path,content_sha256=excluded.content_sha256,size_bytes=excluded.size_bytes,last_seen_at=excluded.last_seen_at,downloaded_at=excluded.downloaded_at,status=excluded.status,last_error=''""", (kind,source_id,role,url,str(relative).replace("\\", "/"),digest,len(payload),timestamp,timestamp,timestamp,"ready"))
            return "ready"
        except Exception as error:
            with self._db() as db:
                db.execute("""INSERT INTO asset_cache (asset_kind,source_id,role,url,local_path,first_seen_at,last_seen_at,status,last_error) VALUES (?,?,?,?,?,?,?,'error',?) ON CONFLICT(asset_kind,source_id,role) DO UPDATE SET url=excluded.url,last_seen_at=excluded.last_seen_at,status='error',last_error=excluded.last_error""", (kind,source_id,role,url,str(relative).replace("\\", "/"),timestamp,timestamp,str(error)))
            return "error"

    def _start_run(self, started: int) -> int:
        with self._db() as db:
            cursor = db.execute("INSERT INTO catalog_runs (started_at) VALUES (?)", (started,))
            return int(cursor.lastrowid)

    def _finish_run(self, run_id: int, status: str, result: dict, error: str) -> None:
        with self._db() as db:
            db.execute("""UPDATE catalog_runs SET completed_at=?,status=?,gift_snapshot=?,effect_snapshot=?,new_gifts=?,changed_gifts=?,new_effects=?,changed_effects=?,downloaded_icons=?,downloaded_effects=?,error=? WHERE id=?""", (_now_ms(),status,_text(result.get("giftSnapshot")),_text(result.get("effectSnapshot")),_number(result.get("newGifts")),_number(result.get("changedGifts")),_number(result.get("newEffects")),_number(result.get("changedEffects")),_number((result.get("downloaded") or {}).get("icons")),_number((result.get("downloaded") or {}).get("effects")),error,run_id))
