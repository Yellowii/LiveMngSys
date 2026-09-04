import unittest
from room_monitor import RoomMonitorRegistry

class RoomMonitorRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_rooms_keep_independent_status_and_session(self):
        async def probe(room_id):
            return {"roomState": "live" if room_id == "a" else "not_live", "sessionId": f"session-{room_id}"}
        registry = RoomMonitorRegistry(probe)
        await registry.configure([{"roomId": "a"}, {"roomId": "b"}])
        result = {item["roomId"]: item for item in await registry.poll_once()}
        self.assertEqual(result["a"]["roomState"], "live")
        self.assertEqual(result["b"]["roomState"], "not_live")
        self.assertEqual(result["a"]["sessionId"], "session-a")
        self.assertEqual(result["b"]["sessionId"], "session-b")
