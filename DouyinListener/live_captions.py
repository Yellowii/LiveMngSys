"""Windows Live Captions reader used by the listener service."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable


class LiveCaptionCapture:
    """Capture stable text from the Windows Live Captions accessibility tree."""

    def __init__(self, archive_root: Path, on_change: Callable[[], None] | None = None):
        self.archive_root = archive_root
        self.on_change = on_change
        self.config = {
            "enabled": False,
            "outputToLiveUi": True,
            "persist": False,
            "fallbackEnabled": False,
            "fallbackTimeoutSeconds": 300,
            "showIdleOnTimeout": False,
        }
        self.task: asyncio.Task | None = None
        self.state = {
            "state": "disabled",
            "message": "实时字幕未启用",
            "text": "",
            "updatedAt": 0,
            "revision": 0,
            "source": "Windows 实时辅助字幕",
        }

    def snapshot(self) -> dict:
        return {**self.state, **self.config}

    async def configure(self, config: dict) -> None:
        previous_enabled = self.config["enabled"]
        try:
            fallback_timeout = int(config.get("fallbackTimeoutSeconds", 300))
        except (TypeError, ValueError):
            fallback_timeout = 300
        self.config = {
            "enabled": bool(config.get("enabled", False)),
            "outputToLiveUi": bool(config.get("outputToLiveUi", True)),
            "persist": bool(config.get("persist", False)),
            "fallbackEnabled": bool(config.get("fallbackEnabled", False)),
            "fallbackTimeoutSeconds": max(5, min(3600, fallback_timeout)),
            "showIdleOnTimeout": bool(config.get("showIdleOnTimeout", False)),
        }
        if not self.config["enabled"]:
            await self.stop()
            self.state.update({"text": "", "updatedAt": 0, "revision": int(self.state["revision"]) + 1})
            self._set_state("disabled", "实时字幕未启用")
        elif not previous_enabled or not self.task or self.task.done():
            self._set_state("starting", "正在连接 Windows 实时辅助字幕")
            self.task = asyncio.create_task(self._run(), name="windows-live-captions")
        else:
            self._notify()

    async def stop(self) -> None:
        task = self.task
        self.task = None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def process_text(self, text: str, now_ms: int | None = None) -> str | None:
        """Publish the newest Windows caption line as soon as it changes."""
        candidate = self._caption_candidate(text)
        if not candidate:
            return None
        if candidate == self.state["text"]:
            return None

        now_ms = now_ms or int(time.time() * 1000)
        self.state.update({
            "state": "connected",
            "message": "正在获取实时字幕",
            "text": candidate,
            "updatedAt": now_ms,
            "revision": int(self.state["revision"]) + 1,
        })
        self._notify()
        return candidate

    async def _run(self) -> None:
        while self.config["enabled"]:
            try:
                text, found = await asyncio.to_thread(self._read_caption_window)
                if not found:
                    self._set_state("waiting", "未检测到 Windows 实时辅助字幕")
                    await asyncio.sleep(2)
                    continue
                if self.state["state"] in {"starting", "waiting", "unavailable"}:
                    self._set_state("connected", "等待字幕内容")
                accepted = self.process_text(text)
                if accepted and self.config["persist"]:
                    await asyncio.to_thread(self._append_archive, accepted)
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                raise
            except ImportError:
                self._set_state("unavailable", "缺少 Windows 字幕采集组件")
                await asyncio.sleep(5)
            except Exception:
                self._set_state("waiting", "等待 Windows 实时辅助字幕")
                await asyncio.sleep(2)

    @staticmethod
    def _read_caption_window() -> tuple[str, bool]:
        try:
            import uiautomation as auto
        except ImportError:
            raise
        auto.SetGlobalSearchTimeout(0.08)
        desktop = auto.GetRootControl()
        captions_window = desktop.Control(searchDepth=1, ClassName="LiveCaptionsDesktopWindow", timeout=0.05)
        if not captions_window.Exists(0):
            return "", False
        scrollviewer = captions_window.Control(searchDepth=5, AutomationId="CaptionsScrollViewer", ClassName="ScrollViewer", timeout=0.05)
        return str(scrollviewer.Name or "").strip(), True

    def _set_state(self, state: str, message: str) -> None:
        if self.state["state"] == state and self.state["message"] == message:
            return
        self.state.update({"state": state, "message": message})
        self._notify()

    def _append_archive(self, text: str) -> None:
        self.archive_root.mkdir(parents=True, exist_ok=True)
        archive = self.archive_root / f"{time.strftime('%Y-%m-%d')}_captions.txt"
        timestamp = time.strftime("%H:%M:%S")
        with archive.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {text}\n")

    @staticmethod
    def _caption_candidate(text: str) -> str:
        lines = [" ".join(line.split()) for line in str(text or "").splitlines() if line.strip()]
        return lines[-1][-240:] if lines else ""

    def _notify(self) -> None:
        if self.on_change:
            self.on_change()
