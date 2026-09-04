# ASR、TTS 与翻译服务

语音能力由 `DouyinListener/speech_services.py` 独立提供，并通过现有 `7000` 网关暴露。该模块默认关闭，未安装可选依赖或未配置模型时不影响直播监听、Windows 实时字幕和其他服务。

## 能力边界

- ASR：使用 sherpa-onnx `OfflineRecognizer`，支持 `sense_voice` 和 `whisper` 模型。
- TTS：使用 sherpa-onnx `OfflineTts`，当前支持 VITS 模型、音色 ID 和语速覆盖。
- 翻译：通用文本翻译不是 sherpa-onnx 的职责，当前支持 LibreTranslate 和 OpenAI-compatible HTTP 接口。API 密钥只从环境变量读取。
- Whisper ASR 可将 `task` 设为 `translate`，提供 sherpa-onnx 原生的音频到英文翻译；这与字幕文本翻译接口是两条独立路径。

## 安装与模型

```powershell
cd DouyinListener
python -m pip install -r requirements-speech.txt
```

从 [sherpa-onnx 官方模型说明](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/index.html) 选择模型，并解压到 `DouyinListener/data/speech_models/`。模型目录已被 Git 忽略，不应提交 ONNX 文件。

在 Listener 的 `data/config.json` 中增加 `speech` 配置。路径相对于 `modelRoot`：

```json
{
  "speech": {
    "enabled": true,
    "modelRoot": "data/speech_models",
    "asr": {
      "enabled": true,
      "modelType": "sense_voice",
      "model": "sense-voice/model.int8.onnx",
      "tokens": "sense-voice/tokens.txt",
      "language": "auto",
      "useItn": true,
      "numThreads": 2,
      "provider": "cpu"
    },
    "tts": {
      "enabled": true,
      "modelType": "vits",
      "model": "vits/model.onnx",
      "tokens": "vits/tokens.txt",
      "lexicon": "vits/lexicon.txt",
      "dataDir": "vits/espeak-ng-data",
      "speakerId": 0,
      "speed": 1.0,
      "numThreads": 2,
      "provider": "cpu"
    },
    "translation": {
      "enabled": true,
      "provider": "libretranslate",
      "endpoint": "http://127.0.0.1:5000/translate",
      "sourceLanguage": "auto",
      "targetLanguage": "en",
      "apiKeyEnv": "LIVEMNGSYS_TRANSLATION_API_KEY",
      "timeoutSeconds": 15
    }
  }
}
```

`openai_compatible` provider 的 `endpoint` 应指向 chat completions 接口，并配置 `model`。设置 API 密钥时使用当前进程的环境变量：

```powershell
$env:LIVEMNGSYS_TRANSLATION_API_KEY = "..."
```

## HTTP API

- `GET /api/livemngsys/live/speech/status`：功能开关、依赖和模型加载状态。
- `POST /api/livemngsys/live/speech/asr`：请求体为未压缩 PCM WAV，响应为识别文本 JSON；单次请求上限 25 MiB。
- `POST /api/livemngsys/live/speech/tts`：JSON 请求 `{"text":"欢迎","speakerId":0,"speed":1.0}`，响应为 `audio/wav`。
- `POST /api/livemngsys/live/speech/translate`：JSON 请求 `{"text":"你好","sourceLanguage":"zh","targetLanguage":"en"}`，响应为翻译文本 JSON。

模型和翻译服务不可用时，接口返回稳定的 `code` 与错误信息。调用方应保留源字幕，不能因次级翻译失败而丢弃 ASR 结果。
