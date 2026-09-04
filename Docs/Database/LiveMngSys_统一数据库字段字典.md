# LiveMngSys 统一数据库字段字典

> 本文是统一数据库重构方案的字段说明。英文名供程序使用，中文名称和含义供人阅读。
>
> 总体方案见：[LiveMngSys_统一数据库重构方案_小白版.md](./LiveMngSys_统一数据库重构方案_小白版.md)

## 一、字段命名约定

数据库字段统一使用小写英文和下划线，例如 `session_id`。不要直接使用中文字段名，因为不同编程语言、导入导出工具和 SQL 客户端对中文标识支持不一致。

| 固定写法 | 中文含义 | 说明 |
| --- | --- | --- |
| `id` | 内部编号 | 数据库自己使用的稳定编号 |
| `*_id` | 关联编号 | 指向另一张表的 `id` |
| `platform_*_id` | 平台编号 | 抖音、网易云等外部平台给出的编号 |
| `*_at` | 时间 | 统一保存 13 位 Unix 毫秒时间戳 |
| `is_*` | 是否 | 保存 0 或 1 |
| `*_count` | 数量 | 非负整数 |
| `*_url` | 网络地址 | 远程资源 URL |
| `*_path` | 本地路径 | 相对项目数据目录的路径 |
| `*_json` | 扩展 JSON | 只放暂时无法稳定拆字段的内容 |
| `status` | 状态 | 必须使用固定枚举，不保存任意中文句子 |

所有主要业务表建议都有 `created_at` 和 `updated_at`。历史流水表通常只需要 `created_at` 或业务发生时间，历史不应被覆盖更新。

## 二、核心身份与直播

### 2.1 `anchors` 主播表

一位主播只建一行。主播改昵称或抖音号时更新当前值，并把旧值写入历史表。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 主播内部 ID | 其他表关联主播时使用 |
| `douyin_uid` | 主播抖音 UID | 抖音账号数字身份，优先作为平台稳定身份 |
| `sec_uid` | 主播 SecUID | 抖音安全身份，可辅助去重 |
| `display_id` | 主播抖音号 | 用户可见且可能修改的抖音号 |
| `nickname` | 主播昵称 | 当前昵称 |
| `avatar_url` | 主播头像地址 | 当前头像网络地址 |
| `signature` | 主播签名 | 当前个人简介 |
| `is_active` | 是否启用 | 是否在配置中继续监控该主播 |
| `created_at` | 建档时间 | 首次进入本系统时间 |
| `updated_at` | 更新时间 | 当前资料最后更新时间 |

建议唯一约束：非空的 `douyin_uid`、`sec_uid` 分别唯一。

### 2.2 `live_rooms` 直播间表

保存稳定直播间，不保存“每次开播”的变化资料。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 直播间内部 ID | 其他表关联直播间时使用 |
| `anchor_id` | 主播内部 ID | 这个直播间属于哪位主播 |
| `web_rid` | 直播间号 | `live.douyin.com/{web_rid}` 中的稳定编号 |
| `room_url` | 直播间地址 | 完整网页地址 |
| `current_title` | 当前标题 | 最近一次检测到的直播标题 |
| `cover_url` | 当前封面 | 最近一次检测到的封面 |
| `last_status` | 最近状态 | `live`、`not_live`、`ended`、`not_found`、`unknown` |
| `last_checked_at` | 最近检测时间 | 最后一次开播监控时间 |
| `created_at` | 建档时间 | 首次加入监控时间 |
| `updated_at` | 更新时间 | 房间资料最后更新时间 |

建议唯一约束：`web_rid` 唯一。

### 2.3 `live_sessions` 直播场次表

主播每次开播建立一行。这里的 `platform_live_id` 是场次号，不是直播间号。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 场次内部 ID | 全项目关联一场直播的统一编号 |
| `anchor_id` | 主播内部 ID | 哪位主播开的直播 |
| `room_id` | 直播间内部 ID | 在哪个稳定直播间开播 |
| `platform_live_id` | 抖音场次号 | 抖音本场直播的长 ID |
| `session_key` | 本地场次键 | 平台场次号缺失时使用的稳定本地键 |
| `session_name` | 场次名称 | 页面显示名称，例如日期、主播和标题 |
| `title` | 直播标题 | 本场直播标题 |
| `status` | 场次状态 | `preparing`、`live`、`ended`、`incomplete` |
| `started_at` | 开始时间 | 开播或开始监听时间 |
| `ended_at` | 结束时间 | 下播或停止监听时间 |
| `archive_path` | 归档目录 | 本场 Raw Proto 和 JSONL 所在目录 |
| `event_count` | 事件数量 | 已归档标准事件数量 |
| `raw_message_count` | 原始消息数量 | 已保存原始协议消息数量 |
| `archive_status` | 归档状态 | `writing`、`complete`、`verified`、`damaged` |
| `created_at` | 建档时间 | 本地建立场次记录时间 |
| `updated_at` | 更新时间 | 场次摘要最后更新时间 |

建议唯一约束：`room_id + platform_live_id`；平台场次号为空时使用唯一 `session_key`。

## 三、用户与粉丝关系

### 3.1 `users` 用户表

保存用户当前资料。一个用户在不同主播直播间出现时仍然是同一个用户。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 用户内部 ID | 全项目统一用户编号 |
| `douyin_uid` | 抖音 UID | 当前已知 UID |
| `sec_uid` | SecUID | 当前已知安全身份 |
| `display_id` | 抖音号 | 当前用户可见抖音号，可能修改 |
| `nickname` | 昵称 | 当前昵称，不能用于唯一识别 |
| `avatar_url` | 头像地址 | 当前头像网络地址 |
| `gender` | 性别 | 平台下发值，不确定时为空 |
| `signature` | 个性签名 | 当前签名 |
| `is_mystery` | 是否神秘人 | 当前是否表现为神秘人 |
| `identity_status` | 身份状态 | `confirmed`、`temporary`、`merged`、`unknown` |
| `merged_into_user_id` | 合并目标用户 | 重复用户档案被合并后指向正确用户 |
| `first_seen_at` | 首次发现时间 | 第一次在项目中出现 |
| `last_seen_at` | 最近出现时间 | 最近一次被任何功能发现 |
| `created_at` | 建档时间 | 数据库建档时间 |
| `updated_at` | 更新时间 | 当前资料最后更新时间 |

身份相关的异常值不能直接写入普通用户主档。例如 `id=111111` 在现有神秘人归档中被多个不同昵称复用，应标记为临时或哨兵身份。

### 3.2 `user_identities` 用户平台身份表

一个用户可以有多个身份值。它是用户去重的关键表。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 身份记录 ID | 本行编号 |
| `user_id` | 用户内部 ID | 这条平台身份属于谁 |
| `platform` | 平台 | 当前固定为 `douyin`，以后可扩展 |
| `identity_type` | 身份类型 | `uid`、`sec_uid`、`display_id`、`id_str`、`im_user_id`、`temporary` |
| `identity_value` | 身份值 | 平台真实编号或字符串 |
| `identity_scope` | 身份作用范围 | `global`、`anchor`、`session`；匿名 `idStr` 通常不能直接取 `global` |
| `confidence` | 身份可信度 | `verified`、`strong`、`temporary`、`sentinel` |
| `is_sentinel` | 是否哨兵值 | `id=111111` 等平台占位值为 1 |
| `is_primary` | 是否主身份 | 同类型中是否优先使用 |
| `first_seen_at` | 首次发现时间 | 第一次见到该值 |
| `last_seen_at` | 最近发现时间 | 最近一次见到该值 |
| `source` | 资料来源 | `wss`、`profile_api`、`rank_api`、`im`、`manual` |

建议唯一约束：`platform + identity_type + identity_value`。

### 3.3 `user_profile_history` 用户资料变更表

只追加，不修改旧历史。昵称、头像、抖音号等变化都写一行。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 变更记录 ID | 本行编号 |
| `user_id` | 用户内部 ID | 哪个用户发生变化 |
| `field_name` | 字段名 | `nickname`、`display_id`、`avatar_url`、`signature` 等 |
| `old_value` | 旧值 | 变化前内容 |
| `new_value` | 新值 | 变化后内容 |
| `changed_at` | 变化时间 | 发现变化的时间 |
| `anchor_id` | 主播内部 ID | 在哪位主播的数据中发现，可为空 |
| `session_id` | 场次内部 ID | 在哪场直播发现，可为空 |
| `source_method` | 来源协议 | 哪个协议或 API 提供了新值 |

### 3.4 `anchor_users` 主播与用户关系表

同一个用户对不同主播可能有不同的粉丝团、会员和星守护状态，因此必须使用 `anchor_id + user_id` 区分。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 主播用户关系 ID | 本行编号 |
| `anchor_id` | 主播内部 ID | 对哪位主播的关系 |
| `user_id` | 用户内部 ID | 哪个用户 |
| `follow_status` | 关注关系 | `none`、`following`、`mutual`、`unknown` |
| `fans_club_name` | 粉丝团名称 | 当前粉丝团名称 |
| `fans_club_level` | 粉丝团等级 | 当前灯牌等级 |
| `member_status` | 会员状态 | `active`、`expired`、`unknown`、空 |
| `member_type` | 会员类型 | 月度、年度等已解析类型 |
| `member_expire_at` | 会员到期时间 | 未知时为 0 或空 |
| `guardian_status` | 星守护状态 | `active`、`expired`、`unknown`、空 |
| `guardian_type` | 星守护类型 | 当前解析到的守护类型 |
| `guardian_expire_at` | 星守护到期时间 | 未知时为 0 或空 |
| `first_seen_at` | 在本主播首次出现 | 第一次出现在该主播数据中的时间 |
| `last_seen_at` | 在本主播最近出现 | 最近出现在该主播数据中的时间 |
| `last_session_id` | 最近场次 ID | 最近出现在哪场直播 |
| `event_count` | 互动总次数 | 所有标准事件累计 |
| `chat_count` | 弹幕次数 | 评论类事件累计 |
| `like_count` | 点赞次数 | 点赞类事件累计 |
| `gift_count` | 送礼次数 | 礼物事件累计，不是礼物件数 |
| `gift_diamond_total` | 礼物总价值 | 按钻石/抖币统一口径累计 |
| `follow_count` | 关注互动次数 | 关注类消息累计 |
| `score_total` | 累计加分 | 收益互动协议累计分 |
| `updated_at` | 更新时间 | 当前关系和统计最后更新时间 |

建议唯一约束：`anchor_id + user_id`。

### 3.5 `user_entitlement_history` 用户权益历史表

合并记录粉丝团、会员、星守护的开通、续费、升级和过期。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 权益历史 ID | 本行编号 |
| `anchor_user_id` | 主播用户关系 ID | 哪位主播下的哪个用户 |
| `entitlement_type` | 权益类型 | `fans_club`、`member`、`star_guardian` |
| `action` | 动作 | `join`、`open`、`renew`、`upgrade`、`expire`、`update` |
| `level` | 等级 | 有等级的权益使用 |
| `subtype` | 子类型 | 月度、年度、守护种类等 |
| `effective_at` | 生效时间 | 权益本次开始时间 |
| `expire_at` | 到期时间 | 未知时为空 |
| `session_id` | 场次内部 ID | 在哪场直播发生 |
| `source_event_id` | 来源事件 ID | 对应标准直播事件 |
| `created_at` | 记录时间 | 本地写入时间 |

## 四、原始消息与标准事件

### 4.1 `raw_messages` 原始消息索引表

只索引磁盘文件，不把 Raw Proto 二进制直接塞进 SQLite。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 原始消息内部 ID | 本行编号 |
| `session_id` | 场次内部 ID | 属于哪场直播 |
| `method` | 协议方法名 | 例如 `WebcastChatMessage` |
| `msg_id` | 抖音消息 ID | 平台消息编号 |
| `sequence_no` | 接收顺序号 | 本地接收顺序 |
| `received_at` | 接收时间 | 收到消息的毫秒时间 |
| `proto_path` | Proto 文件路径 | `.bin` 相对路径 |
| `json_path` | JSON 文件路径 | 单条解析 JSON 相对路径 |
| `payload_sha256` | 内容校验值 | 用于去重和验证文件损坏 |
| `size_bytes` | 文件大小 | Proto 字节数 |
| `parse_status` | 解析状态 | `parsed`、`unknown_method`、`failed`、`partial` |
| `parse_error` | 解析错误 | 成功时为空 |
| `parser_version` | 解析器版本 | 便于协议升级后判断是否重算 |
| `created_at` | 建索引时间 | 本地写入时间 |

建议唯一约束：`session_id + method + msg_id`。

### 4.2 `live_events` 标准直播事件表

这是实时页面、复盘、粉丝统计和业务规则共同使用的标准数据。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 标准事件 ID | 全项目事件编号 |
| `session_id` | 场次内部 ID | 属于哪场直播 |
| `raw_message_id` | 原始消息 ID | 可追溯到哪条 Raw Proto |
| `event_type` | 事件类型 | `chat`、`gift`、`like`、`enter`、`follow`、`score` 等 |
| `subtype` | 事件子类型 | 更细业务分类，例如 `share`、`fansclub_join` |
| `primary_user_id` | 主要用户 ID | 通常是发送者，可为空 |
| `content` | 明文内容 | 页面可直接显示的文字 |
| `event_at` | 事件时间 | 业务发生时间 |
| `dedupe_key` | 去重键 | 经过规则生成的唯一业务键 |
| `business_id` | 业务对象 ID | 礼物批次、活动 ID 等，可为空 |
| `details_json` | 扩展详情 | 尚未稳定拆表的解析字段 |
| `schema_version` | 事件格式版本 | 标准事件结构版本 |
| `created_at` | 写入时间 | 本地生成事件时间 |

建议唯一约束：`session_id + dedupe_key`。

### 4.3 `event_users` 事件人员关系表

一条活动事件可能同时涉及发送者、参与者和中奖者，不能只放一个 `user_id`。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `event_id` | 标准事件 ID | 哪条事件 |
| `user_id` | 用户内部 ID | 涉及哪个用户 |
| `role` | 用户角色 | `sender`、`target`、`participant`、`winner`、`anchor` |
| `position` | 显示顺序 | 名单顺序 |
| `details_json` | 人员扩展详情 | 奖品、排名等本事件专属资料 |

建议唯一约束：`event_id + user_id + role`。

## 五、红包、福袋和礼物

### 5.1 `activities` 直播活动表

红包和福袋结构相似，但 `activity_type` 必须严格区分。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 活动内部 ID | 本行编号 |
| `session_id` | 场次内部 ID | 活动发生在哪场直播 |
| `platform_activity_id` | 平台活动 ID | LuckyBox ID、Lottery ID、Rp ID 等 |
| `activity_type` | 活动类型 | `lucky_bag` 福袋、`red_packet` 红包、`unknown` 未确认 |
| `sender_user_id` | 发起用户 ID | 谁发起活动，可为空 |
| `title` | 活动标题 | 例如钻石福袋、礼物红包 |
| `prize_name` | 奖品名称 | 奖品明文 |
| `diamond_amount` | 钻石金额 | 已确认的钻石数 |
| `total_count` | 总份数 | 奖励总数量 |
| `participant_count` | 参与人数 | 平台下发统计值 |
| `winner_count` | 中奖人数 | 平台下发或名单统计值 |
| `status` | 活动状态 | `created`、`running`、`drawing`、`ended`、`unknown` |
| `started_at` | 开始时间 | 活动发出时间 |
| `draw_at` | 计划开奖时间 | 平台下发的开奖时间 |
| `ended_at` | 结束时间 | 实际结束时间 |
| `icon_media_id` | 图标资源 ID | 关联 `media_assets` |
| `details_json` | 扩展详情 | 暂未稳定拆分的协议字段 |
| `created_at` | 建档时间 | 本地首次收到活动时间 |
| `updated_at` | 更新时间 | 生命周期最后更新时间 |

建议唯一约束：`session_id + activity_type + platform_activity_id`。

### 5.2 `activity_users` 活动人员表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 活动人员记录 ID | 本行编号 |
| `activity_id` | 活动内部 ID | 属于哪个活动 |
| `user_id` | 用户内部 ID | 已识别的用户，可为空 |
| `platform_user_id` | 平台用户 ID | 只有 UID、还没建完整用户时保留 |
| `role` | 人员角色 | `participant` 或 `winner` |
| `reward_name` | 获得奖励 | 中奖者的奖品名称 |
| `reward_amount` | 奖励数量 | 奖品数量或金额 |
| `joined_at` | 参与时间 | 未知时为空 |
| `won_at` | 中奖时间 | 未知时为空 |
| `source_event_id` | 来源事件 ID | 哪条协议事件提供名单 |
| `created_at` | 记录时间 | 本地写入时间 |

不要根据“参与人数 11”伪造 11 个未知用户。只有协议下发了用户 ID 或用户资料时才创建名单行。

### 5.3 `gifts` 礼物目录表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 礼物内部 ID | 本行编号 |
| `platform_gift_id` | 抖音礼物 ID | 平台礼物编号 |
| `name` | 礼物名称 | 当前官方名称 |
| `diamond_count` | 单价 | 单个礼物钻石/抖币价值 |
| `icon_media_id` | 图标资源 ID | 关联统一媒体表 |
| `image_media_id` | 展示图片资源 ID | 关联统一媒体表 |
| `is_active` | 是否仍在目录 | 官方列表是否仍包含 |
| `payload_hash` | 目录内容哈希 | 判断官方资料是否变化 |
| `first_seen_at` | 首次发现时间 | 第一次同步到 |
| `last_seen_at` | 最近发现时间 | 最近一次同步仍存在 |
| `updated_at` | 更新时间 | 名称、价格等最后变化时间 |

### 5.4 `gift_transactions` 送礼明细表

标准事件的礼物查询投影，专门处理连击和 Combo。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 送礼记录 ID | 本行编号 |
| `event_id` | 标准事件 ID | 对应哪条礼物事件 |
| `session_id` | 场次内部 ID | 属于哪场直播 |
| `sender_user_id` | 送礼用户 ID | 谁送的 |
| `gift_id` | 礼物内部 ID | 送了什么 |
| `group_key` | 连击分组键 | 同一批连击的稳定键 |
| `delta_count` | 本次增加数量 | 本消息新增多少个 |
| `total_count` | 本批累计数量 | 合并后的累计值 |
| `repeat_count` | 连击次数 | 平台下发连击值 |
| `combo_count` | Combo 数量 | 平台下发 Combo 值 |
| `total_diamonds` | 本批总价值 | 单价乘有效数量 |
| `is_final` | 是否已结束 | 本批连击是否结束 |
| `event_at` | 送礼时间 | 业务时间 |

### 5.5 `gift_effects` 礼物特效表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 特效内部 ID | 本行编号 |
| `platform_effect_id` | 抖音特效 ID | 官方资源编号 |
| `name` | 特效名称 | 官方或本地识别名称 |
| `resource_type` | 资源类型 | 视频、WebP、压缩包等 |
| `md5` | 官方 MD5 | 平台下发时保存 |
| `primary_media_id` | 主要媒体资源 ID | 预览时优先播放的文件 |
| `payload_hash` | 目录内容哈希 | 判断特效是否更新 |
| `first_seen_at` | 首次发现时间 | 第一次同步到 |
| `last_seen_at` | 最近发现时间 | 最近一次同步仍存在 |
| `updated_at` | 更新时间 | 资源最后变化时间 |

### 5.6 `gift_effect_links` 礼物特效关系表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `gift_id` | 礼物内部 ID | 哪个礼物 |
| `effect_id` | 特效内部 ID | 关联哪个特效 |
| `role` | 关系类型 | `primary` 主要、`alternate` 备选 |
| `priority` | 播放优先级 | 数值越小越优先 |
| `created_at` | 建立时间 | 第一次发现关系时间 |

## 六、公共媒体和表情

### 6.1 `media_assets` 媒体资源表

礼物图标、特效、表情、头像和歌曲封面可共用此表去重。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 媒体内部 ID | 本行编号 |
| `media_type` | 媒体类型 | `image`、`video`、`audio`、`archive` |
| `source_url` | 来源地址 | 官方网络 URL |
| `local_path` | 本地路径 | 缓存文件相对路径 |
| `content_sha256` | 内容哈希 | 相同文件去重和损坏校验 |
| `mime_type` | 文件类型 | 例如 `image/webp`、`video/mp4` |
| `size_bytes` | 文件大小 | 字节数 |
| `width` | 宽度 | 图片/视频像素宽度，可为空 |
| `height` | 高度 | 图片/视频像素高度，可为空 |
| `duration_ms` | 时长 | 视频/音频毫秒时长，可为空 |
| `cache_status` | 缓存状态 | `pending`、`ready`、`failed`、`missing` |
| `last_error` | 最近错误 | 下载或解析错误 |
| `first_seen_at` | 首次发现时间 | 第一次见到 URL |
| `downloaded_at` | 下载时间 | 本地缓存完成时间 |
| `last_used_at` | 最近使用时间 | 清理长期不用缓存时参考 |

建议唯一约束：非空的 `content_sha256` 唯一；下载前可暂按 `source_url` 去重。

### 6.2 `emojis` 表情表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 表情内部 ID | 本行编号 |
| `platform_emoji_id` | 平台表情 ID | 协议下发编号，可为空 |
| `display_name` | 显示文字 | 例如 `[微笑]` 或合成表情名称 |
| `group_name` | 表情组名称 | 合成表情所在分组 |
| `emoji_type` | 表情类型 | `normal` 普通、`activity` 合成/活动 |
| `media_id` | 图片资源 ID | 关联 `media_assets` |
| `effective_from` | 生效时间 | 活动表情使用，可为空 |
| `effective_to` | 失效时间 | 活动表情使用，可为空 |
| `last_seen_at` | 最近发现时间 | 最近一次由官方列表或协议下发 |
| `updated_at` | 更新时间 | 图片或名称最后变化时间 |

## 七、点歌、积分和排队

### 7.1 `songs` 歌曲表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 歌曲内部 ID | 本行编号 |
| `source` | 歌曲来源 | `netease`、`local`、其他来源 |
| `source_song_id` | 来源歌曲 ID | 网易云 ID 或本地稳定键 |
| `title` | 歌名 | 当前歌曲名称 |
| `artist` | 歌手 | 歌手名称 |
| `album` | 专辑 | 专辑名称 |
| `duration_ms` | 时长 | 毫秒时长 |
| `cover_media_id` | 封面资源 ID | 关联媒体表 |
| `audio_media_id` | 音频缓存资源 ID | 关联媒体表，可为空 |
| `metadata_status` | 资料状态 | `complete`、`partial`、`failed` |
| `created_at` | 建档时间 | 第一次加入系统 |
| `updated_at` | 更新时间 | 歌曲资料最后更新 |

建议唯一约束：`source + source_song_id`。

### 7.2 `playlists` 歌单表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 歌单内部 ID | 本行编号 |
| `name` | 歌单名称 | 页面显示名称 |
| `playlist_type` | 歌单类型 | `idle` 空闲、`imported` 导入、`custom` 自建 |
| `source` | 来源 | 网易云、本地目录、系统 |
| `source_playlist_id` | 来源歌单 ID | 外部平台编号，可为空 |
| `cover_media_id` | 封面资源 ID | 关联媒体表 |
| `is_enabled` | 是否启用 | 是否参与空闲播放 |
| `created_at` | 建立时间 | 本地创建时间 |
| `updated_at` | 更新时间 | 名称或启用状态最后变化时间 |

### 7.3 `playlist_songs` 歌单歌曲关系表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `playlist_id` | 歌单内部 ID | 哪个歌单 |
| `song_id` | 歌曲内部 ID | 哪首歌 |
| `position` | 排序位置 | 顺序播放位置 |
| `added_at` | 加入时间 | 何时加入歌单 |

建议唯一约束：`playlist_id + song_id`。

### 7.4 `song_requests` 点歌记录表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 点歌记录 ID | 本行编号 |
| `session_id` | 场次内部 ID | 在哪场直播点歌，可为空 |
| `user_id` | 点歌用户 ID | 谁点的，可为空 |
| `song_id` | 歌曲内部 ID | 点了哪首歌 |
| `request_text` | 原始点歌文字 | 用户发送的原始命令 |
| `request_source` | 点歌来源 | `danmaku`、`ui`、`manual`、`playlist` |
| `status` | 点歌状态 | `queued`、`playing`、`played`、`cancelled`、`failed` |
| `queue_position` | 入队位置 | 入队时排在第几位 |
| `points_cost` | 扣除积分 | 本次点歌费用 |
| `requested_at` | 点歌时间 | 请求进入系统时间 |
| `started_at` | 开始播放时间 | 未播放时为空 |
| `ended_at` | 播放结束时间 | 未结束时为空 |
| `failure_reason` | 失败原因 | 成功时为空 |

### 7.5 `playback_history` 播放历史表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 播放历史 ID | 本行编号 |
| `song_id` | 歌曲内部 ID | 实际播放的歌曲 |
| `song_request_id` | 点歌记录 ID | 来源点歌，可为空 |
| `session_id` | 场次内部 ID | 属于哪场直播，可为空 |
| `started_at` | 开始播放时间 | 实际播放开始 |
| `ended_at` | 结束播放时间 | 实际结束或切歌时间 |
| `end_reason` | 结束原因 | `completed`、`skipped`、`failed`、`stopped` |
| `played_ms` | 实际播放时长 | 毫秒 |

### 7.6 `song_blacklist` 歌曲黑名单表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 黑名单记录 ID | 本行编号 |
| `song_id` | 歌曲内部 ID | 被禁歌曲 |
| `reason` | 禁止原因 | 人工备注或规则原因 |
| `scope_type` | 生效范围 | `global` 或 `anchor` |
| `anchor_id` | 主播内部 ID | 主播范围时填写 |
| `created_by` | 操作来源 | 用户、系统规则或导入 |
| `created_at` | 加入时间 | 何时加入黑名单 |

### 7.7 `point_ledger` 积分流水表

积分只记流水，余额由流水求和或维护缓存，不能只保存一个会被覆盖的余额。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 积分流水 ID | 本行编号 |
| `anchor_id` | 主播内部 ID | 哪位主播体系下的积分 |
| `user_id` | 用户内部 ID | 哪个用户 |
| `session_id` | 场次内部 ID | 在哪场直播发生，可为空 |
| `delta` | 本次变化 | 正数加分，负数扣分 |
| `balance_after` | 变化后余额 | 便于核对 |
| `reason_type` | 原因类型 | `profit`、`song_request`、`queue`、`manual` 等 |
| `reason_text` | 原因说明 | 人能看懂的简短说明 |
| `source_event_id` | 来源事件 ID | 弹幕协议引起时填写 |
| `source_record_id` | 来源业务记录 ID | 点歌等业务引起时填写 |
| `created_at` | 发生时间 | 积分变化时间 |

### 7.8 `queue_entries` 通用排队表

建议用于上车等普通排队。点歌有独立生命周期，继续使用 `song_requests`。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 排队记录 ID | 本行编号 |
| `queue_type` | 队列类型 | `game_car`、未来其他排队类型 |
| `anchor_id` | 主播内部 ID | 哪位主播的队列 |
| `session_id` | 场次内部 ID | 哪场直播的队列 |
| `user_id` | 用户内部 ID | 谁排队 |
| `status` | 状态 | `waiting`、`called`、`active`、`completed`、`cancelled` |
| `priority` | 优先级 | 数值越高越优先 |
| `position` | 当前位置 | 页面展示顺序 |
| `joined_at` | 加入时间 | 入队时间 |
| `updated_at` | 更新时间 | 状态最后变化时间 |
| `details_json` | 扩展规则 | 游戏、座位等特有信息 |

## 八、续火花和私信

### 8.1 `im_conversations` 私信会话表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 会话内部 ID | 本行编号 |
| `platform_conversation_id` | 平台会话 ID | 抖音私信会话稳定编号 |
| `conversation_type` | 会话类型 | `private` 私聊、`group` 群聊、`unknown` |
| `title` | 会话名称 | 私聊昵称或群名，只用于展示 |
| `avatar_url` | 会话头像 | 当前头像地址 |
| `target_user_id` | 对方用户 ID | 私聊可关联统一用户，群聊为空 |
| `streak_status` | 火花状态 | `lit`、`expired`、`rekindled`、`none`、`unknown` |
| `streak_days` | 火花天数 | 已识别的连续天数 |
| `list_offset` | 虚拟列表位置 | 浏览器自动定位会话时使用 |
| `last_message_at` | 最近消息时间 | 页面可见时保存 |
| `last_scanned_at` | 最近扫描时间 | 最近从抖音页面更新会话时间 |
| `created_at` | 建档时间 | 首次发现会话时间 |
| `updated_at` | 更新时间 | 会话资料最后变化时间 |

会话必须依靠平台会话 ID 和列表结构识别，不能仅靠昵称定位。群聊不能强行映射成一个普通用户。

### 8.2 `spark_tasks` 续火花任务表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 任务内部 ID | 本行编号 |
| `status` | 任务状态 | `queued`、`running`、`stopping`、`completed`、`cancelled`、`failed` |
| `message_template` | 发送文案 | 本次任务实际使用的文字 |
| `total_count` | 总会话数 | 计划处理数量 |
| `completed_count` | 成功数量 | 已成功发送数量 |
| `failed_count` | 失败数量 | 发送失败数量 |
| `interval_seconds` | 发送间隔 | 每次发送之间的秒数 |
| `started_at` | 开始时间 | 实际开始时间 |
| `ended_at` | 结束时间 | 任务结束时间 |
| `created_at` | 创建时间 | 点击开始任务时间 |

### 8.3 `spark_task_items` 续火花任务明细表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 任务明细 ID | 本行编号 |
| `task_id` | 任务内部 ID | 属于哪次批量任务 |
| `conversation_id` | 会话内部 ID | 发给哪个会话 |
| `status` | 发送状态 | `pending`、`sending`、`success`、`failed`、`skipped` |
| `attempt_count` | 尝试次数 | 已重试多少次 |
| `error_code` | 错误代码 | 程序使用的稳定错误标识 |
| `error_message` | 错误说明 | 人能看懂的失败原因 |
| `sent_at` | 发送时间 | 成功时记录 |
| `updated_at` | 更新时间 | 状态最后变化时间 |

## 九、字幕、配置和系统记录

### 9.1 `caption_records` 字幕记录表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 字幕记录 ID | 本行编号 |
| `session_id` | 场次内部 ID | 属于哪场直播，可为空 |
| `text` | 字幕正文 | 捕获到的完整文字 |
| `source` | 字幕来源 | 当前为 Windows 实时辅助字幕 |
| `revision` | 字幕版本 | 捕获服务递增版本号 |
| `started_at` | 出现时间 | 首次显示时间 |
| `ended_at` | 结束时间 | 被下一条替换或超时时间 |
| `created_at` | 保存时间 | 本地写入时间 |

### 9.2 `settings` 统一配置表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 配置内部 ID | 本行编号 |
| `scope_type` | 作用范围 | `global`、`anchor`、`device` |
| `scope_id` | 范围对象 ID | 主播 ID 或设备 ID；全局为空 |
| `module` | 所属模块 | `listener`、`musicbot`、`captions`、`gift_assets`、`live_ui` 等 |
| `config_key` | 配置键 | 程序使用的固定英文名 |
| `value_json` | 配置值 | 带类型的 JSON 值 |
| `value_type` | 值类型 | `string`、`number`、`boolean`、`object`、`array` |
| `is_secret` | 是否敏感 | 敏感配置不应在普通接口返回；凭证最好不入库 |
| `updated_by` | 修改来源 | 页面、导入、迁移或系统 |
| `created_at` | 建立时间 | 首次创建配置时间 |
| `updated_at` | 更新时间 | 最近保存时间 |

建议唯一约束：`scope_type + scope_id + module + config_key`。

### 9.3 `ui_presets` 页面预设表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 预设内部 ID | 本行编号 |
| `anchor_id` | 主播内部 ID | 主播专用预设，可为空 |
| `preset_type` | 预设类型 | `live_ui`、`card_layout`、`theme` |
| `name` | 预设名称 | 页面显示名称 |
| `config_json` | 预设内容 | 经过后端校验的配置 JSON |
| `is_default` | 是否默认 | 同类型默认使用 |
| `created_at` | 建立时间 | 创建预设时间 |
| `updated_at` | 更新时间 | 最后修改时间 |

### 9.4 `operation_logs` 操作日志表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `id` | 日志内部 ID | 本行编号 |
| `module` | 所属模块 | 监听、礼物同步、点歌、续火花等 |
| `action` | 操作 | `start`、`stop`、`save_config`、`sync`、`import` 等 |
| `status` | 结果 | `success`、`failed`、`cancelled` |
| `summary` | 简要说明 | 页面显示的结果文字 |
| `details_json` | 详细信息 | 参数摘要、数量和错误上下文；不得写入 Cookie |
| `anchor_id` | 主播内部 ID | 与主播相关时填写 |
| `session_id` | 场次内部 ID | 与场次相关时填写 |
| `created_at` | 发生时间 | 操作记录时间 |

### 9.5 `schema_migrations` 数据库版本表

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `version` | 数据库版本 | 递增版本号，例如 1、2、3 |
| `name` | 升级名称 | 本次结构变化说明 |
| `checksum` | 脚本校验值 | 防止迁移脚本被悄悄修改 |
| `applied_at` | 执行时间 | 何时升级成功 |

### 9.6 `schema_dictionary` 中文字段字典表

让管理页面也能显示中文字段说明。

| 字段 | 中文名称 | 含义 |
| --- | --- | --- |
| `table_name` | 表名 | 英文数据库表名 |
| `field_name` | 字段名 | 英文字段名 |
| `table_name_zh` | 表中文名 | 例如“直播场次表” |
| `field_name_zh` | 字段中文名 | 例如“场次号” |
| `description` | 详细含义 | 给非开发人员看的解释 |
| `value_examples` | 示例值 | 可选示例 |
| `is_sensitive` | 是否敏感 | 导出和展示时是否需要隐藏 |
| `updated_at` | 更新时间 | 字典最后修改时间 |

## 十、状态枚举中文对照

数据库建议保存稳定英文值，页面负责翻译中文。

| 英文值 | 中文显示 | 使用位置 |
| --- | --- | --- |
| `live` | 直播中 | 直播间、场次 |
| `not_live` | 未开播 | 直播间 |
| `ended` | 已下播/已结束 | 场次、活动 |
| `unknown` | 未确认 | 所有无法可靠判断的数据 |
| `active` | 有效/进行中 | 会员、守护、资源 |
| `expired` | 已过期 | 会员、守护、火花 |
| `pending` | 等待处理 | 下载、任务明细 |
| `running` | 运行中 | 任务、活动 |
| `completed` | 已完成 | 任务、队列、播放 |
| `failed` | 失败 | 解析、下载、任务 |
| `cancelled` | 已取消 | 任务、点歌、排队 |
| `private` | 私聊 | 私信会话 |
| `group` | 群聊 | 私信会话 |
| `participant` | 参与者 | 活动人员 |
| `winner` | 中奖者 | 活动人员 |
| `lucky_bag` | 福袋 | 活动类型 |
| `red_packet` | 红包 | 活动类型 |

## 十一、字段来源可信度

同一个字段可能来自多个地方。建议保存来源优先级，避免低质量数据覆盖高质量数据。

| 优先级 | 来源 | 适合字段 |
| --- | --- | --- |
| 1 | 已验证的业务协议 | 活动 ID、中奖用户 ID、礼物 ID、业务时间 |
| 2 | 主播/用户官方资料 API | UID、SecUID、Display ID、昵称、头像 |
| 3 | 直播间榜单和互动用户对象 | 用户当前资料、徽章、贡献值 |
| 4 | 渲染后的直播网页 | 开播/下播状态、页面可见资料 |
| 5 | 本地推断或人工填写 | 只能作为备注，不能覆盖已验证平台字段 |

任何“猜测字段”都必须标记来源和可信度，不能伪装成协议真实下发。

## 十二、敏感字段规则

以下内容不要进入普通业务表或普通备份：

- 抖音 Cookie、`sessionid`
- 网易云 Cookie、`MUSIC_U`
- 登录二维码临时令牌
- 浏览器 Profile 中的认证文件
- 用户未公开的私信正文

如果业务确实需要保存敏感配置，应使用 Windows 凭据管理器或单独加密的凭据文件，并在数据库中只保存凭据引用名，例如 `douyin_listener_account_1`。

## 十三、旧数据迁移对应表

| 旧数据 | 新表 |
| --- | --- |
| 每个主播的 `fans` | `users` + `anchor_users` |
| `fan_field_changes` | `user_profile_history` |
| `fan_member_records` | `user_entitlement_history`，类型为 `member` |
| `fan_star_guardian_records` | `user_entitlement_history`，类型为 `star_guardian` |
| `fan_session_sightings` | `anchor_users` 摘要 + `live_events` 明细 |
| `session.json` | `live_sessions` |
| `raw_proto_index.jsonl` | `raw_messages` |
| `parsed.jsonl` | 保留归档，并生成 `live_events` |
| 礼物 `gift_catalog` | `gifts` |
| 特效 `effect_catalog` | `gift_effects` |
| 礼物 `asset_cache` | `media_assets` + 礼物/特效关联 |
| MusicBot `state.json.users` | `users`，无法对应者进入待合并身份 |
| MusicBot `idlePlaylists` | `playlists` + `playlist_songs` + `songs` |
| MusicBot `blacklist` | `song_blacklist` + `songs` |
| Live UI localStorage | `ui_presets` |
| 续火花内存结果 | `spark_tasks` + `spark_task_items` |

迁移期间必须保留旧文件，先比对数量和抽样内容，再决定何时停止旧写入。
