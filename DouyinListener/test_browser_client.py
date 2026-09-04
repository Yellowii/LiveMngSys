import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from Doubao.client.browser_client import DouyinBrowserClient
from Doubao.client.wss_client import ClientConfig


class _FakeWebSocket:
    url = "wss://webcast.example.com/webcast/im/push/v2/?room_id=7669020013826673451"

    def on(self, _event, _callback):
        return None


class BrowserClientTests(unittest.IsolatedAsyncioTestCase):
    def test_websocket_session_id_does_not_replace_configured_room_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = DouyinBrowserClient(ClientConfig(
                room_id="991263980971",
                output_dir=temp_dir,
            ))
            client._on_websocket(_FakeWebSocket())

            self.assertEqual(client.room_id, "991263980971")
            self.assertEqual(client.live_id, "7669020013826673451")
            self.assertIsNotNone(client.saver)
            self.assertIn("991263980971", str(client.saver.session_dir))
            client.saver.close()

    async def test_headless_fallback_switches_to_visible_once(self):
        class _LoopClient(DouyinBrowserClient):
            def __init__(self, cfg):
                super().__init__(cfg)
                self.calls = []
                self.close_calls = 0

            async def _run_browser_session(self, playwright, headless: bool):
                self.calls.append(headless)
                if len(self.calls) == 1:
                    raise RuntimeError("headless failed")
                self._stop = True

            async def _close_context(self):
                self.close_calls += 1

        client = _LoopClient(ClientConfig(browser_auto_visible_fallback=True, reconnect=False))
        await client._run_browser_session_loop(object(), headless=True)

        self.assertEqual(client.calls, [True, False])
        self.assertEqual(client.close_calls, 1)

    async def test_headless_fallback_stays_headless_when_disabled(self):
        class _LoopClient(DouyinBrowserClient):
            def __init__(self, cfg):
                super().__init__(cfg)
                self.calls = []
                self.close_calls = 0

            async def _run_browser_session(self, playwright, headless: bool):
                self.calls.append(headless)
                raise RuntimeError("headless failed")

            async def _close_context(self):
                self.close_calls += 1

        client = _LoopClient(ClientConfig(browser_auto_visible_fallback=False, reconnect=False))
        await client._run_browser_session_loop(object(), headless=True)

        self.assertEqual(client.calls, [True])
        self.assertEqual(client.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
