import copy
import os
import sys
import types
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
import test_v114 as t114  # noqa: E402
from bot import football as F, llm  # noqa: E402
from bot.telegram import Telegram  # noqa: E402


def fake_module(result):
    mod = types.ModuleType("googlenewsdecoder")
    mod.gnewsdecoder = lambda url, interval=1: result
    return mock.patch.dict(sys.modules, {"googlenewsdecoder": mod})


SCHEDULE = t114.TestEspnFallbackAndErrors.SCHEDULE


class TestDecodeSuccessKey(unittest.TestCase):
    GN = "https://news.google.com/rss/articles/x"

    def test_new_library_key_success(self):
        with fake_module({"success": True, "decoded_url": "https://www.bbc.com/a"}):
            self.assertEqual(llm.decode_gn(self.GN, log=lambda *a: None), "https://www.bbc.com/a")
            self.assertIn("bbc.com", llm.decode_check([self.GN]))

    def test_success_false_and_old_status_key(self):
        with fake_module({"success": False}):
            self.assertEqual(llm.decode_gn(self.GN, log=lambda *a: None), self.GN)
        with fake_module({"status": True, "decoded_url": "https://www.bbc.com/b"}):
            self.assertEqual(llm.decode_gn(self.GN, log=lambda *a: None), "https://www.bbc.com/b")


class TestEspnOrder(unittest.TestCase):
    def test_team_schedule_first_scoreboard_only_as_backup(self):
        seen = []

        def fake_get(url, headers=None, params=None):
            seen.append(url)
            return SCHEDULE
        with mock.patch.object(F, "_get", fake_get):
            self.assertEqual(len(F.espn_fixtures(["eng.1"], 0, 36500)), 1)
        self.assertFalse(any(u.endswith("/scoreboard") for u in seen))

    def test_empty_team_schedule_uses_scoreboard(self):
        def fake_get(url, headers=None, params=None):
            return SCHEDULE if url.endswith("/scoreboard") else {"events": []}
        with mock.patch.object(F, "_get", fake_get):
            self.assertEqual(len(F.espn_fixtures(["eng.1"], 0, 36500)), 1)


class TestNoDuplicates(unittest.TestCase):
    def test_same_link_is_not_sent_twice(self):
        pipe, tg = tp.build()
        pipe.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United midfielder Casemiro has agreed new terms.")])
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 1)
        orig = next(iter(pipe.st["stories"].values()))
        dup = copy.deepcopy(orig)
        dup.update(id="dup", status="pending", msg_id=None, sent_at=None, label=None, body=None,
                   first_seen=tp.CLOCK.t, title="Another title for same link")
        pipe.st["stories"]["dup"] = dup
        tp.CLOCK.adv(20 * 60)
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 1)
        self.assertEqual(dup["drop"], "duplikat")

    def test_checkpoint_after_each_send(self):
        pipe, tg = tp.build()
        calls = []
        pipe.checkpoint = lambda: calls.append(1)
        pipe.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United midfielder Casemiro has agreed new terms."),
                     tp.item("Mbeumo scores twice in derby", "Sky Sports", text="Manchester United Mbeumo scored twice.")])
        pipe.dispatch()
        self.assertEqual(len(calls), len(tg.sent))
        self.assertGreaterEqual(len(calls), 1)

    def test_send_read_timeout_is_not_retried_but_edit_is(self):
        calls = []

        def fake_post(url, json=None, timeout=None):
            calls.append(url)
            raise requests.ReadTimeout("slow")
        with mock.patch("requests.post", fake_post), mock.patch("bot.telegram.time.sleep"):
            tgc = Telegram("t", "42", log=lambda *a: None)
            self.assertEqual(tgc.send("halo"), 0)
            self.assertEqual(len(calls), 1)
            calls.clear()
            self.assertFalse(tgc.edit(5, "x"))
            self.assertEqual(len(calls), 3)

    def test_unknown_message_id_does_not_loop_edits(self):
        pipe, tg = tp.build()
        pipe.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United midfielder Casemiro has agreed new terms.")])
        pipe.dispatch()
        s = next(iter(pipe.st["stories"].values()))
        s.update(msg_id=0, needs_edit=True)
        pipe.refresh_edits()
        self.assertEqual(tg.edits, [])
        self.assertFalse(s["needs_edit"])


if __name__ == "__main__":
    unittest.main()
