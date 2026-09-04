"""Persistent fan records derived from normalized live events."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


TRACKED_FIELDS = (
    "nickname",
    "display_id",
    "sec_uid",
    "avatar",
    "gender",
    "signature",
    "fans_club_name",
    "fans_club_level",
    "badges_json",
)


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _image_url(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    urls = value.get("urlList") or value.get("url_list") or []
    if isinstance(urls, list) and urls:
        return _text(urls[0])
    return _text(value.get("url") or value.get("uri"))


def _number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class FanDatabase:
    """SQLite fan database with stable identities and append-only field history."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=8)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 8000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._lock, self._connection() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("PRAGMA synchronous = NORMAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS fans (
                    identity TEXT PRIMARY KEY,
                    uid TEXT NOT NULL DEFAULT '',
                    sec_uid TEXT NOT NULL DEFAULT '',
                    display_id TEXT NOT NULL DEFAULT '',
                    nickname TEXT NOT NULL DEFAULT '',
                    avatar TEXT NOT NULL DEFAULT '',
                    gender TEXT NOT NULL DEFAULT '',
                    signature TEXT NOT NULL DEFAULT '',
                    fans_club_name TEXT NOT NULL DEFAULT '',
                    fans_club_level INTEGER NOT NULL DEFAULT 0,
                    badges_json TEXT NOT NULL DEFAULT '[]',
                    is_mystery INTEGER NOT NULL DEFAULT 0,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    last_room_id TEXT NOT NULL DEFAULT '',
                    last_session_id TEXT NOT NULL DEFAULT '',
                    event_count INTEGER NOT NULL DEFAULT 0,
                    chat_count INTEGER NOT NULL DEFAULT 0,
                    gift_count INTEGER NOT NULL DEFAULT 0,
                    like_count INTEGER NOT NULL DEFAULT 0,
                    follow_count INTEGER NOT NULL DEFAULT 0
                    ,member_status TEXT NOT NULL DEFAULT ''
                    ,member_type TEXT NOT NULL DEFAULT ''
                    ,member_expire_at INTEGER NOT NULL DEFAULT 0
                    ,guardian_status TEXT NOT NULL DEFAULT ''
                    ,guardian_type TEXT NOT NULL DEFAULT ''
                    ,guardian_expire_at INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS fan_database_meta (
                    meta_key TEXT PRIMARY KEY,
                    meta_value TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fan_field_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity TEXT NOT NULL REFERENCES fans(identity) ON DELETE CASCADE,
                    field_name TEXT NOT NULL,
                    previous_value TEXT NOT NULL DEFAULT '',
                    current_value TEXT NOT NULL DEFAULT '',
                    changed_at INTEGER NOT NULL,
                    room_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    method TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS mystery_users (
                    identity TEXT PRIMARY KEY REFERENCES fans(identity) ON DELETE CASCADE,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    last_nickname TEXT NOT NULL DEFAULT '',
                    last_room_id TEXT NOT NULL DEFAULT '',
                    last_session_id TEXT NOT NULL DEFAULT '',
                    observation_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS fan_session_sightings (
                    identity TEXT NOT NULL REFERENCES fans(identity) ON DELETE CASCADE,
                    room_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    event_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(identity, room_id, session_id)
                );

                CREATE TABLE IF NOT EXISTS fan_interaction_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity TEXT NOT NULL REFERENCES fans(identity) ON DELETE CASCADE,
                    event_time INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    source_method TEXT NOT NULL DEFAULT '',
                    room_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS fan_member_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity TEXT NOT NULL REFERENCES fans(identity) ON DELETE CASCADE,
                    member_type TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL DEFAULT 'update',
                    event_time INTEGER NOT NULL,
                    expire_at INTEGER NOT NULL DEFAULT 0,
                    source_method TEXT NOT NULL DEFAULT '',
                    room_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS fan_star_guardian_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity TEXT NOT NULL REFERENCES fans(identity) ON DELETE CASCADE,
                    guardian_type TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL DEFAULT 'update',
                    event_time INTEGER NOT NULL,
                    expire_at INTEGER NOT NULL DEFAULT 0,
                    source_method TEXT NOT NULL DEFAULT '',
                    room_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_fans_last_seen ON fans(last_seen_at DESC);
                CREATE INDEX IF NOT EXISTS idx_fans_mystery ON fans(is_mystery, last_seen_at DESC);
                CREATE INDEX IF NOT EXISTS idx_fan_changes_identity ON fan_field_changes(identity, changed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_fan_sightings_session ON fan_session_sightings(room_id, session_id);
                CREATE INDEX IF NOT EXISTS idx_fan_interactions_identity ON fan_interaction_records(identity, event_time DESC);
                CREATE INDEX IF NOT EXISTS idx_fan_members_identity ON fan_member_records(identity, event_time DESC);
                CREATE INDEX IF NOT EXISTS idx_fan_guardians_identity ON fan_star_guardian_records(identity, event_time DESC);
                """
            )
            for column, definition in (
                ("member_status", "TEXT NOT NULL DEFAULT ''"),
                ("member_type", "TEXT NOT NULL DEFAULT ''"),
                ("member_expire_at", "INTEGER NOT NULL DEFAULT 0"),
                ("guardian_status", "TEXT NOT NULL DEFAULT ''"),
                ("guardian_type", "TEXT NOT NULL DEFAULT ''"),
                ("guardian_expire_at", "INTEGER NOT NULL DEFAULT 0"),
            ):
                existing_columns = {row[1] for row in db.execute("PRAGMA table_info(fans)").fetchall()}
                if column not in existing_columns:
                    db.execute(f"ALTER TABLE fans ADD COLUMN {column} {definition}")

    def set_anchor_metadata(self, metadata: dict[str, str]) -> None:
        timestamp = _now_ms()
        with self._lock, self._connection() as db:
            for key, value in metadata.items():
                db.execute(
                    """
                    INSERT INTO fan_database_meta (meta_key, meta_value, updated_at) VALUES (?, ?, ?)
                    ON CONFLICT(meta_key) DO UPDATE SET meta_value=excluded.meta_value, updated_at=excluded.updated_at
                    """,
                    (_text(key), _text(value), timestamp),
                )

    def metadata(self) -> dict[str, str]:
        with self._lock, self._connection() as db:
            rows = db.execute("SELECT meta_key, meta_value FROM fan_database_meta").fetchall()
        return {_text(row["meta_key"]): _text(row["meta_value"]) for row in rows}

    def observe_event(self, event: dict | None, record: dict, room: dict, session_id: str = "") -> None:
        if not event:
            return
        timestamp = _number(record.get("ts")) or _now_ms()
        method = _text(record.get("method"))
        room_id = _text(room.get("id"))
        users = self._event_users(event, record)
        if not users:
            return
        with self._lock, self._connection() as db:
            for user in users:
                identity = self._observe_user(db, user, timestamp, room_id, session_id, method, _text(event.get("kind")))
                self._record_event_history(db, identity, event, record, timestamp, room_id, session_id, method)

    def _event_users(self, event: dict, record: dict) -> list[dict]:
        candidates: list[dict] = []

        def add(value: Any) -> None:
            if isinstance(value, dict):
                candidates.append(value)

        for key in ("user", "sender"):
            add(event.get(key))
        for key in ("participants", "winners"):
            for item in event.get(key) or []:
                add(item)

        parsed = record.get("parsed") if isinstance(record.get("parsed"), dict) else {}
        for key in ("user", "anchor", "fromUser", "toUser"):
            add(parsed.get(key))
        common = parsed.get("common") if isinstance(parsed.get("common"), dict) else {}
        add(common.get("user"))
        for container in (parsed, parsed.get("data") if isinstance(parsed.get("data"), dict) else {}):
            for key in ("ranks", "audienceRanks", "rankList", "seats", "latestGuestUser"):
                for item in container.get(key) or []:
                    if isinstance(item, dict):
                        add(item.get("user") or item)

        seen: set[str] = set()
        users = []
        for item in candidates:
            normalized = self._normalize_user(item)
            identity = normalized.get("identity") or ""
            if not identity or identity in seen:
                continue
            seen.add(identity)
            users.append(normalized)
        return users

    def _normalize_user(self, user: dict) -> dict:
        uid = _text(user.get("id") or user.get("idStr") or user.get("userIdStr") or user.get("userId"))
        sec_uid = _text(user.get("secUid") or user.get("sec_uid") or user.get("secUserId"))
        display_id = _text(user.get("displayId") or user.get("display_id") or user.get("uniqueId") or user.get("shortId"))
        identity = uid or (f"sec:{sec_uid}" if sec_uid else (f"display:{display_id}" if display_id else ""))
        club = user.get("fansClub") if isinstance(user.get("fansClub"), dict) else {}
        club = club.get("data") if isinstance(club.get("data"), dict) else club
        nickname = _text(user.get("nickname") or user.get("nickName") or user.get("userName"))
        lowered = nickname.lower()
        mystery = any(bool(user.get(key)) for key in ("isMystery", "isMysteryUser", "isAnonymous", "isAnonym"))
        mystery = mystery or "mystery" in lowered or "anonymous" in lowered or "\u795e\u79d8\u4eba" in nickname
        if nickname == "\u533f\u540d\u89c2\u4f17":
            mystery = False
        badges = user.get("badges") if isinstance(user.get("badges"), list) else []
        return {
            "identity": identity,
            "uid": uid,
            "sec_uid": sec_uid,
            "display_id": display_id,
            "nickname": nickname,
            "avatar": _image_url(user.get("avatar") or user.get("avatarUrl")),
            "gender": _text(user.get("gender")),
            "signature": _text(user.get("signature")),
            "fans_club_name": _text(club.get("name") or club.get("clubName")),
            "fans_club_level": _number(club.get("level")),
            "badges_json": json.dumps(badges, ensure_ascii=False, sort_keys=True),
            "is_mystery": mystery,
        }

    def _resolve_identity(self, db: sqlite3.Connection, user: dict) -> str:
        identity = user["identity"]
        row = db.execute(
            """
            SELECT identity FROM fans
            WHERE identity = ? OR (? <> '' AND uid = ?) OR (? <> '' AND sec_uid = ?) OR (? <> '' AND display_id = ?)
            LIMIT 1
            """,
            (identity, user["uid"], user["uid"], user["sec_uid"], user["sec_uid"], user["display_id"], user["display_id"]),
        ).fetchone()
        return _text(row["identity"]) if row else identity

    def _observe_user(
        self,
        db: sqlite3.Connection,
        user: dict,
        timestamp: int,
        room_id: str,
        session_id: str,
        method: str,
        event_kind: str,
    ) -> str:
        identity = self._resolve_identity(db, user)
        existing = db.execute("SELECT * FROM fans WHERE identity = ?", (identity,)).fetchone()
        if existing is None:
            db.execute(
                """
                INSERT INTO fans (
                    identity, uid, sec_uid, display_id, nickname, avatar, gender, signature,
                    fans_club_name, fans_club_level, badges_json, is_mystery, first_seen_at,
                    last_seen_at, last_room_id, last_session_id, event_count, chat_count,
                    gift_count, like_count, follow_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    identity, user["uid"], user["sec_uid"], user["display_id"], user["nickname"],
                    user["avatar"], user["gender"], user["signature"], user["fans_club_name"],
                    user["fans_club_level"], user["badges_json"], int(user["is_mystery"]), timestamp,
                    timestamp, room_id, session_id, int(event_kind == "chat"), int(event_kind == "gift"),
                    int(event_kind == "like"), int(event_kind == "follow"),
                ),
            )
        else:
            changes = {}
            for field in TRACKED_FIELDS:
                incoming = user.get(field)
                previous = existing[field]
                if incoming in (None, "", 0, "[]") or str(incoming) == str(previous):
                    continue
                changes[field] = incoming
                db.execute(
                    """
                    INSERT INTO fan_field_changes (identity, field_name, previous_value, current_value, changed_at, room_id, session_id, method)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (identity, field, _text(previous), _text(incoming), timestamp, room_id, session_id, method),
                )
            assignments = {
                "uid": user["uid"] or existing["uid"],
                "sec_uid": user["sec_uid"] or existing["sec_uid"],
                "display_id": user["display_id"] or existing["display_id"],
                "nickname": user["nickname"] or existing["nickname"],
                "avatar": user["avatar"] or existing["avatar"],
                "gender": user["gender"] or existing["gender"],
                "signature": user["signature"] or existing["signature"],
                "fans_club_name": user["fans_club_name"] or existing["fans_club_name"],
                "fans_club_level": user["fans_club_level"] or existing["fans_club_level"],
                "badges_json": user["badges_json"] if user["badges_json"] != "[]" else existing["badges_json"],
            }
            db.execute(
                """
                UPDATE fans SET uid=?, sec_uid=?, display_id=?, nickname=?, avatar=?, gender=?, signature=?,
                    fans_club_name=?, fans_club_level=?, badges_json=?, is_mystery=?, last_seen_at=?,
                    last_room_id=?, last_session_id=?, event_count=event_count + 1,
                    chat_count=chat_count + ?, gift_count=gift_count + ?, like_count=like_count + ?, follow_count=follow_count + ?
                WHERE identity=?
                """,
                (
                    assignments["uid"], assignments["sec_uid"], assignments["display_id"], assignments["nickname"],
                    assignments["avatar"], assignments["gender"], assignments["signature"], assignments["fans_club_name"],
                    assignments["fans_club_level"], assignments["badges_json"], int(bool(existing["is_mystery"]) or user["is_mystery"]),
                    timestamp, room_id, session_id, int(event_kind == "chat"), int(event_kind == "gift"),
                    int(event_kind == "like"), int(event_kind == "follow"), identity,
                ),
            )

        is_mystery = bool(user["is_mystery"]) or bool(existing and existing["is_mystery"])
        if is_mystery:
            db.execute(
                """
                INSERT INTO mystery_users (identity, first_seen_at, last_seen_at, last_nickname, last_room_id, last_session_id, observation_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(identity) DO UPDATE SET last_seen_at=excluded.last_seen_at,
                    last_nickname=CASE WHEN excluded.last_nickname <> '' THEN excluded.last_nickname ELSE mystery_users.last_nickname END,
                    last_room_id=excluded.last_room_id, last_session_id=excluded.last_session_id,
                    observation_count=mystery_users.observation_count + 1
                """,
                (identity, timestamp, timestamp, user["nickname"], room_id, session_id),
            )

        db.execute(
            """
            INSERT INTO fan_session_sightings (identity, room_id, session_id, first_seen_at, last_seen_at, event_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(identity, room_id, session_id) DO UPDATE SET last_seen_at=excluded.last_seen_at,
                event_count=fan_session_sightings.event_count + 1
            """,
            (identity, room_id, session_id, timestamp, timestamp),
        )
        return identity

    def _record_event_history(
        self,
        db: sqlite3.Connection,
        identity: str,
        event: dict,
        record: dict,
        timestamp: int,
        room_id: str,
        session_id: str,
        method: str,
    ) -> None:
        kind = _text(event.get("kind"))
        if kind not in {"audience", "room", "state", "membership_snapshot"}:
            action = _text(event.get("label") or event.get("content") or kind or method)
            db.execute(
                """
                INSERT INTO fan_interaction_records (identity, event_time, action, source_method, room_id, session_id, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (identity, timestamp, action[:120], method, room_id, session_id, _text(event.get("content"))[:400]),
            )

        if kind != "membership":
            return
        parsed = record.get("parsed") if isinstance(record.get("parsed"), dict) else {}
        member_type = _text(event.get("membership") or event.get("membershipLabel") or event.get("memberType") or parsed.get("memberType"))
        event_type = _text(event.get("operation") or event.get("membershipAction") or event.get("action") or parsed.get("action") or "update")
        expire_at = _number(event.get("expireAt") or event.get("expireTime") or parsed.get("expireTime") or parsed.get("expireAt"))
        target = "fan_star_guardian_records" if _text(event.get("memberType") or parsed.get("memberType")) == "4" or "guard" in member_type.lower() or "守护" in member_type else "fan_member_records"
        if target.endswith("guardian_records"):
            member_type = _text(event.get("guardianPeriod") or event.get("guardianPeriodLabel") or member_type)
        db.execute(
            f"""
            INSERT INTO {target} (identity, {"guardian_type" if target.endswith("guardian_records") else "member_type"}, event_type, event_time, expire_at, source_method, room_id, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (identity, member_type, event_type, timestamp, expire_at, method, room_id, session_id),
        )
        is_guardian = target.endswith("guardian_records")
        operation = _text(event.get("operation") or event.get("membershipAction") or "open")
        status = "已过期" if operation == "cancel" else "有效"
        if is_guardian:
            db.execute(
                "UPDATE fans SET guardian_status=?, guardian_type=?, guardian_expire_at=? WHERE identity=?",
                (status, member_type, expire_at, identity),
            )
        else:
            db.execute(
                "UPDATE fans SET member_status=?, member_type=?, member_expire_at=? WHERE identity=?",
                (status, member_type, expire_at, identity),
            )

    def list_fans(
        self,
        query: str = "",
        mystery: str = "all",
        min_level: int = 0,
        member_status: str = "",
        guardian_status: str = "",
        sort: str = "recent",
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        limit = max(1, min(int(limit or 100), 300))
        offset = max(0, int(offset or 0))
        where: list[str] = []
        params: list[Any] = []
        query = _text(query)
        if query:
            like = f"%{query}%"
            where.append("(identity LIKE ? OR uid LIKE ? OR sec_uid LIKE ? OR display_id LIKE ? OR nickname LIKE ? OR fans_club_name LIKE ?)")
            params.extend([like] * 6)
        if mystery == "only":
            where.append("is_mystery = 1")
        elif mystery == "exclude":
            where.append("is_mystery = 0")
        if _number(min_level) > 0:
            where.append("fans_club_level >= ?")
            params.append(_number(min_level))
        if _text(member_status):
            where.append("member_status = ?")
            params.append(_text(member_status))
        if _text(guardian_status):
            where.append("guardian_status = ?")
            params.append(_text(guardian_status))
        condition = f"WHERE {' AND '.join(where)}" if where else ""
        order_by = {
            "level": "fans_club_level DESC, last_seen_at DESC, identity ASC",
            "chat": "chat_count DESC, last_seen_at DESC, identity ASC",
            "gift": "gift_count DESC, last_seen_at DESC, identity ASC",
            "name": "nickname COLLATE NOCASE ASC, last_seen_at DESC, identity ASC",
        }.get(_text(sort), "last_seen_at DESC, identity ASC")
        with self._lock, self._connection() as db:
            total = db.execute(f"SELECT COUNT(*) FROM fans {condition}", params).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM fans {condition} ORDER BY {order_by} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            stats = db.execute(
                """
                SELECT COUNT(*) AS total, SUM(is_mystery) AS mystery, SUM(chat_count) AS chats, SUM(gift_count) AS gifts,
                       SUM(CASE WHEN fans_club_level >= 10 THEN 1 ELSE 0 END) AS level_10_plus,
                       SUM(CASE WHEN member_status = '有效' THEN 1 ELSE 0 END) AS active_members,
                       SUM(CASE WHEN guardian_status = '有效' THEN 1 ELSE 0 END) AS active_guardians
                FROM fans
                """
            ).fetchone()
        return {
            "items": [dict(row) for row in rows],
            "total": int(total),
            "limit": limit,
            "offset": offset,
            "stats": {key: int(stats[key] or 0) for key in ("total", "mystery", "chats", "gifts", "level_10_plus", "active_members", "active_guardians")},
        }

    def fan_detail(self, identity: str) -> dict | None:
        with self._lock, self._connection() as db:
            fan = db.execute("SELECT * FROM fans WHERE identity = ?", (_text(identity),)).fetchone()
            if not fan:
                return None
            changes = db.execute(
                "SELECT field_name, previous_value, current_value, changed_at, room_id, session_id, method FROM fan_field_changes WHERE identity = ? ORDER BY changed_at DESC, id DESC LIMIT 200",
                (_text(identity),),
            ).fetchall()
            sessions = db.execute(
                "SELECT room_id, session_id, first_seen_at, last_seen_at, event_count FROM fan_session_sightings WHERE identity = ? ORDER BY last_seen_at DESC LIMIT 100",
                (_text(identity),),
            ).fetchall()
            interactions = db.execute(
                "SELECT event_time, action, source_method, room_id, session_id, note FROM fan_interaction_records WHERE identity = ? ORDER BY event_time DESC, id DESC LIMIT 200",
                (_text(identity),),
            ).fetchall()
            members = db.execute(
                "SELECT member_type, event_type, event_time, expire_at, source_method FROM fan_member_records WHERE identity = ? ORDER BY event_time DESC, id DESC LIMIT 100",
                (_text(identity),),
            ).fetchall()
            guardians = db.execute(
                "SELECT guardian_type, event_type, event_time, expire_at, source_method FROM fan_star_guardian_records WHERE identity = ? ORDER BY event_time DESC, id DESC LIMIT 100",
                (_text(identity),),
            ).fetchall()
        return {
            "fan": dict(fan),
            "changes": [dict(row) for row in changes],
            "sessions": [dict(row) for row in sessions],
            "interactions": [dict(row) for row in interactions],
            "members": [dict(row) for row in members],
            "guardians": [dict(row) for row in guardians],
        }


def _safe_database_key(value: Any) -> str:
    value = _text(value)
    value = re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._-")
    return value[:120] or "unknown-anchor"


class FanDatabaseRegistry:
    """Open one LiveDash-style fan database per stable anchor identity."""

    def __init__(self, root: Path):
        self.root = Path(root) / "anchors"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._databases: dict[str, FanDatabase] = {}

    @staticmethod
    def anchor_key(room: dict | None, config: dict | None = None) -> str:
        room = room if isinstance(room, dict) else {}
        config = config if isinstance(config, dict) else {}
        anchor = room.get("anchor") if isinstance(room.get("anchor"), dict) else {}
        stable = (
            anchor.get("id")
            or anchor.get("secUid")
            or room.get("secAnchorId")
            or room.get("anchorId")
            or config.get("anchorId")
            or anchor.get("displayId")
            or anchor.get("nickname")
            or "unknown-anchor"
        )
        return _safe_database_key(stable)

    def get(self, room: dict | None = None, config: dict | None = None) -> FanDatabase:
        key = self.anchor_key(room, config)
        with self._lock:
            database = self._databases.get(key)
            if database is None:
                database = FanDatabase(self.root / f"{key}.sqlite3")
                self._databases[key] = database
            room = room if isinstance(room, dict) else {}
            anchor = room.get("anchor") if isinstance(room.get("anchor"), dict) else {}
            database.set_anchor_metadata({
                "anchor_key": key,
                "anchor_id": anchor.get("id") or room.get("anchorId") or (config or {}).get("anchorId", ""),
                "sec_anchor_id": anchor.get("secUid") or room.get("secAnchorId") or "",
                "display_id": anchor.get("displayId") or "",
                "nickname": anchor.get("nickname") or room.get("roomName") or "",
                "room_id": room.get("id") or (config or {}).get("roomId", ""),
            })
            return database

    def list_databases(self) -> list[dict[str, Any]]:
        rows = []
        for path in sorted(self.root.glob("*.sqlite3"), key=lambda item: item.stat().st_mtime, reverse=True):
            key = path.stem
            database = self.get({"anchor": {"id": key}})
            metadata = database.metadata()
            listing = database.list_fans(limit=1)
            rows.append({"key": key, "path": str(path), "metadata": metadata, "total": listing["stats"]["total"]})
        return rows
