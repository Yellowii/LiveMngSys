import json
import tempfile
import time
import unittest
from pathlib import Path

from Doubao.client.auth_qr import QrLogin


class CachedCookieTests(unittest.TestCase):
    def test_cached_session_is_not_rejected_only_because_it_is_old(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir) / "cookies.json"
            cookie_file.write_text(json.dumps({
                "saved_at": int(time.time()) - 30 * 86400,
                "cookies": {"sessionid": "still-check-with-server"},
            }), encoding="utf-8")

            cookies = QrLogin.load_cached_cookies(cookie_file)

        self.assertEqual(cookies, {"sessionid": "still-check-with-server"})


if __name__ == "__main__":
    unittest.main()
