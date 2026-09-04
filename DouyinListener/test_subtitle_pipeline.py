import asyncio
import unittest

from subtitle_pipeline import SubtitlePipeline


class FakeSpeech:
    def __init__(self, result="Hello"):
        self.calls = []
        self.result = result

    def translate(self, text, source, target):
        self.calls.append((text, source, target))
        if isinstance(self.result, Exception):
            raise self.result
        return {"text": self.result}


def config(translation=True):
    return {
        "speech": {
            "cleaning": {"enabled": True, "minCharacters": 3, "fillerWords": ["嗯", "啊", "呃"]},
            "translation": {"enabled": translation, "sourceLanguage": "zh", "targetLanguage": "en"},
        }
    }


class SubtitleCleaningTests(unittest.TestCase):
    def test_removes_spacing_and_edge_fillers(self):
        cleaned = SubtitlePipeline.clean_final(" 嗯， 大家 好 啊。\n", config()["speech"]["cleaning"])
        self.assertEqual(cleaned, "大家好")

    def test_discards_short_fragment(self):
        self.assertEqual(SubtitlePipeline.clean_final("你好", config()["speech"]["cleaning"]), "")

    def test_keeps_single_spaces_between_latin_words(self):
        cleaned = SubtitlePipeline.clean_final("TODAY   IS  LIVE", config()["speech"]["cleaning"])
        self.assertEqual(cleaned, "TODAY IS LIVE")


class SubtitlePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_never_translates(self):
        speech = FakeSpeech()
        pipeline = SubtitlePipeline(lambda: config(), speech)
        await pipeline._consume({"revision": 1, "finalRevision": 0, "state": "running", "partial": "大家"})
        self.assertEqual(pipeline.state["partial"], "大家")
        self.assertEqual(speech.calls, [])

    async def test_final_translates_once(self):
        speech = FakeSpeech("Hello everyone")
        pipeline = SubtitlePipeline(lambda: config(), speech)
        state = {"revision": 2, "finalRevision": 1, "state": "running", "final": "嗯，大家好"}
        await pipeline._consume(state)
        await pipeline._consume(state)
        await asyncio.gather(*pipeline.translation_tasks)
        self.assertEqual(speech.calls, [("大家好", "zh", "en")])
        self.assertEqual(pipeline.state["translation"], "Hello everyone")
        self.assertEqual(len(pipeline.history), 1)

    async def test_translation_failure_keeps_asr_text(self):
        speech = FakeSpeech(RuntimeError("server offline"))
        pipeline = SubtitlePipeline(lambda: config(), speech)
        await pipeline._consume({"revision": 3, "finalRevision": 1, "state": "running", "final": "今天开播了"})
        await asyncio.gather(*pipeline.translation_tasks)
        self.assertEqual(pipeline.state["final"], "今天开播了")
        self.assertEqual(pipeline.state["cleaned"], "今天开播了")
        self.assertEqual(pipeline.state["translation"], "")
        self.assertIn("server offline", pipeline.state["translationError"])


if __name__ == "__main__":
    unittest.main()
