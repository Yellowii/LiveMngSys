import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import service


class ReplaySessionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.session_root = Path(self.temp_dir.name)
        self.session_id = "20260729_120000_test-room"
        session_dir = self.session_root / self.session_id
        session_dir.mkdir()
        self.nested_session_id = "测试直播间::场次7954123353336558"
        nested_dir = self.session_root / "测试直播间" / "场次7954123353336558"
        nested_dir.mkdir(parents=True)
        records = [
            {
                "method": "WebcastChatMessage",
                "ts": 300,
                "parsed": {"user": {"id": "2", "nickname": "viewer"}, "content": "hello"},
            },
            {
                "method": "LiveMngRoomInfo",
                "ts": 100,
                "parsed": {"roomId": "test-room", "title": "Replay room", "anchor": "anchor"},
            },
            {
                "method": "WebcastGiftMessage",
                "ts": 200,
                "parsed": {
                    "user": {"id": "1", "nickname": "gifter"},
                    "gift": {"name": "rose", "diamondCount": 1},
                    "repeatCount": 2,
                },
            },
        ]
        (session_dir / "parsed.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        (nested_dir / "parsed.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        self.root_patch = patch.object(service, "SESSION_ROOT", self.session_root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp_dir.cleanup()

    def test_lists_and_normalizes_saved_session(self):
        sessions = service.list_replay_sessions()
        replay = service.load_replay_session(self.session_id)

        session_ids = {session["id"] for session in sessions}
        self.assertIn(self.session_id, session_ids)
        self.assertIn(self.nested_session_id, session_ids)
        self.assertEqual(sessions[0]["eventCount"], 3)
        self.assertEqual(replay["room"]["id"], "test-room")
        self.assertEqual(replay["room"]["title"], "Replay room")
        self.assertEqual([event["kind"] for event in replay["events"]], ["room", "gift", "chat"])
        self.assertEqual(replay["events"][1]["value"], 2)

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            service.load_replay_session("../outside")

    def test_loads_nested_session_path(self):
        replay = service.load_replay_session(self.nested_session_id)
        self.assertEqual(replay["session"]["id"], self.nested_session_id)
        self.assertEqual(replay["room"]["title"], "Replay room")

    def test_replay_gift_value_uses_deduplicated_rank_snapshots(self):
        rank_session_id = "20260729_123000_rank"
        session_dir = self.session_root / rank_session_id
        session_dir.mkdir()
        records = [
            {
                "method": "WebcastRoomRankMessage",
                "ts": 100,
                "parsed": {"ranks": [
                    {"user": {"id": "a"}, "score": 100},
                    {"user": {"id": "b"}, "score": 50},
                ]},
            },
            {
                "method": "WebcastRoomRankMessage",
                "ts": 200,
                "parsed": {"ranks": [
                    {"user": {"id": "a"}, "score": 120},
                    {"user": {"id": "c"}, "score": 10},
                ]},
            },
        ]
        (session_dir / "parsed.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

        replay = service.load_replay_session(rank_session_id)
        rank_events = [event for event in replay["events"] if event.get("giftValueSource") == "rank"]
        self.assertEqual([event["giftValue"] for event in rank_events], [150, 180])
        self.assertEqual(replay["stats"]["giftValue"], 180)


    def test_replay_session_exposes_activity_records(self):
        activity_session_id = "20260729_130000_activity"
        session_dir = self.session_root / activity_session_id
        session_dir.mkdir()
        (session_dir / "parsed.jsonl").write_text(
            json.dumps({
                "method": "WebcastPreviewCjRpMessage",
                "ts": 123,
                "parsed": {
                    "data": {
                        "rpId": "rp-1",
                        "title": "红包雨",
                        "amount": "88",
                        "currency": "抖币",
                    },
                },
            }) + "\n",
            encoding="utf-8",
        )

        replay = service.load_replay_session(activity_session_id)
        self.assertEqual(replay["events"][0]["kind"], "redPacket")
        self.assertEqual(replay["records"]["redPackets"][0]["activity"]["id"], "rp-1")


if __name__ == "__main__":
    unittest.main()
