import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
import test_v118 as t118  # noqa: E402
from bot import draft as D, llm, text as T  # noqa: E402

SEP = T.BILINGUAL_SEP


class R:
    def __init__(self, code, text=""):
        self.status_code, self.text = code, text


class TestBodyLimits(unittest.TestCase):
    def test_clip_sentences_and_characters(self):
        t = "Satu kalimat. Dua kalimat. Tiga kalimat. Empat kalimat. Lima kalimat. Enam kalimat."
        self.assertEqual(D.clip(t, 1024, 5), "Satu kalimat. Dua kalimat. Tiga kalimat. Empat kalimat. Lima kalimat.")
        self.assertEqual(D.clip(t, 30, 5), "Satu kalimat. Dua kalimat.")
        self.assertEqual(D.clip("Harga £52.5m, kata Dr. smith. Selesai.", 1024, 1), "Harga £52.5m, kata Dr. smith.")
        self.assertEqual(D.clip('Ia berkata "selesai." Lalu pergi. Ketiga.', 1024, 2), 'Ia berkata "selesai." Lalu pergi.')
        self.assertLessEqual(len(D.clip("Kata " * 400 + "akhir.", 1024, 5)), 1024)

    def test_story_body_is_cut_at_five_sentences_and_1024_chars(self):
        out = t118.run(t118.story(), t118.fake_ai(t118.draft(isi_en="Kalimat. " * 80, isi_id="Kalimat. " * 80)))
        idn, en = T.split_bilingual(out)
        for part in (idn, en):
            body = part.split("\n\n", 1)[1]
            self.assertEqual(body.count("Kalimat."), 5)
            self.assertLessEqual(len(body), 1024)

    def test_prompt_asks_for_curious_non_question_headline_and_five_sentences(self):
        ai = t118.fake_ai(t118.draft())
        t118.run(t118.story(), ai)
        p = ai.calls[0][2]
        self.assertIn("maksimal 5 kalimat dan 1024 karakter per bahasa", p)
        self.assertIn("penasaran", p)
        self.assertIn("Dilarang: kalimat tanya", p)
        self.assertIn("Jangan menyesatkan", p)


class TestDivider(unittest.TestCase):
    def test_divider_is_its_own_block(self):
        lines = T.format_message("BERITA", "Isi.", ["BBC"], "English.").split("\n")
        i = lines.index(T.DIVIDER)
        self.assertEqual((lines[i - 1], lines[i + 1], lines[i + 2]), ("", "", "English."))

    def test_divider_kept_when_message_is_edited(self):
        pipe, tg = tp.build()
        pipe.summarize = lambda s: f"Judul.\n\nIsi.\n{SEP}\nTitle.\n\nBody."
        pipe.ingest([tp.item("Casemiro agrees new Manchester United contract", "BBC Sport",
                             text="Manchester United midfielder Casemiro has agreed a new contract at Old Trafford.")])
        pipe.dispatch()
        self.assertIn(T.DIVIDER, tg.sent[0][1])
        tp.CLOCK.adv(300)
        pipe.ingest([tp.item("Casemiro extends Manchester United contract", "ESPN", pub=tp.CLOCK.t - 30,
                             text="Manchester United midfielder Casemiro has extended his contract.")])
        pipe.dispatch()
        pipe.refresh_edits()
        self.assertEqual(len(tg.edits), 1)
        self.assertIn(T.DIVIDER, tg.edits[0][1])


class TestGoneModel(unittest.TestCase):
    def setUp(self):
        llm._SKIP.clear()
        llm._STRIKES.clear()
        llm.BLOCKS = {}

    def tearDown(self):
        llm.BLOCKS = None

    def test_http_410_is_skipped_for_a_day_like_404(self):
        calls = []

        def fake(url, headers, payload, read=30):
            calls.append(payload["model"])
            return R(410, '{"detail": "model gone"}')
        with mock.patch.object(llm, "_post", fake):
            llm.call_openai_compat("https://x", ["m1", "m2"], "k", "p", lambda *a: None, tag="nvidia")
            llm.call_openai_compat("https://x", ["m1", "m2"], "k", "p", lambda *a: None, tag="nvidia")
        self.assertEqual(calls, ["m1", "m2"])
        self.assertIn("nvidia:m1", llm.BLOCKS)


if __name__ == "__main__":
    unittest.main()
