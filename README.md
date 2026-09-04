# LiveMngSys

LiveMngSys is served as one LAN service. The root launcher starts the MusicBot on a loopback-only internal port and exposes its UI, API and WebSocket through the GUI gateway.

## Start

Run `Start-LiveMngSys.cmd` or:

```powershell
.\Start-LiveMngSys.ps1 -NoBrowser
```

The service configuration is in `config/service.json`. The public service listens on `0.0.0.0:7000` by default.

## LAN endpoints

- Main UI: `http://<LAN-IP>:7000/GUIDemo/`
- MusicBot UI gateway: `http://<LAN-IP>:7000/musicbot/`
- Health: `http://<LAN-IP>:7000/health`

MusicBot's `7001` port and DouyinListener's `7002` port are internal loopback dependencies. The `7000` gateway is the only LAN entry point.

## Extension points

- Add LiveMngSys APIs under `/api/livemngsys/*`.
- Add independent UI pages under `GUIDemo/` and link them from `GUIDemo/index.html`.
- Keep service-wide host and port changes in `config/service.json`; do not hard-code LAN addresses in pages.

## Dynamic content order

- Time-based streams such as messages, gifts, logs and task results are chronological: old entries stay above and new entries append at the bottom.
- A stream follows the latest entry only while the viewer is already near the bottom. Scrolling upward to inspect history must preserve the viewer's position.
- Rankings, priority queues, playlists and explicitly sorted tables keep their domain-specific order.

Historical prototypes and generated browser data are kept under `Archive/` and are not served by the gateway.
