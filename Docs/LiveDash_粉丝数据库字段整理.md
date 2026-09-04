# LiveDash 粉丝数据库字段整理

来源：`D:\Proj\LiveDash\FansMng\app\utils\db.py`、`app\services\fan_service.py`、当前 `fan_manager.db`、已配置自定义字段。

## 1. 主表 `fans`

| 字段 | 含义 |
|---|---|
| `id` | 内部自增主键 |
| `avatar_url` | 头像 URL |
| `remark_name` | 备注名 |
| `nickname` | 昵称 |
| `douyin_unique_id` | 抖音号 / display_id |
| `douyin_sec_uid` | sec_uid |
| `douyin_profile_url` | 抖音主页 URL |
| `birthday` | 生日 |
| `gender` | 抖音资料性别 |
| `actual_gender` | 实际性别 |
| `join_group_date` | 入团时间 |
| `follow_date` | 关注日期 |
| `fansclub_level` | 粉丝团/灯牌等级 |
| `pay_grade_level` | 付费等级 |
| `pay_grade_recorded_at` | 付费等级记录日期 |
| `member_status` | 会员状态 |
| `member_type` | 会员类型 |
| `member_subscribed_at` | 会员订阅时间 |
| `member_expire_at` | 会员到期时间 |
| `star_guardian_status` | 星守护状态 |
| `star_guardian_type` | 星守护类型 |
| `star_guardian_latest_at` | 星守护最近时间 |
| `star_guardian_expire_at` | 星守护到期时间 |
| `default_address_id` | 默认地址 ID |
| `note` | 备注 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

## 2. 关联表

### `fan_addresses`
- `fan_id`
- `receiver_name`
- `receiver_phone`
- `province`
- `city`
- `district`
- `address_detail`
- `full_address`
- `note`
- `is_default`
- `created_at`
- `updated_at`

### `fan_level_logs`
- `fan_id`
- `level_value`
- `level_up_time`
- `source_type`
- `source_ref`
- `note`
- `created_at`
- `updated_at`

### `fan_member_records`
- `fan_id`
- `member_type`
- `subscribed_at`
- `expire_at`
- `source_type`
- `source_ref`
- `note`
- `created_at`
- `updated_at`

### `fan_star_guardian_records`
- `fan_id`
- `guardian_type`
- `event_time`
- `event_type`
- `expire_at`
- `source_type`
- `source_ref`
- `note`
- `created_at`
- `updated_at`

### `fan_interaction_records`
- `fan_id`
- `event_time`
- `action`
- `source_type`
- `source_ref`
- `note`
- `created_at`
- `updated_at`

### `fan_custom_field_values`
- `fan_id`
- `field_id`
- `value_text`
- `value_number`
- `value_date`
- `value_json`
- `created_at`
- `updated_at`

### `custom_fields`
- `field_name`
- `field_key`
- `field_type`
- `is_required`
- `is_enabled`
- `is_visible_in_list`
- `is_filterable`
- `is_searchable`
- `is_exportable`
- `default_value`
- `options_json`
- `sort_order`
- `description`
- `created_at`
- `updated_at`

### 其他表
- `import_logs`
- `fan_files`
- `live_viewer_stats`
- `live_sessions`
- `hud_announcements`
- `ride_queue_entries`
- `ride_queue_state`
- `native_field_settings`

## 3. 当前内置字段配置

### 默认展示/编辑字段
- 头像 URL
- 备注名
- 昵称
- 抖音号
- sec_uid
- 抖音主页 URL
- 生日
- 抖音资料性别
- 实际性别
- 入团时间
- 关注日期
- 灯牌等级
- 付费等级
- 付费等级记录日期
- 会员状态
- 会员类型
- 会员订阅时间
- 会员到期时间
- 星守护状态
- 星守护类型
- 星守护最近时间
- 星守护到期时间
- 收件人
- 手机号
- 完整地址
- 备注

### 当前自定义字段
- `like_ip`：喜欢的 IP、角色等
- `address_note`：地址备注

## 4. 归档建议

- `douyin_sec_uid` 优先作为匹配键。
- `douyin_unique_id` 用于抖音号补充识别。
- 互动、会员、星守护、等级变化应分别落到独立记录表。
- 备注名、昵称、抖音号、头像等是易变字段，保留历史更适合后续回溯。

## 5. 对照 LiveMngSys 时建议补的点

- 主档案表
- 变更历史表
- 会员/星守护独立记录表
- 会话归档表
- 神秘人或匿名用户标记
- 自定义字段定义与值表

