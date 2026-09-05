"""Model catalog and safe background downloads for the speech laboratory."""

from __future__ import annotations

import asyncio
import shutil
import tarfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable


MODEL_CATALOG = [
    {
        "id": "asr-streaming-zipformer-zh-en",
        "type": "asr_streaming",
        "name": "Zipformer 流式中英 ASR",
        "source": "ModelScope 镜像",
        "targetDir": "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20",
        "archiveName": "streaming-zipformer-bilingual.tar.bz2",
        "sizeHint": "约 488 MB 下载",
        "urls": [
            "https://modelscope.cn/models/ZhaoChaoqun/sherpa-onnx-asr-models/resolve/master/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2",
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2",
        ],
    },
    {
        "id": "asr-sensevoice-int8",
        "type": "asr_offline",
        "name": "SenseVoice/FunASR 中文多语 INT8",
        "source": "ModelScope 镜像",
        "targetDir": "sherpa-onnx-sense-voice-funasr-nano-int8-2025-12-17",
        "archiveName": "sense-voice-int8.tar.bz2",
        "sizeHint": "约 179 MB 下载",
        "urls": [
            "https://modelscope.cn/models/ZhaoChaoqun/sherpa-onnx-asr-models/resolve/master/sherpa-onnx-sense-voice-funasr-nano-int8-2025-12-17.tar.bz2",
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2",
        ],
    },
    {
        "id": "tts-melo-zh-en",
        "type": "tts",
        "name": "MeloTTS 中文/英文 VITS",
        "source": "GitHub Releases",
        "targetDir": "vits-melo-tts-zh_en",
        "archiveName": "vits-melo-tts-zh_en.tar.bz2",
        "sizeHint": "约 200 MB",
        "urls": [
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2",
        ],
    },
    {
        "id": "translation-hy-mt-1.8b-q4",
        "type": "translation",
        "name": "HY-MT1.5-1.8B Q4_K_M",
        "source": "ModelScope 镜像",
        "targetFile": "HY-MT1.5-1.8B-Q4_K_M.gguf",
        "sizeHint": "约 1.13 GB",
        "urls": [
            "https://modelscope.cn/models/tencent-hunyuan/hy-mt1.5-1.8b-gguf/resolve/master/HY-MT1.5-1.8B-Q4_K_M.gguf",
            "https://huggingface.co/tencent/HY-MT1.5-1.8B-GGUF/resolve/main/HY-MT1.5-1.8B-Q4_K_M.gguf",
        ],
    },
]


class SpeechModelManager:
    def __init__(self, config_provider: Callable[[], dict], root: Path):
        self.config_provider = config_provider
        self.root = root.resolve()
        self.lock = threading.RLock()
        self.jobs: dict[str, dict[str, Any]] = {}
        self.cancel_events: dict[str, threading.Event] = {}
        self.tasks: set[asyncio.Task] = set()

    def model_root(self) -> Path:
        speech = self.config_provider().get("speech") or {}
        configured = Path(str(speech.get("modelRoot") or "data/speech_models")).expanduser()
        return (configured if configured.is_absolute() else self.root / configured).resolve()

    def catalog(self) -> list[dict]:
        root = self.model_root()
        result = []
        for item in MODEL_CATALOG:
            current = dict(item)
            current.pop("urls", None)
            target = root / item.get("targetDir", "") if item.get("targetDir") else root / item["targetFile"]
            current["installed"] = target.is_dir() if item.get("targetDir") else target.is_file()
            if target.exists():
                try:
                    current["path"] = str(target.relative_to(self.root)).replace("\\", "/")
                except ValueError:
                    current["path"] = str(target)
            else:
                current["path"] = ""
            with self.lock:
                job = self.jobs.get(item["id"])
                current["download"] = dict(job) if job else {"state": "ready" if current["installed"] else "not_downloaded"}
            result.append(current)
        return result

    def downloads(self) -> list[dict]:
        with self.lock:
            return [dict(job) for job in self.jobs.values()]

    def _set_job(self, model_id: str, **values: Any) -> None:
        with self.lock:
            job = self.jobs.setdefault(model_id, {"modelId": model_id, "state": "queued", "progress": 0, "downloaded": 0, "total": 0, "error": "", "updatedAt": 0})
            job.update(values)
            job["updatedAt"] = int(time.time() * 1000)

    def _entry(self, model_id: str) -> dict:
        for item in MODEL_CATALOG:
            if item["id"] == model_id:
                return item
        raise ValueError("未知模型 ID")

    def start(self, model_id: str) -> dict:
        entry = self._entry(str(model_id or ""))
        root = self.model_root()
        target = root / entry.get("targetDir", "") if entry.get("targetDir") else root / entry["targetFile"]
        installed = target.is_dir() if entry.get("targetDir") else target.is_file()
        if installed:
            return {"modelId": entry["id"], "state": "ready", "progress": 100, "downloaded": 0, "total": 0, "error": "", "updatedAt": int(time.time() * 1000)}
        with self.lock:
            current = self.jobs.get(entry["id"])
            if current and current["state"] in {"queued", "downloading", "extracting"}:
                return dict(current)
            cancel = threading.Event()
            self.cancel_events[entry["id"]] = cancel
            self.jobs[entry["id"]] = {"modelId": entry["id"], "state": "queued", "progress": 0, "downloaded": 0, "total": 0, "error": "", "updatedAt": int(time.time() * 1000)}
        task = asyncio.create_task(asyncio.to_thread(self._download, entry, cancel), name=f"speech-model-{entry['id']}")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        with self.lock:
            return dict(self.jobs[entry["id"]])

    def cancel(self, model_id: str) -> dict:
        self._entry(model_id)
        with self.lock:
            event = self.cancel_events.get(model_id)
            job = self.jobs.get(model_id)
            if event and job and job["state"] in {"queued", "downloading", "extracting"}:
                event.set()
                job["state"] = "cancelling"
                job["updatedAt"] = int(time.time() * 1000)
            return dict(job or {"modelId": model_id, "state": "not_started"})

    def _download(self, entry: dict, cancel: threading.Event) -> None:
        root = self.model_root()
        root.mkdir(parents=True, exist_ok=True)
        target = root / entry.get("targetDir", "") if entry.get("targetDir") else root / entry["targetFile"]
        part = root / (entry.get("archiveName") or (entry["targetFile"] + ".part"))
        last_error = ""
        for url in entry["urls"]:
            try:
                self._set_job(entry["id"], state="downloading", source=url, progress=0, error="")
                request = urllib.request.Request(url, headers={"User-Agent": "LiveMngSys/1.0"})
                with urllib.request.urlopen(request, timeout=30) as response, part.open("wb") as output:
                    total = int(response.headers.get("Content-Length") or 0)
                    downloaded = 0
                    self._set_job(entry["id"], total=total)
                    while True:
                        if cancel.is_set():
                            raise InterruptedError("下载已取消")
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        self._set_job(entry["id"], downloaded=downloaded, progress=round(downloaded / total * 100, 1) if total else 0)
                downloaded_size = part.stat().st_size if part.exists() else 0
                self._install(entry, part, target, cancel)
                self._set_job(entry["id"], state="ready", progress=100, downloaded=downloaded_size, error="")
                if part.exists():
                    part.unlink()
                return
            except InterruptedError as error:
                last_error = str(error)
                break
            except (OSError, urllib.error.URLError, tarfile.TarError, zipfile.BadZipFile) as error:
                last_error = str(error)
                if part.exists():
                    part.unlink()
        state = "cancelled" if cancel.is_set() else "error"
        self._set_job(entry["id"], state=state, error=last_error or "下载失败")
        if part.exists():
            part.unlink()

    def _install(self, entry: dict, archive: Path, target: Path, cancel: threading.Event) -> None:
        if cancel.is_set():
            raise InterruptedError("下载已取消")
        if entry.get("targetFile"):
            self._set_job(entry["id"], state="extracting", progress=99)
            target.parent.mkdir(parents=True, exist_ok=True)
            archive.replace(target)
            return
        self._set_job(entry["id"], state="extracting", progress=95)
        staging = target.parent / f".{target.name}.staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        try:
            staging_root = staging.resolve()
            if archive.name.lower().endswith((".zip", ".zip.part")):
                with zipfile.ZipFile(archive) as package:
                    for member in package.infolist():
                        destination = (staging / member.filename).resolve()
                        try:
                            destination.relative_to(staging_root)
                        except ValueError as error:
                            raise OSError("模型压缩包包含非法路径") from error
                    package.extractall(staging)
            else:
                with tarfile.open(archive, "r:*") as package:
                    for member in package.getmembers():
                        destination = (staging / member.name).resolve()
                        try:
                            destination.relative_to(staging_root)
                        except ValueError as error:
                            raise OSError("模型压缩包包含非法路径") from error
                    package.extractall(staging)
            extracted = staging / target.name
            source = extracted if extracted.is_dir() else next((path for path in staging.iterdir() if path.is_dir()), staging)
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(source), str(target))
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    async def close(self) -> None:
        for event in self.cancel_events.values():
            event.set()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
