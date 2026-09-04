"""Optional ASR, TTS, and translation services for LiveMngSys."""

from __future__ import annotations

import array
import importlib
import importlib.util
import io
import json
import os
import re
import threading
import urllib.error
import urllib.request
import wave
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_SPEECH_CONFIG = {
    "enabled": False,
    "modelRoot": "data/speech_models",
    "asrServiceUrl": "http://127.0.0.1:7003",
    "cleaning": {"enabled": True, "minCharacters": 3, "fillerWords": ["嗯", "啊", "呃", "额", "唔"]},
    "asr": {
        "enabled": False,
        "modelType": "sense_voice",
        "model": "",
        "tokens": "",
        "encoder": "",
        "decoder": "",
        "language": "auto",
        "task": "transcribe",
        "useItn": True,
        "numThreads": 2,
        "provider": "cpu",
        "streamingModel": "",
    },
    "tts": {
        "enabled": False,
        "modelType": "vits",
        "model": "",
        "tokens": "",
        "lexicon": "",
        "dataDir": "",
        "dictDir": "",
        "ruleFsts": "",
        "ruleFars": "",
        "speakerId": 0,
        "speed": 1.0,
        "numThreads": 2,
        "provider": "cpu",
    },
    "translation": {
        "enabled": False,
        "provider": "none",
        "endpoint": "",
        "sourceLanguage": "auto",
        "targetLanguage": "en",
        "model": "",
        "apiKeyEnv": "LIVEMNGSYS_TRANSLATION_API_KEY",
        "timeoutSeconds": 15,
    },
}


class SpeechServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def normalize_speech_config(value: Any) -> dict:
    source = value if isinstance(value, dict) else {}
    result = deepcopy(DEFAULT_SPEECH_CONFIG)
    result["enabled"] = bool(source.get("enabled", False))
    result["modelRoot"] = str(source.get("modelRoot") or result["modelRoot"]).strip()
    result["asrServiceUrl"] = str(source.get("asrServiceUrl") or result["asrServiceUrl"]).strip()[:2048]
    cleaning = source.get("cleaning") if isinstance(source.get("cleaning"), dict) else {}
    filler_words = cleaning.get("fillerWords") if isinstance(cleaning.get("fillerWords"), list) else result["cleaning"]["fillerWords"]
    result["cleaning"] = {
        "enabled": bool(cleaning.get("enabled", True)),
        "minCharacters": _bounded_int(cleaning.get("minCharacters"), 3, 1, 20),
        "fillerWords": [str(item).strip()[:16] for item in filler_words if str(item).strip()][:50],
    }

    asr = source.get("asr") if isinstance(source.get("asr"), dict) else {}
    result["asr"].update({key: str(asr.get(key) or "").strip() for key in ("model", "tokens", "encoder", "decoder")})
    result["asr"]["streamingModel"] = str(asr.get("streamingModel") or "").strip()[:512]
    result["asr"].update({
        "enabled": bool(asr.get("enabled", False)),
        "modelType": str(asr.get("modelType") or "sense_voice").strip().lower(),
        "language": str(asr.get("language") or "auto").strip(),
        "task": "translate" if str(asr.get("task") or "transcribe").lower() == "translate" else "transcribe",
        "useItn": bool(asr.get("useItn", True)),
        "numThreads": _bounded_int(asr.get("numThreads"), 2, 1, 32),
        "provider": str(asr.get("provider") or "cpu").strip().lower(),
    })

    tts = source.get("tts") if isinstance(source.get("tts"), dict) else {}
    result["tts"].update({key: str(tts.get(key) or "").strip() for key in (
        "model", "tokens", "lexicon", "dataDir", "dictDir", "ruleFsts", "ruleFars"
    )})
    result["tts"].update({
        "enabled": bool(tts.get("enabled", False)),
        "modelType": str(tts.get("modelType") or "vits").strip().lower(),
        "speakerId": _bounded_int(tts.get("speakerId"), 0, 0, 10000),
        "speed": _bounded_float(tts.get("speed"), 1.0, 0.25, 4.0),
        "numThreads": _bounded_int(tts.get("numThreads"), 2, 1, 32),
        "provider": str(tts.get("provider") or "cpu").strip().lower(),
    })

    translation = source.get("translation") if isinstance(source.get("translation"), dict) else {}
    result["translation"].update({
        "enabled": bool(translation.get("enabled", False)),
        "provider": str(translation.get("provider") or "none").strip().lower(),
        "endpoint": str(translation.get("endpoint") or "").strip()[:2048],
        "sourceLanguage": str(translation.get("sourceLanguage") or "auto").strip()[:32],
        "targetLanguage": str(translation.get("targetLanguage") or "en").strip()[:32],
        "model": str(translation.get("model") or "").strip()[:256],
        "apiKeyEnv": str(translation.get("apiKeyEnv") or "LIVEMNGSYS_TRANSLATION_API_KEY").strip()[:128],
        "timeoutSeconds": _bounded_float(translation.get("timeoutSeconds"), 15, 1, 120),
    })
    return result


class SpeechServices:
    """Lazily loads local models so disabled speech features cost nothing."""

    def __init__(self, root: Path, config: Any = None, sherpa_module: Any = None):
        self.root = root.resolve()
        self.config = normalize_speech_config(config)
        self._sherpa_module = sherpa_module
        self._asr = None
        self._tts = None
        self._asr_lock = threading.RLock()
        self._tts_lock = threading.RLock()

    def configure(self, config: Any) -> None:
        normalized = normalize_speech_config(config)
        if normalized != self.config:
            self.config = normalized
            self._asr = None
            self._tts = None

    def _model_root(self) -> Path:
        configured = Path(self.config["modelRoot"]).expanduser()
        return (configured if configured.is_absolute() else self.root / configured).resolve()

    def _path(self, value: Any, required: bool = False, label: str = "model file") -> str:
        raw = str(value or "").strip()
        if not raw:
            if required:
                raise SpeechServiceError("model_not_configured", f"Missing {label}", 503)
            return ""
        path = Path(raw).expanduser()
        resolved = (path if path.is_absolute() else self._model_root() / path).resolve()
        if not resolved.exists():
            raise SpeechServiceError("model_not_found", f"{label} does not exist: {resolved}", 503)
        return str(resolved)

    def _path_list(self, value: Any, label: str) -> str:
        paths = [item.strip() for item in str(value or "").split(",") if item.strip()]
        return ",".join(self._path(item, False, label) for item in paths)

    def _sherpa(self) -> Any:
        if self._sherpa_module is not None:
            return self._sherpa_module
        try:
            self._sherpa_module = importlib.import_module("sherpa_onnx")
            return self._sherpa_module
        except ImportError as error:
            raise SpeechServiceError(
                "dependency_missing", "sherpa-onnx is not installed; run pip install -r requirements-speech.txt", 503
            ) from error

    def status(self) -> dict:
        dependency_available = importlib.util.find_spec("sherpa_onnx") is not None if self._sherpa_module is None else True
        return {
            "enabled": self.config["enabled"],
            "dependencyAvailable": dependency_available,
            "modelRoot": str(self._model_root()),
            "asr": {
                "enabled": self.config["asr"]["enabled"],
                "modelType": self.config["asr"]["modelType"],
                "loaded": self._asr is not None,
            },
            "tts": {
                "enabled": self.config["tts"]["enabled"],
                "modelType": self.config["tts"]["modelType"],
                "loaded": self._tts is not None,
            },
            "translation": {
                "enabled": self.config["translation"]["enabled"],
                "provider": self.config["translation"]["provider"],
                "targetLanguage": self.config["translation"]["targetLanguage"],
            },
        }

    def options(self) -> dict:
        """Return model and voice choices discoverable from the local model root."""
        root = self._model_root()
        asr_models = []
        streaming_asr_models = []
        tts_models = []
        translation_models = []
        if root.is_dir():
            for directory in sorted(item for item in root.iterdir() if item.is_dir()):
                files = {item.name for item in directory.iterdir() if item.is_file()}
                if "tokens.txt" in files and any(name.endswith(".onnx") for name in files):
                    if any(name.startswith("encoder-") for name in files) and any(name.startswith("decoder-") for name in files) and any(name.startswith("joiner-") for name in files):
                        streaming_asr_models.append({"id": str(directory.relative_to(root)).replace("\\", "/"), "name": directory.name})
                    if "sense-voice" in directory.name.lower() and ("model.int8.onnx" in files or "model.onnx" in files):
                        asr_models.append({
                            "id": str(directory.relative_to(root)).replace("\\", "/"),
                            "name": directory.name,
                            "model": str(directory.relative_to(root)).replace("\\", "/") + ("/model.int8.onnx" if "model.int8.onnx" in files else "/model.onnx"),
                            "tokens": str(directory.relative_to(root)).replace("\\", "/") + "/tokens.txt",
                            "modelType": "sense_voice" if "sense-voice" in directory.name.lower() else "sense_voice",
                        })
                if "model.onnx" in files and "tokens.txt" in files and ("lexicon.txt" in files or "vits" in directory.name.lower()):
                    tts_models.append({
                        "id": str(directory.relative_to(root)).replace("\\", "/"),
                        "name": directory.name,
                        "model": str(directory.relative_to(root)).replace("\\", "/") + "/model.onnx",
                        "tokens": str(directory.relative_to(root)).replace("\\", "/") + "/tokens.txt",
                        "lexicon": str(directory.relative_to(root)).replace("\\", "/") + ("/lexicon.txt" if "lexicon.txt" in files else ""),
                        "modelType": "vits",
                    })
            for model in sorted(root.glob("*.gguf")):
                translation_models.append({"id": model.name, "name": model.name, "path": str(model.relative_to(self.root)).replace("\\", "/")})
        speaker_count = 1
        if self._tts is not None:
            try:
                speaker_count = max(1, int(getattr(self._tts, "num_speakers", 1) or 1))
            except (TypeError, ValueError):
                speaker_count = 1
        return {
            "asrModels": asr_models,
            "streamingAsrModels": streaming_asr_models,
            "ttsModels": tts_models,
            "translationModels": translation_models,
            "languages": [
                {"id": "auto", "name": "自动检测"}, {"id": "zh", "name": "中文"},
                {"id": "en", "name": "English"}, {"id": "ja", "name": "日本語"},
                {"id": "ko", "name": "한국어"}, {"id": "yue", "name": "粤语"},
            ],
            "speakerCount": speaker_count,
        }

    def _require_enabled(self, feature: str) -> dict:
        if not self.config["enabled"]:
            raise SpeechServiceError("speech_disabled", "Speech services are disabled", 503)
        feature_config = self.config[feature]
        if not feature_config["enabled"]:
            raise SpeechServiceError(f"{feature}_disabled", f"{feature.upper()} is disabled", 503)
        return feature_config

    def _create_asr(self) -> Any:
        config = self.config["asr"]
        sherpa = self._sherpa()
        model_type = config["modelType"]
        common = {
            "tokens": self._path(config["tokens"], True, "ASR tokens"),
            "num_threads": config["numThreads"],
            "provider": config["provider"],
        }
        if model_type == "sense_voice":
            return sherpa.OfflineRecognizer.from_sense_voice(
                model=self._path(config["model"], True, "SenseVoice model"),
                use_itn=config["useItn"],
                **common,
            )
        if model_type == "whisper":
            return sherpa.OfflineRecognizer.from_whisper(
                encoder=self._path(config["encoder"], True, "Whisper encoder"),
                decoder=self._path(config["decoder"], True, "Whisper decoder"),
                language=config["language"],
                task=config["task"],
                **common,
            )
        raise SpeechServiceError("unsupported_asr_model", f"Unsupported ASR model type: {model_type}")

    def _get_asr(self) -> Any:
        if self._asr is None:
            with self._asr_lock:
                if self._asr is None:
                    self._asr = self._create_asr()
        return self._asr

    @staticmethod
    def decode_wav(data: bytes) -> tuple[int, list[float]]:
        try:
            with wave.open(io.BytesIO(data), "rb") as wav:
                if wav.getcomptype() != "NONE":
                    raise SpeechServiceError("unsupported_audio", "Only uncompressed PCM WAV is supported", 415)
                channels = wav.getnchannels()
                width = wav.getsampwidth()
                sample_rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except (wave.Error, EOFError) as error:
            raise SpeechServiceError("invalid_audio", "Request body must be a valid PCM WAV file", 415) from error
        if channels < 1 or width not in {1, 2, 4} or sample_rate < 1000:
            raise SpeechServiceError("unsupported_audio", "Unsupported WAV channel, width, or sample rate", 415)
        typecode = {1: "B", 2: "h", 4: "i"}[width]
        samples = array.array(typecode)
        samples.frombytes(frames)
        if width > 1 and os.sys.byteorder != "little":
            samples.byteswap()
        scale = {1: 128.0, 2: 32768.0, 4: 2147483648.0}[width]
        offset = 128.0 if width == 1 else 0.0
        floats = [(float(value) - offset) / scale for value in samples]
        if channels > 1:
            floats = [sum(floats[index:index + channels]) / channels for index in range(0, len(floats), channels)]
        if not floats:
            raise SpeechServiceError("empty_audio", "WAV file contains no samples")
        return sample_rate, floats

    def recognize_wav(self, data: bytes) -> dict:
        config = self._require_enabled("asr")
        sample_rate, samples = self.decode_wav(data)
        with self._asr_lock:
            recognizer = self._get_asr()
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            recognizer.decode_stream(stream)
            result = stream.result
        text = result.text if hasattr(result, "text") else str(result or "")
        return {
            "text": text.strip(),
            "sampleRate": sample_rate,
            "modelType": config["modelType"],
            "task": config["task"],
        }

    def _create_tts(self) -> Any:
        config = self.config["tts"]
        if config["modelType"] != "vits":
            raise SpeechServiceError("unsupported_tts_model", f"Unsupported TTS model type: {config['modelType']}")
        sherpa = self._sherpa()
        vits = sherpa.OfflineTtsVitsModelConfig(
            model=self._path(config["model"], True, "VITS model"),
            tokens=self._path(config["tokens"], True, "TTS tokens"),
            lexicon=self._path(config["lexicon"], False, "TTS lexicon"),
            data_dir=self._path(config["dataDir"], False, "TTS data directory"),
            dict_dir=self._path(config["dictDir"], False, "TTS dictionary directory"),
        )
        model = sherpa.OfflineTtsModelConfig(
            vits=vits,
            num_threads=config["numThreads"],
            provider=config["provider"],
        )
        return sherpa.OfflineTts(sherpa.OfflineTtsConfig(
            model=model,
            rule_fsts=self._path_list(config["ruleFsts"], "TTS rule FST"),
            rule_fars=self._path_list(config["ruleFars"], "TTS rule FAR"),
        ))

    def _get_tts(self) -> Any:
        if self._tts is None:
            with self._tts_lock:
                if self._tts is None:
                    self._tts = self._create_tts()
        return self._tts

    @staticmethod
    def encode_wav(samples: Any, sample_rate: int) -> bytes:
        pcm = array.array("h", (max(-32768, min(32767, round(float(sample) * 32767))) for sample in samples))
        if os.sys.byteorder != "little":
            pcm.byteswap()
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm.tobytes())
        return output.getvalue()

    def synthesize(self, text: str, speaker_id: Any = None, speed: Any = None) -> tuple[bytes, dict]:
        config = self._require_enabled("tts")
        clean_text = str(text or "").strip()
        if not clean_text:
            raise SpeechServiceError("empty_text", "TTS text cannot be empty")
        if len(clean_text) > 2000:
            raise SpeechServiceError("text_too_long", "TTS text cannot exceed 2000 characters", 413)
        sid = _bounded_int(speaker_id, config["speakerId"], 0, 10000) if speaker_id is not None else config["speakerId"]
        rate = _bounded_float(speed, config["speed"], 0.25, 4.0) if speed is not None else config["speed"]
        with self._tts_lock:
            audio = self._get_tts().generate(clean_text, sid=sid, speed=rate)
        samples = audio.samples
        if len(samples) == 0:
            raise SpeechServiceError("empty_tts_audio", "TTS model returned no audio", 502)
        wav = self.encode_wav(samples, int(audio.sample_rate))
        return wav, {"sampleRate": int(audio.sample_rate), "speakerId": sid, "speed": rate}

    def translate(self, text: str, source: str = "", target: str = "") -> dict:
        config = self._require_enabled("translation")
        clean_text = str(text or "").strip()
        if not clean_text:
            raise SpeechServiceError("empty_text", "Translation text cannot be empty")
        if len(clean_text) > 10000:
            raise SpeechServiceError("text_too_long", "Translation text cannot exceed 10000 characters", 413)
        provider = config["provider"]
        if provider not in {"libretranslate", "openai_compatible", "llama_cpp"}:
            raise SpeechServiceError("translation_not_configured", "Configure llama_cpp, libretranslate, or openai_compatible", 503)
        endpoint = config["endpoint"]
        if not endpoint.startswith(("http://", "https://")):
            raise SpeechServiceError("translation_not_configured", "Translation endpoint must be an HTTP(S) URL", 503)
        source_language = str(source or config["sourceLanguage"])
        target_language = str(target or config["targetLanguage"])
        api_key = os.environ.get(config["apiKeyEnv"], "") if config["apiKeyEnv"] else ""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if provider == "llama_cpp":
            payload = {
                "model": config["model"] or "hy-mt",
                "messages": [{
                    "role": "user",
                    "content": f"Translate the following segment into {target_language}, without additional explanation.\n\n{clean_text}",
                }],
                "max_tokens": 256,
                "temperature": 0.7,
                "top_k": 20,
                "top_p": 0.6,
                "repeat_penalty": 1.05,
                "stream": False,
            }
        elif provider == "libretranslate":
            payload = {"q": clean_text, "source": source_language, "target": target_language, "format": "text"}
            if api_key:
                payload["api_key"] = api_key
        else:
            payload = {
                "model": config["model"],
                "messages": [{
                    "role": "user",
                    "content": f"Translate from {source_language} to {target_language}. Return only the translation.\n\n{clean_text}",
                }],
                "temperature": 0,
            }
        request = urllib.request.Request(endpoint, json.dumps(payload).encode("utf-8"), headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=config["timeoutSeconds"]) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise SpeechServiceError("translation_failed", f"Translation provider failed: {error}", 502) from error
        if provider == "llama_cpp":
            try:
                translated = result["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                translated = None
        elif provider == "libretranslate":
            translated = result.get("translatedText") if isinstance(result, dict) else None
        else:
            try:
                translated = result["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                translated = None
        if not isinstance(translated, str) or not translated.strip():
            raise SpeechServiceError("translation_failed", "Translation provider returned no text", 502)
        translated = translated.strip()
        if provider == "llama_cpp":
            tagged = re.search(r"<target>\s*(.*?)\s*</target>", translated, flags=re.DOTALL | re.IGNORECASE)
            if tagged:
                translated = tagged.group(1).strip()
        return {"text": translated, "sourceLanguage": source_language, "targetLanguage": target_language, "provider": provider}
