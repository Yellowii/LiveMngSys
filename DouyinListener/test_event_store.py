import base64
import json
import unittest
from unittest.mock import patch

from Doubao.core.parser import DoubaoParser
from event_store import EventStore, _merge_badges, normalize_user


class BadgeParsingTests(unittest.TestCase):
    def test_room_owner_unique_id_becomes_display_id(self):
        user = normalize_user({
            "id_str": "2593124099558011",
            "sec_uid": "MS4wLjABAAAAexample",
            "unique_id": "jiufangjun",
            "nickname": "anchor",
        })

        self.assertEqual(user["displayId"], "jiufangjun")

    def test_follow_info_uses_douyin_mutual_follow_enum(self):
        mutual = normalize_user({"followInfo": {"followStatus": "2"}})
        fan = normalize_user({"followInfo": {"followStatus": "1"}})
        stranger = normalize_user({"followInfo": {"followStatus": "0"}})

        self.assertEqual(mutual["anchorRelation"], "互关")
        self.assertEqual(mutual["anchorFollowStatus"], 2)
        self.assertEqual(fan["anchorRelation"], "粉丝")
        self.assertEqual(stranger["anchorRelation"], "")

    def test_duplicate_badge_sources_keep_a_single_guard_and_hide_fans_badge(self):
        user = normalize_user({
            "fansClub": {"data": {"clubName": "club", "level": 11, "badge": {"icons": {
                "4": {"urlList": ["https://example.test/star_guard_advanced_badge_11_xmp.png"], "imageType": 51},
            }}}},
            "badgeList": [
                {"urlList": ["https://example.test/star_guard_advanced_badge_11_xmp.png"], "imageType": 51},
                {"urlList": ["https://example.test/fansclub_new_advanced_badge_11_xmp.png"], "imageType": 7},
            ],
        })

        self.assertEqual([badge["type"] for badge in user["badges"]].count("guard"), 1)
        self.assertNotIn("fans", {badge["type"] for badge in user["badges"]})

    def test_same_badge_url_and_uri_are_not_rendered_twice(self):
        badges = _merge_badges(
            [{"type": "admin", "kind": "admin", "label": "admin", "icon": "https://p3.example.test/img/webcast/admin.png~tplv-obj.image"}],
            [{"type": "admin", "kind": "admin", "label": "admin", "icon": "https://p3.example.test/img/webcast/admin.png~tplv-obj.image", "uri": "webcast/admin.png"}],
        )

        self.assertEqual(len(badges), 1)
        self.assertEqual(badges[0]["uri"], "webcast/admin.png")

    def test_badges_follow_the_shared_display_order(self):
        badges = _merge_badges([
            {"type": "admin", "label": "admin", "icon": "https://example.test/admin.png"},
            {"type": "member", "label": "member", "icon": "https://example.test/member.png"},
            {"type": "guard", "label": "guard", "icon": "https://example.test/star_guard.png"},
            {"type": "badge", "label": "special", "icon": "https://example.test/special.png"},
            {"type": "consumer", "label": "level", "icon": "https://example.test/level.png"},
        ])

        self.assertEqual([badge["type"] for badge in badges], ["consumer", "badge", "guard", "member", "admin"])

    def test_same_badge_merge_keeps_highest_level_in_either_group_order(self):
        low = {"type": "fans", "label": "粉丝团Lv11", "level": 11, "icon": "https://example.test/fansclub_11.png"}
        high = {"type": "fans", "label": "粉丝团Lv12", "level": 12, "icon": "https://example.test/fansclub_12.png"}

        for badges in (_merge_badges([low], [high]), _merge_badges([high], [low])):
            self.assertEqual(len(badges), 1)
            self.assertEqual(badges[0]["level"], 12)
            self.assertTrue(badges[0]["icon"].endswith("fansclub_12.png"))

    def test_subscribe_status_does_not_imply_membership(self):
        user = normalize_user({
            "nickname": "ordinary fan",
            "subscribeStatus": 1,
            "payGrade": {"level": 10},
            "fansClub": {"data": {"level": 8}},
            "badgeList": [
                {"urlList": ["https://example.test/new_user_grade_level_v1_10.png"], "imageType": 1},
                {"urlList": ["https://example.test/fansclub_new_advanced_badge_8_xmp.png"], "imageType": 51},
            ],
        })

        self.assertFalse(user["membership"]["opened"])
        self.assertNotIn("member", {badge["type"] for badge in user["badges"]})

    def test_member_and_guard_are_classified_from_badge_images(self):
        member = normalize_user({
            "badgeList": [{"urlList": ["https://example.test/opaque.png"], "imageType": 59}],
        })
        guard = normalize_user({
            "fansClub": {"data": {"level": 17, "badge": {"icons": {
                "4": {"urlList": ["https://example.test/star_guard_advanced_badge_17_xmp.png"]},
            }}}},
        })

        self.assertTrue(member["membership"]["opened"])
        self.assertIn("member", {badge["type"] for badge in member["badges"]})
        self.assertIn("guard", {badge["type"] for badge in guard["badges"]})

    def test_ranklist_fansclub_xmp_badge_is_star_guard(self):
        user = normalize_user({
            "nickname": "ranklist guard",
            "fansClub": {"data": {"clubName": "九权", "level": 11, "badge": {"icons": {
                "2": {"urlList": ["https://p11-webcast.douyinpic.com/img/webcast/ranklist_fansclub_advanced_badge_11.png~tplv-obj.image"]},
                "4": {"urlList": ["https://p11-webcast.douyinpic.com/img/webcast/ranklist_fansclub_advanced_badge_11_xmp.png~tplv-obj.image"], "imageType": 51},
            }}}},
            "badgeList": [
                {"urlList": ["https://p11-webcast.douyinpic.com/img/webcast/ranklist_fansclub_advanced_badge_11.png~tplv-obj.image"], "imageType": 7},
                {"urlList": ["https://p11-webcast.douyinpic.com/img/webcast/ranklist_fansclub_advanced_badge_11_xmp.png~tplv-obj.image"], "imageType": 51},
            ],
        })

        self.assertIn("guard", {badge["type"] for badge in user["badges"]})
        self.assertNotIn("fans", {badge["type"] for badge in user["badges"]})

    def test_ranklist_fansclub_pop_xmp_badge_is_plain_fans_club(self):
        user = normalize_user({
            "nickname": "ranklist fans",
            "fansClub": {"data": {"level": 5, "badge": {"icons": {
                "4": {"urlList": ["https://p11-webcast.douyinpic.com/img/webcast/ranklist_fansclub_pop_advanced_badge_5_xmp.png~tplv-obj.image"], "imageType": 51},
            }}}},
            "badgeList": [
                {"urlList": ["https://p11-webcast.douyinpic.com/img/webcast/ranklist_fansclub_pop_advanced_badge_5_xmp.png~tplv-obj.image"], "imageType": 51},
            ],
        })

        self.assertIn("fans", {badge["type"] for badge in user["badges"]})
        self.assertNotIn("guard", {badge["type"] for badge in user["badges"]})


class EmojiParsingTests(unittest.TestCase):
    def test_structured_emoji_image_becomes_an_image_url(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastEmojiChatMessage",
            "parsed": {
                "user": {"id": 2, "nickname": "member"},
                "emoji": {"image": {"urlList": [
                    "https://cdn.example.test/emoji.png https://cdn.example.test/emoji-alt.png"
                ]}},
                "content": "[会员表情]",
            },
        })

        self.assertEqual(event["emojiImage"], "https://cdn.example.test/emoji.png")

    def test_base64_emoji_content_becomes_an_image_url(self):
        raw_content = b"\x0a\x04test\x12https://cdn.example.test/member-emoji.png\x00"
        store = EventStore()
        event = store.apply({
            "method": "WebcastEmojiChatMessage",
            "parsed": {
                "user": {"id": 1, "nickname": "member"},
                "content": base64.b64encode(raw_content).decode("ascii"),
            },
        })

        self.assertEqual(event["content"], "[会员表情]")
        self.assertEqual(event["emojiImage"], "https://cdn.example.test/member-emoji.png")


class GiftFansClubAndActivityTests(unittest.TestCase):
    def test_exhibition_user_uses_session_profile_and_renders_display_text(self):
        store = EventStore()
        store.apply({
            "method": "WebcastRoomRankMessage",
            "ts": 1_000,
            "parsed": {
                "ranks": [{
                    "user": {
                        "id": "fan-exhibition",
                        "nickname": "小饭团",
                        "avatarThumb": {"urlList": ["https://example.test/fan.jpg"]},
                    },
                }],
            },
        })
        event = store.apply({
            "method": "WebcastExhibitionChatMessage",
            "ts": 2_000,
            "parsed": {
                "common": {
                    "displayText": {
                        "defaultPattern": "{0:user} 成功冠名了{1:string}{2:image}",
                        "piecesV2": [
                            {"type": 11, "userValue": {"user": {"id": "fan-exhibition", "nickname": "小饭团"}}},
                            {"type": 1, "stringValue": "展馆"},
                            {"type": 15, "imageValue": {"urlList": ["https://example.test/exhibition.png"]}},
                        ],
                    },
                },
            },
        })

        self.assertEqual(event["user"]["id"], "fan-exhibition")
        self.assertEqual(event["user"]["avatar"], "https://example.test/fan.jpg")
        self.assertEqual(event["content"], "小饭团 成功冠名了展馆")

    def test_exhibition_without_user_is_marked_as_system_event(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastExhibitionChatMessage",
            "ts": 3_000,
            "parsed": {"displayText": {"defaultPattern": "system"}},
        })
        self.assertTrue(event["systemEvent"])
        self.assertEqual(event["user"]["nickname"], "直播间")

    def test_session_memory_keeps_user_totals_across_audience_refresh(self):
        store = EventStore()
        store.configure_room({"roomId": "room-1"})
        store.apply({
            "method": "LiveMngRoomInfo",
            "ts": 1_000,
            "parsed": {"liveId": "session-1", "roomId": "room-1"},
        })
        store.apply({
            "method": "WebcastLikeMessage",
            "ts": 2_000,
            "msgId": "like-1",
            "parsed": {"user": {"id": "fan-1", "nickname": "老观众"}, "count": 5},
        })
        store.apply({
            "method": "WebcastGiftMessage",
            "ts": 3_000,
            "msgId": "gift-1",
            "parsed": {"user": {"id": "fan-1", "nickname": "老观众", "badges": [{"type": "fans", "label": "粉丝团Lv5"}]}, "gift": {"name": "玫瑰", "diamondCount": 10}, "count": 2},
        })
        store.apply({
            "method": "WebcastRoomRankMessage",
            "ts": 10_000,
            "parsed": {"ranks": [{"user": {"id": "fan-1", "nickname": "老观众", "badges": [{"type": "guard", "label": "星守护"}]}, "score": 80}]},
        })
        store.apply({
            "method": "WebcastRoomRankMessage",
            "ts": 20_000,
            "parsed": {"ranks": [{"user": {"id": "fan-1", "nickname": "老观众"}, "score": 0}]},
        })

        memory = store.snapshot()["sessionMemory"]
        user = memory["users"][0]
        self.assertEqual(memory["sessionId"], "session-1")
        self.assertEqual(memory["summary"]["totalLikes"], 5)
        self.assertEqual(memory["summary"]["totalGiftCount"], 2)
        self.assertEqual(memory["summary"]["totalGiftValue"], 80)
        self.assertEqual(memory["summary"]["giftMessageValue"], 20)
        self.assertEqual(memory["summary"]["rankGiftValue"], 80)
        self.assertEqual(memory["summary"]["giftValueSource"], "rank")
        self.assertEqual(store.snapshot()["stats"]["giftValue"], 80)
        self.assertEqual(user["likes"], 5)
        self.assertEqual(user["giftCount"], 2)
        self.assertEqual(user["giftValue"], 20)
        self.assertEqual(user["contribution"], 80)
        self.assertEqual({badge["type"] for badge in user["badges"]}, {"fans", "guard"})

    def test_session_memory_deduplicates_duplicate_events_and_resets_on_new_session(self):
        store = EventStore()
        store.apply({"method": "LiveMngRoomInfo", "ts": 500, "parsed": {"liveId": "session-1"}})
        record = {
            "method": "WebcastLikeMessage",
            "msgId": "same-like",
            "ts": 1_000,
            "parsed": {"user": {"id": "fan-1"}, "count": 3},
        }
        store.apply(record)
        store.apply(record)
        self.assertEqual(store.snapshot()["sessionMemory"]["summary"]["totalLikes"], 3)

        store.apply({"method": "LiveMngRoomInfo", "ts": 2_000, "parsed": {"liveId": "session-2"}})
        self.assertEqual(store.snapshot()["sessionMemory"]["sessionId"], "session-2")
        self.assertEqual(store.snapshot()["sessionMemory"]["summary"]["totalLikes"], 0)
        self.assertEqual(store.snapshot()["sessionMemory"]["users"], [])

    def test_rank_gift_value_keeps_each_users_highest_contribution(self):
        store = EventStore()
        store.apply({
            "method": "WebcastRoomRankMessage",
            "ts": 1_000,
            "parsed": {"ranks": [
                {"user": {"id": "a"}, "score": 100},
                {"user": {"id": "b"}, "score": 50},
            ]},
        })
        event = store.apply({
            "method": "WebcastRoomRankMessage",
            "ts": 2_000,
            "parsed": {"ranks": [
                {"user": {"id": "a"}, "score": 120},
                {"user": {"id": "c"}, "score": 10},
            ]},
        })

        snapshot = store.snapshot()
        self.assertEqual(event["giftValue"], 180)
        self.assertEqual(snapshot["stats"]["giftValue"], 180)
        self.assertEqual(snapshot["sessionMemory"]["summary"]["rankGiftValue"], 180)
        self.assertEqual(snapshot["sessionMemory"]["summary"]["rankContributorCount"], 3)

    def test_rank_gift_value_is_not_incremented_by_later_gift_messages(self):
        store = EventStore()
        store.apply({
            "method": "WebcastRoomRankMessage",
            "ts": 1_000,
            "parsed": {"ranks": [{"user": {"id": "a"}, "score": 100}]},
        })
        store.apply({
            "method": "WebcastGiftMessage",
            "ts": 2_000,
            "msgId": "gift-after-rank",
            "parsed": {
                "user": {"id": "a"},
                "gift": {"name": "玫瑰", "diamondCount": 10},
                "count": 1,
            },
        })

        snapshot = store.snapshot()
        summary = snapshot["sessionMemory"]["summary"]
        self.assertEqual(snapshot["stats"]["giftValue"], 100)
        self.assertEqual(summary["totalGiftValue"], 100)
        self.assertEqual(summary["giftMessageValue"], 10)
        self.assertEqual(summary["giftValueSource"], "rank")

    def test_rank_gift_value_merges_user_identity_aliases(self):
        store = EventStore()
        store.apply({
            "method": "WebcastRoomRankMessage",
            "ts": 1_000,
            "parsed": {"ranks": [{"user": {"secUid": "secure-a"}, "score": 100}]},
        })
        store.apply({
            "method": "WebcastRoomRankMessage",
            "ts": 2_000,
            "parsed": {"ranks": [{"user": {"id": "a", "secUid": "secure-a"}, "score": 120}]},
        })

        snapshot = store.snapshot()
        self.assertEqual(snapshot["stats"]["giftValue"], 120)
        self.assertEqual(snapshot["sessionMemory"]["summary"]["rankContributorCount"], 1)
        self.assertEqual(len(snapshot["sessionMemory"]["users"]), 1)

    def test_lucky_box_reward_parser_keeps_rewarded_details(self):
        parser = DoubaoParser()
        message = parser._class_index["WebcastLuckyBoxRewardMessage"]()
        message.luckyBoxId = 123
        message.luckyBoxIdStr = "bag-123"
        message.winnerUserIds.append("10001")
        message.rewardedDetails.append(json.dumps({
            "userId": "10002",
            "userName": "winner",
            "avatarUrl": "https://example.test/winner.jpg",
        }, ensure_ascii=False))

        decoded = parser._dispatch("WebcastLuckyBoxRewardMessage", message.SerializeToString())
        self.assertEqual(decoded["luckyBoxId"], "123")
        self.assertEqual(decoded["rewardedDetails"][0], '{"userId": "10002", "userName": "winner", "avatarUrl": "https://example.test/winner.jpg"}')

        event = EventStore().apply({"method": "WebcastLuckyBoxRewardMessage", "parsed": decoded})
        self.assertEqual({user["id"] for user in event["winners"]}, {"10001", "10002"})
        self.assertTrue(any(user.get("nickname") == "winner" for user in event["winners"]))

    def test_xg_lottery_parser_feeds_winner_profiles(self):
        parser = DoubaoParser()
        message = parser._class_index["WebcastXGLotteryMessage"]()
        message.lotteryInfo.lotteryId = 456
        message.lotteryInfo.lotteryIdStr = "lottery-456"
        message.lotteryInfo.status = 3
        message.lotteryInfo.luckyCount = 1
        message.lotteryInfo.candidateNum = 2
        winner = message.lotteryInfo.luckyUsers.add()
        winner.userId = 10003
        winner.userName = "draw winner"
        winner.avatarUrl = "https://example.test/draw-winner.jpg"
        winner.secUserId = "sec-winner"

        decoded = parser._dispatch("WebcastXGLotteryMessage", message.SerializeToString())
        event = EventStore().apply({"method": "WebcastXGLotteryMessage", "parsed": decoded})

        self.assertEqual(event["activity"]["id"], "456")
        self.assertEqual(event["winners"][0]["id"], "10003")
        self.assertEqual(event["winners"][0]["nickname"], "draw winner")
        self.assertEqual(event["winners"][0]["avatar"], "https://example.test/draw-winner.jpg")

    def test_lottery_melon_messages_merge_participants_and_winners(self):
        parser = DoubaoParser()
        store = EventStore()

        start = parser._class_index["WebcastLotteryEventNewMessage"]()
        start.lotteryId = 789
        start.lotteryStatus = 1
        start.lotteryStartTime = 1785675600
        start.lotteryDrawTime = 1785676200
        start.prizeCount = 30
        start.luckyCount = 3
        decoded_start = parser._dispatch("WebcastLotteryEventNewMessage", start.SerializeToString())
        event = store.apply({"method": "WebcastLotteryEventNewMessage", "parsed": decoded_start, "ts": 1785675600000})
        self.assertEqual(event["activity"]["id"], "789")
        self.assertEqual(event["activity"]["status"], "active")
        self.assertEqual(event["activity"]["luckyCount"], 3)

        candidate = parser._class_index["WebcastLotteryCandidateEventMessage"]()
        candidate.lotteryId = 789
        candidate.userId = 10001
        candidate.participateSuccess = True
        decoded_candidate = parser._dispatch("WebcastLotteryCandidateEventMessage", candidate.SerializeToString())
        event = store.apply({"method": "WebcastLotteryCandidateEventMessage", "parsed": decoded_candidate, "ts": 1785675700000})
        self.assertEqual([user["id"] for user in event["participants"]], ["10001"])

        result = parser._class_index["WebcastLotteryDrawResultEventMessage"]()
        result.lotteryId = 789
        result.userIds.extend([10001, 10002, 10003])
        decoded_result = parser._dispatch("WebcastLotteryDrawResultEventMessage", result.SerializeToString())
        event = store.apply({"method": "WebcastLotteryDrawResultEventMessage", "parsed": decoded_result, "ts": 1785676200000})
        self.assertEqual(event["activity"]["status"], "ended")
        self.assertEqual({user["id"] for user in event["winners"]}, {"10001", "10002", "10003"})
        self.assertEqual([user["id"] for user in event["participants"]], ["10001"])

    def test_profit_interaction_uses_registered_protocol_fields(self):
        parser = DoubaoParser()
        message = parser._class_index["WebcastProfitInteractionMessage"]()
        message.userId = 10001
        message.anchorId = 20002
        message.profitScore = 10
        message.totalScore = 80
        message.interactionType = 3
        message.interactionName = "点赞互动"
        message.roomId = 30003
        message.displayText.defaultPattern = "为主播加了 10 分"
        user_piece = message.displayText.piecesV2.add()
        user_piece.userValue.user.id = 10001
        user_piece.userValue.user.nickname = "加分用户"

        decoded = parser._dispatch("WebcastProfitInteractionMessage", message.SerializeToString())
        self.assertEqual(decoded["userId"], "10001")
        self.assertEqual(decoded["profitScore"], "10")
        self.assertEqual(decoded["displayText"]["defaultPattern"], "为主播加了 10 分")

        event = EventStore().apply({"method": "WebcastProfitInteractionMessage", "parsed": decoded})
        self.assertEqual(event["kind"], "score")
        self.assertEqual(event["user"]["id"], "10001")
        self.assertEqual(event["user"]["nickname"], "加分用户")
        self.assertEqual(event["score"], 10)
        self.assertEqual(event["totalScore"], 80)
        self.assertEqual(event["interactionType"], 3)
        self.assertEqual(event["interactionName"], "点赞互动")
        self.assertEqual(event["anchorId"], "20002")
        self.assertEqual(event["roomId"], "30003")
        self.assertEqual(event["content"], "为主播加了 10 分")

    def test_configured_room_id_is_not_replaced_by_live_session_id(self):
        store = EventStore()
        store.configure_room({"roomId": "991263980971"})

        store.apply_room_status_probe({
            "roomId": "7669020013826673451",
            "sessionId": "7669020013826673451",
            "roomState": "live",
        })
        store.apply({
            "method": "LiveMngRoomInfo",
            "parsed": {
                "roomId": "7669020013826673451",
                "liveId": "7669020013826673451",
            },
        })

        room = store.snapshot()["room"]
        self.assertEqual(room["id"], "991263980971")
        self.assertEqual(room["sessionId"], "7669020013826673451")
        self.assertEqual(room["liveId"], "7669020013826673451")

    def test_room_signal_score_uses_the_observed_rich_text_template_only(self):
        parser = DoubaoParser()
        message = parser._class_index["WebcastRoomMessage"]()
        message.common.roomId = 30003
        message.common.displayText.key = "live_signal_msg_special_key"
        message.common.displayText.defaultPattern = "{0:user} 为主播加了 {1:string}分"
        user_piece = message.common.displayText.piecesV2.add()
        user_piece.userValue.user.id = 10001
        user_piece.userValue.user.nickname = "加分用户"
        score_piece = message.common.displayText.piecesV2.add()
        score_piece.stringValue = "10"

        decoded = parser._dispatch("WebcastRoomMessage", message.SerializeToString())
        event = EventStore().apply({"method": "WebcastRoomMessage", "parsed": decoded})

        self.assertEqual(event["kind"], "score")
        self.assertEqual(event["user"]["nickname"], "加分用户")
        self.assertEqual(event["score"], 10)
        self.assertEqual(event["content"], "为主播加了 10 分")
        self.assertEqual(event["roomId"], "30003")

        message.common.displayText.defaultPattern = "恭喜{0:user}成为No.{1:string}本场1000贡献用户"
        decoded = parser._dispatch("WebcastRoomMessage", message.SerializeToString())
        non_score_event = EventStore().apply({"method": "WebcastRoomMessage", "parsed": decoded})
        self.assertNotEqual(non_score_event["kind"], "score")

    def test_duplicate_message_ids_are_ignored(self):
        store = EventStore()
        record = {
            "method": "WebcastChatMessage",
            "msgId": "dup-1",
            "parsed": {
                "user": {"id": "1", "nickname": "alpha"},
                "content": "hello",
            },
        }

        first = store.apply(record)
        second = store.apply(record)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(store.snapshot()["interactions"]), 1)

    def test_normal_chat_splits_known_inline_emoji_without_losing_text(self):
        with patch("event_store.emoji_url", side_effect=lambda name: "https://example.test/smile.png" if name == "[smile]" else ""):
            event = EventStore().apply({
                "method": "WebcastChatMessage",
                "parsed": {
                    "user": {"id": "1", "nickname": "tester"},
                    "content": "before[smile]after[unknown]",
                },
            })

        self.assertEqual(event["content"], "before[smile]after[unknown]")
        self.assertEqual(event["contentSegments"], [
            {"type": "text", "text": "before"},
            {"type": "emoji", "text": "[smile]", "name": "smile", "image": "https://example.test/smile.png"},
            {"type": "text", "text": "after"},
            {"type": "text", "text": "[unknown]"},
        ])

    def test_activity_emoji_groups_register_composite_display_name(self):
        store = EventStore()
        catalog_event = store.apply({
            "method": "ActivityEmojiGroupsMessage",
            "parsed": {
                "activityEmojiGroups": [{
                    "emojiGroup": {
                        "name": "合成表情",
                        "emojiList": [{
                            "name": "弹",
                            "emoji": {"urlList": ["https://example.test/composite.png"]},
                        }],
                    },
                }],
            },
        })
        self.assertEqual(catalog_event["kind"], "state")
        event = store.apply({
            "method": "WebcastChatMessage",
            "parsed": {"user": {"id": "1", "nickname": "tester"}, "content": "看这个[合成表情_弹]"},
        })
        self.assertEqual(event["contentSegments"][1]["image"], "https://example.test/composite.png")

    def test_combo_gift_messages_merge_incrementally(self):
        store = EventStore()
        base = {
            "method": "WebcastGiftMessage",
            "parsed": {
                "user": {"id": "1", "nickname": "gifter"},
                "gift": {"name": "rose", "diamondCount": 1},
                "groupId": 9,
                "groupCount": 2,
                "batchCompose": True,
            },
        }

        first = store.apply({**base, "msgId": "gift-1", "parsed": {**base["parsed"], "repeatCount": 2, "totalDiamondCount": 2}})
        second = store.apply({**base, "msgId": "gift-2", "parsed": {**base["parsed"], "groupCount": 3, "repeatCount": 5, "totalDiamondCount": 5}})

        self.assertEqual(first["count"], 2)
        self.assertEqual(second["count"], 5)
        self.assertTrue(second["merged"])
        self.assertEqual(second["groupCount"], 3)
        self.assertTrue(second["batchCompose"])
        self.assertEqual(second["totalDiamondCount"], 5)
        snapshot = store.snapshot()
        self.assertEqual(len(snapshot["gifts"]), 1)
        self.assertEqual(snapshot["gifts"][0]["count"], 5)
        self.assertEqual(snapshot["stats"]["giftValue"], 5)

    def test_fansclub_message_is_rendered_as_plaintext(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastFansclubMessage",
            "parsed": {
                "user": {"id": "2", "nickname": "fan"},
                "action": 1,
                "clubName": "星光团",
                "level": 7,
                "content": "加入粉丝团",
            },
        })

        self.assertEqual(event["kind"], "fansclub")
        self.assertEqual(event["action"], "join")
        self.assertIn("加入了", event["content"])
        self.assertEqual(event["clubName"], "星光团")
        self.assertEqual(event["user"]["fansClub"]["name"], "星光团")

    def test_social_follow_uses_display_key_and_embedded_user(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastSocialMessage",
            "parsed": {
                "common": {
                    "displayText": {
                        "key": "room_follow_msg",
                        "piecesV2": [{"userValue": {"user": {"id": "follow-1", "nickname": "follow-user"}}}],
                    },
                },
            },
        })

        self.assertEqual(event["content"], "\u5173\u6ce8\u4e86\u4e3b\u64ad")
        self.assertEqual(event["user"]["nickname"], "follow-user")

    def test_fansclub_uses_user_embedded_in_display_text(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastFansclubMessage",
            "parsed": {
                "action": 3,
                "common": {
                    "displayText": {
                        "key": "fansclub_upgrade",
                        "piecesV2": [
                            {"userValue": {"user": {"id": "fan-2", "nickname": "club-user"}}},
                            {"stringValue": "Club"},
                        ],
                    },
                },
            },
        })

        self.assertEqual(event["action"], "upgrade")
        self.assertEqual(event["user"]["nickname"], "club-user")
        self.assertEqual(event["clubName"], "Club")

    def test_activity_messages_keep_detail_fields(self):
        store = EventStore()
        red_packet = store.apply({
            "method": "WebcastPreviewCjRpMessage",
            "parsed": {
                "data": {
                    "rpId": "rp-1",
                    "title": "红包雨",
                    "amount": "88",
                    "currency": "抖币",
                    "status": "live",
                    "totalCount": 20,
                    "claimedCount": 4,
                    "schemaUrl": "douyin://redpacket",
                },
            },
        })
        lucky_bag = store.apply({
            "method": "WebcastPrizeNoticeMessage",
            "parsed": {
                "winner": {"id": "3", "nickname": "winner"},
                "prizeName": "福袋",
                "prizeCount": 1,
                "lotteryId": "lb-1",
                "data": {
                    "title": "新春福袋",
                    "amount": "66",
                    "currency": "抖币",
                    "status": "won",
                    "totalCount": 10,
                    "claimedCount": 2,
                },
            },
        })

        self.assertEqual(red_packet["activity"]["id"], "rp-1")
        self.assertEqual(red_packet["activity"]["title"], "红包雨")
        self.assertEqual(red_packet["activity"]["type"], "red_packet")
        self.assertEqual(store.snapshot()["records"]["redPackets"][0]["activity"]["id"], "rp-1")
        original_red_packet_title = red_packet["activity"]["title"]
        updated_red_packet = store.apply({
            "method": "WebcastPreviewCjRpMessage",
            "msgId": "rp-update-1",
            "parsed": {
                "data": {
                    "rpId": "rp-1",
                    "status": "ended",
                    "claimedCount": 20,
                },
            },
        })
        self.assertEqual(updated_red_packet["activity"]["status"], "ended")
        self.assertEqual(updated_red_packet["activity"]["claimedCount"], 20)
        self.assertEqual(updated_red_packet["activity"]["title"], original_red_packet_title)
        self.assertEqual(len(store.snapshot()["records"]["redPackets"]), 1)
        self.assertEqual(lucky_bag["activity"]["id"], "lb-1")
        self.assertEqual(lucky_bag["activity"]["status"], "won")
        self.assertEqual(lucky_bag["winners"][0]["nickname"], "winner")
        self.assertEqual(store.snapshot()["records"]["luckyBags"][0]["activity"]["title"], "新春福袋")

    def test_empty_prize_notice_does_not_become_lucky_bag(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastPrizeNoticeMessage",
            "parsed": {
                "common": {"method": "WebcastPrizeNoticeMessage", "msgId": "notice-1"},
                "winner": {},
                "prizeId": None,
                "prizeName": None,
                "prizeIcon": None,
                "prizeCount": None,
                "lotteryId": None,
            },
            "ts": 1785686629200,
        })

        self.assertEqual(event["kind"], "room")
        self.assertTrue(event["systemEvent"])
        self.assertEqual(event["user"]["nickname"], "直播间")
        self.assertEqual(event["content"], "中奖通知")
        snapshot = store.snapshot()
        self.assertEqual(snapshot["records"]["luckyBags"], [])
        self.assertEqual(snapshot["records"]["redPackets"], [])
        self.assertEqual(snapshot["interactions"][0]["method"], "WebcastPrizeNoticeMessage")

    def test_prize_count_only_notice_is_not_classified_as_lucky_bag(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastPrizeNoticeMessage",
            "parsed": {
                "common": {"method": "WebcastPrizeNoticeMessage", "msgId": "notice-count-only"},
                "prizeCount": 3,
            },
        })

        self.assertEqual(event["kind"], "room")
        self.assertEqual(event["content"], "中奖通知")
        self.assertEqual(event["prizeNotice"]["prizeCount"], 3)
        self.assertEqual(store.snapshot()["records"]["luckyBags"], [])
        self.assertEqual(store.snapshot()["records"]["redPackets"], [])

    def test_prize_notice_with_red_packet_id_is_red_packet(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastPrizeNoticeMessage",
            "parsed": {
                "winner": {"id": "winner-1", "nickname": "winner"},
                "redPacketId": "rp-notice-1",
                "prizeName": "现金奖励",
                "prizeCount": 1,
            },
        })

        self.assertEqual(event["kind"], "redPacket")
        self.assertEqual(event["activity"]["id"], "rp-notice-1")
        self.assertEqual(event["activity"]["type"], "red_packet")
        snapshot = store.snapshot()["records"]
        self.assertEqual(snapshot["luckyBags"], [])
        self.assertEqual(snapshot["redPackets"][0]["winners"][0]["id"], "winner-1")

    def test_lucky_box_lifecycle_is_merged_by_lucky_box_id(self):
        store = EventStore()
        store.apply({
            "method": "WebcastLuckyBoxMessage",
            "parsed": {
                "luckyBoxId": "bag-1",
                "luckyBoxIdStr": "bag-1",
                "activityId": "activity-1",
                "title": "Lucky Bag",
                "sender": {"id": "sender-1", "nickname": "sender"},
                "endTime": 1000,
                "totalDiamondCount": 50,
            },
        })
        store.apply({
            "method": "WebcastLuckyBoxRewardMessage",
            "parsed": {"luckyBoxId": "bag-1", "winnerUserIds": ["member-1", "member-2"]},
        })
        store.apply({
            "method": "WebcastLuckyBoxEndMessage",
            "parsed": {"luckyBoxIdStr": "bag-1"},
        })

        records = store.snapshot()["records"]["luckyBags"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["activity"]["id"], "bag-1")
        self.assertEqual(records[0]["activity"]["status"], "ended")
        self.assertEqual(records[0]["sender"]["id"], "sender-1")
        self.assertEqual({user["id"] for user in records[0]["winners"]}, {"member-1", "member-2"})
        self.assertEqual([item["method"] for item in records[0]["updates"]], [
            "WebcastLuckyBoxMessage", "WebcastLuckyBoxRewardMessage", "WebcastLuckyBoxEndMessage",
        ])

    def test_lucky_box_channel_uses_red_packet_title_and_keeps_user_lists(self):
        store = EventStore()
        store.apply({
            "method": "WebcastLuckyBoxMessage",
            "parsed": {"luckyBoxIdStr": "packet-1", "title": "\u7ea2\u5305", "user": {"id": "host", "nickname": "host"}},
        })
        store.apply({
            "method": "WebcastLuckyBoxRewardMessage",
            "parsed": {
                "luckyBoxIdStr": "packet-1",
                "winnerUserIds": ["joiner-1", "joiner-2"],
                "rewardedDetails": ['{"userId":"winner-1","userName":"winner","avatarUrl":"https://example.test/winner.jpg"}'],
            },
        })
        store.apply({
            "method": "WebcastLuckyBoxEndMessage",
            "parsed": {"luckyBoxIdStr": "packet-1", "title": "\u7ea2\u5305", "diamondCount": 120},
        })

        snapshot = store.snapshot()["records"]
        self.assertEqual(snapshot["luckyBags"], [])
        self.assertEqual(len(snapshot["redPackets"]), 1)
        record = snapshot["redPackets"][0]
        self.assertEqual(record["kind"], "redPacket")
        self.assertEqual(record["activity"]["type"], "red_packet")
        self.assertEqual(record["content"], "\u7ea2\u5305\u5f00\u5956")
        self.assertEqual({user["id"] for user in record["winners"]}, {"joiner-1", "joiner-2", "winner-1"})
        self.assertTrue(any(user.get("nickname") == "winner" for user in record["winners"]))

    def test_lucky_box_temp_status_attaches_to_latest_active_bag(self):
        store = EventStore()
        store.apply({
            "method": "WebcastLuckyBoxMessage",
            "parsed": {"luckyBoxIdStr": "bag-temp-1", "title": "Lucky Bag"},
        })
        store.apply({
            "method": "WebcastLuckyBoxTempStatusMessage",
            "parsed": {"status": 2},
        })

        records = store.snapshot()["records"]["luckyBags"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["activity"]["id"], "bag-temp-1")
        self.assertEqual(records[0]["updates"][-1]["method"], "WebcastLuckyBoxTempStatusMessage")

    def test_explicit_red_packet_end_migrates_a_previous_generic_lucky_box_record(self):
        store = EventStore()
        store.apply({
            "method": "WebcastLuckyBoxMessage",
            "parsed": {"luckyBoxIdStr": "packet-migrate-1", "title": "Lucky Box"},
        })
        store.apply({
            "method": "WebcastLuckyBoxEndMessage",
            "parsed": {"luckyBoxIdStr": "packet-migrate-1", "title": "\u7ea2\u5305"},
        })

        snapshot = store.snapshot()["records"]
        self.assertEqual(snapshot["luckyBags"], [])
        self.assertEqual(len(snapshot["redPackets"]), 1)
        self.assertEqual(snapshot["redPackets"][0]["activity"]["id"], "packet-migrate-1")
        self.assertEqual(snapshot["redPackets"][0]["activity"]["type"], "red_packet")

    def test_xg_lottery_keeps_winner_profile_details(self):
        store = EventStore()
        store.apply({
            "method": "WebcastXGLotteryMessage",
            "parsed": {
                "lotteryInfo": {
                    "lotteryId": "lottery-1",
                    "lotteryIdStr": "lottery-1",
                    "status": 3,
                    "luckyCount": "2",
                    "candidateNum": "8",
                    "luckyUsers": [{
                        "userId": "winner-1",
                        "userName": "中奖用户",
                        "avatarUrl": "https://example.invalid/winner.png",
                        "secUserId": "sec-winner-1",
                        "prizeName": "钻石福袋",
                    }],
                },
            },
        })

        record = store.snapshot()["records"]["luckyBags"][0]
        self.assertEqual(record["activity"]["id"], "lottery-1")
        self.assertEqual(record["activity"]["luckyCount"], 2)
        self.assertEqual(record["activity"]["candidateTotalCount"], 8)
        self.assertEqual(record["winners"][0]["id"], "winner-1")
        self.assertEqual(record["winners"][0]["nickname"], "中奖用户")
        self.assertEqual(record["winners"][0]["avatar"], "https://example.invalid/winner.png")

    def test_room_probe_marks_a_live_session_as_ended_after_offline(self):
        store = EventStore()
        store.apply_room_status_probe({
            "roomState": "live",
            "checkedAt": 1000,
            "rawStatus": 4,
            "roomId": "room-1",
        })
        self.assertEqual(store.status["roomState"], "live")
        self.assertTrue(store.status["hasLiveSession"])
        store.apply_room_status_probe({
            "roomState": "not_live",
            "checkedAt": 2000,
            "rawStatus": 3,
        })
        self.assertEqual(store.status["roomState"], "ended")
        self.assertEqual(store.status["state"], "monitoring")
        self.assertEqual(store.status["lastOfflineAt"], 2000)

    def test_room_probe_keeps_web_rid_and_session_id_separate(self):
        store = EventStore()
        store.apply_room_status_probe({
            "roomState": "not_live",
            "checkedAt": 1000,
            "roomId": "991263980971",
            "sessionId": "7668281241556388671",
            "pageState": "not_live",
            "pageStatusMessage": "直播已结束",
            "anchorDisplayId": "anchor-id",
        })
        self.assertEqual(store.room["id"], "991263980971")
        self.assertEqual(store.room["sessionId"], "7668281241556388671")
        self.assertEqual(store.room["anchor"]["displayId"], "anchor-id")
        self.assertEqual(store.status["roomState"], "ended")

    def test_lottery_sync_messages_merge_by_embedded_lottery_id(self):
        def encode_varint(value):
            encoded = bytearray()
            while value > 0x7F:
                encoded.append((value & 0x7F) | 0x80)
                value >>= 7
            encoded.append(value)
            return bytes(encoded)

        store = EventStore()
        data = base64.b64encode(b"\x08" + encode_varint(987654321)).decode("ascii")
        for index in range(4):
            store.apply({
                "method": "WebcastRoomDataSyncMessage",
                "msgId": f"lottery-sync-{index}",
                "ts": 1000 + index * 1000,
                "parsed": {
                    "roomId": "room-1",
                    "dataType": "LotteryInfoSyncData",
                    "data": data,
                },
            })

        records = store.snapshot()["records"]["luckyBags"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["activity"]["id"], "987654321")
        self.assertEqual(records[0]["activity"]["status"], "active")
        self.assertEqual(records[0]["content"], "福袋活动状态同步")
        self.assertEqual(records[0]["prize"], "待协议补全")
        self.assertEqual(len(records[0]["updates"]), 1)

    def test_lottery_sync_message_maps_lottery_details_and_draw_state(self):
        def encode_varint(value):
            encoded = bytearray()
            while value > 0x7F:
                encoded.append((value & 0x7F) | 0x80)
                value >>= 7
            encoded.append(value)
            return bytes(encoded)

        fields = {
            1: 987654321,
            2: 5,
            3: 5,
            5: 1,
            6: 50,
            7: 1000,
            8: 1060,
            12: 50,
            13: 5,
        }
        encoded = b"".join(
            encode_varint(field_number << 3) + encode_varint(value)
            for field_number, value in fields.items()
        )
        store = EventStore()
        store.apply({
            "method": "WebcastRoomDataSyncMessage",
            "ts": 1061 * 1000,
            "parsed": {
                "roomId": "room-1",
                "dataType": "LotteryInfoSyncData",
                "data": base64.b64encode(encoded).decode("ascii"),
            },
        })

        record = store.snapshot()["records"]["luckyBags"][0]
        self.assertEqual(record["activity"]["status"], "ended")
        self.assertEqual(record["activity"]["startAt"], 1000 * 1000)
        self.assertEqual(record["activity"]["endAt"], 1060 * 1000)
        self.assertEqual(record["activity"]["luckyCount"], 5)
        self.assertEqual(record["activity"]["candidateTotalCount"], 5)
        self.assertEqual(record["activity"]["amount"], 50)
        self.assertEqual(record["prize"], {"name": "钻石福袋", "amount": 50, "currency": "钻石"})
        self.assertEqual(record["content"], "福袋开奖状态同步")
        self.assertEqual(record["updates"][0]["status"], "ended")

    def test_lottery_sync_snapshot_marks_expired_draw_as_ended_without_an_end_message(self):
        def encode_varint(value):
            encoded = bytearray()
            while value > 0x7F:
                encoded.append((value & 0x7F) | 0x80)
                value >>= 7
            encoded.append(value)
            return bytes(encoded)

        fields = {1: 123, 2: 5, 3: 5, 6: 50, 7: 1000, 8: 1060}
        encoded = b"".join(
            encode_varint(field_number << 3) + encode_varint(value)
            for field_number, value in fields.items()
        )
        store = EventStore()
        with patch("event_store.time.time", return_value=1020):
            store.apply({
                "method": "WebcastRoomDataSyncMessage",
                "ts": 1020 * 1000,
                "parsed": {"dataType": "LotteryInfoSyncData", "data": base64.b64encode(encoded).decode("ascii")},
            })
            self.assertEqual(store.records["luckyBags"][0]["activity"]["status"], "active")
        with patch("event_store.time.time", return_value=1061):
            record = store.snapshot()["records"]["luckyBags"][0]
        self.assertEqual(record["activity"]["status"], "ended")
        self.assertEqual(record["content"], "福袋开奖状态同步")
        self.assertEqual(record["updates"][0]["status"], "ended")

    def test_subscription_message_uses_state_and_expiry_fields(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastSubscriptionMessage",
            "parsed": {
                "user": {"id": "4", "nickname": "member"},
                "subscribeLevel": 3,
                "subscribeState": 2,
                "subscribeTime": 1000,
                "expireTime": 2000,
                "isAutoRenew": True,
                "displayText": {"defaultPattern": "续费 1 个月会员"},
                "badge": {"urlList": ["https://example.test/sub.png"]},
            },
        })

        self.assertEqual(event["membership"], "会员")
        self.assertEqual(event["operation"], "renew")
        self.assertEqual(event["subscribeState"], 2)
        self.assertEqual(event["subscriptionLevel"], 3)
        self.assertEqual(event["expireAt"], 2000)
        self.assertTrue(event["isAutoRenew"])

    def test_resident_guest_update_type_controls_star_guard_operation(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastResidentGuestMessage",
            "parsed": {
                "latestGuestUser": [{
                    "user": {"id": "5", "nickname": "guard"},
                    "guestLevel": 5,
                    "guestDays": 30,
                    "continueWeeks": 2,
                    "residentCount": 8,
                    "guardType": 4,
                    "expireTimestamp": 3000,
                    "guestTitle": "钻石守护",
                }],
                "updateType": 3,
                "guestNum": 8,
                "badge": {"urlList": ["https://example.test/guard.png"]},
                "displayText": {"defaultPattern": "星守护已过期"},
            },
        })

        self.assertEqual(event["membership"], "星守护")
        self.assertEqual(event["operation"], "cancel")
        self.assertEqual(event["action"], "星守护过期")
        self.assertEqual(event["guardType"], 4)
        self.assertEqual(event["residentCount"], 8)
        self.assertEqual(event["expireAt"], 3000)
        self.assertEqual(event["user"]["badges"][0]["type"], "guard")

    def test_star_guard_room_announcement_is_an_explicit_open_event(self):
        store = EventStore()
        event = store.apply({
            "method": "WebcastRoomMessage",
            "ts": 1000,
            "parsed": {
                "common": {
                    "displayText": {
                        "key": "live_signal_msg_special_key",
                        "defaultPattern": "恭喜 {0:user} 成为星守护",
                        "piecesV2": [{
                            "userValue": {"user": {"id": "guard-1", "nickname": "如何呢"}},
                        }],
                    },
                },
            },
        })

        self.assertEqual(event["kind"], "membership")
        self.assertEqual(event["membership"], "星守护")
        self.assertEqual(event["operation"], "open")
        self.assertEqual(event["action"], "点亮星守护")
        self.assertEqual(event["user"]["nickname"], "如何呢")

    def test_star_guard_status_and_entry_messages_are_not_purchase_events(self):
        store = EventStore()
        info = store.apply({
            "method": "WebcastStarGuardInfoMessage",
            "parsed": {
                "user": {"id": "guard-2", "nickname": "observer"},
                "isGuard": True,
                "guardLevel": 5,
                "welcomeText": {"defaultPattern": "欢迎钻石守护回家"},
            },
        })
        entrance = store.apply({
            "method": "WebcastMemberSpecialTipMessage",
            "parsed": {
                "user": {"id": "guard-2", "nickname": "observer"},
                "memberType": 4,
                "memberName": "钻石守护",
                "displayText": {"defaultPattern": "钻石守护进入直播间"},
            },
        })

        self.assertEqual(info["kind"], "membership_snapshot")
        self.assertEqual(info["membership"], "星守护")
        self.assertTrue(info["active"])
        self.assertEqual(entrance["kind"], "membership_snapshot")
        self.assertEqual(len(store.snapshot()["memberships"]), 0)

    def test_resident_guest_level_change_is_not_a_renewal(self):
        event = EventStore().apply({
            "method": "WebcastResidentGuestMessage",
            "parsed": {
                "latestGuestUser": [{
                    "user": {"id": "guard-3", "nickname": "level up"},
                    "guestLevel": 6,
                    "guardType": 3,
                    "expireTimestamp": 5000,
                }],
                "updateType": 4,
            },
        })

        self.assertEqual(event["membership"], "星守护")
        self.assertEqual(event["operation"], "update")
        self.assertEqual(event["action"], "星守护等级变更")
        self.assertEqual(event["guardianPeriod"], "quarterly")

    def test_notify_effect_decodes_subscription_text_and_merges_notice_chain(self):
        parser = DoubaoParser()
        display = parser._class_index["Text"]()
        display.key = "subscribe_purchase_tip"
        display.defaultPattern = "{0:user}{1:string}{2:string}会员"
        user_piece = display.piecesV2.add()
        user_piece.userValue.user.id = 111
        user_piece.userValue.user.nickname = "Echo"
        user_piece.userValue.user.displayId = "echo_test"
        renew_piece = display.piecesV2.add()
        renew_piece.stringValue = "续费了"
        period_piece = display.piecesV2.add()
        period_piece.stringValue = "月度"

        effect = parser._class_index["WebcastNotifyEffectMessage"]()
        effect.template.key = "subscribe_purchase_tip"
        purchase_type = effect.vars.add()
        purchase_type.key = "purchase_type"
        purchase_type.value = "renew"
        subscribe_type = effect.vars.add()
        subscribe_type.key = "subscribe_type"
        subscribe_type.value = "month"
        effect.payload.templateData.content.contentData = display.SerializeToString()

        decoded = parser._dispatch("WebcastNotifyEffectMessage", effect.SerializeToString())
        self.assertEqual(decoded["displayText"]["key"], "subscribe_purchase_tip")
        self.assertEqual(decoded["displayText"]["piecesV2"][0]["userValue"]["user"]["nickname"], "Echo")

        room_display = {
            "key": "subscribe_anchor_mvp_v2",
            "defaultPattern": "{0:user} {1:string}了{2:string}会员",
            "piecesV2": [
                {"userValue": {"user": {"id": "111", "nickname": "Echo", "displayId": "echo_test"}}},
                {"stringValue": "续费"},
                {"stringValue": "月度"},
            ],
        }
        notify_display = {**room_display, "key": "subscribe_anchor_mvp_top_notify_for_anchor_v3"}
        store = EventStore()
        first = store.apply({"method": "WebcastNotifyEffectMessage", "ts": 1000, "parsed": decoded})
        second = store.apply({"method": "WebcastRoomMessage", "ts": 1200, "parsed": {"displayText": room_display}})
        third = store.apply({"method": "WebcastRoomNotifyMessage", "ts": 1400, "parsed": {"common": {"displayText": notify_display}}})

        self.assertEqual(first["kind"], "membership")
        self.assertEqual(first["operation"], "renew")
        self.assertEqual(first["membership"], "会员")
        self.assertEqual(first["user"]["nickname"], "Echo")
        self.assertEqual(first["months"], 1)
        self.assertEqual(second["kind"], "state")
        self.assertEqual(third["kind"], "state")
        memberships = store.snapshot()["memberships"]
        self.assertEqual(len(memberships), 1)
        self.assertEqual(
            memberships[0]["sourceMethods"],
            ["WebcastNotifyEffectMessage", "WebcastRoomMessage", "WebcastRoomNotifyMessage"],
        )


class AudienceRankTests(unittest.TestCase):
    def test_interaction_follow_relation_updates_and_survives_audience_refresh(self):
        store = EventStore()
        audience_user = {"id": "1", "nickname": "alpha", "followInfo": {"followStatus": 1}}
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [{"user": audience_user, "score": 1}]}},
        })
        initial = store.snapshot()["audience"][0]
        self.assertEqual(initial["anchorFollowStatus"], 1)
        self.assertEqual(initial["anchorRelationSource"], "http")
        store.apply({
            "method": "WebcastChatMessage",
            "parsed": {
                "user": {"id": "1", "nickname": "alpha", "followInfo": {"followStatus": 2}},
                "content": "hello",
            },
        })
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [{"user": audience_user, "score": 1}]}},
        })

        audience = store.snapshot()["audience"][0]
        self.assertEqual(audience["anchorFollowStatus"], 2)
        self.assertEqual(audience["anchorRelation"], "互关")
        self.assertTrue(audience["hasAnchorRelation"])
        self.assertEqual(audience["anchorRelationSource"], "interaction")

    def test_audience_rank_list_replaces_visible_audience(self):
        store = EventStore()
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [
                {"user": {"id": "1", "nickname": "alpha"}, "score": 100},
                {"user": {"id": "2", "nickname": "beta"}, "score": 50},
            ], "total": 2}},
        })
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [
                {"user": {"id": "3", "nickname": "gamma"}, "score": 80},
            ], "total": 1}},
        })

        snapshot = store.snapshot()
        self.assertEqual([item["nickname"] for item in snapshot["audience"]], ["gamma"])
        self.assertEqual(snapshot["stats"]["online"], 1)

    def test_audience_rank_http_refresh_keeps_cached_score(self):
        store = EventStore()
        store.apply({
            "method": "WebcastRoomRankMessage",
            "parsed": {"data": {"audienceRanks": [
                {"user": {"id": "1", "nickname": "alpha"}, "score": 100},
            ]}},
        })
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [
                {"user": {"id": "2", "nickname": "beta"}, "score": 1},
            ], "total": 1}},
        })
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [
                {"user": {"id": "1", "nickname": "alpha"}, "score": 1},
            ], "total": 1}},
        })

        snapshot = store.snapshot()
        self.assertEqual(snapshot["audience"][0]["contribution"], 100)
        self.assertTrue(snapshot["audience"][0]["hasContribution"])
        self.assertEqual(snapshot["audience"][0]["nickname"], "alpha")

    def test_rank_push_updates_existing_badges_and_score_revision(self):
        store = EventStore()
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [
                {"user": {"id": "1", "nickname": "alpha"}, "score": 1},
            ]}},
        })
        store.apply({
            "method": "WebcastRoomRankMessage",
            "parsed": {"data": {"audienceRanks": [
                {"user": {"id": "1", "nickname": "alpha", "badgeList": [
                    {"urlList": ["https://example.test/new_user_grade_level_v1_12.png"], "imageType": 1},
                ]}, "score": 120},
            ]}},
        })

        snapshot = store.snapshot()
        audience = snapshot["audience"][0]
        self.assertEqual(audience["contribution"], 120)
        self.assertTrue(audience["hasContribution"])
        self.assertIn("consumer", {badge["type"] for badge in audience["badges"]})
        self.assertGreater(snapshot["audienceStatus"]["revision"], 1)

    def test_higher_interaction_badge_replaces_list_badge_and_survives_refresh(self):
        store = EventStore()
        def user(level):
            return {
                "id": "1",
                "nickname": "alpha",
                "fansClub": {"data": {"level": level, "badge": {"icons": {
                    "4": {"urlList": [f"https://example.test/fansclub_new_advanced_badge_{level}_xmp.png"], "imageType": 51},
                }}}},
            }

        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [{"user": user(11), "score": 1}]}},
        })
        store.apply({
            "method": "WebcastRoomRankMessage",
            "parsed": {"audienceRanks": [{"user": user(12), "score": 12}]},
        })
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [{"user": {"id": "1", "nickname": "alpha"}, "score": 1}]}},
        })

        badge = next(badge for badge in store.snapshot()["audience"][0]["badges"] if badge["type"] == "fans")
        self.assertEqual(badge["level"], 12)
        self.assertIn("_12_xmp", badge["icon"])

    def test_room_rank_prefers_audience_ranks_score_over_generic_ranks(self):
        store = EventStore()
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [
                {"user": {"id": "1", "nickname": "alpha"}, "score": 1},
            ]}},
        })
        store.apply({
            "method": "WebcastRoomRankMessage",
            "parsed": {"ranks": [
                {"user": {"id": "1", "nickname": "alpha"}, "score": 5},
            ], "audienceRanks": [
                {"user": {"id": "1", "nickname": "alpha"}, "score": 120},
            ]},
        })

        self.assertEqual(store.snapshot()["audience"][0]["contribution"], 120)

    def test_audience_refresh_preserves_guard_club_name_from_rank_push(self):
        store = EventStore()
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [{"user": {"id": "1", "nickname": "alpha", "fansClub": {"data": {}}}, "score": 1}]}},
        })
        guard_user = {
            "id": "1",
            "nickname": "alpha",
            "fansClub": {"data": {"clubName": "club-name", "level": 17, "badge": {"icons": {
                "4": {"urlList": ["https://example.test/star_guard_advanced_badge_17_xmp.png"], "imageType": 51},
            }}}},
        }
        store.apply({
            "method": "WebcastRoomRankMessage",
            "parsed": {"audienceRanks": [{"user": guard_user, "score": 100}]},
        })
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [{"user": {"id": "1", "nickname": "alpha", "fansClub": {"data": {}}}, "score": 1}]}},
        })

        audience = store.snapshot()["audience"][0]
        self.assertEqual(audience["fansClub"]["name"], "club-name")
        self.assertEqual(next(badge for badge in audience["badges"] if badge["type"] == "guard")["clubName"], "club-name")

    def test_room_config_reset_clears_live_snapshot(self):
        store = EventStore()
        store.apply({
            "method": "WebcastChatMessage",
            "parsed": {"user": {"id": "1", "nickname": "alpha"}, "content": "hello"},
        })
        store.apply({
            "method": "WebcastAudienceRankList",
            "parsed": {"data": {"ranks": [{"user": {"id": "1", "nickname": "alpha"}, "score": 1}]}},
        })
        store.reset_live_data({"roomId": "2", "roomUrl": ""})

        snapshot = store.snapshot()
        self.assertEqual(snapshot["room"]["id"], "2")
        self.assertEqual(snapshot["room"]["anchor"]["nickname"], "未连接主播")
        self.assertFalse(snapshot["interactions"])
        self.assertFalse(snapshot["audience"])
        self.assertEqual(snapshot["stats"], {"online": 0, "likes": 0, "giftValue": 0})


class ActivityAndStatusTests(unittest.TestCase):
    def test_activity_records_are_not_truncated_during_a_session(self):
        store = EventStore()
        for index in range(81):
            store.apply({
                "method": "WebcastPreviewCjRpMessage",
                "msgId": f"red-{index}",
                "parsed": {"info": {"rpId": f"red-{index}", "title": "red"}},
            })

        self.assertEqual(len(store.snapshot()["records"]["redPackets"]), 81)

    def test_lucky_box_and_red_packet_are_saved_as_activity_records(self):
        store = EventStore()
        store.apply({
            "method": "WebcastLuckyBoxEndMessage",
            "parsed": {"luckyBoxIdStr": "bag-1"},
        })
        store.apply({
            "method": "WebcastPreviewCjRpMessage",
            "parsed": {"info": {"rpId": "red-1", "title": "测试红包", "totalCount": 3, "currency": "抖币"}},
        })

        snapshot = store.snapshot()
        self.assertEqual(snapshot["records"]["luckyBags"][0]["content"], "福袋开奖")
        self.assertEqual(snapshot["records"]["luckyBags"][0]["prize"]["luckyBoxId"], "bag-1")
        self.assertEqual(snapshot["records"]["redPackets"][0]["prize"]["redPacketId"], "red-1")

    def test_room_info_with_explicit_not_live_state_marks_room_not_live(self):
        store = EventStore()
        store.apply({
            "method": "LiveMngRoomInfo",
            "parsed": {"roomId": "1", "roomExists": True, "isLive": False, "title": "offline"},
        })
        self.assertEqual(store.snapshot()["status"]["roomState"], "not_live")

    def test_room_info_marks_missing_room_without_being_overwritten(self):
        store = EventStore()
        store.apply({
            "method": "LiveMngRoomInfo",
            "parsed": {"roomId": "1", "roomExists": False, "statusCode": 404},
        })
        self.assertEqual(store.snapshot()["status"]["roomState"], "not_found")
        self.assertEqual(store.snapshot()["status"]["state"], "error")


if __name__ == "__main__":
    unittest.main()
