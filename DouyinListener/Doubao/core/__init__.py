# -*- coding: utf-8 -*-
"""Doubao core: parser, frames, protobuf bindings."""
from Doubao.core.parser import DoubaoParser
from Doubao.core.frame import (
    parse_wss_message, build_heartbeat_frame, build_ack_frame,
    unzip_response,
)
from Doubao.core.pb import douyin_pb2 as pb2


def get_method_index():
    """返回 method -> proto class 映射（实例化后访问 _class_index）。"""
    return DoubaoParser()._class_index


__all__ = [
    'DoubaoParser', 'pb2', 'get_method_index',
    'parse_wss_message', 'build_heartbeat_frame', 'build_ack_frame',
    'unzip_response',
]