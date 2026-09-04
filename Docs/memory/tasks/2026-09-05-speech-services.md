# 实时 ASR、TTS 与字幕翻译验证

任务：在 `LiveMngSys-refactor-test` 中实现可实际验证的语音实验室，按独立 sherpa-onnx 流式 ASR、Python final-only 字幕管线和独立 llama.cpp/HY-MT 翻译服务组织进程。

状态：已完成。

完成内容：
- 可枚举并选择系统输入设备，按约 100ms 音频块进行 sherpa-onnx OnlineRecognizer 流式识别，并使用内置 endpoint detection 提交完整句子。
- `partial` 仅作为前端可修订字幕预览；只有 VAD 后的 `final` 会进入规则清洗和异步翻译。
- Python 清洗支持语气词、短片段、空格及换行规则；翻译失败时保留 ASR 源字幕。
- llama.cpp server 独立监听 7004，以 `n_parallel=1` 加载 HY-MT1.5-1.8B GGUF；ASR 独立监听 7003，Listener 编排服务监听 7002。
- GUIDemo 语音实验室提供设备刷新、采集启停、partial/final/清洗/翻译、历史字幕和原有 TTS 配置。
- 已完成真实设备状态流转、WAV 到翻译端到端验证，以及 1440px/390px 浏览器检查。
- 全量 `DouyinListener` 回归 147 项通过；翻译进程离线时源语言 final 与清洗结果仍正常保留，恢复启动后 7004 健康检查通过。
- 追加模型选择：新增 `/speech/options` 目录发现接口，支持实时 streaming ASR、离线诊断 ASR、TTS、GGUF、翻译语言和动态 TTS 音色选项；单模型翻译与实时 ASR 的切换在保存后通过重启对应独立进程生效。
