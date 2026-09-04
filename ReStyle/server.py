"""Local ReStyle server with writes restricted to the saved directory."""

from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
SAVE_ROOT = (ROOT / "saved").resolve()
MAX_BODY_SIZE = 5 * 1024 * 1024


def resolve_save_path(value: str) -> Path:
    normalized = value.strip().replace("\\", "/").lstrip("/")
    relative = PurePosixPath(normalized)
    if not normalized or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("保存路径必须是 saved 目录内的相对路径")
    if relative.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("保存路径必须以 .html 或 .htm 结尾")
    target = (SAVE_ROOT / Path(*relative.parts)).resolve()
    if target != SAVE_ROOT and SAVE_ROOT not in target.parents:
        raise ValueError("保存路径超出 saved 目录")
    return target


def write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, target)


class ReStyleHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/health":
            self.send_json(200, {"ok": True, "saveRoot": str(SAVE_ROOT)})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/save":
            self.send_json(404, {"ok": False, "error": "接口不存在"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_SIZE:
                raise ValueError("保存内容为空或超过 5 MB")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            html_target = resolve_save_path(str(payload.get("path", "")))
            files = {
                html_target: str(payload.get("html", "")),
                html_target.with_suffix(".css"): str(payload.get("css", "")),
                html_target.with_suffix(".js"): str(payload.get("js", "")),
                html_target.with_suffix(".meta.json"): json.dumps(
                    {
                        "name": str(payload.get("name", "未命名组件")),
                        "type": str(payload.get("type", "组件")),
                        "sourcePath": str(payload.get("path", "")),
                        "updatedAt": str(payload.get("updatedAt", "")),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }
            for target, content in files.items():
                write_text(target, content)
            relative_files = [str(target.relative_to(ROOT)).replace("\\", "/") for target in files]
            self.send_json(200, {"ok": True, "files": relative_files})
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            self.send_json(400, {"ok": False, "error": str(error)})
        except OSError as error:
            self.send_json(500, {"ok": False, "error": f"写入失败：{error}"})


if __name__ == "__main__":
    port = int(os.environ.get("RESTYLE_PORT", "7650"))
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), ReStyleHandler)
    print(f"ReStyle: http://127.0.0.1:{port}/")
    print(f"Save root: {SAVE_ROOT}")
    server.serve_forever()
