import unittest

from profile_client import _normalize_current_account


class CurrentAccountTests(unittest.TestCase):
    def test_normalizes_current_account_identity_and_avatar(self):
        account = _normalize_current_account({
            "status_code": 0,
            "data": {
                "id": 123,
                "id_str": "123",
                "sec_uid": "sec-user",
                "display_id": "douyin-user",
                "nickname": "account",
                "avatar_medium": {"url_list": ["https://example.test/avatar.png"]},
            },
        })

        self.assertEqual(account["uid"], "123")
        self.assertEqual(account["secUid"], "sec-user")
        self.assertEqual(account["displayId"], "douyin-user")
        self.assertEqual(account["nickname"], "account")
        self.assertEqual(account["avatar"], "https://example.test/avatar.png")

    def test_rejects_empty_current_account_response(self):
        with self.assertRaises(RuntimeError):
            _normalize_current_account({"status_code": 0, "data": {}})


if __name__ == "__main__":
    unittest.main()
