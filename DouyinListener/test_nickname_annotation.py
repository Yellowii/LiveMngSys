import unittest

from nickname_annotation import annotate_nickname


class NicknameAnnotationTests(unittest.TestCase):
    def test_uses_phrase_context_and_keeps_polyphonic_alternatives(self):
        annotations = annotate_nickname("重庆小面")

        self.assertEqual(
            [item["annotation"] for item in annotations],
            ["chóng", "qìng", "xiǎo", "miàn"],
        )
        self.assertEqual(annotations[0]["alternatives"], ["zhòng", "tóng"])
        self.assertEqual(annotations[1]["alternatives"], [])

    def test_phrase_context_is_applied_to_each_contiguous_han_run(self):
        annotations = annotate_nickname("音乐 银行")
        han_annotations = [item for item in annotations if item["kind"] == "han"]

        self.assertEqual(
            [item["annotation"] for item in han_annotations],
            ["yīn", "yuè", "yín", "háng"],
        )
        self.assertIn("lè", han_annotations[1]["alternatives"])
        self.assertIn("xíng", han_annotations[3]["alternatives"])


if __name__ == "__main__":
    unittest.main()
