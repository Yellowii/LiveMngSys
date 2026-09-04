# 实时 ASR、TTS 与字幕翻译

测试项目采用三个相互隔离的进程：

```text
输入设备 -> 进程 A: sherpa-onnx OnlineRecognizer (7003)
                         | partial / final JSON
                         v
           Python Listener 字幕管线 (7002)
             清洗 final，保留原文，维护历史
                         | 仅 final HTTP POST
                         v
           进程 B: llama.cpp server (7004)
```

- `partial` 是当前话语的可修订预览，只通过 WebSocket 更新实验室界面，绝不进入翻译。
- sherpa-onnx endpoint detection 检测到尾部静音后提交 `final`，Python 才执行规则清洗和翻译。
- 清洗是纯代码：去掉换行与多余空格、首尾语气词，并丢弃少于配置字符数的碎片。
- 翻译失败不会覆盖或丢弃 ASR 原文；7003、7004 任一服务退出时另一个仍可独立运行。
- TTS 仍由 Listener 中按需加载的 sherpa-onnx VITS 模型提供，不参与字幕翻译链路。

## 本机安装

安装 Python 依赖并下载 streaming Zipformer、SenseVoice 与 MeloTTS：

```powershell
cd DouyinListener
.\Install-SpeechModels.ps1
```

安装 Windows x64 CPU 版 llama.cpp 与 `HY-MT1.5-1.8B-Q4_K_M.gguf`：

```powershell
.\Install-TranslationService.ps1
```

模型和 llama.cpp 二进制位于 Git 忽略目录，不会进入仓库。根目录 `Start-LiveMngSys.ps1` 会先启动 7003，再启动可选 7004，最后启动 Listener；翻译启动失败只产生警告。

## 配置

进程启动项位于 `config/service.json`：

```json
{
  "speechAsr": { "enabled": true, "host": "127.0.0.1", "port": 7003 },
  "translation": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 7004,
    "executable": "tools/llama.cpp/llama-server.exe",
    "model": "DouyinListener/data/speech_models/HY-MT1.5-1.8B-Q4_K_M.gguf",
    "contextSize": 2048,
    "parallel": 1
  }
}
```

字幕清洗、目标语言和 TTS 设置位于 Listener 的本地 `data/config.json`，也可在 `运行状态 > 配置 > 语音实验室` 修改。llama.cpp endpoint 应为 `http://127.0.0.1:7004/v1/chat/completions`。

## 接口

- `GET /api/livemngsys/live/speech/devices`：系统音频输入设备。
- `POST /api/livemngsys/live/speech/capture/start`：`{"deviceId": 1}`，启动持续采集。
- `POST /api/livemngsys/live/speech/capture/stop`：停止采集。
- `GET /api/livemngsys/live/captions`：Windows 字幕源状态。
- `GET /api/livemngsys/live/state` 中的 `speechCaptions`：partial、final、清洗、翻译和历史。
- `POST /api/livemngsys/live/speech/asr`：保留的离线 PCM WAV 识别诊断接口。
- `POST /api/livemngsys/live/speech/tts`：`{"text":"欢迎","speakerId":0,"speed":1.0}`，返回 WAV。
- `POST /api/livemngsys/live/speech/translate`：手工翻译诊断接口，不参与 partial 处理。

7003 和 7004 默认仅监听回环地址；浏览器通过 7000 网关和 Listener 使用能力，无需直接暴露推理端口。
