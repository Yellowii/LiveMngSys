# 2026-08-08 StreamDock TouchBar 歌词插件

任务：新建独立 StreamDock TouchBar 歌词插件，复用 `MusicBot` 已有歌词推送接口，采用左右错位双行歌词布局，并开放画布、背景、渐变、透明度、模糊、字体和位置样式设置。

状态：已完成（待目标局域网进行真实歌词切换确认）

当前步骤：已修复歌词与“暂无歌词”闪跳：首次无状态时不再渲染空画面；同一首歌的空歌词状态不会覆盖已收到的歌词状态；保留 `/api/state` 轮询和 `Arial,Microsoft YaHei` 字体。已部署并重启宿主，等待用户现场确认。

完成内容：
- 新建 `C:\Users\Administrator\AppData\Roaming\HotSpot\StreamDock\touchbar-lyrics-plugin`。
- 运行端同时支持 `current.lyric` LRC 与 `current.wordLyrics` 逐字歌词，并按 `playback.position/updatedAt/status` 计算当前行。
- TouchBar 使用动态 SVG 绘制左右错位的当前行和下一行。
- 属性页已提供 WebSocket 地址、背景/渐变/透明度/模糊、字体颜色和大小、行距/偏移/对齐、画布大小和位置设置。
- `node tests/mock_host.js` 通过：已验证宿主注册、`setImage` 输出、画布尺寸和无歌曲降级显示。
- 行动控制器同时声明 `Keypad` 和 `Information`：TouchBar 正式显示使用
  `Information`，普通按键设备可从插件列表发现、配置和预览该行动。
- 已确认插件进程已连接 StreamDock；为使动作库可拖拽，清单补充标准的
  默认 `States` 定义，待重启后确认前端分类出现。
- 当前前端列表仍未显示该分类；已定位现有可见插件统一使用 PNG/JPG 图标，
  已改用 PNG 图标并升级插件版本至 `1.0.1`，待刷新索引确认。
- MusicBot 源码的服务与 WebSocket 已确认：`bot/server.js` 使用
  `process.env.HOST || '0.0.0.0'` 监听 `7001`，`/ws` 推送完整 state；
  当前工作站并不位于 `192.168.0.0/24`，实测该目标地址端口超时，不能在此处
  完成远端实际歌词验证。
- `SecondaryScreen` 已加入歌词行动的 Controllers，以适配 TouchBar 的可变宽度
  组件布局；LRC 端到端模拟测试已验证当前句/下一句被渲染到 SVG。
- 动作默认配置和旧配置迁移均使用 `ws://192.168.0.10:7001/ws`；属性页增加
  MusicBot 连接/歌词状态提示，便于现场验证局域网服务是否真正推送歌词。

# 2026-07-30 批量续火花启动登录同步

任务：监听服务重启后自动恢复批量续火花私信登录状态，使火花会话列表无需手动检查即可加载。
状态：已完成
已确认：`SparkManager` 登录态仅存于进程内存；服务重启后状态为 `unknown`，前端不会自动触发火花会话加载。
完成内容：
- 服务启动时异步检查独立私信登录态，不阻塞监听服务启动。
- 前端轮询获取 `logged_in` 后自动触发全量火花会话加载。
- 已重启 DouyinListener，未点击检查登录时已自动恢复 `logged_in` 和账号资料。
验证：39 项单元/回归测试、Python 编译、7000 网关启动后状态轮询通过。

# 2026-07-30 批量续火花全量火花会话

任务：批量续火花加载全部带火花状态的私信会话，而不是仅加载会话列表首屏。
状态：已完成
已确认：抖音私信会话根节点包含 `commonStreakstreakContainer/commonStreakicon`；会话栏是虚拟滚动列表，首屏约 12 条但实际滚动高度约 68,000px。
完成内容：
- 分段滚动扫描虚拟会话栏并回到顶部，按昵称和头像组合去重，不再局限于首屏。
- 仅保留存在 `commonStreak` 组件的会话，解析连续天数、火花图标及 `active/inactive/reigniting` 状态。
- 前端改为“火花会话”列表，展示火花天数或重燃状态，并保持多选和全选。
- 已重启 DouyinListener；真实全量扫描返回 23 个火花会话，全部有火花状态，涵盖正常、失效和重燃中。
验证：39 项单元/回归测试、Python 编译、GUIDemo 内联脚本通过；7000 网关全量扫描实测通过。

# 2026-07-30 批量续火花会话加载竞态修复

任务：修复批量续火花已显示登录但读取最近会话提示“请先登录抖音私信”、会话列表空白的问题。
状态：已完成
已确认：状态检查与会话读取并发打开同一 `chat_profile` 时发生竞态；实测并发请求中状态检查失败但会话接口仍读取到 12 条记录。
完成内容：
- 为私信浏览器的登录检查和会话读取增加同一异步锁，避免并发抢占 `chat_profile`。
- 后端缓存最近一次成功读取的会话，后续临时读取失败时返回缓存列表。
- 前端确认私信已登录后自动读取一次会话；手动刷新时保留已选项和已加载列表。
- 已重启 DouyinListener；并发实测登录状态为 `logged_in`、账号资料存在、会话接口成功返回 12 条。
验证：38 项单元/回归测试、Python 编译、前端脚本解析通过；7000 网关并发登录检查与会话读取实测通过。

# 2026-07-30 批量续火花登录态保留

任务：修复批量续火花登录成功后因聊天页加载慢被误判未登录，导致账号资料和登录态丢失的问题。
状态：已完成
已确认：登录窗口内能读取头像昵称，Cookie 已生效；后续检查仅等待 3 秒寻找聊天搜索框，页面慢加载时会覆写为 `logged_out` 并清空账号。
完成内容：
- 聊天页面登录验证等待时间从 3 秒提高到 15 秒。
- 账号资料接口验证作为聊天 UI 的兜底证据；Cookie 有效时即使搜索框晚到也保持私信已登录。
- 瞬时检查失败保留已确认的登录态和账号资料，不再清空头像昵称；浏览器上下文确保关闭。
- 已重启 DouyinListener，真实检查返回私信已登录和账号资料；最近会话接口实际读取到 12 条 `id/name/avatar` 列表项。
验证：账号/会话选择测试 7 项、EventStore/复盘测试 31 项通过；Python 编译、7000 网关登录检查和会话读取实测通过。

# 2026-07-30 批量续火花会话列表选择

任务：批量续火花不再通过手工输入或逐个点击昵称选择接收人，改为从最近私信会话列表中多选。
状态：已完成
已确认：当前界面将会话昵称拼接到文本框，后端也只接收昵称字符串；这会造成选择过程不直观，也不利于后续扩展会话标识。
完成内容：
- 移除接收人昵称文本框，改为最近会话的多选列表，支持头像、单项选择、全选和选中人数。
- 最近会话条目扩展为 `id/name/avatar`，前端提交所选对象数组而不是昵称文本。
- 后端按会话 ID 归一化和去重对象化接收人，保留旧多行昵称请求兼容；任务结果保留 `recipientId`。
- 已重启 DouyinListener；7000 页面和服务健康检查通过。私信独立登录后即可读取其最近会话。
验证：账号/会话选择测试 7 项、EventStore/复盘测试 31 项通过；Python 编译、GUIDemo 内联脚本、网关页面检查通过。

# 2026-07-30 批量续火花登录账号展示

任务：批量续火花页面在私信登录态可用时显示该独立登录账号的头像、昵称和抖音号。
状态：已完成
已确认：续火花使用独立的 `Doubao/chat_profile`，不能直接复用直播监听账号；当前 `spark/status` 仅返回简化的 `login` 状态。
完成内容：
- 从续火花 Playwright 浏览器上下文读取独立 Cookie，复用签名账号接口加载昵称、头像和抖音号。
- `spark/status` 增加 `account/accountLoading/accountError`，检查登录和登录成功时自动刷新；资料失败不改变私信登录状态。
- 批量续火花工具栏增加独立账号头像、昵称、抖音号、登录状态及加载/头像兜底展示。
- 已重启 DouyinListener；当前私信浏览器实测为未登录，接口正确返回空账号且未停留在加载状态。
验证：账号相关测试 5 项、EventStore/复盘测试 31 项通过；Python 编译、GUIDemo 内联脚本解析、7000 网关和页面检查通过。

# 2026-07-30 登录卡片账号资料

任务：登录卡片在抖音登录态可用时加载并展示当前账号头像、昵称和抖音号。
状态：已完成
完成内容：
- `ProfileClient` 新增 `/webcast/user/me/` 当前账号查询，归一化昵称、头像、抖音号、UID、secUid 和主页地址。
- 登录完成、服务启动以及已登录但资料缺失时刷新 `login.account`；资料查询失败不误判登录失效，保留登录态并给出降级提示。
- 登录卡片在已登录状态展示头像、昵称和抖音号，包含加载中、头像文字兜底和资料暂不可用状态。
- 已重启 DouyinListener；经 7000 网关实测返回昵称 `237`、抖音号 `Mngaccount` 和有效头像。
验证：`test_profile_client.py` 2 项、`test_event_store.py + test_replay.py` 31 项通过；Python 编译、GUIDemo 页面和网关接口检查通过。

# 2026-07-30 DouyinWebSourceCode 插件与解析参考

任务：检查 `Docs/DouyinWebSourceCode` 中直播网页插件、粉丝团、会员/星守护、礼物连击、红包/福袋活动的可复用协议字段和状态映射，并按批次把有价值内容接入 LiveMngSys。
状态：已完成
已完成内容：
- 已读取 `docs/memory`，确认当前项目已有 EventStore 归一化层、会员/星守护/粉丝团解析、活动记录和回放入口。
- 已定位网页抓取产物中的 `GiftTrayPlugin`、`GiftEffectPlugin`、`RedPacketNew`、`VipRedpacket`、`LotteryShortTouchPlugin`、`fansclub` 页面和直播客户端入口。
完成内容：
- 网页端 bundle 确认是压缩后的前端消费代码，不作为后端协议实现直接复制。
- EventStore 补充 `groupCount`、`batchCompose`、`totalDiamondCount`，并将批量礼物数量纳入连击增量合并。
- 红包/福袋在有稳定活动 ID 时按 ID 更新原记录，合并活动详情、参与者和中奖者。
- 已补充 EventStore 活动合并与礼物字段测试。
未接入内容：`LuckyBoxMessage`、`LuckyBoxReward`、`LuckyBoxTempStatus` 等仅凭网页 bundle 无法可靠确定 protobuf 字段，待 `DmProto` 提供对应定义后再接入。
验证：EventStore 27 项、复盘 4 项、Python 编译检查全部通过。

# 2026-07-30 弹幕复盘空态修复

任务：修复 `GUIDemo/index.html` 的回放页空态模板截断，恢复场次选择和页面渲染。
状态：进行中
完成内容：已把空态标题恢复为 `正在读取场次列表 / 正在读取场次 / 选择一场已保存直播开始复盘`，并确认模板节点可被正常解析。
当前步骤：继续检查是否还有同类模板损坏。

# 2026-07-30 会员与星守护协议补全

已完成：补充 `WebcastSubscriptionMessage`、`WebcastSpecialMemberMessage`、`WebcastStarGuardMessage`、`WebcastResidentGuestMessage` 的状态码解析，支持开通/续费/取消/过期语义，并保留 `expireTime`、`anchorId`、`guardType`、`subscribeState` 等字段。
验证：`python -m unittest test_event_store`、`python -m unittest test_replay`
# 2026-07-30 任务已完成

已完成：礼物合并、消息去重、粉丝团明文解析、红包/福袋活动详情回放联动、回放场次命名与加载优化。
验证：`python -m unittest test_event_store`、`python -m unittest test_replay`、`python -m py_compile DouyinListener\event_store.py DouyinListener\service.py DouyinListener\test_event_store.py DouyinListener\test_replay.py`
# 当前任务

## 2026-07-30 礼物、粉丝团、活动与场次统一解析

任务：参考 `SourceCodeDouyinBarrageGrab-2.8.0` 与 `DmProto`，完善连击礼物合并、事件去重、粉丝团明文、福袋/红包活动详情及直播间/场次命名，并确保实时与回放共用归一化结果。
状态：进行中
当前步骤：先改 `EventStore` 归一化层，再补客户端会话元数据、前端展示和回放接口。

## 2026-07-30 粉丝团协议核对

任务：确认当前仓库是否已有粉丝团类型消息解析协议，并在必要时参考外部仓库。
状态：已完成
完成内容：
- 当前仓库 `DouyinListener/Doubao/core/gen/douyin_extra_pb2.py` 已包含 `WebcastFansclubMessage`。
- `DouyinListener/Doubao/dict/field_mapping.json` 已为该消息提供字段说明与 `fansclub` 分类。
- `DouyinListener/event_store.py` 已将 `WebcastFansclubMessage` 归入 `score` 类事件处理。
- 参考仓库 `D:\Proj\DmProto\Doubao\proto\douyin_extra.proto` 与 `field_mapping.json` 也存在同名协议定义。

下一步：如需继续补全解析细节，再对照参考仓库的实际落盘样本。

## 2026-07-29

## 2026-07-29 Online badge follow-up

## 2026-07-30 Audience follow relation follow-up

## 2026-07-30 Badge order and relation priority

## 2026-07-30 Badge level merge

## 2026-07-30 Member emoji display

任务：放大会员表情图片并隐藏重复的 `[会员表情]` 文本。

状态：已完成

完成内容：
- 会员表情存在图片时仅渲染图片，不再显示 `[会员表情]` 回退文本。
- 表情图片从 22px 放大至 26px。
- 实时互动和弹幕复盘保持一致。

修改文件：
- `GUIDemo/index.html`
- `GUIDemo/style.css`

验证：
- GUIDemo 内联脚本 Node 解析通过。

当前步骤：
- 修改实时互动和弹幕复盘的会员表情模板条件及图片尺寸。

任务：同类徽章双向合并，保留最高等级与最后有效状态。

状态：已完成

完成内容：
- 同类徽章按等级合并：较高等级替换图标、文字和来源；同等级使用后到状态；较低等级不能回退已有高等级徽章。
- 后续在线榜刷新缺失该徽章时，保留互动/推送已更新的高等级记录。
- 已覆盖 `11级榜单 -> 12级互动 -> 空徽章榜单刷新` 时序；最终保留 12 级图标和等级。

修改文件：
- `DouyinListener/event_store.py`
- `DouyinListener/test_event_store.py`

验证：
- `python -m unittest test_event_store.py`：21 项通过。
- 已重启 DouyinListener，实时在线榜无同类型重复徽章。

任务：统一徽章顺序，并将互动关注状态设为高于 HTTP 榜单的优先来源。

状态：已完成

完成内容：
- 徽章统一排序：等级、特殊、灯牌/星守护、会员、管理；所有后端合并和各展示页共用该顺序。
- 关注状态新增来源标记：HTTP/榜单只作兜底，互动事件中的 `follow_status` 0/1/2 强制覆盖并保持最高优先级。
- 实测小饭团顺序为 `consumer > guard > member > admin`；灯牌用户顺序为 `consumer > fans > member > admin`。
- 实测 3 名在线用户由互动消息映射为互关，且没有逆序徽章用户。

修改文件：
- `DouyinListener/event_store.py`
- `DouyinListener/test_event_store.py`

验证：
- `python -m unittest test_event_store.py`：19 项通过。
- 已重启 DouyinListener，并经网关实时状态验证。

当前规则：
- 徽章顺序为等级、特殊、灯牌/星守护、会员、管理。
- HTTP 榜单的 `follow_status` 作为初始兜底；互动消息内明确的 `0/1/2` 以最新值强制覆盖，并阻止后续 HTTP 覆盖。

任务：将互动消息中的主播关注关系可靠映射到在线榜。

状态：已完成

完成内容：
- 在线榜名单和贡献值仍由榜单快照更新；主播关注关系只由互动消息映射。
- 榜单消息中的默认 `followStatus=0` 不再覆盖已映射的互关/粉丝关系。
- 实测在线榜 28 人中有 2 人已由互动消息映射为互关，且无默认 0 状态残留。

修改文件：
- `DouyinListener/event_store.py`
- `DouyinListener/test_event_store.py`

验证：
- `python -m unittest test_event_store.py`：18 项通过。
- 已重启 DouyinListener 并通过网关实时状态

当前发现：
- 互动消息已解析出互关/粉丝，但 HTTP 在线榜携带的默认 `followStatus=0` 覆盖了榜单用户的 `anchorFollowStatus`。
- 需要区分“消息明确携带关系”与“关系字段缺失”，仅前者可以更新在线榜关系。
- 实测榜单推送也普遍附带默认 `followStatus=0`；关注关系需以互动消息为唯一更新来源，榜单快照只负责名单、徽章与贡献值。

任务：修复在线榜的残留重复徽章与星守护粉丝团名称。

状态：已完成

完成内容：
- 统一 URL 与 URI 的图片资源键，同一房管/勋章不再因 URL 形式不同而重复。
- HTTP 榜单刷新会合并而非覆盖已有 `fansClub` 名称，星守护徽章同时持久化 `clubName`。
- 在线榜与上车队列增加前端视觉去重兜底，星守护沿用实时弹幕的共享 `badge-chip` 渲染。
- 实测“小饭团”：粉丝团名为“哎哟未”，徽章从 8 个收敛为 4 个，重复资源数为 0。

当前发现：
- 在线榜“小饭团”当前快照中，同一房管和同一消费勋章因 URL/URI 形式不同被重复合并。
- 在线榜 HTTP 用户的 `fansClub` 为空时，会覆盖此前互动事件已获得的粉丝团名称，使星守护只能回退显示等级。

完成状态：已完成

完成内容：
- `FollowInfo.followStatus` 已按抖音枚举映射：1 为粉丝、2 为互关；前端昵称着色同步识别互关。
- 在线榜对 `WebcastRoomRankMessage` 优先使用 `audienceRanks`，贡献值可映射并在 HTTP 全量榜刷新后保留。
- 徽章按语义类型去重，星守护会压制普通粉丝团灯牌；在线榜与实时弹幕继续共用同一星守护 `badge-chip` 九宫格绘制。
- 状态拆分为连接状态与 `roomState`，支持直播中、未开播、房间不存在；普通事件不再覆盖未开播/房间不存在结论。
- 已重启 DouyinListener 并验证实时状态为 `connected/live`、贡献值已映射、无重复徽章类型。

修改文件：
- `DouyinListener/event_store.py`
- `DouyinListener/service.py`
- `DouyinListener/Doubao/client/wss_client.py`
- `DouyinListener/Doubao/client/browser_client.py`
- `DouyinListener/test_event_store.py`
- `GUIDemo/index.html`
- `GUIDemo/style.css`

验证：
- `python -m unittest test_event_store.py`：15 项通过。
- Python 编译与 GUIDemo 内联脚本 Node 解析通过。
- 重启后实际 API：在线榜有贡献值映射，最高贡献 300，重复徽章用户 0。

任务：修复直播状态、关注关系、在线榜贡献值与徽章去重渲染

状态：进行中

已完成内容：
- 已重新读取项目记忆，确认本轮沿用现有事件存储、统一 `badge-chip` 和榜单轮询结构。
修改文件：
- 待更新：`DouyinListener/event_store.py`、`DouyinListener/Doubao/client/wss_client.py`、`GUIDemo/index.html`、`GUIDemo/style.css`、测试与项目记忆。

当前步骤：
- 核对 `WebcastRoomRankMessage` 的 `audienceRanks` 贡献值路径、`FollowInfo.followStatus` 枚举，以及房间信息响应中的开播状态字段。
遇到的问题：
- 当前关注关系把 `followStatus=2` 错误映射为“被关注”，而协议中的 2 是互关。
- 榜单合并优先读取 `ranks`，可能错过 `audienceRanks` 的准确贡献值；徽章合并按完整文字/图片去重，无法抑制同类型重复徽章。
- 房间状态会被后续普通事件覆盖，且当前未区分连接状态与房间开播状态。

任务：修复在线观众榜单、实时弹幕清屏、局域网访问、红包福袋及直播间状态

状态：已完成

已完成内容：
- 已确认前端观众榜来自 `/api/livemngsys/live/state`。
- 已定位到 `GUIDemo/index.html` 中观众榜状态仅在页面切换时加载。
- 已补充观众榜定时轮询兜底，避免只靠 websocket 时出现旧数据停留。
- 本轮已重新读取项目记忆，准备继续核对后端快照、服务监听地址、清屏和红包福袋状态。
- 榜单轮询增加请求顺序保护、刷新版本、刷新时刻和轮询状态灯；轮询成功时状态灯亮 1 秒。
- 榜单用户在 HTTP 全量替换、WSS 贡献值更新及互动事件到达时，都会合并最新徽章与用户资料。
- 实时弹幕页新增前端清屏按钮；直播间配置切换会停止旧监听并清空主播、弹幕、榜单、统计和红包/福袋记录。
- 红包和福袋按新增协议归一化为结构化记录，记录抽屉会主动读取最新数据。
- 顶栏直播间状态接入未连接、连接中、已连接、重连中、未开播和异常。
- 网关、MusicBot、监听服务配置统一为 `0.0.0.0` 绑定；网关代理和启动健康检查保留本机回环地址。
- 已定位保存配置未清空的原因：前端仅检测连接字段变化，且旧 WebSocket/轮询状态可在重置后覆盖前端。
- 已将运行配置页保存改为显式会话重置：后端停止旧监听、清空运行态并返回空快照；前端保存前立即清空并拒绝晚到的旧快照。
- 已重启 DouyinListener，使本轮后端逻辑生效并确认监听绑定 `0.0.0.0`。
- 已实际验证：保存前榜单 129 人；保存后状态为 `stopped` 且房间、弹幕、榜单、红包、福袋均为空；启动后状态为 `connecting`，随后恢复 `connected` 并从新会话积累数据。

修改文件：
- `GUIDemo/index.html`
- `GUIDemo/style.css`
- `DouyinListener/event_store.py`
- `DouyinListener/service.py`
- `DouyinListener/test_event_store.py`
- `WebServer/server.js`
- `config/service.json`
- `Start-LiveMngSys.ps1`
- `MusicBot/Start-MusicBot.ps1`

当前步骤：
- 已完成实现、服务重启与实际 API 验证。

遇到的问题：
- 旧前端轮询只靠 websocket/切页，且没有防止慢响应覆盖新状态。
- 当前运行中的 `7001/7002` 进程在修改前启动，仍绑定 `127.0.0.1`；配置和启动脚本已改为局域网绑定，但不在直播中强制终止旧进程。
- 运行中的服务已重启并绑定 `0.0.0.0`，但保存配置的会话重置语义仍未完整落地。
- 无阻塞问题。

## 2026-08-08 Prize notice misclassified as lucky bag - completed

- Traced the screenshot at `2026-08-07 22:46:28` to session `场次20260807_213436_7671282108083440435`, message ID `7671301068386538502`, method `WebcastPrizeNoticeMessage`.
- Verified the 58-byte raw protobuf. It contains only `common` plus wire field 6 decoded as `prizeCount=3`; it has no lucky-box ID, lottery ID, red-packet ID, prize name, display text, or winner user.
- This method is a generic prize/winner notification, not intrinsically a lucky-bag message. DmProto's own update document marks its schema as previously unverified because no representative sample was available.
- Root cause: `event_store.py` treated any nonzero `prizeCount` as sufficient activity detail and then used `luckyBag` as the default category. That produced the incorrect `福袋（已中奖）` card and an unknown winner.
- Tightened classification: `WebcastPrizeNoticeMessage` enters red-packet records only with a red-packet ID/text, and lucky-bag records only with a lucky-box/lottery/activity ID or explicit lucky-bag text. A count-only or winner-only generic notice remains a normal `room` event named `中奖通知`.
- Generic prize notices retain a structured `prizeNotice` object (`winner`, `prizeId`, `prizeName`, `prizeCount`, `lotteryId`) so partially decoded fields are not discarded while the protocol is being completed.
- Replaying the exact archived JSON now yields `kind=room`, `content=中奖通知`, `prizeCount=3`, with no lucky-bag or red-packet record.
- Added a count-only regression test. All 118 Listener unit tests pass.
- Restarted Listener port 7002. Health is `ok`, and the barrage stream is connected with the persisted configuration.

## 2026-08-08 Profile pinyin tone marks - completed

- Root cause: `DouyinListener/nickname_annotation.py` used `pypinyin.Style.NORMAL`, so profile-card pronunciation was intentionally returned without tone marks.
- Changed Han phrase primary readings and polyphonic alternatives to `pypinyin.Style.TONE`; existing phrase-aware conversion, alternative expansion, and frontend layout were preserved.
- Example: `重庆小面` now produces `chóng`, `qìng`, `xiǎo`, `miàn`; `重` alternatives include `zhòng` and `tóng`.
- Updated `test_nickname_annotation.py`; the focused suite passes (`Ran 2 tests ... OK`).
- The running 7002 Listener must be restarted after this module change so the profile endpoint uses the new pronunciation output.

## 2026-08-08 Session temporary memory - completed

- Added `EventStore.session_memory` for the current live session. It is reset only by `reset_live_data()` or a new `room.sessionId`; an audience rank refresh or a viewer re-entry does not clear it.
- Snapshot field: `sessionMemory` with `sessionId`, `roomId`, `startedAt`, `lastUpdatedAt`, `summary`, `users`, and `activities`.
- `summary` tracks `totalLikes`, `totalGiftCount`, `totalGiftValue`, red-packet/lucky-bag counts, unique participants/winners, and unique users.
- Each session user keeps stable identity fields, nickname/avatar, retained historical badges, `watchDurationMs`, likes, gift count/value, highest observed contribution, profit score, participation and winning flags.
- Like and gift totals are added only after existing message de-duplication. Combo gifts use the normalized incremental count to avoid double counting cumulative combo totals. Audience rank pushes update the session user's highest contribution and historical badges.
- Added regression coverage for re-entry/rank refresh retention, duplicate-event de-duplication, and new-session reset. Listener suite passes (`Ran 120 tests ... OK`).
- Frontend state merge now preserves `sessionMemory`; no separate UI has been added yet.
- Restarted Listener port 7002 and verified health: `ok`, `connected`, `live`, barrage stream connected.

## 2026-08-08 Exhibition and anonymous prize replay - completed

- Investigated the archive session `DouyinListener/data/sessions/未说的直播间_MS4wLjABAAAAoqyEw_zA8y_UllvbhZEvLBL8Sd02jRy4CopE958Z91RZtvfGHH1Pew3ry4ZPsstW/场次20260808_014345_7671282108083440435`, focusing on 02:40-02:42, which matches the user's report around 02:43.
- `WebcastExhibitionChatMessage` has two different payloads: the light-up notice contains no user identity, while the paired naming notice contains user ID `3123032006076653` (`小饭团`).
- The same session's `WebcastRoomRankMessage` contains 小饭团's avatar. `EventStore.find_user()` now also searches session-memory profiles, and `apply()` enriches event users/senders from that cache, so known users no longer lose their avatar when a later protocol omits it.
- Exhibition display pieces now render as plain text from `defaultPattern` and `piecesV2`; the replay output is `小饭团 成功冠名了爱你哟` / `小饭团 成功冠名了棒棒糖`, instead of `{0:user}` templates.
- Identity-free light-up and count-only `WebcastPrizeNoticeMessage` events are marked `systemEvent` and shown as `直播间`, not as an unknown user. The prize notice archive is only 58 bytes and contains `common` plus `prizeCount=3`; it has no winner ID, so no winner name or avatar can be recovered from this capture.
- Added regression coverage. `python -m unittest test_event_store` passes with 60 tests; `python -m py_compile event_store.py` passes.
- GUIDemo live interaction rows render `systemEvent` with a non-clickable `直播间` system avatar. The currently running 7002 process could not be restarted because the environment blocked process termination; restart the Listener service before testing the live UI.

## 2026-08-08 Gift total calculated from rank pushes - completed

- Root cause: realtime and replay gift totals were based mainly on `WebcastGiftMessage`. Pushed contribution rankings updated user contribution but did not update the room gift total.
- Rank pushes are partial cumulative snapshots. Snapshots must not be added together, and the latest visible list cannot replace the whole session. Session memory now keeps every user's highest observed contribution and sums those deduplicated maxima.
- User aliases (`id`, `secUid`, and `displayId`) are merged before aggregation, preventing one viewer from being counted more than once when identity fields change between pushes.
- Once a scored rank snapshot arrives, `stats.giftValue` and `sessionMemory.summary.totalGiftValue` use the rank result. Gift-message value remains separately available as `giftMessageValue` for diagnostics and no longer temporarily increments the rank-derived total.
- Added diagnostics: `rankGiftValue`, `giftValueSource`, `rankSnapshotCount`, and `rankContributorCount`.
- Replay retains leaderboard events and updates the displayed gift total at each rank snapshot; rank events remain hidden from the interaction feed.
- Real archive verification: session `场次20260808_034625_7671282108083440435` had three `WebcastRoomRankMessage` pushes. Deduplicated totals progressed `4729 -> 4733 -> 4734`; the final value is 4734 from 13 unique contributors. The replay API returned the same snapshots and final total.
- Validation: `python -m unittest test_replay` passed 5 tests; `python -m unittest discover` passed 126 tests; `python -m py_compile event_store.py service.py` passed.
- Modified files: `DouyinListener/event_store.py`, `DouyinListener/service.py`, `DouyinListener/test_event_store.py`, `DouyinListener/test_replay.py`, and `GUIDemo/index.html`.
- Runtime note: port 7002 is healthy but is served by PID 8688 started at 03:46, before these changes. Restart DouyinListener to load the new calculation.

## 2026-08-09 ��Ļ����-��蹦��
���񣺴�ͨ DouyinListener ��Ļ��� MusicBot �����ӱջ���
״̬�������У��Ⱥ˶�����Э�顢�ӿ����������á�

## 2026-08-09 ��Ļ����-��蹦�ܣ���ɣ�
״̬������ɴ���ջ�����ʵ��ֱ����Ļ�� MusicBot ���н������ֳ����ȷ�ϡ�
��ɣ�Listener �첽 POST �����¼��� MusicBot /api/integrations/danmaku/command��ת������ı����û����ݡ����º�ͷ������ musicBot.enabled��commandUrl��timeoutSeconds ���á�
��֤��Python/Node �﷨ͨ����EventStore 63 �����ͨ���������ع��� Windows ��ʱĿ¼Ȩ��ʧ�ܣ�7000/7001/7002 ��ǰδ���У������ʵ��δ��ɡ�

2026-08-09 update: MusicBot forwarding narrowed to WebcastChatMessage only. Emoji, voice, exhibition, likes, gifts, and all other events are not forwarded.

## 2026-08-09 GUIDemo ���ÿ�Ƭ����Ӧ�Ų�
״̬������� CSS ���������ÿ�Ƭ�����ÿ����Զ����в������ݸ߶��ŷţ���������ӿ�ȷ�ϡ�

## 2026-08-09 Memory maintenance policy

Status: active.
Every development change must be recorded in Docs/memory before handoff. Record completed work, current state, decisions, validation, restart/deployment needs, and unresolved checks.

2026-08-09 update: GUIDemo configuration-card layout verified with Edge screenshots at 1440px and 760px. Desktop wrapping and narrow single-column layout have no overlap.

2026-08-09 update: MusicBot supports attached song-query commands (point song/top/super top) while retaining strict argument-less control commands. Focused BotCore harness passed.

2026-08-09 update: existing intelligentRequest setting now controls tolerant vs strict song-command matching. Focused BotCore harness passed; MusicBot restart required.

2026-08-09 update: GUIDemo preserves unsaved room ID/URL drafts against listener polling and WebSocket snapshots. Inline script parsed; configuration route returned HTTP 200.

2026-08-09 update: removed GUIDemo running/config max-width cap. 2560px browser screenshot shows five cards in one row without overlap.

2026-08-09 update: fixed live-monitor avatar rendering and added room-owner unique_id to displayId normalization. Focused test, Python compilation, and GUIDemo script parse passed. The 7002 Listener runtime remains old because its restart was blocked by execution policy; restart it to populate the current anchor Douyin ID.

2026-08-09 update: resolved Listener WebSocket memory exhaustion. Per-event full-state broadcast tasks are now coalesced into one latest-event worker; slow clients time out after 5 seconds. Process peaked at 38 GB private / 22 GB working set, was restarted, then stayed near 114 MB private after 410 events in 30 seconds. Python compilation and live health checks passed.

2026-08-09 update: fixed MusicBot top/super-top queue behavior. Super-top now stays before every normal top; normal top is ahead of ordinary requests. Node syntax and in-memory order harness passed. MusicBot 7001 was restarted and confirmed healthy.

2026-08-11 task started: build a dedicated MusicBot Soundpad page and service. Scope: file/folder import, independent sound playback/status/external mapping, configurable draggable button board, device/master volume settings, and GUIDemo navigation. Stream Deck plugin will be developed separately and consume stable button IDs and local APIs.

2026-08-11 update: Soundpad implementation completed. Added independent MusicBot Soundpad player/page, 30 persistent uniquely mapped buttons, single-file and recursive-folder import, configure drawer, play/configure modes, drag reorder, button image/color/loop/volume/delay, output/master settings, and opt-in external status/control APIs. GUIDemo now exposes 直播 > 音效板. MusicBot 7001 restarted. Node syntax, unique-ID harness, gateway HTTP 200, and disabled external POST HTTP 403 checks passed.

2026-08-11 update: Soundpad buttons moved into a collapsible left dock; main workspace now holds playback overview/library/settings. Soundpad device selection now enumerates its own mpv devices and migrates follow_musicbot to auto. Buttons persist separate fillColor and progressColor, with playback progress filling the button surface. MusicBot 7001 restarted; Node, state, device enumeration, and Edge visual checks passed.

2026-08-11 update: SoundPad refinement completed. Top header removed; sidebar owns navigation, import, play/configure mode, pages and terminal-local 3-8 column selector, while playable buttons stay in the main workspace. Brand is dual-color SoundPad without MusicBot. Native browser file/folder uploads now copy validated audio into Cache/Soundpad/imports. Drawer edits are protected from polling resets; loop count supports 0/off, positive repeats and -1/infinite. Node checks, HTTP validation and Edge screenshots passed. MusicBot 7001 restarted.

2026-08-11 update: SoundPad frontend rebuilt after layout/persistence defects. Default direct view is the board; sidebar contains navigation/actions/pages, top status bar has current name/progress/time and Stop All. Color labels no longer trigger the picker. Button and playback settings use explicit error-handled save actions and drafts resist polling. Node checks, direct persistence check, restore check, and Edge 1440px screenshot passed. Static assets apply on reload; no service restart required.

2026-08-11 update: SoundPad removed top progress bar; active-button fill now interpolates with requestAnimationFrame between 500ms snapshots. Added terminal-local 72-200px row height and 3-10 columns. Empty buttons are silent in play mode. New Page uses in-app modal instead of browser prompt. Node checks and 1440px Edge screenshot passed; static refresh only, no restart needed.

2026-08-11 update: SoundPad status bar is sticky, forced single-row, with state left and square Stop All icon right. Browser-managed filenames now display original basenames only and startup migrates old timestamp/UUID labels without overwriting manual labels. Node checks, API migration confirmation, and Edge screenshot passed. MusicBot 7001 restarted.

2026-08-11 update: Created and deployed independent StreamDock SoundPad Control plugin. Source: C:\Users\Administrator\AppData\Roaming\HotSpot\StreamDock\soundpad-streamdeck-plugin; installed plugin ID com.hotspot.streamdock.soundpad.sdPlugin. Includes stable page/button play action, stop-all action, inspector enumeration, read-only 350ms state polling, ws dependency and mock-host test. StreamDock restarted; live log confirms plugin connected.

2026-08-11 update: StreamDock plugin renamed to SoundPad (manifest 1.0.1). Fixed keydown reliability by accepting action field variants and refreshing SoundPad state before deciding a mapping is missing. Real external POST with enabled control returned 200; mock test passed; StreamDock restarted and live log confirms connection.

2026-08-12 update: unified MusicBot time synchronization. Added serverTime/revision/bootId to state snapshots; synchronized public player, MusicBot UI, and GUIDemo lyrics playback clocks; stale state rejection and restart boot reset implemented.
# 2026-09-05 GitHub 上传与模块化重构规划

任务：将 LiveMngSys 主代码安全上传到 GitHub，并在仓库内按模块逐步重构整个项目；保持现有功能和用户数据，先建立可回滚的版本基线，再进行分模块改造。

状态：进行中。已读取项目 memory；已确认当前目录尚未初始化 Git，未配置 remote。尚未执行 GitHub 推送。

当前步骤：
- 盘点项目模块、运行数据、配置和潜在敏感文件，制定 .gitignore 与上传边界。
- 初始化本地 Git 并创建首次基线提交前，检查用户现有文件和凭据文件。
- 检查本机 GitHub CLI/凭据状态；若无法自动创建远端，等待用户提供 GitHub 仓库 URL 或仓库名。
- 上传完成后建立模块化重构计划，优先拆分服务层、数据层和前端模块，每阶段独立验证。

设计约束：
- 不上传 Cookie、浏览器 profile、数据库、日志、缓存、媒体、临时输出、密钥或本地机器路径凭据。
- 不在首次上传前大规模改写源码；先保留可复现的原始代码基线。
- 重构采用小步提交、每模块独立验证和可回滚迁移，不改变现有 UI 布局或已确认业务规则，除非后续任务明确要求。

待确认/未验证：GitHub 账户登录状态、目标仓库地址/可见性、是否需要保留 Archive/Docs 截图、首次基线的测试命令与运行依赖。

## 2026-09-05 GitHub CLI 与远端配置进展

- 已通过 WinGet 安装 GitHub CLI 2.100.0。
- 已将 `https://github.com/Yellowii/LiveMngSys.git` 配置为本地 `origin`。
- 当前 `gh auth status` 显示尚未登录 GitHub；代码尚未提交或推送。
- 下一步：完成 `gh auth login` 后，再进行最终敏感文件复核、baseline 提交和 `main` 分支推送。

## 2026-09-05 GitHub baseline 推送结果

- 已使用项目级身份 `Yellowii <yellow1468119954@gmail.com>` 创建 baseline 提交 `4134465`（`chore: establish pre-refactor baseline`）。
- 向 `origin/main` 推送两次均因当前网络到 `github.com:443` 连接重置/失败而未完成；需网络恢复后重试。
- 本地提交可回滚，工作树状态需在网络恢复后再次确认。

## 2026-09-05 GitHub 上传完成确认

- 已确认 `Yellowii/LiveMngSys` 公开仓库可访问，默认分支为 `main`。
- 远端 `main` 已接收提交 `513c988`，本地与远端同步。
- GitHub 上传阶段完成；后续任务转入模块盘点、架构边界设计和分阶段重构。

## 2026-09-05 需求描述整理

- 已将根目录 `需求.txt` 从简单功能清单扩充为需求与模块边界说明。
- 重新按平台基础层、直播采集层、数据运营层、互动业务层、展示工具层和外部扩展层分类。
- 增加总体原则、P0-P3 优先级、验收顺序、当前目录映射及渐进式重构约束。
- 明确点歌、上车、批量续火花、礼物资源、字幕/翻译、复盘等能力的范围和未完成项，避免把规划误写成已实现功能。
