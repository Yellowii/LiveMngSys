# DouyinListener

LiveMngSys 的无界面抖音直播监听服务。监听、protobuf 解析和浏览器登录代码来自 `DmProto/Doubao`，但运行时不依赖原 Tkinter GUI。

默认使用纯 Python 签名直连 `/webcast/im/fetch/` 和观众榜接口，不启动浏览器。仅当抖音签名规则变化、直连失败时，才会短暂启动隐藏浏览器获取动态接口并在连接后关闭。纯签名兼容模块的来源记录见 `vendor/douyin_spider_signing/SOURCE.md`。

观众榜默认每 15 秒通过已登录账号主动拉取一次；WSS 榜单消息只作为两次主动拉取之间的增量更新。管理员登录态可返回榜单成员的贡献值，在线总人数来自实时流，因此两者可能因采样时刻不同而短暂不一致。刷新间隔由 `audiencePollInterval` 配置，范围为 5-300 秒。

服务仅监听 `127.0.0.1:7002`，由主网关 `7000` 端口通过 `/api/livemngsys/live/*` 和 `/live-ws` 对外提供访问。

首次登录可在主界面配置页使用抖音扫码登录；登录态保存在本模块自己的 `Doubao/browser_profile` 与 `Doubao/client/cookies.json`。日常监听不需要保持浏览器运行。

## 扩展接口

- `POST /api/livemngsys/live/users/profile`：使用直播消息中的 `secUid` 采集主页资料，并合并当前直播间勋章、粉丝团和会员信息。
- `GET /api/livemngsys/live/protocol/audit`：统计解析器覆盖、已观察方法、未知方法、解析错误及原始帧样本位置。
- `/api/livemngsys/live/spark/*`：私信登录、最近会话读取和顺序批量发送。它使用独立的 `Doubao/chat_profile`，不会占用直播监听的浏览器目录。

批量私信默认由页面开启“仅预演”，实际发送必须填写接收人和内容并再次勾选确认。链接卡片由抖音网页端生成，平台页面结构变化时可能退化为普通文本。
