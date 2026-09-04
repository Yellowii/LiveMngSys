# -*- coding: utf-8 -*-
"""WSS 帧拆包 / 压缩 / 心跳 / ACK。

抖音 WebSocket 二进制帧格式：
    - 帧头 8 字节:
        bytes[0:4] big-endian uint32 = header_length（固定 0xb 即 11? 实际为 8/11/16 可变）
        bytes[4:8] big-endian uint32 = packet_type
          0x01 = HEARTBEAT      (客户端->服务端)
          0x02 = HEARTBEAT_RESP
          0x03 = RESPONSE (普通消息)
          0x04 = ACK
          0x05 = PUSH
          其余值按 RESPONSE 处理
    - 后续 header_length 字节为头部字段（协议版本/压缩标记等）
    - 剩余为 payload，若 internalExt/compressed 标志为真则使用 gzip 解压
"""
from __future__ import annotations
import gzip, struct
from typing import Iterable, Tuple

# WSS 帧类型常量
FRAME_HEARTBEAT = 0x01
FRAME_HEARTBEAT_RESP = 0x02
FRAME_RESPONSE = 0x03
FRAME_ACK = 0x04
FRAME_PUSH = 0x05


def parse_wss_message(raw: bytes) -> Iterable[Tuple[bytes, str, int]]:
    """拆分 WSS 二进制帧，yield (payload, ptype, compression_flag)。

    ptype ∈ {"hb", "resp", "ack", "push", "unknown"}
    """
    if not raw or len(raw) < 8:
        return
    hdr_len = struct.unpack(">I", raw[0:4])[0]
    ptype = struct.unpack(">I", raw[4:8])[0]
    total = len(raw)
    # header 之后为 payload
    if hdr_len < 8:
        hdr_len = 8
    payload = raw[hdr_len:]
    compression = 0
    # 第 8 字节起，header 剩余字段: 常见为 [proto_ver(1)] [compress(1)] ...
    if hdr_len > 8 and len(raw) >= hdr_len:
        try:
            compression = raw[8]  # 0 或 1 (gzip)
        except Exception:
            compression = 0

    if ptype == FRAME_HEARTBEAT_RESP:
        yield payload, "hb", compression
    elif ptype in (FRAME_RESPONSE, FRAME_PUSH):
        yield payload, "resp", compression
    elif ptype == FRAME_ACK:
        yield payload, "ack", compression
    elif ptype == FRAME_HEARTBEAT:
        yield payload, "hb", compression
    else:
        yield payload, "unknown", compression


def unzip_response(payload: bytes) -> bytes:
    """gzip 解压（若需要），返回解析后的 Response 原始 bytes。"""
    if not payload:
        return payload
    # 抖音的 gzip magic: 1f 8b
    if payload[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(payload)
        except Exception:
            pass
    return payload


def build_heartbeat_frame() -> bytes:
    """构造心跳帧（向服务端保活）。"""
    hdr_len = 8
    body = b""  # 心跳不带 payload
    header = struct.pack(">II", hdr_len, FRAME_HEARTBEAT)
    return header + body


def build_ack_frame(internal_ext: str) -> bytes:
    """构造 ACK 帧（响应 internalExt）。"""
    hdr_len = 8
    body = internal_ext.encode("utf-8") if isinstance(internal_ext, str) else internal_ext
    header = struct.pack(">II", hdr_len, FRAME_ACK)
    return header + body