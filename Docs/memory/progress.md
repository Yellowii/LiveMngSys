# LiveMngSys 进度记录

## 2026-07-31 Live captions integration

- Added independent capture service, API state, local persistence option, and focused tests.
- Configuration has four equal desktop cards: monitor, barrage listener, live captions, and service access.
- Live UI polls the existing listener state endpoint once per second and redraws its bottom ticker only for a caption revision or output-mode change.
- Verified: 68 Python tests passed; capture reached `connected` against the local Windows Live Captions window; service restarted and the feature was restored to disabled.
- Selenium screenshot could not run because local driver initialization timed out. HTTP checks for both pages and the listener state API passed.

## 2026-07-31 Subtitle fallback and presentation

- Replaced the bottom music icon with the existing announcement icon, removed ticker edge masking, and made heavy text shadow optional through caption styling.
- Added Live UI caption controls: font, size, color, stroke width/color, shadow blur/color, idle text, and idle scrolling duration.
- Added fallback controls to the listener configuration card and compatibility merging for saved pre-fallback subtitle configuration.
- Verification: 69 Python tests passed; both GUI inline scripts parsed; listener restarted and returned active captions with the new fallback fields.

## 2026-07-31 LiveDash refresh alignment

- Removed the previous two-read stability delay and sentence similarity filtering from live caption output; unchanged lines are still ignored.
- Added the lightweight caption endpoint and changed the live UI refresh from 1 second to 150ms polling with request overlap protection.
- Marked live captions as static output, while idle text keeps its independent scrolling behavior.
- Verification: 69 Python tests passed, inline JavaScript parsed, endpoint returned HTTP 200 after service restart, and live caption state returned a current revision/text.

## 2026-07-29

## 2026-07-30

- 会员表情在实时互动与复盘中改为图片优先显示，隐藏回退文字，并将显示尺寸提升至 26px。

- 徽章同类合并升级为双向等级合并：保留最高等级，较高等级立即替换显示资源，同等级采用最后到达状态；在线榜后续刷新不带徽章时保留最新有效记录。

- 新增统一徽章显示顺序：等级、特殊、灯牌/星守护、会员、管理。
- 关注状态改为带来源优先级的映射：HTTP 榜单作初始兜底，互动消息中的 `follow_status` 强制更新并跨榜单刷新保留。

- 在线榜主播关系改为由互动消息增量映射；榜单推送/HTTP 快照只更新名单、徽章和贡献值，不再使用其默认 `followStatus=0` 覆盖互关或粉丝关系。

- 修复在线榜后续发现的徽章问题：URL/URI 等价资源统一去重；榜单刷新保留星守护粉丝团名称；在线榜和上车队列增加渲染去重兜底。

- 修复直播间状态、主播关系和在线榜映射：状态快照新增 `roomState`，顶部可区分直播中、未开播和房间不存在。
- 修正 `FollowInfo.followStatus`：`1=粉丝`、`2=互关`，昵称颜色按正确关系显示。
- `WebcastRoomRankMessage` 改为优先消费 `audienceRanks`，在线榜保留贡献值缓存，并完成徽章语义去重与星守护优先规则。
- 已重启监听服务进行实测：榜单贡献值正常、徽章无同类型重复。

## 已完成功能

- 已存在统一启动脚本：`Start-LiveMngSys.ps1`、`Start-LiveMngSys.cmd`。
- 已存在 WebServer 网关，README 中说明公网/LAN 入口为 `7000`，MusicBot 与 DouyinListener 为内部依赖服务。
- 已存在 MusicBot 点歌服务和前端资源。
- 已存在 DouyinListener 弹幕监听、事件存储、协议审计和回放测试相关代码。
- 已存在 GUIDemo 视觉原型、互动聊天素材和参考截图。
- 已存在 GameQueue 与 MusicQueue 业务规则文档。
- 2026-07-28：初始化长期记忆目录 `docs/memory`。
- 2026-07-28：完成徽章解析与展示增强：
  - DouyinListener 后端参考 DmProto/Doubao 的 `badge_urls.json` 分类徽章。
  - 实时弹幕、观众榜、上车队列和弹幕复盘继续使用统一 `user.badges` 展示，新增徽章颜色与更完整的事件级徽章。
  - MusicBot 点歌人徽章保留 `kind/bgColor/fgColor` 并在点歌 UI 中渲染。
- 2026-07-28：完成徽章与互动区视觉调整：
  - 普通徽章改为纯图片，不再显示标签底纹和文字。
  - 星守护徽章采用抖音风格 `border-image`，在徽章内显示粉丝团名称和等级。
  - 实时弹幕与复盘互动行按事件类型使用不同背景色；顶部筛选按钮使用同一颜色分类。
- 2026-07-28：修复前三个徽章显示：
  - 付费等级徽章保持现有图片加载逻辑。
  - 有星守护徽章时，后端 `user.badges` 与前端渲染均隐藏粉丝团灯牌。
  - 星守护徽章文字改为优先使用 `fansClub.name/clubName`，不再追加等级；样式增加高度与最大宽度约束。
  - 确认当前样本会员徽章来自原始 `badgeList` 的 `subscribe_new_3x.png`，未携带普通会员/年费会员 V 图标。
- 2026-07-28：完成互动行与观众资料增强：
  - 实时礼物、实时互动、复盘礼物、复盘互动改为内容与昵称同一行，超宽自动换行。
  - 昵称按直播间关系着色：互关紫色、粉丝蓝色、未关注灰白。
  - 在线观众榜收到 `WebcastAudienceRankList` 时按网页/HTTP 观众榜整榜刷新，不再只在首次初始化。
  - 弹出资料卡新增个性签名展示，后端透传直播用户签名并合并主页资料签名。
- 2026-07-28：继续修复互动卡片和路由行为：
  - 卡片背景色加深并增加左侧色条，礼物/评论/点赞/入场/关注区分更明显。
  - 实时礼物与互动行把徽章移回昵称同行，内容仍可自动换行，不再把徽章挤到下一行。
  - 九权直播间的 `ranklist_fansclub_advanced_badge_11_xmp.png` / `ranklist_fansclub_pop_advanced_badge_6_xmp.png` 归类为星守护。
  - GUIDemo 通过 hash/localStorage 保持当前 tab/subTab，刷新不再总回第一页。
- 2026-07-28：修正灯牌版本识别与行内顺序：
  - 版本二普通灯牌 `ranklist_fansclub_pop_advanced_badge_*_xmp.png` 改回普通图片显示，不拉伸。
  - 版本二星守护 `ranklist_fansclub_advanced_badge_*_xmp.png` 保持星守护拉伸并填充粉丝团名称。
  - 版本一普通灯牌 `fansclub_new_advanced_badge_*_xmp.png` 保持普通图片显示；版本一星守护 `star_guard_advanced_badge_*_xmp.png` 保持拉伸。
  - 实时与复盘礼物/互动行顺序改为徽章、昵称、content；昵称不裁切，多徽章自然撑开后续内容。
- 2026-07-28：修正星守护徽章左侧压缩：
  - 星守护徽章恢复更接近抖音原始的 14px 高度与 18px 左侧切片宽度。
  - 普通灯牌继续保持纯图片显示，不受星守护 border-image 影响。
  - GUIDemo 与 MusicBot 的星守护样式保持一致。
- 2026-07-29：按抖音官方 DOM 再次校准星守护徽章：
  - `star_guard_advanced_badge_*` 保持文字 `margin-left: 12px`。
  - `ranklist_fansclub_advanced_badge_*` 使用文字 `margin-left: 14px`。
  - 九宫绘制保留 `border-image-width: 0 9px 0 18px`，布局边框宽度只保留上下 0、左右 `medium`，避免整体被拉得过宽或把高度撑高。
- 2026-07-29：统一星守护徽章 GUI 缩放比例：
  - 星守护高度提升到与普通徽章一致的 20px，避免在同一行里显得细长。
  - `border-image-width`、字体和文字内缩按统一缩放因子一起放大，保证固定边缘和文字间距的比例一致。
- 2026-07-29：按用户反馈仅缩小星守护字号：
  - 保持星守护徽章几何尺寸不变。
  - 仅将字号从统一放大值压回更小一档，避免文字显得过满。

## 当前进度

- 2026-07-30：审阅 `Docs/DouyinWebSourceCode` 网页抓取产物。确认 `GiftTrayPlugin/GiftEffectPlugin/RedPacketNew/VipRedpacket/LotteryShortTouchPlugin` 和 `fansclub` 页面可作为前端状态行为参考，但不是可直接复用的后端源码。
- 2026-07-30：EventStore 按网页端礼物行为补充 `groupCount`、`batchCompose`、`totalDiamondCount`，连击消息使用批次增量合并并保留累计值。
- 2026-07-30：活动记录按稳定活动 ID 做更新合并，红包/福袋多条状态消息不会在复盘中重复堆叠；无活动 ID 的消息仍按消息 ID 去重。
- 2026-07-30：验证通过 `python -m unittest test_event_store.py`（27 项）、`python -m unittest test_replay.py`（4 项）和 `python -m py_compile ...`。

- 长期记忆系统已初始化。
- 当前互动行、关系色、在线观众榜刷新、资料卡签名、SPA 路由保持与星守护 GUI 缩放统一已实现，并通过 AST 解析、单元测试、前端脚本解析与 GUIDemo 页面截图检查。
- 2026-07-29：完成实时弹幕清屏、榜单刷新指示、活动记录和直播间状态增强：
  - 在线榜单轮询使用请求顺序保护，展示后端榜单版本、刷新时刻，并在每次成功轮询时点亮状态灯 1 秒。
  - 全量榜单、实时贡献榜和互动用户数据会合并到同一榜单用户，保留最近有效贡献值并同步徽章。
  - 清屏只清空当前浏览器中的实时展示；切换直播间配置会停止旧监听并清空旧房间数据。
  - 红包、福袋记录补齐开奖/预览字段并支持在抽屉打开时主动刷新。
  - 顶栏显示未连接、连接中、已连接、重连中、未开播和异常等监听状态。
  - 所有服务配置为 `0.0.0.0` 局域网监听，网关内部反代自动使用回环地址。

## 修改记录

- 2026-07-28：新增 `docs/memory/project.md`、`docs/memory/progress.md`、`docs/memory/decisions.md`、`docs/memory/tasks/current_task.md`。
- 2026-07-28：修改 `DouyinListener/event_store.py`、`GUIDemo/index.html`、`GUIDemo/style.css`、`MusicBot/UI/html/musicbot-ui.js`、`MusicBot/UI/html/musicbot-ui.css`、`MusicBot/bot/lib/botCore.js`。
- 2026-07-28：再次修改 `GUIDemo/index.html`、`GUIDemo/style.css`、`MusicBot/UI/html/musicbot-ui.js`、`MusicBot/UI/html/musicbot-ui.css`。
- 2026-07-28：修复 `DouyinListener/event_store.py`、`GUIDemo/index.html`、`GUIDemo/style.css`、`MusicBot/UI/html/musicbot-ui.js`、`MusicBot/UI/html/musicbot-ui.css` 的粉丝团/星守护徽章显示规则。
- 2026-07-28：修改 `DouyinListener/event_store.py`、`DouyinListener/service.py`、`DouyinListener/test_event_store.py`、`GUIDemo/index.html`、`GUIDemo/style.css`。
- 2026-07-28：再次修改 `DouyinListener/event_store.py`、`DouyinListener/test_event_store.py`、`GUIDemo/index.html`、`GUIDemo/style.css`、`MusicBot/UI/html/musicbot-ui.js`。
- 2026-07-28：修正 `DouyinListener/event_store.py`、`DouyinListener/test_event_store.py`、`GUIDemo/index.html`、`GUIDemo/style.css`、`MusicBot/UI/html/musicbot-ui.js` 的灯牌分类与行内布局。
- 2026-07-28：再次修改 `GUIDemo/style.css`、`MusicBot/UI/html/musicbot-ui.css`、`docs/memory/tasks/current_task.md`。
- 2026-07-29：再次修改 `GUIDemo/index.html`、`GUIDemo/style.css`、`MusicBot/UI/html/musicbot-ui.js`、`MusicBot/UI/html/musicbot-ui.css`、`docs/memory/tasks/current_task.md`、`docs/memory/progress.md`、`docs/memory/decisions.md`。
- 2026-07-29：完成 DmProto 新增协议与在线观众榜适配：
  - 同步新增的 6 个业务协议解析。
  - 在线观众榜改为轮询全量刷新并保留 score 映射缓存。
  - 补齐主播、房间、封面、开播信息等映射。
  - 会话数据改为按直播间/场次分目录落盘，并保留回放兼容。
  - `event_store`、`service`、`browser_client`、`wss_client` 与测试已同步更新。
- 2026-07-29：修复前端在线观众榜刷新停留旧数据：
  - `GUIDemo/index.html` 新增观众榜轮询兜底。
  - 观众榜从仅切页加载，改为按配置间隔持续刷新。
  - 仍保留 websocket 推送，用轮询补足推送丢失或未触发的场景。
- 2026-07-29：本轮修改 `DouyinListener/event_store.py`、`DouyinListener/service.py`、`DouyinListener/test_event_store.py`、`GUIDemo/index.html`、`GUIDemo/style.css`、`WebServer/server.js`、`config/service.json`、`Start-LiveMngSys.ps1`、`MusicBot/Start-MusicBot.ps1`；监听服务测试 11 项通过，前端/Node/PowerShell 语法检查通过。
- 2026-07-29：修复运行配置页保存后旧直播数据残留：
  - 配置页保存请求携带 `resetLiveData`，监听服务停止旧连接、清空运行态并返回空状态快照；实时页展示配置保存不触发该重置。
  - 前端在保存前立即清空房间、主播、统计、弹幕、榜单和活动记录，并忽略重置期间晚到的旧 WebSocket/轮询快照。
  - 顶栏和配置页状态灯补齐未连接、等待连接、连接中、获取榜单、已连接、重连中、未开播和异常状态。
  - 已重启 DouyinListener 并实际验证保存后全部运行数据为零、启动后状态依次进入 `connecting` 和 `connected`。
- 2026-07-30：登录卡片接入当前抖音账号资料。后端通过 `/webcast/user/me/` 加载头像、昵称和抖音号并写入统一登录状态；前端提供加载、头像兜底和失败降级显示。已重启监听服务，经 7000 网关实测账号 `237 / Mngaccount` 与头像正常返回。
- 2026-07-30：批量续火花工具栏接入其独立私信登录账号资料。`spark/status` 返回头像、昵称、抖音号和加载状态，前端按该状态展示；新增 3 项续火花账号测试并重启监听服务验证。
- 2026-07-30：批量续火花将接收人选择改为最近会话多选列表，移除手工昵称输入。会话条目带 `id/name/avatar`，前端提交所选对象，后端按会话 ID 去重并兼容旧文本请求。
- 2026-07-30：修复批量续火花私信登录态被慢加载聊天页面误判丢失。聊天 UI 验证等待 15 秒，账号 Cookie 验证作为兜底，瞬时失败保留已确认账号；实测登录态有效并读取到 12 条最近会话。
- 2026-07-30：修复批量续火花会话列表读取竞态。私信登录检查和会话读取串行访问独立浏览器目录，成功会话在服务端缓存；前端登录确认后自动加载会话。并发网关实测仍保持已登录并返回 12 条会话。
- 2026-07-30：批量续火花改为全量扫描虚拟私信会话栏，仅返回带 `commonStreak` 火花组件的会话，并解析正常、失效和重燃状态。真实扫描返回 23 个火花会话。
- 2026-07-30：监听服务启动时自动校验独立私信登录态，前端无需手动检查即可进入已登录状态并自动加载火花会话；重启后实测状态和账号资料正常恢复。
- 2026-07-30：火花会话行的状态展示升级为固定火花徽标，18px 图标配合连续、失效或重燃文字及状态底色。真实页面验证 54 条会话均显示徽标。

## 2026-08-09 Danmaku-to-MusicBot song requests

- Listener chat processing now forwards only `WebcastChatMessage` (ordinary text danmaku) to MusicBot `POST /api/integrations/danmaku/command`.
- Forwarded requester data includes text, user ID, nickname, avatar, display ID, inferred roles, and badges. Emoji, voice, exhibition, likes, gifts, and all other event methods are excluded to avoid command noise.
- Listener configuration adds `musicBot.enabled`, `musicBot.commandUrl`, and `musicBot.timeoutSeconds`; default endpoint is `http://127.0.0.1:7001/api/integrations/danmaku/command`.
- Validation: `python -m py_compile DouyinListener/service.py` and MusicBot Node syntax checks passed. EventStore focused suite passed 63 tests. Full Listener suite remains blocked by Windows temporary-directory permissions. Listener must be restarted to load this change; MusicBot does not require restart.

## 2026-08-09 GUIDemo configuration card layout

- The running/config listener dashboard now uses an auto-fit grid with 300px minimum cards, dense row placement, and content-height cards instead of fixed four columns and 536px minimum card height.
- Browser verification completed at 1440px and 760px widths: desktop cards wrap naturally without overlap; narrow layout is single-column.
- WebServer was started on port 7000 for verification. The page is available through the LAN gateway at `/GUIDemo/#/running/config`.

## 2026-08-09 Attached song-command arguments

- MusicBot now accepts attached song arguments for request commands: `点歌成都`, `顶歌成都`, and `超级置顶成都` are equivalent to the spaced forms.
- Argument-less control commands remain strict. For example, `切歌成都` is ignored rather than skipping playback.
- Validation: Node syntax checks passed. A focused BotCore behavior harness verified attached request/top/super-top queries and the strict skip-command guard.

## 2026-08-09 Intelligent song command mode

- Existing `permissions.intelligentRequest` now controls attached-argument parsing for request, top, and super-top song commands.
- When enabled, a command keyword may be immediately followed by its song query. When disabled, only the existing whitespace-separated command format is accepted.
- Validation: BotCore harness passed for enabled attached requests, disabled rejection, and standard spaced commands.

## 2026-08-09 Live monitor anchor identity

- Fixed the running/config live-monitor card to render `room.anchor.avatar` when the Listener state provides it, with the existing initial-letter avatar retained only as a fallback.
- Listener user normalization now maps room-owner `unique_id` / `uniqueId` to the public `displayId`, so the room-enter response can populate the displayed Douyin ID without substituting a room ID.
- Validation: focused `test_room_owner_unique_id_becomes_display_id` passed; `python -m py_compile event_store.py` and the GUIDemo inline script parse passed.
- Runtime: the current Listener service on port 7002 was already started before this change. Its restart was attempted but blocked by the execution policy, so restart `DouyinListener/service.py` before expecting the current live room to receive the new display-ID mapping. The avatar UI change takes effect after browser refresh whenever the state contains an avatar URL.

## 2026-08-09 Listener WebSocket memory exhaustion

- Root cause: each incoming live event created an independent WebSocket broadcast task. Every task materialized the complete live state, including all session users; a slow browser or gateway connection allowed those full-state tasks to accumulate without bound.
- Replaced per-event task creation with one coalescing broadcast worker. While it is sending, only the newest event is retained. Slow WebSocket sends time out after five seconds and the socket is removed.
- The Listener process had reached about 38 GB private memory and 22 GB working set. It was stopped and restarted. After 410 live events over 30 seconds, memory changed only from 111.2 MB to 113.8 MB private and from 134 MB to 137.4 MB working set; port 7002 was healthy and connected.
- Validation: `python -m py_compile service.py event_store.py` passed; live service health and post-restart memory observation passed.

## 2026-08-09 MusicBot top and super-top priority

- Root cause: `topSong()` assigned different priority labels but inserted both top and super-top songs with `queue.unshift()`, making their playback order identical.
- Super-top songs now always lead the queue. Regular top songs insert after all super-top songs and before ordinary requests; new requests of the same priority remain newest-first.
- Validation: Node syntax check and an in-memory queue-order harness passed. MusicBot port 7001 was restarted and its active command configuration was confirmed as `顶歌` / `超级顶歌`.

## 2026-08-11 MusicBot Soundpad

- Added a dedicated Soundpad service and page at `/musicbot/soundpad`, with GUIDemo navigation under `直播 > 音效板`.
- Soundpad has an independent mpv process and IPC name (`musicbot-soundpad-mpv`), so an effect never loads, stops, or advances the MusicBot song queue.
- The page provides board/library/settings navigation, 30 persistent per-page buttons, single-file and recursive folder import, color/image/loop/volume/delay button settings, configuration drawer, play/configure modes, and drag-to-reorder in configure mode.
- Each button has a stable unique ID across pages. External clients read `GET /api/integrations/soundpad` and, after explicit enablement, control `POST /api/integrations/soundpad` with `pageId`, `buttonId`, and `action`.
- Validation: Node syntax checks, a Soundpad state/unique-ID harness, gateway page/script HTTP 200 checks, and disabled external-control HTTP 403 check passed. MusicBot 7001 was restarted.

## 2026-08-11 Soundpad dock, device, and color refinement

- Moved every playable Soundpad button into the left-side dock. The dock holds pages, navigation, and a scrollable two-column button grid; it can collapse into a compact icon/button column while preserving playback access.
- Soundpad playback devices are enumerated from its own mpv instance through `/api/soundpad/devices`. The historical `follow_musicbot` setting migrates to `auto`; Soundpad no longer follows the MusicBot output device.
- Buttons now persist separate `fillColor` and `progressColor` fields. The base fill remains visible at rest, while active playback fills the button by progress using its independent progress color.
- Validation: Node syntax and migration checks passed; Soundpad state confirmed `audioDevice=auto`, seven enumerated devices, distinct color fields, and idle status. Edge screenshot confirmed the left-side dock layout. MusicBot 7001 was restarted.

## 2026-08-11 SoundPad sidebar, import, and per-terminal board refinement

- Corrected the earlier dock interpretation: only navigation, page controls, import/play/configure actions, and the board-size control live in the collapsible left sidebar. Playable SoundPad buttons remain in the main workspace.
- Removed the SoundPad top header. The sidebar brand is now `SoundPad`, with `Sound` and `Pad` rendered in separate colors; no MusicBot name is shown inside the SoundPad page.
- Added a per-browser panel-column selector (3 through 8 columns). It persists as `musicbot.soundpad.columns` in browser local storage and never changes the shared server configuration, so each terminal keeps its own grid size.
- Replaced system-dialog-only audio import with native browser file/folder selection. Browser uploads are validated and copied to `MusicBot/Cache/Soundpad/imports` before being registered; the legacy Windows picker routes remain compatible.
- Replaced the loop toggle with loop count semantics: `0` disabled, a positive value repeats that many times, and `-1` is infinite. Stored legacy boolean loop settings migrate to `-1` or `0`.
- Protected open drawer form edits from the 500 ms state refresh, preventing selected colors and other unsaved fields from being reset while editing.
- Validation: `node --check` passed for SoundPad server, manager, and browser script; SoundPad state exposed migrated `loopCount=0`; upload endpoint rejected an unsupported file with HTTP 400; Edge screenshots at 1440px confirmed the direct page and gateway layout. MusicBot 7001 was restarted.

## 2026-08-11 SoundPad layout and persistence correction

- Replaced the accumulated SoundPad frontend patches with a single clean page structure. The direct SoundPad page now always starts in the board view; it has no hidden duplicate toolbar or duplicate element IDs.
- Added a compact top playback status bar with current sound name, activity state, progress, elapsed/total time, and a single `停止全部` command.
- Reworked the sidebar into navigation, import actions, mode selection, terminal-local columns, and page selection. The main area is reserved for the audio-button grid, library, or settings view.
- Color labels are no longer wrapping color inputs, so only the actual color swatch opens the native color picker.
- Button drawer saves have one error-handled request path. Playback settings now have an explicit `保存播放设置` command; unsaved settings and drawer data are protected from polling renders.
- Validation: browser script and MusicBot files pass `node --check`; direct HTTP PUT confirmed button values persist and the test values were restored to the original auto-mapped clip/default settings; 1440px Edge screenshot confirms the corrected default board layout and top status bar. No MusicBot restart was required because this correction changes static frontend assets only.

## 2026-08-11 SoundPad control density and modal refinement

- Removed the horizontal progress bar from the top playback status area. It now contains playback identity/state, elapsed/total time, and the stop-all command only.
- Button-fill progress uses browser `requestAnimationFrame` interpolation between server snapshots. Server polling remains at 500 ms, avoiding an increase in backend broadcasts while making an active fill animate smoothly.
- Added terminal-local button row-height control (72-200 px) alongside the terminal-local column setting. Column support now extends through 10 columns.
- In play mode, an empty button is a no-op and no longer opens an error alert. In configure mode it still opens its configuration drawer.
- Replaced the browser `window.prompt` new-page flow with an in-page modal dialog.
- Validation: `node --check` for the browser script and MusicBot server passed; Edge 1440px screenshot confirms the missing top progress bar, row-height control, and stable board layout. Static assets apply on refresh; no service restart required.

## 2026-08-11 SoundPad sticky status and display-name migration

- The SoundPad status bar is now a sticky, forced single row at every supported viewport width. Playback state remains on the left; elapsed time and a square stop icon with a `停止全部` tooltip remain on the right.
- Browser-uploaded files retain a unique managed cache filename but use the original source filename without its extension for all display labels. This avoids exposing timestamps, UUIDs, cache paths, or IDs.
- SoundPad startup migrates prior browser-uploaded clip names with the managed filename prefix and updates only button labels that still equal the former automatic clip name. Manually edited labels are retained.
- Validation: Node syntax checks passed; after restarting MusicBot 7001, the state API confirmed existing `178...UUID...-撒钱` data migrated to `撒钱` for both clip and automatic button label. Edge 1440px screenshot confirms one-line sticky status and clean file labels.

## 2026-08-11 StreamDock SoundPad Control plugin

- Created independent source plugin at `C:\Users\Administrator\AppData\Roaming\HotSpot\StreamDock\soundpad-streamdeck-plugin\plugin\com.hotspot.streamdock.soundpad.sdPlugin` and published it to StreamDock's `plugins\com.hotspot.streamdock.soundpad.sdPlugin` directory.
- Added `SoundPad Button` action with terminal-configurable SoundPad URL, page ID, and stable button ID, plus a `SoundPad Stop All` action. The property inspector loads available pages/buttons from the read-only integration endpoint.
- The plugin polls `GET /api/integrations/soundpad` every 350 ms to render button label/activity/progress. It sends `POST /api/integrations/soundpad` only on controller key-down; play/stop therefore continue to require SoundPad's explicit external-control setting.
- Installed `ws@8.18.3`, added a PNG manifest icon compatible with the verified local StreamDock plugin pattern, and added a mock host/API test.
- Validation: Node syntax checks passed; mock host verified plugin registration, `setImage` output, 50% progress image, and correct POST play payload. StreamDock was restarted. Its live log confirms `com.hotspot.streamdock.soundpad.sdPlugin is now connected`.

## 2026-08-11 StreamDock SoundPad naming and keydown reliability

- Renamed the plugin display name to `SoundPad` and bumped the manifest to `1.0.1`; the action/property-inspector headings now use the same name.
- Keydown handling now tolerates the action field in either the host message or payload and forces a fresh state read when the per-context snapshot has not arrived yet. This prevents a valid mapped button from being silently ignored during startup or configuration changes.
- Real SoundPad external control was independently verified with `externalEnabled=true`, a live `pageId/buttonId`, and HTTP 200 playback response. The updated plugin passed the mock-host play request test and StreamDock's new log confirms the reloaded plugin connection.

## 2026-08-09 Listener room configuration draft preservation

- Fixed the running/config room ID and URL inputs being overwritten by Listener polling or WebSocket state snapshots during editing.
- Typing either room field marks it as an unsaved draft. Incoming configuration updates preserve both room fields until a successful save, after which the confirmed server configuration is applied.
- Validation: GUIDemo inline JavaScript parsed and the configuration route returned HTTP 200 through WebServer.

## 2026-08-09 Configuration grid width cap removal

- Removed the 1280px/1440px maximum width from the GUIDemo running/config container. The auto-fit card grid can now use all available workspace width instead of being capped at four columns.
- Validation: 2560px browser screenshot rendered all five configuration cards in one row without overlap.

## 2026-08-12 Unified project time base

- Added `musicbot-state-v1` synchronization metadata to every MusicBot state snapshot: monotonic revision, server epoch time, and process boot ID.
- MusicBot public player, full UI, and GUIDemo live lyric page now estimate playback from server time and ignore stale state arriving out of order across HTTP/WebSocket.
- MusicBot 7001 restarted; `/api/state` returned the new protocol with revision 2. Node syntax checks passed for all changed JavaScript files.

## 2026-09-05 Multi-room monitor and anonymous identity (test refactor)

- Added `DouyinListener/room_monitor.py` with an independent `RoomMonitorRegistry` that probes multiple rooms concurrently and keeps each room's live state and session ID separate from barrage EventStore data.
- Fixed stale anonymous payload handling: when a message contains an anonymous `payload.user` but a resolved user in `displayText.piecesV2`, the resolved identity is selected.
- Normalized users now expose `isAnonymous`; anonymous labels (`匿名`, `匿名.`, `匿名用户`, `匿名观众`) map to `true`, while resolved names map to `false`. This is intended for a frontend badge such as `匿`.
- Validation: `python -m unittest test_event_store.py test_room_status.py test_room_monitor.py test_anonymous_identity.py` passed 73 tests.
- This work is in the separate `LiveMngSys-refactor-test` checkout; the original local workspace was not modified. The registry is not yet wired into the single-room HTTP configuration.
- Scope decision: this refactor remains limited to live monitoring, barrage listening, identity normalization, and externally consumable state; unrelated UI, gift, caption, and MusicBot changes are deferred.
- Mystery users follow the same identity resolution path as anonymous users. `isMystery` and `privacyLabel` are retained even when a known nickname/avatar is recovered from the message or session memory.
## 2026-09-05 GitHub 上传与模块化重构准备

- 已确认 `D:\Proj\LiveMngSys` 原先不是 Git 仓库，也未配置 GitHub remote。
- 已创建根目录 `.gitignore`，排除运行数据、Cookie/浏览器 profile、SQLite/日志、媒体、缓存、压缩包、临时目录和网页抓取源码；其中 `MusicBot\Cache\Data\config.json` 含有效 Netease Cookie，禁止上传。
- 已初始化本地 Git，分支为 `main`；尚未创建首次提交，尚未推送远端。
- 首次候选清单约 3,024 个文件、约 207 MB（排除规则生效后）；仍需在提交前检查大文件、凭据命中和第三方/生成目录边界。
- `gh`（GitHub CLI）未安装；创建 GitHub 远端需要用户提供仓库 URL，或安装/配置 GitHub CLI 后再继续。
- 待后续：建立无敏感数据的 baseline commit，补充公开配置示例和部署说明，再按 DouyinListener、WebServer、MusicBot、GUIDemo/ReStyle 等模块制定渐进式重构任务。

- GitHub CLI 2.100.0 已安装，origin 已配置为 Yellowii/LiveMngSys；待完成 gh 登录后再提交和推送。

- baseline 提交 4134465 已创建；推送因 github.com:443 网络连接失败，尚未确认远端接收。

- 已确认 GitHub 公开仓库 Yellowii/LiveMngSys 的 main 已接收提交 513c988；上传阶段完成，下一步进入模块化重构。

- 已重写根目录需求.txt：完成模块重分类、优先级/验收标准、当前实现映射和重构约束。
