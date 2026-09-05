import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speech_model_manager import SpeechModelManager


class SpeechModelManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = SpeechModelManager(lambda: {"speech": {"modelRoot": "models"}}, self.root)

    async def asyncTearDown(self):
        await self.manager.close()
        self.temp.cleanup()

    async def test_catalog_exposes_install_and_download_state(self):
        catalog = await asyncio.to_thread(self.manager.catalog)
        self.assertEqual({item["type"] for item in catalog}, {"asr_streaming", "asr_offline", "tts", "translation"})
        self.assertTrue(all("installed" in item and "download" in item for item in catalog))
        self.assertEqual(catalog[-1]["download"]["state"], "not_downloaded")

    async def test_unknown_model_is_rejected(self):
        with self.assertRaises(ValueError):
            self.manager.start("missing-model")

    async def test_start_returns_the_requested_job(self):
        with self.manager.lock:
            self.manager.jobs["translation-hy-mt-1.8b-q4"] = {
                "modelId": "translation-hy-mt-1.8b-q4", "state": "queued", "progress": 0,
                "downloaded": 0, "total": 0, "error": "", "updatedAt": 0,
            }
        with patch.object(self.manager, "_download"):
            result = self.manager.start("asr-streaming-zipformer-zh-en")
        self.assertEqual(result["modelId"], "asr-streaming-zipformer-zh-en")
        await self.manager.close()


if __name__ == "__main__":
    unittest.main()
