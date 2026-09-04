import unittest
from event_store import _event_raw_user, normalize_user

class AnonymousIdentityTests(unittest.TestCase):
    def test_resolved_display_text_user_wins_over_stale_anonymous_user(self):
        payload = {
            "user": {"id": "42", "nickname": "匿名", "displayId": "old"},
            "common": {"displayText": {"piecesV2": [{"type": 11, "userValue": {
                "user": {"id": "42", "nickname": "清清", "displayId": "qingqing"}
            }}]}},
        }
        self.assertEqual(_event_raw_user(payload)["nickname"], "清清")

    def test_normalized_user_exposes_anonymous_flag(self):
        self.assertTrue(normalize_user({"nickname": "匿名", "id": "1"})["isAnonymous"])
        self.assertFalse(normalize_user({"nickname": "清清", "id": "1"})["isAnonymous"])

    def test_mystery_flag_is_retained_when_real_identity_is_available(self):
        user = normalize_user({"nickname": "清清", "id": "1", "isMysteryUser": True})
        self.assertEqual(user["nickname"], "清清")
        self.assertTrue(user["isMystery"])
        self.assertEqual(user["privacyLabel"], "神秘人")

    def test_session_memory_retains_privacy_label(self):
        from event_store import EventStore
        store = EventStore()
        store.apply({"method": "WebcastChatMessage", "ts": 1, "parsed": {"user": {
            "id": "1", "nickname": "清清", "isMysteryUser": True
        }, "content": "hello"}})
        saved = store.snapshot()["sessionMemory"]["users"][0]
        self.assertTrue(saved["isMystery"])
        self.assertEqual(saved["privacyLabel"], "神秘人")
