import asyncio
import sys
import unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import AsyncMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent))

from service import DEFAULT_CONFIG, ListenerManager, ROOT, gift_asset_storage_root, should_verify_room_page


class ListenerManagerConfigUpdateTests(unittest.IsolatedAsyncioTestCase):
    def test_gift_asset_storage_path_supports_relative_and_absolute_values(self):
        self.assertEqual(gift_asset_storage_root("data/gift_assets"), (ROOT / "data" / "gift_assets").resolve())
        self.assertEqual(gift_asset_storage_root(str(ROOT / "data" / "custom_gifts")), (ROOT / "data" / "custom_gifts").resolve())

    async def test_config_update_stops_monitor_before_listener(self):
        manager = object.__new__(ListenerManager)
        manager.auto_start_paused = False
        manager.room_monitor_task = asyncio.create_task(asyncio.sleep(60))
        manager._stop_for_room_transition = AsyncMock()
        manager.room_probe = type("RoomProbeStub", (), {"close": AsyncMock()})()

        await manager._stop_for_config_update()

        self.assertTrue(manager.auto_start_paused)
        self.assertIsNone(manager.room_monitor_task)
        manager._stop_for_room_transition.assert_awaited_once()
        manager.room_probe.close.assert_awaited_once()

    async def test_browser_fallback_setting_triggers_reconfigure(self):
        manager = object.__new__(ListenerManager)
        manager.auto_start_paused = False
        manager.room_monitor_task = None
        manager.task = None
        manager.config = deepcopy(DEFAULT_CONFIG)
        manager.config["browserVisibleFallback"] = False
        manager.store = type(
            "StoreStub",
            (),
            {
                "reset_live_data": lambda self, _config: None,
                "configure_room": lambda self, _config: None,
            },
        )()
        manager.captions = type("CaptionsStub", (), {"configure": AsyncMock()})()
        manager.reconfigure_gift_assets = AsyncMock()
        manager.broadcast = AsyncMock()
        manager.ensure_room_monitor = AsyncMock()
        manager._stop_for_config_update = AsyncMock()

        with patch("service.save_config"):
            ok, _ = await manager.update_config({"browserVisibleFallback": True})

        self.assertTrue(ok)
        manager._stop_for_config_update.assert_awaited_once()

    def test_active_barrage_stream_skips_page_verification(self):
        self.assertFalse(should_verify_room_page(
            {"roomState": "live", "lastEventAt": 990_000},
            poll_interval=30,
            now_ms=1_000_000,
        ))

    def test_stale_live_stream_uses_page_verification(self):
        self.assertTrue(should_verify_room_page(
            {"roomState": "live", "lastEventAt": 900_000},
            poll_interval=30,
            now_ms=1_000_000,
        ))

    def test_offline_room_skips_page_verification(self):
        self.assertFalse(should_verify_room_page(
            {"roomState": "ended", "lastEventAt": 0},
            poll_interval=30,
            now_ms=1_000_000,
        ))


if __name__ == "__main__":
    unittest.main()
