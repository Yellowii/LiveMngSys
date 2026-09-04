import unittest

from live_captions import LiveCaptionCapture


class LiveCaptionCaptureTests(unittest.TestCase):
    def setUp(self):
        self.capture = LiveCaptionCapture(__import__("pathlib").Path("data/test-captions"))

    def test_caption_updates_on_first_changed_read(self):
        self.assertEqual(self.capture.process_text("今天的直播内容已经开始。", 100), "今天的直播内容已经开始。")
        self.assertEqual(self.capture.state["revision"], 1)

    def test_caption_uses_last_line_like_livedash(self):
        self.assertEqual(self.capture.process_text("上一句字幕\n这是当前字幕", 100), "这是当前字幕")

    def test_repeated_caption_does_not_trigger_an_update(self):
        self.capture.process_text("好的", 100)
        self.assertIsNone(self.capture.process_text("好的", 200))

    def test_disabled_snapshot_does_not_keep_old_caption(self):
        self.capture.process_text("这是一段可以展示的字幕内容。", 100)
        import asyncio
        asyncio.run(self.capture.configure({"enabled": False}))
        self.assertFalse(self.capture.state["text"])

    def test_snapshot_exposes_timeout_fallback_settings(self):
        import asyncio

        asyncio.run(self.capture.configure({
            "enabled": False,
            "fallbackEnabled": True,
            "fallbackTimeoutSeconds": 420,
            "showIdleOnTimeout": True,
        }))
        snapshot = self.capture.snapshot()
        self.assertTrue(snapshot["fallbackEnabled"])
        self.assertEqual(snapshot["fallbackTimeoutSeconds"], 420)
        self.assertTrue(snapshot["showIdleOnTimeout"])
