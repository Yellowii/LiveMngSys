import tempfile
import unittest
from pathlib import Path

from fan_database import FanDatabase, FanDatabaseRegistry


class FanDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = FanDatabase(Path(self.temp_dir.name) / "fans.sqlite3")
        self.room = {"id": "room-1"}

    def tearDown(self):
        self.temp_dir.cleanup()

    def observe(self, user, timestamp, kind="chat", method="WebcastChatMessage"):
        self.database.observe_event(
            {"kind": kind, "user": user},
            {"method": method, "ts": timestamp, "parsed": {"user": user}},
            self.room,
            "session-1",
        )

    def test_tracks_mutable_fields_with_change_dates(self):
        self.observe({"id": "u-1", "nickname": "first", "displayId": "first-id"}, 100)
        self.observe({"id": "u-1", "nickname": "second", "displayId": "second-id"}, 200)

        detail = self.database.fan_detail("u-1")
        self.assertEqual(detail["fan"]["nickname"], "second")
        self.assertEqual(detail["fan"]["display_id"], "second-id")
        self.assertEqual({item["field_name"] for item in detail["changes"]}, {"nickname", "display_id"})
        self.assertTrue(all(item["changed_at"] == 200 for item in detail["changes"]))
        self.assertEqual(detail["sessions"][0]["session_id"], "session-1")

    def test_keeps_mystery_users_in_a_separate_index(self):
        self.observe({"id": "m-1", "nickname": "\u795e\u79d8\u4ebaA", "isMysteryUser": True}, 100)
        result = self.database.list_fans(mystery="only")

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["identity"], "m-1")
        self.assertEqual(result["items"][0]["is_mystery"], 1)
        self.assertEqual(result["stats"]["mystery"], 1)

    def test_rank_payload_users_are_collected_without_a_normalized_event_user(self):
        self.database.observe_event(
            {"kind": "audience"},
            {
                "method": "WebcastAudienceRankList",
                "ts": 100,
                "parsed": {"data": {"ranks": [{"user": {"id": "rank-1", "nickname": "rank user"}}]}},
            },
            self.room,
            "session-1",
        )
        self.assertEqual(self.database.list_fans()["items"][0]["identity"], "rank-1")

    def test_membership_purchase_uses_normalized_type_operation_and_expiry(self):
        user = {"id": "member-1", "nickname": "Echo"}
        event = {
            "kind": "membership",
            "user": user,
            "membership": "会员",
            "action": "续费会员",
            "operation": "renew",
            "expireAt": 987654,
            "content": "续费会员",
        }
        self.database.observe_event(
            event,
            {"method": "WebcastNotifyEffectMessage", "ts": 100, "parsed": {}},
            self.room,
            "session-1",
        )

        detail = self.database.fan_detail("member-1")
        self.assertEqual(detail["members"][0]["member_type"], "会员")
        self.assertEqual(detail["members"][0]["event_type"], "renew")
        self.assertEqual(detail["members"][0]["expire_at"], 987654)
        self.assertEqual(detail["fan"]["member_status"], "有效")

    def test_star_guard_purchase_is_stored_in_guardian_history(self):
        user = {"id": "guard-1", "nickname": "guardian"}
        self.database.observe_event(
            {
                "kind": "membership",
                "user": user,
                "membership": "星守护",
                "action": "续费星守护",
                "operation": "renew",
                "guardianPeriod": "quarterly",
                "expireAt": 123456,
                "content": "续费星守护",
            },
            {"method": "WebcastResidentGuestMessage", "ts": 100, "parsed": {}},
            self.room,
            "session-1",
        )

        detail = self.database.fan_detail("guard-1")
        self.assertEqual(detail["guardians"][0]["guardian_type"], "quarterly")
        self.assertEqual(detail["guardians"][0]["event_type"], "renew")
        self.assertEqual(detail["fan"]["guardian_status"], "有效")

    def test_registry_uses_a_different_database_for_each_anchor(self):
        registry = FanDatabaseRegistry(Path(self.temp_dir.name) / "fan-databases")
        first_room = {"id": "room-1", "anchor": {"id": "anchor-1", "nickname": "first"}}
        second_room = {"id": "room-2", "anchor": {"id": "anchor-2", "nickname": "second"}}
        first = registry.get(first_room)
        second = registry.get(second_room)

        first.observe_event(
            {"kind": "chat", "user": {"id": "same-user", "nickname": "only first"}},
            {"method": "WebcastChatMessage", "ts": 100, "parsed": {}},
            first_room,
            "session-1",
        )

        self.assertNotEqual(first.path, second.path)
        self.assertEqual(first.list_fans()["total"], 1)
        self.assertEqual(second.list_fans()["total"], 0)
        self.assertEqual(first.metadata()["anchor_id"], "anchor-1")
        self.assertEqual(second.metadata()["anchor_id"], "anchor-2")


if __name__ == "__main__":
    unittest.main()
