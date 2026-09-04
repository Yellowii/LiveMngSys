"""Runtime protocol coverage report based on parser and captured sessions."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from Doubao.core.parser import DoubaoParser


def build_protocol_audit(session_root: Path, line_limit: int = 100000) -> dict:
    parser = DoubaoParser()
    classes = sorted(parser._class_index)
    observed: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    samples: dict[str, list[dict]] = {}
    scanned = 0
    files = sorted(session_root.glob("**/parsed.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if scanned >= line_limit:
                        break
                    scanned += 1
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        errors["invalid_json"] += 1
                        continue
                    method = str(record.get("method") or "(empty)")
                    observed[method] += 1
                    parsed = record.get("parsed")
                    if method not in parser._class_index:
                        unknown[method] += 1
                        method_samples = samples.setdefault(method, [])
                        if len(method_samples) < 3:
                            method_samples.append({
                                "session": path.parent.relative_to(session_root).as_posix().replace("/", "::"),
                                "rawprotoFile": str(record.get("rawproto_file") or ""),
                                "messageId": str(record.get("msg_id") or record.get("msgId") or ""),
                            })
                    if isinstance(parsed, dict) and parsed.get("_error"):
                        errors[str(parsed["_error"])[:160]] += 1
                if scanned >= line_limit:
                    break
        except OSError as error:
            errors[f"read:{path.name}:{error}"] += 1
    return {
        "transport": "signed protobuf fetch (HTTP long polling)",
        "parserClassCount": len(classes), "parserMethods": classes,
        "observedMethodCount": len(observed), "observed": dict(observed.most_common()),
        "unknown": dict(unknown.most_common()), "unknownSamples": samples,
        "parseErrors": dict(errors.most_common(20)),
        "recordsScanned": scanned,
        "sourceComparison": {
            "activeParser": "Doubao compiled protobuf modules",
            "douYinSpiderProtoMessageCount": 14,
            "douYinSpiderReplacedActiveProto": False,
        },
        "analysisHint": "优先检查 unknown 和 parseErrors；同一房间增加重复连接不会增加协议类型，只会重复事件。",
    }
