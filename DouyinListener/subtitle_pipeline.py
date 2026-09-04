"""Orchestrates partial/final ASR captions, cleaning, and final-only translation."""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from typing import Any, Callable

from aiohttp import ClientSession, ClientTimeout

from speech_services import SpeechServiceError, SpeechServices


class SubtitlePipeline:
    def __init__(self, config_provider: Callable[[], dict], speech: SpeechServices, on_update: Callable[[], None] | None = None):
        self.config_provider = config_provider
        self.speech = speech
        self.on_update = on_update
        self.task: asyncio.Task | None = None
        self.translation_tasks: set[asyncio.Task] = set()
        self.http: ClientSession | None = None
        self.last_asr_revision = -1
        self.last_final_revision = 0
        self.history: deque[dict] = deque(maxlen=100)
        self.state = {
            "state": "idle", "message": "等待启动实时识别", "deviceId": None, "deviceName": "",
            "partial": "", "final": "", "cleaned": "", "translation": "",
            "revision": 0, "finalRevision": 0, "translationRevision": 0,
            "updatedAt": 0, "lastFinalAt": 0, "asrError": "", "translationError": "",
        }

    def _config(self) -> dict:
        return self.config_provider().get("speech") or {}

    def snapshot(self) -> dict:
        return {**self.state, "history": list(self.history)}

    def _update(self, **values: Any) -> None:
        changed = any(self.state.get(key) != value for key, value in values.items())
        self.state.update(values)
        if changed:
            self.state["revision"] += 1
            self.state["updatedAt"] = int(time.time() * 1000)
            if self.on_update:
                self.on_update()

    @staticmethod
    def clean_final(text: str, config: dict) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        cleaned = re.sub(r"(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff])", "", cleaned)
        cleaned = re.sub(r"\s*([，。！？、；：,.!?;:])\s*", r"\1", cleaned)
        if not config.get("enabled", True):
            return cleaned
        fillers = [re.escape(str(item).strip()) for item in config.get("fillerWords", []) if str(item).strip()]
        if fillers:
            pattern = "|".join(sorted(fillers, key=len, reverse=True))
            cleaned = re.sub(rf"^(?:(?:{pattern})[，,。.!！？?、]*)+", "", cleaned)
            cleaned = re.sub(rf"[，,、]*(?:(?:{pattern})[。.!！？?]*)+$", "", cleaned)
        visible = re.sub(r"[\W_]+", "", cleaned, flags=re.UNICODE)
        return cleaned if len(visible) >= int(config.get("minCharacters", 3)) else ""

    async def start(self) -> None:
        if self.task and not self.task.done():
            return
        self.http = self.http or ClientSession(timeout=ClientTimeout(total=5))
        self.task = asyncio.create_task(self._poll_loop(), name="subtitle-pipeline")

    async def stop(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
        for translation_task in self.translation_tasks:
            translation_task.cancel()
        if self.translation_tasks:
            await asyncio.gather(*self.translation_tasks, return_exceptions=True)
        self.translation_tasks.clear()
        if self.http and not self.http.closed:
            await self.http.close()
        self.http = None

    async def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        if not self.http or self.http.closed:
            self.http = ClientSession(timeout=ClientTimeout(total=5))
        url = self._config().get("asrServiceUrl", "http://127.0.0.1:7003").rstrip("/") + path
        async with self.http.request(method, url, json=body) as response:
            result = await response.json()
            if not response.ok or not result.get("ok", True):
                raise RuntimeError(result.get("message") or f"ASR service HTTP {response.status}")
            return result

    async def devices(self) -> list[dict]:
        return (await self._request("GET", "/devices")).get("devices") or []

    async def start_capture(self, device_id: Any) -> dict:
        result = await self._request("POST", "/start", {"deviceId": device_id})
        await self._consume(result.get("state") or {})
        return self.snapshot()

    async def stop_capture(self) -> dict:
        result = await self._request("POST", "/stop", {})
        await self._consume(result.get("state") or {})
        return self.snapshot()

    async def _poll_loop(self) -> None:
        while True:
            try:
                result = await self._request("GET", "/state")
                await self._consume(result.get("state") or {})
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._update(state="unavailable", message="ASR 独立进程不可用", asrError=str(error))
            await asyncio.sleep(0.15)

    async def _consume(self, asr: dict) -> None:
        revision = int(asr.get("revision") or 0)
        if revision != self.last_asr_revision:
            self.last_asr_revision = revision
            self._update(
                state=asr.get("state") or "idle", message=asr.get("message") or "",
                deviceId=asr.get("deviceId"), deviceName=asr.get("deviceName") or "",
                partial=asr.get("partial") or "", asrError=asr.get("error") or "",
            )
        final_revision = int(asr.get("finalRevision") or 0)
        if final_revision <= self.last_final_revision:
            return
        self.last_final_revision = final_revision
        raw = str(asr.get("final") or "").strip()
        cleaned = self.clean_final(raw, self._config().get("cleaning") or {})
        now = int(time.time() * 1000)
        self._update(final=raw, cleaned=cleaned, partial="", finalRevision=final_revision, lastFinalAt=now, translation="", translationError="")
        item = {"revision": final_revision, "at": now, "raw": raw, "cleaned": cleaned, "translation": "", "translationError": ""}
        self.history.appendleft(item)
        if not cleaned:
            self._update(message="final 已由清洗规则丢弃")
            return
        translation = self._config().get("translation") or {}
        if not translation.get("enabled"):
            return
        task = asyncio.create_task(
            self._translate_item(item, cleaned, final_revision, translation),
            name=f"subtitle-translation-{final_revision}",
        )
        self.translation_tasks.add(task)
        task.add_done_callback(self.translation_tasks.discard)

    async def _translate_item(self, item: dict, cleaned: str, final_revision: int, translation: dict) -> None:
        try:
            result = await asyncio.to_thread(self.speech.translate, cleaned, translation.get("sourceLanguage", "zh"), translation.get("targetLanguage", "en"))
            item["translation"] = result["text"]
            if self.state["finalRevision"] == final_revision:
                self._update(translation=result["text"], translationRevision=final_revision, translationError="")
        except Exception as error:
            item["translationError"] = str(error)
            if self.state["finalRevision"] == final_revision:
                self._update(translation="", translationRevision=final_revision, translationError=str(error))
