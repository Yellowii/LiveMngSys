import json
import tempfile
import unittest
from pathlib import Path

from Doubao.client.wss_client import ClientConfig, SessionSaver


class SessionSaverTests(unittest.TestCase):
    def test_archives_json_and_raw_proto_under_room_and_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            saver = SessionSaver(
                ClientConfig(output_dir=temp_dir, save_raw=True),
                room_id="room-1",
                room_title="Test Live",
                live_id="session-1",
                anchor="demo",
                anchor_id="anchor-1",
            )
            raw_path = saver.save_raw("WebcastChatMessage", 101, 1, b"proto")
            json_path = saver.save_json(
                "WebcastChatMessage",
                101,
                1,
                {"method": "WebcastChatMessage", "parsed": {"text": "hello"}},
            )
            saver.save_parsed({"method": "WebcastChatMessage", "json_file": json_path})
            session_dir = saver.session_dir
            saver.close()

            self.assertTrue(session_dir.parent.name.startswith("demo"))
            self.assertEqual(session_dir.name, "场次session-1")
            self.assertTrue((session_dir / raw_path).read_bytes() == b"proto")
            self.assertTrue((session_dir / json_path).exists())
            self.assertTrue((session_dir / "parsed.jsonl").read_text(encoding="utf-8").strip())

            index = json.loads((session_dir / "raw_proto_index.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(index["file"], raw_path)
            metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["roomId"], "room-1")
            self.assertEqual(metadata["liveId"], "session-1")
            self.assertTrue(metadata["archive"]["rawProtoEnabled"])


if __name__ == "__main__":
    unittest.main()
