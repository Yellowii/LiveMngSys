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
