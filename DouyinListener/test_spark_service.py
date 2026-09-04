import asyncio
import unittest
from unittest.mock import patch

from spark_service import (
    FALLBACK_QUOTES,
    SparkManager,
    _cookie_header,
    _fetch_hitokoto_quote,
    _is_group_avatar,
    _normalize_recipients,
    _normalize_spark_conversation,
)


class FakeContext:
    async def cookies(self, urls):
        self.urls = urls
        return [
            {"name": "sessionid", "value": "session-value"},
            {"name": "ttwid", "value": "token-value"},
        ]


class FakeProfileClient:
    def __init__(self, error=None):
        self.error = error
        self.cookie_header = ""

    async def get_current_account(self, cookie_header=None):
        self.cookie_header = cookie_header
        if self.error:
            raise self.error
        return {"nickname": "spark-account", "displayId": "spark-id", "avatar": "avatar-url"}


class SparkAccountTests(unittest.IsolatedAsyncioTestCase):
    def test_cookie_header_deduplicates_cookie_names(self):
        header = _cookie_header([
            {"name": "sessionid", "value": "old"},
            {"name": "sessionid", "value": "new"},
            {"name": "ttwid", "value": "token"},
        ])
        self.assertEqual(header, "sessionid=new; ttwid=token")

    async def test_refreshes_account_from_spark_browser_cookies(self):
        profile_client = FakeProfileClient()
        manager = SparkManager(profile_client=profile_client)
        manager._set(login="logged_in", message="私信已登录")

        refreshed = await manager._refresh_account(FakeContext())

        self.assertTrue(refreshed)
        self.assertEqual(manager.status["login"], "logged_in")
        self.assertEqual(manager.status["account"]["displayId"], "spark-id")
        self.assertEqual(profile_client.cookie_header, "sessionid=session-value; ttwid=token-value")
        self.assertFalse(manager.status["accountLoading"])

    async def test_account_failure_keeps_private_message_login(self):
        manager = SparkManager(profile_client=FakeProfileClient(RuntimeError("profile failed")))
        saved_account = {"nickname": "saved", "displayId": "saved-id"}
        manager._set(login="logged_in", message="私信已登录", account=saved_account)

        refreshed = await manager._refresh_account(FakeContext())

        self.assertFalse(refreshed)
        self.assertEqual(manager.status["login"], "logged_in")
        self.assertEqual(manager.status["message"], "私信已登录")
        self.assertEqual(manager.status["account"], saved_account)
        self.assertEqual(manager.status["accountError"], "profile failed")


class SparkBatchLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_releases_task_before_the_next_batch_starts(self):
        manager = SparkManager()
        started = asyncio.Event()

        async def pending_batch(_options):
            started.set()
            await asyncio.Event().wait()

        manager._run_batch = pending_batch
        payload = {"recipients": [{"id": "friend-1", "name": "friend"}], "message": "hello"}

        ok, _ = await manager.start_batch(payload)
        self.assertTrue(ok)
        await started.wait()

        stopped, _ = await manager.stop_batch()
        self.assertTrue(stopped)
        self.assertIsNone(manager.batch_task)
        self.assertEqual(manager.status["state"], "stopped")

        ok, _ = await manager.start_batch(payload)
        self.assertTrue(ok)
        await manager.stop_batch()


class SparkRecipientTests(unittest.TestCase):
    def test_normalizes_selected_conversation_objects_by_id(self):
        recipients = _normalize_recipients([
            {"id": "conversation-1", "name": "first"},
            {"id": "conversation-1", "name": "duplicate"},
            {"conversationId": "conversation-2", "name": "second"},
            {"id": "missing-name"},
        ])
        self.assertEqual(recipients, [
            {"id": "conversation-1", "name": "first"},
            {"id": "conversation-2", "name": "second"},
        ])

    def test_keeps_avatar_for_search_result_disambiguation(self):
        recipients = _normalize_recipients([{"id": "conversation-1", "name": "same name", "avatar": "avatar-url"}])
        self.assertEqual(recipients, [{"id": "conversation-1", "name": "same name", "avatar": "avatar-url"}])

    def test_keeps_group_flag_for_conversation_list_opening(self):
        recipients = _normalize_recipients([{"id": "group-1", "name": "spark group", "isGroup": True, "listOffset": 528}])
        self.assertEqual(recipients, [{"id": "group-1", "name": "spark group", "isGroup": True, "listOffset": 528}])

    def test_matches_avatar_ignoring_query_parameters(self):
        self.assertTrue(SparkManager._same_avatar("https://example/avatar.webp?from=list", "https://example/avatar.webp?from=search"))

    def test_keeps_conversation_list_offset(self):
        conversation = _normalize_spark_conversation({
            "name": "spark friend",
            "listOffset": 240,
            "spark": {"label": "12", "state": "active"},
        })
        self.assertEqual(conversation["listOffset"], 240)

    def test_keeps_legacy_multiline_recipients_compatible(self):
        recipients = _normalize_recipients("first\nsecond\nfirst")
        self.assertEqual(recipients, [
            {"id": "first", "name": "first"},
            {"id": "second", "name": "second"},
        ])

    def test_normalizes_only_conversations_with_spark_state(self):
        conversation = _normalize_spark_conversation({
            "name": "spark friend",
            "avatar": "avatar-url",
            "spark": {"label": "重燃中 1/3", "state": "reigniting", "icon": "flame-url"},
        })
        self.assertEqual(conversation, {
            "id": "spark friend|avatar-url",
            "name": "spark friend",
            "avatar": "avatar-url",
            "isGroup": False,
            "spark": {"label": "重燃中 1/3", "state": "reigniting", "icon": "flame-url"},
        })
        self.assertIsNone(_normalize_spark_conversation({"name": "regular friend", "spark": None}))

    def test_keeps_group_conversation_type(self):
        conversation = _normalize_spark_conversation({
            "name": "spark group",
            "isGroup": True,
            "spark": {"label": "12", "state": "active"},
        })
        self.assertTrue(conversation["isGroup"])

    def test_identifies_group_avatar_when_group_name_has_no_hint(self):
        avatar = "http://p3-aweme-im-img.byteimg.com/tos-cn-i-7lppr0tkux/group-cover.webp"
        conversation = _normalize_spark_conversation({
            "name": "未兰冰蛋",
            "avatar": avatar,
            "spark": {"label": "重燃中 1/3", "state": "reigniting"},
        })

        self.assertTrue(_is_group_avatar(avatar))
        self.assertTrue(conversation["isGroup"])
        self.assertTrue(_normalize_recipients([conversation])[0]["isGroup"])

    def test_does_not_classify_private_avatar_as_group(self):
        self.assertFalse(_is_group_avatar("https://p3.douyinpic.com/img/aweme-avatar/private.webp"))


class SparkQuoteTests(unittest.IsolatedAsyncioTestCase):
    def test_fetches_literary_hitokoto_content(self):
        class Response:
            def read(self):
                return b'{"hitokoto":"  \xe6\x84\xbf  \xe4\xbd\xa0  \xe5\xa5\xbd  "}'

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        requested = []

        def opener(request, timeout):
            requested.append((request.full_url, timeout))
            return Response()

        self.assertEqual(_fetch_hitokoto_quote(("d", "i", "k"), opener), "愿 你 好")
        self.assertIn("c=d", requested[0][0])
        self.assertIn("c=i", requested[0][0])
        self.assertIn("c=k", requested[0][0])

    async def test_uses_local_candidates_when_remote_request_fails(self):
        manager = SparkManager()
        with patch("spark_service._fetch_hitokoto_quote", side_effect=RuntimeError("offline")):
            messages = await manager.generate_copywriting("random", 3)

        self.assertEqual(len(messages), 3)
        self.assertTrue(set(messages).issubset(FALLBACK_QUOTES))

    async def test_generates_requested_number_of_candidates(self):
        manager = SparkManager()
        with patch("spark_service._fetch_hitokoto_quote", return_value="来自接口的文案"):
            messages = await manager.generate_copywriting("poetry", 3)

        self.assertEqual(messages[0], "来自接口的文案")
        self.assertEqual(len(messages), 3)

    async def test_rejects_unknown_copywriting_type(self):
        manager = SparkManager()
        with self.assertRaisesRegex(ValueError, "不支持的文案类型"):
            await manager.generate_copywriting("unknown", 1)

if __name__ == "__main__":
    unittest.main()
