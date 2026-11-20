import os
import sys
import types
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_v112 as t112  # noqa: E402
from bot import commands as C, football as F, llm, state as S, text as T  # noqa: E402

CFG = t112.CFG
SEP = T.BILINGUAL_SEP


class R:
    def __init__(self, code, body=None, text=""):
        self.status_code, self._b, self.text = code, body, text

    def json(self):
        return self._b


def fake_module(result):
    mod = types.ModuleType("googlenewsdecoder")
    mod.gnewsdecoder = lambda url, interval=1: result
    return mock.patch.dict(sys.modules, {"googlenewsdecoder": mod})


class TestDecodeDiagnostics(unittest.TestCase):
    def test_failure_log_shows_raw_result(self):
        logs = []
        with fake_module({"status": False, "message": ""}):
            out = llm.decode_gn("https://news.google.com/rss/articles/x", log=logs.append)
        self.assertEqual(out, "https://news.google.com/rss/articles/x")
        self.assertIn("'status': False", logs[0])

    def test_decode_check_reports_raw_result_or_success(self):
        self.assertIn("tidak ada tautan", llm.decode_check([]))
        with fake_module({"status": False, "message": ""}):
            with self.assertRaises(RuntimeError) as cm:
                llm.decode_check(["https://news.google.com/rss/articles/x"])
        self.assertIn("'status': False", str(cm.exception))
        with fake_module({"status": True, "decoded_url": "https://www.bbc.com/a"}):
            self.assertIn("bbc.com", llm.decode_check(["https://news.google.com/rss/articles/x"]))

    def test_diagnosa_has_google_news_line(self):
        st = S.new_state()
        st["stories"]["a"] = {"first_seen": 1, "sources": [{"name": "x", "url": "https://news.google.com/rss/articles/x"}]}
        with mock.patch.object(F, "diagnose", return_value=["OK  ESPN jadwal: ok"]), \
                fake_module({"status": False, "message": ""}):
            out = C.reply_for("/diagnosa", [], st, CFG, 1_800_000_000)
        self.assertIn("GAGAL  Google News decode: RuntimeError hasil mentah", out)
        with mock.patch.object(F, "diagnose", return_value=["OK  ESPN jadwal: ok"]):
            out = C.reply_for("/diagnosa", [], S.new_state(), CFG, 1_800_000_000)
        self.assertIn("OK  Google News decode: tidak ada tautan", out)


class TestServerBusy(unittest.TestCase):
    def setUp(self):
        llm._SKIP.clear()
        llm._STRIKES.clear()

    tearDown = setUp

    def test_gemini_503_twice_benches_model(self):
        calls = []
        ok = {"candidates": [{"content": {"parts": [{"text": f"Casemiro sepakat kontrak baru dengan klub.\n{SEP}\nCasemiro agrees a new contract with the club."}]}}]}

        def fake_post(url, headers, payload, read=30):
            m = url.split("/models/")[1].split(":")[0]
            calls.append(m)
            return R(503, text="high demand") if m == "a" else R(200, ok)
        with mock.patch.object(llm, "_post", fake_post):
            for _ in range(3):
                llm.call_gemini(["a", "b"], "k", "p", lambda *x: None)
        self.assertEqual(calls, ["a", "b", "a", "b", "b"])


if __name__ == "__main__":
    unittest.main()
