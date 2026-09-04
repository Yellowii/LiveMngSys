import tempfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from gift_assets import GiftAssetCatalog


def gift_payload(icon_url="https://example.invalid/heart.png"):
    return {
        "status_code": 0,
        "data": {
            "pages": [{"gifts": [{
                "id": "463", "name": "heart", "diamond_count": 1,
                "primary_effect_id": "10", "asset_ids": ["10"],
                "icon": {"url_list": [icon_url]},
            }]}]
        },
    }


def effects_payload(md5="first"):
    return {
        "status_code": 0,
        "data": {"assets": [{
            "id": "10", "name": "heart effect", "resource_type": 1, "md5": md5,
            "resource_url": {"url_list": ["https://example.invalid/heart.zip"]},
        }]},
    }


class GiftAssetCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.catalog = GiftAssetCatalog(Path(self.temp_dir.name))

    async def asyncTearDown(self):
        await self.catalog.stop()
        self.temp_dir.cleanup()

    async def test_catalog_snapshot_diff_tracks_new_and_changed_assets(self):
        first = await self.catalog.ingest_snapshot(gift_payload(), effects_payload(), download=False)
        repeated = await self.catalog.ingest_snapshot(gift_payload(), effects_payload(), download=False)
        changed = await self.catalog.ingest_snapshot(gift_payload("https://example.invalid/heart-v2.png"), effects_payload("second"), download=False)

        self.assertEqual((first["newGifts"], first["newEffects"]), (1, 1))
        self.assertEqual((repeated["newGifts"], repeated["changedGifts"], repeated["newEffects"], repeated["changedEffects"]), (0, 0, 0, 0))
        self.assertEqual((changed["changedGifts"], changed["changedEffects"]), (1, 1))
        self.assertEqual(len(changed["giftResources"]), 1)
        self.assertEqual(len(changed["effectResources"]), 1)
        self.assertTrue((self.catalog.root / changed["giftSnapshot"]).exists())
        self.assertTrue((self.catalog.root / changed["effectSnapshot"]).exists())

    async def test_sync_waits_for_room_metadata_without_recording_a_failed_run(self):
        result = await self.catalog.sync()

        self.assertEqual(result, {"skipped": "room_metadata"})
        self.assertEqual(self.catalog.public_state()["state"], "waiting")
        self.assertEqual(self.catalog.public_state()["lastAttemptAt"], 0)

    async def test_incomplete_run_is_marked_for_resume_on_startup(self):
        self.catalog._start_run(123)
        self.catalog._load_status()

        self.assertEqual(self.catalog.public_state()["state"], "waiting")
        self.assertEqual(self.catalog.public_state()["lastAttemptAt"], 0)

    async def test_recent_runs_exposes_latest_catalog_run_summary(self):
        run_id = self.catalog._start_run(123)
        self.catalog._finish_run(run_id, "success", {"newGifts": 2, "downloaded": {"icons": 3}}, "")

        runs = self.catalog.recent_runs()

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["newGifts"], 2)
        self.assertEqual(runs[0]["downloadedIcons"], 3)

    def test_parse_gifts_supports_current_top_level_gifts_list(self):
        parsed = self.catalog._parse_gifts({"data": {"gifts": gift_payload()["data"]["pages"][0]["gifts"]}})

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["id"], "463")
        self.assertEqual(parsed[0]["iconUrls"], ["https://example.invalid/heart.png"])

    async def test_catalog_listing_and_effect_preview_use_cached_records(self):
        await self.catalog.ingest_snapshot(gift_payload(), effects_payload(), download=False)
        effect_path = self.catalog.effects_dir / "10_standard.zip"
        with zipfile.ZipFile(effect_path, "w") as archive:
            archive.writestr("config.json", '{"portrait":{"w":720,"h":1280}}')
            archive.writestr("output.mp4", b"preview")
        with self.catalog._db() as db:
            db.execute("INSERT INTO asset_cache (asset_kind,source_id,role,url,local_path,first_seen_at,last_seen_at,downloaded_at,status,last_error) VALUES (?,?,?,?,?,?,?,?,?,?)", ("effect", "10", "standard", "https://example.invalid/heart.zip", "cache/effects/10_standard.zip", 1, 1, 1, "ready", ""))

        catalog = self.catalog.list_gifts()
        preview = self.catalog.effect_preview_path("10")

        self.assertEqual(catalog["total"], 1)
        self.assertEqual(catalog["items"][0]["effect"]["id"], "10")
        self.assertTrue(catalog["items"][0]["effect"]["cached"])
        self.assertTrue(catalog["items"][0]["effect"]["previewable"])
        self.assertIsNotNone(preview)
        self.assertEqual(preview[0].read_bytes(), b"preview")
        self.assertEqual(preview[1]["portrait"]["h"], 1280)

    async def test_effect_preview_uses_alternate_package_when_standard_has_no_video(self):
        await self.catalog.ingest_snapshot(gift_payload(), effects_payload(), download=False)
        standard_path = self.catalog.effects_dir / "10_standard.zip"
        alternate_path = self.catalog.effects_dir / "10_format265.zip"
        with zipfile.ZipFile(standard_path, "w") as archive:
            archive.writestr("config.json", "{}")
        with zipfile.ZipFile(alternate_path, "w") as archive:
            archive.writestr("output.mp4", b"alternate-preview")
        with self.catalog._db() as db:
            for role, filename in (("standard", "10_standard.zip"), ("format265", "10_format265.zip")):
                db.execute("INSERT INTO asset_cache (asset_kind,source_id,role,url,local_path,first_seen_at,last_seen_at,downloaded_at,status,last_error) VALUES (?,?,?,?,?,?,?,?,?,?)", ("effect", "10", role, "https://example.invalid/heart.zip", f"cache/effects/{filename}", 1, 1, 1, "ready", ""))

        catalog = self.catalog.list_gifts()
        preview = self.catalog.effect_preview_path("10")

        self.assertTrue(catalog["items"][0]["effect"]["previewable"])
        self.assertIsNotNone(preview)
        self.assertEqual(preview[0].read_bytes(), b"alternate-preview")


if __name__ == "__main__":
    unittest.main()
