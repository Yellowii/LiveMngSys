"""Independent streaming sherpa-onnx microphone ASR service."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import threading
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
import sherpa_onnx
import sounddevice as sd
from aiohttp import web


class StreamingAsr:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.recognizer = None
        self.stream = None
        self.state = {
            "state": "idle", "message": "等待启动", "deviceId": None, "deviceName": "",
            "partial": "", "final": "", "revision": 0, "finalRevision": 0,
            "updatedAt": 0, "lastFinalAt": 0, "error": "",
        }

    def devices(self) -> list[dict]:
        result = []
        default_id = int(sd.default.device[0]) if sd.default.device[0] is not None else -1
        for index, device in enumerate(sd.query_devices()):
            if int(device.get("max_input_channels") or 0) < 1:
                continue
            result.append({
                "id": index, "name": str(device.get("name") or f"Input {index}"),
                "hostApi": int(device.get("hostapi") or 0), "channels": int(device.get("max_input_channels") or 0),
                "defaultSampleRate": int(float(device.get("default_samplerate") or 16000)), "default": index == default_id,
            })
        return result

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.state)

    def _set(self, **values: Any) -> None:
        with self.lock:
            changed = any(self.state.get(key) != value for key, value in values.items())
            self.state.update(values)
            if changed:
                self.state["revision"] += 1
                self.state["updatedAt"] = int(time.time() * 1000)

    def _create_recognizer(self):
        if self.recognizer is None:
            self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=self.args.tokens, encoder=self.args.encoder, decoder=self.args.decoder, joiner=self.args.joiner,
                num_threads=self.args.num_threads, provider=self.args.provider,
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=self.args.rule1_silence,
                rule2_min_trailing_silence=self.args.rule2_silence,
                rule3_min_utterance_length=self.args.max_utterance,
            )
        return self.recognizer

    def _new_stream(self):
        self.stream = self._create_recognizer().create_stream()

    def _accept(self, samples: np.ndarray, sample_rate: int) -> None:
        recognizer = self._create_recognizer()
        if self.stream is None:
            self._new_stream()
        self.stream.accept_waveform(sample_rate, samples.reshape(-1))
        while recognizer.is_ready(self.stream):
            recognizer.decode_stream(self.stream)
        text = str(recognizer.get_result(self.stream) or "").strip()
        endpoint = recognizer.is_endpoint(self.stream)
        with self.lock:
            if text != self.state["partial"]:
                self.state["partial"] = text
                self.state["revision"] += 1
                self.state["updatedAt"] = int(time.time() * 1000)
            if endpoint:
                if text:
                    self.state["final"] = text
                    self.state["finalRevision"] += 1
                    self.state["revision"] += 1
                    self.state["lastFinalAt"] = int(time.time() * 1000)
                self.state["partial"] = ""
                recognizer.reset(self.stream)

    def _capture_loop(self, device_id: int, sample_rate: int) -> None:
        block_size = max(1, int(sample_rate * self.args.chunk_ms / 1000))
        try:
            self._new_stream()
            with sd.InputStream(device=device_id, channels=1, dtype="float32", samplerate=sample_rate, blocksize=block_size) as audio:
                self._set(state="running", message="正在监听输入设备", error="")
                while not self.stop_event.is_set():
                    samples, overflowed = audio.read(block_size)
                    if overflowed:
                        logging.warning("ASR audio input overflow")
                    self._accept(samples, sample_rate)
        except Exception as error:
            logging.exception("Streaming ASR stopped unexpectedly")
            self._set(state="error", message="音频采集或识别失败", error=str(error))
        finally:
            if self.state["state"] != "error":
                self._set(state="idle", message="已停止")

    def start(self, device_id: Any = None) -> dict:
        if self.worker and self.worker.is_alive():
            return self.snapshot()
        devices = self.devices()
        if not devices:
            raise RuntimeError("没有可用的音频输入设备")
        selected = next((item for item in devices if item["id"] == int(device_id)), None) if device_id is not None else None
        selected = selected or next((item for item in devices if item["default"]), devices[0])
        sample_rate = selected["defaultSampleRate"] or 48000
        self.stop_event.clear()
        self._set(state="starting", message="正在加载 sherpa-onnx", deviceId=selected["id"], deviceName=selected["name"], error="")
        self.worker = threading.Thread(target=self._capture_loop, args=(selected["id"], sample_rate), daemon=True, name="sherpa-asr-capture")
        self.worker.start()
        return self.snapshot()

    def stop(self) -> dict:
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=3)
        self.worker = None
        if self.state["state"] != "error":
            self._set(state="idle", message="已停止", partial="")
        return self.snapshot()

    def decode_test_wav(self, data: bytes) -> dict:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if wav.getsampwidth() != 2:
                raise ValueError("测试 WAV 必须是 16-bit PCM")
            sample_rate = wav.getframerate()
            channels = wav.getnchannels()
            samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
        self._new_stream()
        block_size = max(1, int(sample_rate * self.args.chunk_ms / 1000))
        for offset in range(0, len(samples), block_size):
            self._accept(samples[offset:offset + block_size], sample_rate)
        self._accept(np.zeros(int(sample_rate * max(self.args.rule1_silence, self.args.rule2_silence + 0.3)), dtype=np.float32), sample_rate)
        return self.snapshot()


def create_app(engine: StreamingAsr) -> web.Application:
    app = web.Application(client_max_size=25 * 1024 * 1024)

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "sherpa-asr", "state": engine.snapshot()})

    async def devices(_: web.Request) -> web.Response:
        try:
            return web.json_response({"ok": True, "devices": await asyncio.to_thread(engine.devices)})
        except Exception as error:
            return web.json_response({"ok": False, "message": str(error)}, status=503)

    async def state(_: web.Request) -> web.Response:
        return web.json_response({"ok": True, "state": engine.snapshot()})

    async def start(request: web.Request) -> web.Response:
        try:
            body = await request.json() if request.can_read_body else {}
            return web.json_response({"ok": True, "state": await asyncio.to_thread(engine.start, body.get("deviceId"))})
        except Exception as error:
            return web.json_response({"ok": False, "message": str(error)}, status=400)

    async def stop(_: web.Request) -> web.Response:
        return web.json_response({"ok": True, "state": await asyncio.to_thread(engine.stop)})

    async def test_wav(request: web.Request) -> web.Response:
        try:
            return web.json_response({"ok": True, "state": await asyncio.to_thread(engine.decode_test_wav, await request.read())})
        except Exception as error:
            return web.json_response({"ok": False, "message": str(error)}, status=400)

    app.router.add_get("/health", health)
    app.router.add_get("/devices", devices)
    app.router.add_get("/state", state)
    app.router.add_post("/start", start)
    app.router.add_post("/stop", stop)
    app.router.add_post("/test-wav", test_wav)
    app.on_cleanup.append(lambda _: asyncio.to_thread(engine.stop))
    return app


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent / "data" / "speech_models" / "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
    parser = argparse.ArgumentParser(description="LiveMngSys streaming sherpa-onnx ASR service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7003)
    parser.add_argument("--tokens", default=str(root / "tokens.txt"))
    parser.add_argument("--encoder", default=str(root / "encoder-epoch-99-avg-1.int8.onnx"))
    parser.add_argument("--decoder", default=str(root / "decoder-epoch-99-avg-1.onnx"))
    parser.add_argument("--joiner", default=str(root / "joiner-epoch-99-avg-1.onnx"))
    parser.add_argument("--num-threads", type=int, default=2)
    parser.add_argument("--provider", default="cpu")
    parser.add_argument("--chunk-ms", type=int, default=100)
    parser.add_argument("--rule1-silence", type=float, default=1.2)
    parser.add_argument("--rule2-silence", type=float, default=0.8)
    parser.add_argument("--max-utterance", type=float, default=20.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for name in ("tokens", "encoder", "decoder", "joiner"):
        if not Path(getattr(args, name)).is_file():
            raise FileNotFoundError(f"Missing streaming ASR {name}: {getattr(args, name)}")
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
    web.run_app(create_app(StreamingAsr(args)), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
