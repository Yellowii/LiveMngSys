import unittest
from unittest.mock import patch

from room_status import RoomStatusProbe, classify_room_response


class RoomStatusResponseTests(unittest.TestCase):
    def test_status_four_is_not_live_without_page_confirmation(self):
        result = classify_room_response({
            "status_code": 0,
            "data": {"data": [{"id_str": "room-1", "status": 4, "title": "直播中"}]},
        }, checked_at=1000, web_rid="web-1")
        self.assertEqual(result["roomState"], "not_live")
        self.assertFalse(result["isLive"])
        self.assertEqual(result["roomId"], "web-1")
        self.assertEqual(result["sessionId"], "room-1")

    def test_legacy_live_status_two_is_compatible(self):
        result = classify_room_response({
            "status_code": 0,
            "data": {"data": [{"id_str": "room-2", "status": 2}]},
        })
        self.assertEqual(result["roomState"], "live")

    def test_reads_anchor_display_id_from_response_data(self):
        result = classify_room_response({
            "status_code": 0,
            "data": {"user": {"display_id": "anchor-id"}, "data": [{"id_str": "session-1", "status": 2}]},
        })
        self.assertEqual(result["anchorDisplayId"], "anchor-id")

    def test_offline_status_is_not_live(self):
        result = classify_room_response({
            "status_code": 0,
            "data": {"data": [{"id_str": "room-3", "status": 3}]},
        })
        self.assertEqual(result["roomState"], "not_live")
        self.assertFalse(result["isLive"])

    def test_failed_response_is_unknown_not_offline(self):
        result = classify_room_response({"status_code": 10011, "status_msg": "request rejected"})
        self.assertEqual(result["roomState"], "unknown")


class _FakePage:
    def __init__(self, result=None, error=None):
        self.result = result or {"pageState": "not_live", "pageStatusMessage": "直播已结束"}
        self.error = error
        self.goto_calls = 0

    def is_closed(self):
        return False

    async def goto(self, *_args, **_kwargs):
        self.goto_calls += 1

    async def wait_for_function(self, *_args, **_kwargs):
        return None

    async def evaluate(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return self.result


class _Probe(RoomStatusProbe):
    def __init__(self, page):
        super().__init__()
        self.test_page = page
        self.open_calls = 0
        self.close_calls = 0

    async def _open_page(self):
        self.open_calls += 1
        return object(), object(), self.test_page

    async def _close_page(self, _playwright, _browser, _page):
        self.close_calls += 1


class RoomStatusBrowserLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_page_probes_close_each_temporary_page(self):
        page = _FakePage()
        probe = _Probe(page)

        with patch.dict("sys.modules", {"playwright.async_api": object()}):
            first = await probe._probe_page_state("room-1")
            second = await probe._probe_page_state("room-1")

        self.assertEqual(first["pageState"], "not_live")
        self.assertEqual(second["pageState"], "not_live")
        self.assertEqual(page.goto_calls, 2)
        self.assertEqual(probe.open_calls, 2)
        self.assertEqual(probe.close_calls, 2)

    async def test_failed_page_probe_closes_temporary_browser(self):
        probe = _Probe(_FakePage(error=RuntimeError("page crashed")))

        with patch.dict("sys.modules", {"playwright.async_api": object()}):
            result = await probe._probe_page_state("room-1")

        self.assertEqual(result["pageState"], "unknown")
        self.assertIn("page crashed", result["pageStatusMessage"])
        self.assertEqual(probe.close_calls, 1)
