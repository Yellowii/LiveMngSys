# LiveMngSys 项目记忆

## 项目目标

LiveMngSys 是一个面向直播间互动管理的本地/LAN 服务系统。当前整体目标是把直播弹幕监听、实时互动展示、排队上车、点歌、弹幕复盘等能力整合到同一套管理与展示界面中。

系统倾向于本地运行：根启动脚本启动内部服务，通过统一网关暴露给局域网设备访问。

## 功能模块

- WebServer：统一网关与管理入口，代理内部服务。
- DouyinListener：抖音直播间弹幕监听、协议解析、事件落盘与复盘数据来源。
- MusicBot：直播间点歌机器人，包含点歌队列、播放控制、UI 和 API。
- GUIDemo：当前 GUI/互动聊天视觉原型与参考实现。
- Docs：规则文档、GUI 设计资料、GameQueue 与 MusicQueue 业务规则。
- config：服务端口与公开路径配置。
- Archive/tmp/Cache/data：历史归档、临时输出、运行数据或验证截图，开发时默认不作为核心源码修改对象。

## 整体认知

- 项目处于持续迭代阶段，需求会逐步补充，不应一次性重构为完整大系统。
- 每次开发前先读取 `docs/memory`，并更新 `tasks/current_task.md`。
- 对已有模块保持小步修改，优先沿用现有代码结构和 UI 风格。
- 涉及直播弹幕字段时，应优先复用或参考 `D:\Proj\DmProto\Doubao` 中已经验证过的协议解析方法。

## Development status recording policy

- Record every completed, partial, blocked, or runtime-pending development change in `Docs/memory` before handoff.
- Update `tasks/current_task.md` at task start and completion. Add implementation, validation, runtime/restart requirements, and unresolved verification to `progress.md`; add durable behavioral choices to `decisions.md`.
