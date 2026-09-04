# LiveMngSys 设计决定

## 2026-07-31 Red packet activity semantics

- Do not infer the business activity type solely from `WebcastLuckyBox*`. Use explicit business labels first, then keep the transport activity ID as the cross-message merge key.
- Participant IDs and winner details are different protocol facts. Only render a named participant or winner when that corresponding user record is actually present in a received payload; otherwise explicitly report that the platform did not provide the list.

## 2026-07-31 Live captions integration

- Live captions are independent from the Douyin barrage connection lifecycle.
- Source: Windows Live Captions accessibility tree (`LiveCaptionsDesktopWindow` / `CaptionsScrollViewer`).
- Poll every 250ms, accept after two stable reads, and suppress near-duplicates unless the new text is more complete.
- `liveCaptions.enabled` controls capture; `outputToLiveUi` controls ticker takeover; `persist` archives accepted captions locally.
- Disabling capture clears the current caption snapshot to prevent stale ticker text.

## 2026-07-31 Subtitle fallback and presentation

- Caption timeout is persisted in `liveCaptions`: `fallbackEnabled`, `fallbackTimeoutSeconds`, and `showIdleOnTimeout`.
- A fresh caption displays normally. After the configured timeout: enabled fallback plus idle switch shows idle text; enabled fallback without idle keeps the last caption; disabled fallback hides ticker content.
- Live UI presentation remains local UI configuration. Font, size, text color, stroke, shadow, idle text, and idle scroll duration are stored in the existing Live UI local storage configuration.

## 2026-07-31 Configuration page inline controls

- Room ID/URL selection and its input stay on one row; the selected mode is UI-local and does not replace either persisted room value.
- Listener account profile and login action share one row. Transport label and transport buttons also share one row.
- The main save action belongs inside the live-monitor card, anchored at its bottom; service port saving remains local to the service card.
- Configuration form rows use left labels and right, width-constrained inputs rather than stacked full-width inputs.

## 2026-07-31 Controlled listener reconfiguration

- A full listener configuration save (`resetLiveData=true`) is a controlled reconfiguration: cancel the room monitor, stop the active WSS client, apply and persist the config, reset live data, then create a fresh room monitor if enabled.
- This sequencing prevents an old monitor task from probing or auto-starting with stale room settings while a new configuration is being applied.

## 2026-07-31 LiveDash refresh alignment

- Match LiveDash by reading the last non-empty Windows caption line, without sentence-stability delay or similarity replacement.
- Keep only exact-repeat suppression; every changed line increments the caption revision immediately.
- Use `/api/livemngsys/live/captions` as a lightweight caption-only endpoint. Live UI polls it every 150ms with an in-flight guard.
- Caption output stays single-line and static. When it exceeds the available width, split it into LiveDash-style width-fitting segments and switch to the next segment; only idle text uses the configured scrolling duration.
- Reflowing caption segments for a font or viewport change must preserve the active segment index, clamped to the new segment count. A same-text refresh must not rebuild segments or return the display to the first segment.

## 2026-07-29

## 2026-07-30

- 同类等级徽章的合并规则为“最高等级优先，同等级最后状态优先”。这适用于 HTTP 榜单、实时 rank 推送和互动事件的双向合并，避免低等级或空快照回退已更新的灯牌/星守护。

- 徽章顺序由后端 `_merge_badges` 统一排序，避免各前端页面自行排序造成不一致。顺序为 `consumer -> special -> fans/guard -> member -> admin`。
- 用户主播关注关系保存来源。`interaction` 的优先级高于 `http/rank`；互动事件中明确携带的 0（非关）、1（关注主播）、2（互关）均应覆盖 HTTP 兜底值。

- 在线榜的主播关注关系以互动事件为唯一可信来源。榜单接口和 rank 推送中的 `followStatus=0` 是普遍默认值，不可用于覆盖已有关系映射。

- 徽章资源去重必须将 `https://.../img/<uri>~...` 与 `<uri>` 视为同一资源；在线榜的空 `fansClub` 数据不能覆盖已有非空粉丝团信息。星守护名称优先读取徽章保存的 `clubName`，再回退用户 `fansClub.name`。

- 监听连接状态与直播间业务状态分离：`status.state` 表示未连接、连接中、已连接或异常，`status.roomState` 表示 `unknown/live/not_live/not_found`。前端优先展示房间业务状态，避免“已连接”掩盖未开播或房间不存在。
- 在线榜贡献值以 `WebcastRoomRankMessage.audienceRanks` 为优先来源；`ranks` 只作为兼容兜底，避免同一推送中的泛用榜单覆盖观众榜真实 score。
- 徽章去重以业务类别而不是图片 URL 或文字作为主键。星守护与普通粉丝团同时出现时，只保留星守护，所有页面继续共用统一组件和原有九宫格样式。

## 已确认原则

- 长期持续开发：需求逐步补充，记忆文件持续维护。
- 开发前先读取 `docs/memory`。
- 每次任务开始更新 `docs/memory/tasks/current_task.md`。
- 开发过程中记录已完成内容、修改文件、当前步骤和遇到的问题。
- 任务中断后优先读取 `current_task.md` 恢复。
- 不随意重构已有代码；如发现架构问题，先说明原因再行动。

## 当前技术判断
- `Docs/DouyinWebSourceCode` 是浏览器抓取后的压缩 bundle 集合，插件名和字符串可用于确认前端消费语义，但不能据此反推新的 protobuf 字段。
- 礼物归一化沿用后端 `EventStore`，将 `comboId` 作为连击流主键，`groupCount` 作为批次增量提示，`totalDiamondCount` 作为累计价值展示字段；缺失字段时保持旧的 `count/repeatCount` 兼容行为。
- 活动记录采用“消息 ID 去重 + 活动 ID 更新合并”两层规则：消息 ID 防止同一消息重复落盘，活动 ID 保证同一红包/福袋的状态更新复用一条复盘记录。
- `LuckyBoxMessage/LuckyBoxReward/LuckyBoxTempStatus` 等网页端消息暂不接入，必须先取得 `DmProto` 的确定 schema 或实际解析样本，避免从压缩 UI bundle 猜字段。

- 抖音协议字段和徽章解析优先参考 `D:\Proj\DmProto\Doubao`，避免重复摸索协议结构。
- UI 样式优先参考 `GUIDemo/互动聊天` 和 `GUIDemo/Tray.png`，并保持现有项目风格一致。
- 徽章后端 API 保持现有 `type/label/icon` 字段兼容，同时新增 `kind/level/uri/bgColor/fgColor/source`，便于未来细化展示和权限规则。
- DmProto 的 `fans_club/pay_grade` 在 LiveMngSys 前端继续兼容为 `fans/consumer` 类型，避免破坏已有上车和 MusicBot 角色判断。
- 事件级徽章（会员、订阅、贵族、星守护等）应合并到事件用户的 `user.badges`，这样实时区和复盘读取相同结构。
- 徽章展示默认采用纯图片，不使用文字标签、底纹或人工颜色块；仅星守护保留徽章内文字，并按平台 `border-image` 样式渲染。
- 互动类别不在事件行内显示文字标签，改由事件卡片背景色识别；实时与复盘筛选按钮使用同一套颜色映射。
- 星守护徽章优先级高于粉丝团灯牌：同一用户同时存在星守护和粉丝团灯牌时，只展示星守护。
- 星守护徽章内文字优先使用粉丝团 `ClubName` 对应的 `fansClub.name/clubName`，不额外拼接等级，避免把已含数字的团名重复显示。
- 会员徽章暂时只渲染原始用户数据中携带的图片；不把 `subscribe_new_3x.png` 强制替换为普通会员 `1231241211V.png` 或年费会员 `31231321Vnian.png`，除非后续确认会员类型字段与稳定规则。
- 实时弹幕/礼物与复盘行优先采用紧凑扫描布局：用户昵称、正文或礼物摘要同一行，徽章独立一行，正文超宽换行。
- 直播间关系色统一为：互关紫色、粉丝蓝色、未关注或未知灰白；`被关注` 暂不归入粉丝色，避免误判。
- `WebcastAudienceRankList` 来自网页或签名 HTTP 观众榜，应视为当前可见在线观众榜的权威快照，每次收到有 ranks 的数据都整榜替换；WebSocket rank/seq 消息只补充贡献值。
- 用户个性签名优先使用主页资料接口返回的 `signature`，若为空则使用直播消息归一化用户中的 `signature` 兜底。
- 实时互动行的徽章应与昵称处于同一 identity 组，content 作为后续可换行内容；避免长内容把徽章挤到下一行。
- 九权等直播间出现的 `ranklist_fansclub*_advanced_badge_*_xmp` 且 `imageType=51` 应按星守护处理；非 xmp 或普通 `imageType=7` 版本仍按粉丝团灯牌处理。
- `ranklist_fansclub_pop_advanced_badge_*_xmp` 属于普通版本二粉丝团灯牌，不做 `border-image` 拉伸，只按普通图片显示。
- `fansclub_new_advanced_badge_*_xmp` 属于普通版本一粉丝团灯牌，不做 `border-image` 拉伸；只有 `star_guard_advanced_badge_*_xmp` 与 `ranklist_fansclub_advanced_badge_*_xmp` 才作为星守护拉伸渲染。
- 星守护徽章的左侧视觉压缩通常来自 `border-image-width` 左切片过小；应优先恢复接近原始的 18px 左切片与 14px 高度，再观察整体宽度。
- 星守护徽章按抖音官方 DOM 拆分版本：`star_guard_advanced_badge_*` 内部文字左缩进 12px，`ranklist_fansclub_advanced_badge_*` 内部文字左缩进 14px；`border-image-width` 继续使用 18px/9px 九宫切片，但布局 `border-width` 只保留上下 0、左右 `medium`，避免把切片宽度直接算进元素布局或把 14px 高度撑成 20px。
- 星守护徽章在 LiveMngSys 的 GUI 中不再保持原始 14px 高度，而是与普通徽章统一到 20px 视觉尺度；固定切片、字号和内缩一起按同一缩放因子放大，保证同一行内的徽章视觉比例一致。
- 在星守护徽章已经完成统一缩放后，后续微调优先只改内部字号，不再继续改徽章几何尺寸，避免反复扰动已认可的整体比例。
- 徽章显示顺序固定为“徽章 -> 昵称 -> content”，其中徽章组不设置会裁切自身宽度的容器上限，避免多徽章互相遮挡。
- GUIDemo 采用 hash 路由作为轻量 SPA 状态保持方案，路径格式为 `#/tab/subTab`，并用 localStorage 在无 hash 时兜底恢复最近页面。
- `WebcastAudienceRankList` 仅作为在线观众榜快照，不再把其中默认 `score=1` 视为真实贡献值。
- 真实贡献值优先来自实时推送的 rank/seq 数据，并按用户身份缓存，后续轮询全量刷新时保留最近一次有效值。
- 会话数据按 `直播间名/场次<id>/proto` 与 `json` 落盘，历史扁平 session 仍然保留兼容读取。
- 主播与房间详情优先从 `room/web/enter` 与 WSS 房间信息补全，便于后续页面展示与复盘。
- 前端观众榜不只依赖 websocket 推送，页面处于直播页时会按配置间隔轮询 `/api/livemngsys/live/state`，作为数据更新兜底。
- 观众榜快照以 `audienceStatus.revision`、榜单刷新时间和最近事件时间作为前端更新依据；前端忽略晚到的旧响应，避免慢请求覆盖新榜单。
- 用户点击实时弹幕清屏只影响当前浏览器展示，服务端事件存储和落盘数据不删除；切换直播间连接参数则停止旧监听并清空运行态，防止不同房间的数据混合。
- `0.0.0.0` 仅用于服务监听。网关访问 MusicBot 和 DouyinListener 时将通配绑定地址转换为 `127.0.0.1`，因为通配地址不能作为稳定的 HTTP 上游目标。
- 红包/福袋以独立活动记录保存：超级红包预览保存红包标识、标题、数量和时间；福袋开奖保存福袋标识，前端抽屉按活动类型主动刷新。活动记录在当前监听场次内不设截断，实时弹幕“清屏”不影响其保留。
- 活动聚合以业务 ID 而不是消息 ID 或通用 `activityId` 为主键：福袋优先 `luckyBoxId/luckyBoxIdStr`，红包优先 `rpId/redPacketId`。同一活动的发放、参与和开奖更新同一条记录，并追加生命周期 `updates`、参与者和中奖者。
- `WebcastRoomDataSyncMessage` 的 `LotteryInfoSyncData` 是高频福袋状态同步，不应逐条作为活动记录。解析其 Base64 protobuf `data` 的 field 1 varint 作为稳定 `lotteryId` 合并；缺失该 ID 时，仅在同一房间 120 秒窗口内按回退键合并。该类同步不使用内部 `dataType` 作为前端文案，并只保留最新一条“状态同步”生命周期节点。
- `LotteryInfoSyncData` 的正式字段为：1 `lottery_id`、2 `lucky_count`、3 `candidate_total_count`、5 `lottery_type`、6 `prize_count`、7 `start_time`、8 `draw_time`、12/13 为扩容前的奖品/名额。抽屉应使用 2/3/6/7/8 显示名额、参与数、钻石、开始和开奖时间。若平台未发送结束包，`draw_time` 已过时必须在事件处理和快照读取时自动收敛为 `ended`，但不得伪造未在最后同步中出现的参与者名单或最终人数。
- 红包/福袋活动抽屉应将摘要和详情分层：卡片默认显示概览，用户可展开查看已解析的时间、数量、条件、人员、生命周期和原始字段。`LotteryInfoSyncData` 的通用活动标题只能写入活动标题，不能作为奖品；全空奖品对象统一表示为“待协议补全”。
- 互动事件的展示用户按 `payload.user`、`common.user`、`displayText.pieces/piecesV2[].userValue.user` 依次取值；后者是粉丝团和关注提示的常见实际落点。
- 运行配置页的“保存配置”视为一次新的监听会话，即使房间号未变化也发送 `resetLiveData` 并清空旧运行态；实时页“保存”仅保存展示选项，不中断监听。
- 前端在等待配置重置确认期间拒绝带有旧事件时间的 `connected` 快照，直到收到空的停止状态或新的连接中状态，避免旧 WebSocket/HTTP 响应重新填充已清空的卡片。
- 登录账号资料使用抖音网页端 `/webcast/user/me/`，复用 `ProfileClient` 的 Cookie、msToken 和 a_bogus 签名链路；资料是登录态的附加信息，查询失败时不得把有效 `sessionid` 降级为未登录。
- 批量续火花账号必须来自 `Doubao/chat_profile` 的独立浏览器 Cookie，不能复用直播监听账号资料；两边可能登录不同账号。账号资料查询失败仅影响工具栏资料展示，不改变私信功能的登录判定。
- 批量续火花接收人以最近私信会话列表为唯一页面选择入口，使用会话条目的 `id` 做前端选择和后端去重；后端保留多行昵称请求兼容，供已有自动化调用继续使用。
- 批量续火花登录核验不能只依赖聊天页的搜索框渲染。聊天 UI 可能慢于 Cookie 生效，因此以独立 Cookie 的当前账号验证为兜底；一次核验异常不清空已确认的私信账号资料。
- 使用同一个 Playwright persistent profile 的私信登录检查、会话读取和后续发送必须互斥执行。并发打开会导致 Cookie/页面状态判断不稳定；会话读取成功后可缓存最近列表作为短暂失败的降级结果。
- 批量续火花不以首屏最近会话作为完整数据源。私信会话栏是虚拟列表，必须滚动扫描至末尾；火花会话以 `commonStreakstreakContainer/commonStreakicon` 的存在作为判定依据，并透传连续、失效和重燃状态。
- `SparkManager` 的状态不持久化到磁盘，但其浏览器登录 Cookie 已持久化。因此监听服务启动时应异步重做一次私信登录校验，让前端从 `unknown` 自动收敛到可用状态。
- 火花状态不应作为行尾微小图标呈现。会话选择列表中，每位用户必须显示固定尺寸的火花徽标及文字状态；失效和重燃需要独立颜色，避免在深色界面中被误认为无状态。
- 批量续火花的随机文案采用 `DouYinSparkFlow` 已使用的一言接口 `v1.hitokoto.cn`，仅请求文学、诗词、哲学类别。接口只在用户点击生成时调用，单条结果直接填入输入框，多条结果由用户选择后填入；批量发送阶段不调用第三方文案接口，也不自动追加内容。请求设置短超时和本地文案后备。
- 批量续火花在桌面端采用横向等宽三卡片布局：会话列表、消息与配置、任务进度与日志；窄屏才纵向堆叠。火花“已亮”包含正常和重燃状态，“未亮”仅指失效状态；群聊优先使用页面明确类型语义。对名称不带群语义、但会话头像实际来自抖音 `*-aweme-im-img.byteimg.com` 群头像资源的条目，也归类为群聊；其他未确认条目仍按私聊处理。
- 批量私信不得用页面全局同名文本定位。私聊应点击搜索面板结果的“发消息”操作；群聊不一定出现在联系人搜索中，因此会话采集时保存虚拟列表 `listOffset`，发送时按头像、名称和偏移量直达会话行。无偏移量的旧请求才回退全表虚拟滚动扫描。
- `WebcastEmojiChatMessage` is a verified image-bearing barrage protocol. Its generated protobuf descriptor contains `emoji: EmojiStruct`, while observed payloads may encode the EmojiStruct in `content`; the event layer must support both and expose `emojiImage` for live and replay UI rendering.
- 批量续火花的停止和启动共享同一后端异步锁。停止必须先取消、等待任务和浏览器上下文释放、清空任务引用，随后才允许新批次创建；前端在停止请求完成前禁用再次发送，避免两个请求乱序导致旧任务判定为运行中。
- 福袋详情必须区分“参与人数”和“参与者名单”：`LotteryInfoSyncData.candidate_total_count` 只能展示人数，不能据此构造用户列表；`LuckyBoxRewardMessage.rewarded_user_id` 只能作为中奖 UID。若收到 `XGLotteryMessage.lotteryInfo.luckyUsers`，才可显示包含昵称、头像、奖品的完整中奖名单。`/webcast/luckybox/box/list/` 是进行中活动列表，不能作为历史参与者名单来源。
- 直播状态不能由 WSS 是否有消息推断。`room/web/enter` 只提供候选数据，因为关播后仍可能保留旧场次快照。`web_rid` 是稳定直播间号，接口 `id_str` 是场次号；前者不能被后者覆盖。仅接口 `status=2` 可作为开播候选，`status=4` 不是开播证明。使用无头浏览器读取渲染页的“直播已结束/暂未开播/直播间不存在”作为优先否决结论；页面确认未开播或已结束时停止 WSS、保持轮询，`autoStart` 只在确认开播后创建监听。前端分别标明直播间号、场次号和主播抖音号，缺失 `display_id` 时不以 UID 或场次号代替。
## 2026-08-01 Fan database and strict archive

- The fan database is a durable SQLite projection of normalized events, while room/session JSON and Raw Proto remain the authoritative event archive.
- Each listener session is stored under `data/sessions/<room>/<session>` and must retain parsed JSONL, per-message JSON, Raw Proto, and a Raw Proto index.
- Raw Proto retention is mandatory for service-created sessions so later protocol improvements can reprocess the original payloads.
- A fan record uses a stable identity from uid, secUid, or display id. Mutable profile fields are updated in place and appended to `fan_field_changes` with `changed_at`.
- Mystery users are indexed separately from ordinary fans. A mystery flag or explicit mystery nickname is stored as a state, while the visible nickname remains historical data that may change.
- The primary UI is the fan list. Mystery users are a filter/view over the same database, not a separate manually maintained list.

## 2026-08-01 Per-anchor fan database boundary

- Fan data is isolated per broadcaster. The stable database key prefers the anchor uid, then secUid, then configured anchor identity; room id and live session id must not choose the database because they can change per broadcast.
- Every anchor database lives at `DouyinListener/data/fans/anchors/<anchor-key>.sqlite3` and stores its own `fan_database_meta`, member records, star guardian records, interaction records, field history, and session sightings.
- The previous `data/fans/fans.sqlite3` is retained as an unscoped legacy file and is no longer used for new listener writes, preventing uncertain historical ownership from contaminating a broadcaster-specific database.
- The fan UI follows the LiveDash management pattern: structured filters, membership/guardian/level statistics, listener status, selectable list rows, and a full member detail workspace instead of a generic drawer.

## 2026-08-01 Douyin gift assets discovery

- The captured Douyin web source contains signed requests for `/webcast/gift/list/` and `/webcast/assets/effects/`. The former is the room-specific gift catalog; the latter is the downloadable effect/resource catalog.
- Captured gift-list requests include `room_id`, `sec_anchor_id`, `gift_scene=1`, and `fetch_giftlist_from=3`. Captured effect-list requests include `is_living` and `download_assets_from=3`.
- `/webcast/gift/detail/` and `/webcast/gift/extra/` are also registered in the client source for per-gift supplemental data.
- Incoming `WebcastGiftMessage` already includes the sent gift's `gift.image`/`gift.icon` URL list, suitable for per-event rendering; the catalog endpoints are needed for the complete selectable gift and effect inventory.

## 2026-08-02 Inline chat emoji rendering

- Verified from `D:\Proj\LiveDash\抖音网页\ChatRoom.js` that Douyin web loads `GET /aweme/v1/web/emoji/list`, maps each `display_name` such as `[微笑]` to `emoji_url.url_list[0]`, and splits ordinary chat text with the `[... ]` convention.
- Added `DouyinListener/emoji_assets.py` with a local JSON cache under `DouyinListener/data/emoji/`; the listener refreshes the official list at startup and retains the previous cache on network failure.
- Ordinary `WebcastChatMessage` events now keep the original `content` and additionally expose `contentSegments` for mixed text/image rendering. Unknown bracketed text remains text. Live and replay interaction templates use the same segment renderer.
- The web source also defines `ActivityEmojiGroupsMessage`: `common`, repeated `EffectiveActivityEmojiGroup`, then `ActivityEmojiGroup` (`id`, `idStr`, `name`, `tagIcon`, `desc`, `emojiList`, `insertEmojiNum`) and `ActivityEmoji` (`id`, `idStr`, `name`, `emoji`). Composite display names use the verified `[group_name_emoji_name]` format and resolve to the nested image URL.
- Added and compiled these activity emoji messages. The event store registers their composite-name-to-image mappings before normal chat rendering, so live and replay can resolve composite emoji without guessing a URL.

## 2026-08-02 Listener browser transport and memory diagnosis

- Root cause of the listener repeatedly entering browser compatibility mode: the score-capture troubleshooting on 2026-08-01 persisted `transport=browser` and `browserVisibleFallback=true` in `DouyinListener/data/config.json`. These were temporary capture settings, but `load_config()` restores them on every service start, so the behavior appeared forced.
- Browser compatibility mode launches a persistent Playwright Chromium/Edge context. Headless mode still consumes substantial memory, and visible fallback can keep additional browser processes alive; the observed 3.9 GB system/process total is consistent with this configuration plus other live-browser tools on the machine.
- Restored the active listener configuration to `transport=wss` and `browserVisibleFallback=false`. `bootstrapBrowser=true` remains enabled only as a bounded WSS fallback: it opens a headless browser temporarily to resolve dynamic transport values and calls `shutdown()` in `finally`; it is not the steady-state transport.
- Do not enable visible browser fallback for routine listening. Use explicit browser transport only when a clean protocol-capture task requires it, and revert the persisted transport immediately after capture.

## 2026-08-02 Listener runtime fallback cleanup

- Listener runtime settings are now treated as connection-affecting. Changing `transport`, `saveRaw`, `browserHeadless`, `browserBlockMedia`, `browserVisibleFallback`, `bootstrapBrowser`, `reconnect`, `reconnectMax`, `reconnectDelay`, or `audiencePollInterval` forces a stop/restart so the running client actually picks up the new behavior.
- Browser compatibility mode now goes through a locked single-context launch path. The headless-to-visible fallback happens once inside `_run_browser_session_loop`; the outer duplicate visible-browser fallback in `connect_and_run` was removed so retries do not stack extra browser instances.
- Browser shutdown now uses serialized cleanup with timeouts, which keeps visible-browser retries from accumulating when a page fails.
- Validation: browser client and listener service tests passed, Python compilation passed, and the listener service was restarted on port 7002 with a healthy `/health` response.

## 2026-08-02 GUIDemo responsive layout

- Use dynamic viewport height (`100dvh` fallback) and safe-area bottom padding on the main workspace so mobile browsers do not hide the lower edge behind their address bars or gesture bars.
- Let the root flex chain shrink with `min-width: 0` / `min-height: 0` so nested scroll areas can actually compress on narrow screens.
- Collapse the listener dashboard and live monitor to single-column layouts at smaller widths instead of preserving desktop multi-column grids that push content below the viewport.
- Keep the sidebar responsive to resize events so a device rotation or browser resize does not leave the layout stuck in the old collapsed state.

## 2026-08-02 MusicBot responsive layout

- The MusicBot UI must not keep a hard `1440px` minimum width in the embedded page. Responsive behavior should come from the bundle itself, not from the outer LiveMngSys iframe.
- On narrow screens, the MusicBot workspace should stack its main content and log panes, and the header tab strip should wrap instead of hiding later tabs behind the viewport edge.
- The top song header can expand vertically on small widths, because keeping it at a fixed 140px row height caused clipped content once the layout wrapped.
- Do not use `zoom` plus inverse root width for high-DPI MusicBot scaling. It leaves unpainted iframe space on some browser/resolution combinations; keep the root at full width and use dark iframe/page backgrounds as the fallback fill.

- `WebcastLuckyBoxMessage`, `WebcastLuckyBoxTempStatusMessage`, and `WebcastLuckyBoxRewardMessage` are now registered from the DmProto schema, and `ActivityEmojiGroupsMessage` is categorized as `emoji` again to match the updated parser contract.
- `DouyinListener/Doubao/core/gen/douyin_extra_pb2.py` is regenerated from the local `douyin_extra.proto` using the DmProto `douyin_live.proto` include base; no generated protobuf file is edited by hand.
- Do not import the old standalone `DouyinListener/Doubao/core/gen/lucky_box_pb2.py` after the DmProto merge. Its lucky-box symbols duplicate the definitions now compiled into `douyin_extra_pb2.py` and will break pure-signature barrage parsing.
- For lucky-box records, trust the protocol ID on `WebcastLuckyBoxMessage` / `WebcastLuckyBoxRewardMessage` / `WebcastLuckyBoxEndMessage`. `WebcastLuckyBoxTempStatusMessage` has no independent lucky-box ID in the current DmProto schema, so it should only attach to the nearest active lucky bag instead of inventing a synthetic identifier.
- Treat `winnerUserIds` / `rewardedDetails` as the winner list for lucky-box reward packets, and preserve the explicit sender from the lucky-box open message instead of letting later winner data overwrite it.
- Do not claim that `LotteryInfoSyncData` contains participant or winner names. Real archived samples only show ID, count, amount, and timing fields. Participant names remain unavailable from this sync packet; winner details can only be filled from `WebcastLuckyBoxRewardMessage` (`winnerUserIds` / optional `rewardedDetails`) or `WebcastXGLotteryMessage.lotteryInfo.luckyUsers`.
- Treat `DouyinListener/Doubao/proto/douyin_extra.proto` as the canonical lucky-box schema inside this project. The external `_merged.proto` snapshot is older and does not carry the extended reward/lottery detail fields, so do not backport behavior from it into the live parser.
- `LotteryEventNewMessage`, `LotteryCandidateEventMessage`, and `LotteryDrawResultEventMessage` are the authoritative lottery/melon participant-winner chain. `LotteryInfoSyncData` remains a status sync only, so the event store must not fabricate participant or winner names from it when the candidate/draw messages were never captured.

## 2026-08-03 Unified project data architecture

- The long-term target is one logical SQLite database, `data/livemngsys.sqlite3`, containing multiple relational tables. "One database" does not mean one wide table.
- Broadcaster separation remains mandatory. Shared entities such as users, gifts, songs, and media are stored once, while broadcaster-specific relationships and statistics are keyed by `anchor_id`.
- Stable identity order is Douyin UID, SecUID, then Display ID. Nicknames must never be identity keys; uncertain anonymous/mystery identities remain temporary until verified.
- `web_rid` is the stable room identifier and platform `live_id` is the changing session identifier. They must map to separate `live_rooms` and `live_sessions` records.
- Raw protocol archives are authoritative evidence, normalized `live_events` are the shared business contract, and feature tables are query projections. Projections must remain rebuildable from events and archives.
- Large binary/media data stays file-backed. SQLite stores metadata and indexes rather than Raw Proto, video, audio, browser profiles, or plaintext credentials.
- A single repository owner performs database writes. Node services and browser pages access shared data through APIs to avoid duplicate field interpretation and cross-process SQLite write contention.
- Migration must be phased with old/new dual-write comparison before legacy writes are disabled. Strict session archive retention remains required throughout migration.

## 2026-08-03 Mystery identity handling

- A mystery user may still carry usable platform fields. Prefer normal non-sentinel `uid`, then `secUid`, then `displayId`; keep `shortId` and `idStr` as additional identity observations.
- `id=111111` is a confirmed collision sentinel in the local archive and must never become a global user identity. The identity resolver must reject known sentinel values before matching.
- A record with only `idStr` or an incomplete user object is scoped to `anchor_id + session_id` until repeated evidence proves a wider scope. It must not be merged across anchors or sessions by nickname, avatar, pay level, or follow counts.
- `secret=1` is not equivalent to mystery mode. It appears on ordinary users too and should be stored as a privacy/profile field rather than used as the classifier.
- Mystery UI should expose an anonymous profile with evidence fields and confidence/scope labels, not promise recovery of the underlying real account. Automatic cross-mode de-anonymization is prohibited without verified user/platform evidence.

## 2026-08-04 Listener browser lifecycle

- Chromium renderer/GPU/utility subprocesses under one browser root are expected; count browser root processes/Playwright drivers when detecting leaks, not every Chromium subprocess as an independent listener.
- Room-status monitoring must not retain a loaded Douyin live page. Use the signed room API for normal polling and launch a temporary headless page only when live API status conflicts with a stale/silent barrage stream.
- Every temporary page verification must block heavy static/media resources and close its page, browser, and Playwright driver in `finally`. It must never use a visible fallback window.
- Browser compatibility listening may own at most one active persistent context per client. Pure-signature bootstrap browsers and interactive login browsers are temporary resources and require unconditional `finally` cleanup.
- Cached Douyin cookies must not be rejected solely because a local save timestamp crossed an arbitrary age threshold. Try the cached `sessionid` and let the authenticated server request establish whether it is expired.

## 2026-08-05 Membership event evidence and extraction

- Douyin may deliver a membership purchase/renewal through generic `WebcastNotifyEffectMessage`, `WebcastRoomMessage`, and `WebcastRoomNotifyMessage` methods rather than a dedicated `WebcastSubscriptionMessage`.
- Membership normalization must inspect rich-text users under `common.displayText.piecesV2[].userValue.user` and operation strings such as `renew` / `续费`; top-level `payload.user` alone is insufficient.
- `subscribe_enter_effect` is a subscribed-member entrance effect and must not be classified as an open/renew transaction.

## 2026-08-06 Viewer identity card presentation

- The profile hero shows nickname plus one pronunciation line only. Do not repeat the display ID or render the annotated Chinese nickname characters a second time.
- The profile badge band has no heading. Anchor relationship chips show only the relationship value, and profile-context badges use a 24px visual height while retaining the shared badge renderer.

## 2026-08-09 Danmaku command integration

- The Listener-to-MusicBot bridge forwards only `WebcastChatMessage` ordinary text danmaku. Do not use broad `kind=chat` forwarding because that category also includes emoji, voice, and exhibition events.
- Delivery is asynchronous and best-effort. MusicBot rejection or an unavailable endpoint must be logged without blocking the Douyin listener event loop.

## 2026-08-09 GUIDemo configuration layout

- Configuration dashboard cards must use content-responsive grid placement. Avoid fixed equal card heights when card contents differ materially; retain the existing single-column narrow-screen rule.

## 2026-08-09 Song command matching

- Commands that require a song query may accept the query immediately after the configured keyword as well as after whitespace. Argument-less playback controls must retain whitespace/exact matching to prevent accidental actions from ordinary chat text.

## 2026-08-09 Intelligent song-command switch

- `permissions.intelligentRequest` is the sole switch for tolerant attached-argument parsing of song-query commands. Disabled mode must preserve strict whitespace-separated parsing.

## 2026-08-09 Listener configuration draft ownership

- A user-edited room ID or URL is local draft state until save succeeds. Periodic state polling and WebSocket snapshots may refresh runtime state but must not overwrite an unsaved room-target draft.

## 2026-08-09 Configuration dashboard width

- Do not cap the running/config dashboard container width. Grid column count must be determined only by workspace width, card minimum width, and responsive breakpoints.

## 2026-08-09 Live monitor anchor identity

- Treat `unique_id` / `uniqueId` in a room-enter owner payload as the anchor's public Douyin ID, normalized into the existing `displayId` field. Do not label the numeric live room ID as a Douyin ID when the public ID is absent.
- The monitor card should render the Listener-provided avatar URL directly and only fall back to an initial avatar when no URL is available.

## 2026-08-09 Listener WebSocket backpressure

- High-frequency live events must be coalesced before WebSocket delivery. A slow client may receive the newest state but must never create an unbounded backlog of full-state snapshots in the Listener process.
- WebSocket delivery has a finite timeout; timed-out sockets are stale and must be removed rather than retaining server memory.

## 2026-08-09 MusicBot priority tiers

- Queue priority order is `super-top > top > ordinary request`. The priority marker must control insertion order, not merely UI metadata.
- Within each priority tier, newer requests are inserted first. A regular top request must never overtake any super-top request.

## 2026-08-11 Soundpad isolation and external mapping

- Soundpad owns an independent mpv player and IPC channel. It must not reuse the song player's `load`, `stop`, or end-event lifecycle because those operations control the request queue.
- Soundpad pages persist stable unique button IDs. External controller mappings use `pageId + buttonId`, while the UI may show a compact button token for readability.
- External Soundpad writes are disabled by default. Status remains readable through the integration endpoint, but playback/stop requires the explicit Soundpad external-control setting.
- Soundpad state is separate from the regular MusicBot queue snapshot. Progress reports only the current Soundpad button and its playback timing; do not broadcast the entire library on frequent progress updates.

## 2026-08-11 Soundpad interaction layout

- The Soundpad board is a left-side control dock, not a main-workspace grid. The main workspace is reserved for status, library, and settings views; the dock may collapse without disabling the button controls.
- Soundpad output is always an independently selected device. Do not offer a follow-MusicBot device setting because independent routing is required for its dedicated external controller workflow.
- Each Soundpad button stores a base fill color and a distinct progress fill color. Playback progress is expressed by filling the existing button surface, rather than changing the button label or only showing a separate progress indicator.

## 2026-08-11 SoundPad terminal-local board layout and browser import

- Keep SoundPad control/navigation actions in the collapsible sidebar, but keep the playable audio-button grid in the main workspace. This separates page navigation and configuration from performance controls.
- Panel column count is a browser-local presentation preference, not shared SoundPad data. Store it in local storage so different control terminals can use their own physical-grid density without overwriting each other.
- Browser audio import must upload a managed copy to the service cache. Do not depend only on a server-side native file dialog, because the page may be opened from a different terminal.
- Draft values in the configuration drawer are authoritative while the drawer is being edited. Polling state may update playback indicators, but must not overwrite unsaved color or control values.
- Loop behavior is represented as a count, with `-1` reserved for infinite playback. Legacy boolean loop values remain readable and migrate during normalization.

## 2026-08-11 SoundPad page composition

- SoundPad has one visible initial view: the board. Do not retain hidden legacy headers, duplicate controls, or duplicated IDs merely to preserve old markup.
- Place live playback state at the top because it is global to every SoundPad view. Keep its stop command there so it remains available while browsing the library or settings.
- Labels and native color inputs must be separate controls. A descriptive row should not make its full width open the operating system color dialog.
- Settings that change playback routing or master volume use an explicit save action. The button drawer likewise saves through its own explicit action and reports request failures instead of silently closing.

## 2026-08-11 SoundPad progress and local panel geometry

- Do not raise backend state broadcast frequency solely for visual fill smoothness. Animate the active button from the most recent authoritative playback position in the browser, then correct it on the next snapshot.
- SoundPad grid columns and row height are terminal-local rendering preferences. Persist both in browser local storage and do not write either setting to shared SoundPad data.
- Empty playable slots are intentionally quiet. Only configured clips cause playback requests; configuration mode remains the explicit way to populate an empty slot.
- Use in-page modal dialogs for SoundPad creation flows so the interaction styling and keyboard behavior remain part of the application rather than depending on browser prompts.

## 2026-08-11 SoundPad status and managed-import names

- The global playback status remains one row and sticks to the top of the SoundPad workspace while its content scrolls. Its stop-all action is a compact square icon with an accessible label and tooltip.
- Managed upload storage names are implementation details. Clip display names and automatic button labels derive from the source filename, excluding its extension and generated storage prefix.
- Migration may update an automatic label only when it exactly matches the prior generated display name; a user-authored label takes precedence.

## 2026-08-11 StreamDock SoundPad integration

- Keep StreamDock control in its own plugin, separate from the MusicBot and SoundPad web processes. Bind controller actions to SoundPad's persisted `pageId/buttonId`, not displayed positions or labels.
- Use the read-only external SoundPad endpoint for frequent button state/progress rendering. Use the write endpoint only when the physical control is pressed, and respect the server-side external-control switch.
- Publish a complete plugin copy, including its runtime dependencies, under StreamDock's plugin directory and restart the host. Treat a logged plugin connection as the live-load verification, in addition to mock-host tests.

## 2026-08-11 StreamDock action startup behavior

- The plugin identity exposed to users is `SoundPad`; internal action UUIDs remain stable so existing mappings are not invalidated by a display-name change.
- A keydown must not depend on a prior successful poll. If a context has no snapshot, perform one synchronous state refresh before deciding whether to send the play/stop request.
- Accept action identity from both common StreamDock message shapes (`message.action` and `message.payload.action`) to accommodate host firmware/runtime differences.

## 2026-08-12 Unified project time base

- Use server epoch milliseconds as the single MusicBot playback timeline. Each state payload carries `sync.serverTime`, `sync.revision`, and `sync.bootId`; clients extrapolate locally for smooth rendering while applying the server offset.
- Reject lower revisions only within the same boot ID. A new boot ID is authoritative after restart.
- Keep SoundPad's independent audio timeline separate from MusicBot song playback; this protocol targets shared MusicBot status and lyrics.
## 2026-09-05 GitHub 上传边界与重构基线

- GitHub 首次上传采用“源码与可公开文档入库、运行态与凭据完全排除”的策略；不把本地运行配置当作可公开模板。
- `MusicBot\Cache`、`DouyinListener\data`、浏览器 profile、Cookie、数据库、session/raw archive、日志和媒体属于机器/账户状态，不进入 Git。
- `Docs\DouyinWebSourceCode` 是网页抓取/参考材料，不作为主代码仓库上传内容；保留 `Docs\memory`、`Docs\Rules` 和必要设计文档。
- 分模块重构必须从首次 baseline commit 开始，采用小步提交、单模块验证和可回滚迁移，不先做跨模块大重写。
