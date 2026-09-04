# 本地点歌机器人

## 启动

```bash
npm install
npm start
```

独立调试地址（仅本机）：

```text
http://127.0.0.1:7001
```

正式使用时请从 LiveMngSys 根目录启动统一网关，并访问：

```text
http://<LAN-IP>:7000/musicbot/
```

7001 是 MusicBot 的回环内部端口，不作为局域网服务入口。

也可以临时指定端口：

```bash
$env:PORT=3220; npm start
```

## 播放器

当前使用 `mpv` 作为本地播放器，浏览器只负责控制和显示。这样可以在 mpv 里选择音频输出设备，方便接虚拟声卡、音频跳线或 OBS/调音台链路。

请先安装 mpv，并确保 `mpv.exe` 在 PATH 中；或者修改：

```text
Cache\Data\config.json
```

```json
{
  "player": {
    "command": "mpv",
    "audioDevice": "auto"
  }
}
```

前端支持刷新播放器设备、切换输出设备、播放、暂停、下一首、音量和进度跳转。

## 登录

前端已经提供登录区域：

- 二维码登录
- 手动保存网易云 Cookie
- 检查登录状态

对应接口：

- `GET /api/login/qr`
- `GET /api/login/qr/check?key=...`
- `POST /api/login/cookie`
- `GET /api/login/status`
- `POST /api/login/refresh`
- `POST /api/login/logout`

系统只会保存包含 `MUSIC_U` 且通过登录状态校验的 Cookie。登录后，点歌会优先使用该账号的网易云播放权限获取歌曲地址；如果账号权限也只能拿到试听片段或不可播放，才会尝试备用音源解灰。

## 测试弹幕通道

真实弹幕接口暂未接入，当前保留可删除的测试通道：

```http
POST /api/test/danmaku
Content-Type: application/json

{
  "userId": "u1",
  "nickname": "测试用户",
  "text": "点歌 晴天"
}
```

支持命令：

- `点歌 歌名或ID`：加入队列末尾；如果当前空闲，立即播放
- `顶歌 歌名或ID`：加入下一首
- `超级置顶 歌名或ID`：加入最高优先级
- `切歌` / `下一首`
- `播放`
- `暂停`
- `查询余额`

## 空闲列表导入

网易云歌单导入：

```http
POST /api/idle/import/playlist
Content-Type: application/json

{
  "id": "3778678",
  "limit": 200
}
```

本地歌曲目录导入：

```http
POST /api/idle/import/local
Content-Type: application/json

{
  "directory": "D:\\Music",
  "recursive": true
}
```

本地歌曲支持 `.mp3`、`.flac`、`.wav`、`.m4a`、`.aac`、`.ogg`。同名 `.lrc` 文件会自动作为歌词载入。

## 35 秒试听处理

系统会检测网易云返回的试听片段。如果只拿到 35 秒左右的试听地址，会自动尝试备用音源解灰；仍拿不到完整地址时会拒绝加入队列，避免播放到一半断掉。

## 数据位置

```text
Cache
├── Cover
├── Data
│   ├── config.json
│   └── state.json
├── Lyric
└── Music
```

当前默认不缓存网络音频文件，只保存配置、空闲列表、黑名单等轻量数据。
