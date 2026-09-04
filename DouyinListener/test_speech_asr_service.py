import argparse
import threading
import unittest

from speech_asr_service import StreamingAsr


class StreamingAsrStateTests(unittest.TestCase):
    def setUp(self):
        self.engine = StreamingAsr.__new__(StreamingAsr)
        self.engine.lock = threading.RLock()
        self.engine.state = {
            "state": "idle",
            "message": "等待启动",
            "revision": 0,
            "updatedAt": 0,
        }

    def test_visible_state_change_increments_revision(self):
        self.engine._set(state="starting", message="正在加载 sherpa-onnx")

        self.assertEqual(self.engine.state["revision"], 1)
        self.assertGreater(self.engine.state["updatedAt"], 0)

    def test_unchanged_state_does_not_increment_revision(self):
        self.engine._set(state="idle", message="等待启动")

        self.assertEqual(self.engine.state["revision"], 0)


if __name__ == "__main__":
    unittest.main()
