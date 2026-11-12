import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
from bot import llm, text as T  # noqa: E402

CFG = tp.CFG
ARTICLE = ("Manchester United have agreed terms with the player, according to David Ornstein. " * 12)


class TestGoogleNewsDecode(unittest.TestCase):
    def test_decode_passthrough_and_failure_fallback(self):
        self.assertEqual(llm.decode_gn("https://bbc.com/a"), "https://bbc.com/a")
        gn = "https://news.google.com/rss/articles/CBMiabc"
        self.assertEqual(llm.decode_gn(gn, log=lambda *a: None), gn)  # pustaka tidak ada atau gagal

    def test_decoded_url_gives_article_text_and_journalist(self):
        gn = "https://news.google.com/rss/articles/CBMiabc"
        story = {"title": "Deal agreed", "text": "Deal agreed", "content": "", "journalists": [],
                 "sources": [{"name": "Daily Mail", "tier": 2, "url": gn}], "verify": False}
        summ = llm.make_summarizer(CFG, {"GEMINI_API_KEY": "x"}, log=lambda *a: None)
        seen = {}
        with mock.patch.object(llm, "decode_gn", return_value="https://www.dailymail.co.uk/real"), \
                mock.patch.object(llm, "fetch_article", return_value=(ARTICLE, None)) as fa, \
                mock.patch.object(llm, "call_gemini", side_effect=lambda m, k, prompt, log, finish=None: seen.setdefault("p", prompt) and "Manchester United sepakat dengan pemain itu, kata Ornstein."):
            out = summ(story)
        self.assertIn("Ornstein", out)
        self.assertEqual(story["sources"][0]["url"], "https://www.dailymail.co.uk/real")
        self.assertEqual(story["journalists"], ["David Ornstein"])
        fa.assert_called_with("https://www.dailymail.co.uk/real", CFG["summary"]["max_article_chars"])

    def test_decode_budget_per_cycle(self):
        summ = llm.make_summarizer(CFG, {"GEMINI_API_KEY": "x"}, log=lambda *a: None)
        calls = []
        def fake_decode(u, log=print):
            calls.append(u)
            return u
        with mock.patch.object(llm, "decode_gn", fake_decode), mock.patch.object(llm, "fetch_article", return_value=("", None)), \
                mock.patch.object(llm, "call_gemini", return_value="Ringkasan berita Manchester United yang cukup panjang."):
            for i in range(12):
                summ({"title": "t", "text": "t", "content": "", "journalists": [], "verify": False,
                      "sources": [{"name": "x", "tier": 2, "url": f"https://news.google.com/rss/articles/{i}"}]})
        self.assertEqual(len(calls), 8)

    def test_new_journalists_detected(self):
        jr = T.build_journalist_re(CFG)
        txt = "Per James Ducker and Ducker's colleague Sam Wallace; Indy Kaila and Andy Mitten also reported."
        self.assertEqual(T.find_journalists(txt, jr), ["James Ducker", "Sam Wallace", "Indy Kaila", "Andy Mitten"])
        self.assertGreaterEqual(len(CFG["people"]["trusted_journalists"]), 34)


if __name__ == "__main__":
    unittest.main()
