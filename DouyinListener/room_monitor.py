"""Independent multi-room live-status monitoring."""
from __future__ import annotations
import asyncio
import time
from copy import deepcopy
from typing import Awaitable, Callable

Probe = Callable[[str], Awaitable[dict]]

class RoomMonitorRegistry:
    """Probe multiple rooms without sharing a barrage EventStore/session."""
    def __init__(self, probe: Probe, interval: float = 30.0) -> None:
        self._probe, self._interval = probe, max(1.0, float(interval))
        self._rooms: dict[str, dict] = {}
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(room: dict) -> str:
        return str(room.get("roomId") or room.get("roomUrl") or "").strip()

    async def configure(self, rooms: list[dict]) -> None:
        normalized = {}
        for room in rooms or []:
            if not isinstance(room, dict): continue
            key = self._key(room)
            if key:
                normalized[key] = {"roomId": str(room.get("roomId") or "").strip(), "roomUrl": str(room.get("roomUrl") or "").strip(), "enabled": room.get("enabled", True), "roomState": "unknown", "lastCheckedAt": 0}
        async with self._lock: self._rooms = normalized

    def snapshot(self) -> list[dict]: return deepcopy(list(self._rooms.values()))

    async def poll_once(self) -> list[dict]:
        async with self._lock: rooms = list(self._rooms.values())
        async def check(room):
            if room.get("enabled") is not False:
                try: room.update(await self._probe(str(room.get("roomId") or room.get("roomUrl"))))
                except Exception as error: room.update({"roomState": "unknown", "error": str(error)})
            room["lastCheckedAt"] = int(time.time() * 1000)
            return room
        checked = await asyncio.gather(*(check(room) for room in rooms))
        async with self._lock: self._rooms = {self._key(room): room for room in checked}
        return self.snapshot()

    async def run(self) -> None:
        while True:
            await self.poll_once(); await asyncio.sleep(self._interval)

    async def start(self) -> None:
        if not self._task or self._task.done(): self._task = asyncio.create_task(self.run(), name="douyin-multi-room-monitor")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task and not task.done(): task.cancel(); await asyncio.gather(task, return_exceptions=True)
