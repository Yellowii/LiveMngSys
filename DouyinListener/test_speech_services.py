import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from speech_services import SpeechServiceError, SpeechServices, normalize_speech_config


class _Result:
    text = "测试字幕"


class _AsrStream:
    result = _Result()

    def accept_waveform(self, sample_rate, samples):
        self.sample_rate = sample_rate
        self.samples = samples


class _Recognizer:
    def create_stream(self):
        self.stream = _AsrStream()
        return self.stream

    def decode_stream(self, stream):
        self.decoded = stream


class _OfflineRecognizer:
    @staticmethod
    def from_sense_voice(**kwargs):
        instance = _Recognizer()
        instance.options = kwargs
        return instance


class _Audio:
    samples = [0.0, 0.25, -0.25]
    sample_rate = 22050


class _Tts:
    def __init__(self, config):
        self.config = config

    def generate(self, text, sid, speed):
        self.request = (text, sid, speed)
        return _Audio()


class _Config:
    def __init__(self, **kwargs):
        self.options = kwargs


class _Sherpa:
    OfflineRecognizer = _OfflineRecognizer
    OfflineTtsVitsModelConfig = _Config
    OfflineTtsModelConfig = _Config
    OfflineTtsConfig = _Config
    OfflineTts = _Tts


def _wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00\x00\x10\x00\xf0")
    return output.getvalue()


class SpeechServicesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.models = self.root / "models"
        self.models.mkdir()
        for name in ("asr.onnx", "tts.onnx", "tokens.txt"):
            (self.models / name).write_bytes(b"model")

    def tearDown(self):
        self.temp.cleanup()

    def config(self):
        return {
            "enabled": True,
            "modelRoot": "models",
            "asr": {"enabled": True, "model": "asr.onnx", "tokens": "tokens.txt"},
            "tts": {"enabled": True, "model": "tts.onnx", "tokens": "tokens.txt", "speakerId": 2},
        }

    def test_normalization_clamps_runtime_values(self):
        config = normalize_speech_config({
            "asr": {"numThreads": 100},
            "tts": {"speed": 99},
            "translation": {"timeoutSeconds": 0},
        })
        self.assertEqual(config["asr"]["numThreads"], 32)
        self.assertEqual(config["tts"]["speed"], 4.0)
        self.assertEqual(config["translation"]["timeoutSeconds"], 1)

    def test_disabled_feature_does_not_load_optional_dependency(self):
        services = SpeechServices(self.root)
        with self.assertRaisesRegex(SpeechServiceError, "disabled"):
            services.recognize_wav(_wav_bytes())

    def test_sense_voice_recognizes_pcm_wav(self):
        services = SpeechServices(self.root, self.config(), _Sherpa())
        result = services.recognize_wav(_wav_bytes())
        self.assertEqual(result["text"], "测试字幕")
        self.assertEqual(result["sampleRate"], 16000)
        self.assertEqual(len(services._asr.stream.samples), 3)

    def test_vits_returns_wav(self):
        services = SpeechServices(self.root, self.config(), _Sherpa())
        data, metadata = services.synthesize("欢迎来到直播间", speed=1.25)
        with wave.open(io.BytesIO(data), "rb") as wav:
            self.assertEqual(wav.getframerate(), 22050)
            self.assertEqual(wav.getnframes(), 3)
        self.assertEqual(metadata["speakerId"], 2)
        self.assertEqual(metadata["speed"], 1.25)

    def test_missing_model_has_structured_error(self):
        config = self.config()
        config["asr"]["model"] = "missing.onnx"
        services = SpeechServices(self.root, config, _Sherpa())
        with self.assertRaises(SpeechServiceError) as raised:
            services.recognize_wav(_wav_bytes())
        self.assertEqual(raised.exception.code, "model_not_found")
        self.assertEqual(raised.exception.status, 503)

    def test_libretranslate_provider(self):
        config = self.config()
        config["translation"] = {
            "enabled": True,
            "provider": "libretranslate",
            "endpoint": "http://translator.test/translate",
            "targetLanguage": "en",
        }
        services = SpeechServices(self.root, config, _Sherpa())
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"translatedText": "hello"}).encode()
        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            result = services.translate("你好")
        self.assertEqual(result["text"], "hello")
        request = urlopen.call_args.args[0]
        self.assertEqual(json.loads(request.data)["target"], "en")


if __name__ == "__main__":
    unittest.main()
