import os
import sys
import unittest
from datetime import datetime
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_v112 as t112  # noqa: E402
from bot import football as F, llm, matchday, state as S, text as T  # noqa: E402
from bot.reminders import WIB  # noqa: E402

CFG = t112.CFG
SEP = T.BILINGUAL_SEP


class R:
    def __init__(self, code, body=None, text=""):
        self.status_code, self._b, self.text = code, body, text

    def json(self):
        return self._b


class TestUkTime(unittest.TestCase):
    KO = t112.utc(2026, 11, 22, 17, 30)

    def test_gmt_in_winter_bst_in_summer(self):
        self.assertEqual(F.fmt_uk(self.KO), "Min 22/11 17.30 GMT")
        self.assertEqual(F.fmt_uk(t112.utc(2027, 7, 10, 17, 30)), "Sab 10/07 18.30 BST")
        self.assertEqual(F.fmt_when(self.KO), "Sen 23/11 00.30 WIB")
        self.assertEqual(F.fmt_when(self.KO, True), "Sen 23/11 00.30 WIB (Min 22/11 17.30 GMT)")

    def test_date_can_differ_between_wib_and_uk(self):
        fx = F.parse_espn_events(t112.ESPN_SB, "eng.1")[0]
        fx["ts"] = t112.wib(2026, 11, 26, 3, 0)
        self.assertEqual(F.fmt_fixture_block(fx).splitlines()[:2], ["<b>Kam 26/11 · 03.00 WIB</b>", "Rab 25/11 · 20.00 GMT"])

    def test_reminders_show_gmt(self):
        fx = F.parse_espn_events(t112.ESPN_SB, "eng.1")
        ko = fx[0]["ts"]
        st, tg = S.new_state(), t112.RecTG()
        matchday.run(tg, st, CFG, ko - 86400 + 60, fixtures_fn=lambda d: ("ESPN", [dict(f) for f in fx]),
                     lineup_fn=lambda f, allow_apif=True: (_ for _ in ()).throw(RuntimeError("belum")), log=lambda *a: None)
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("(Min 22/11 17.30 GMT)", tg.sent[0])


class TestEspnFixtures(unittest.TestCase):
    def test_empty_scoreboard_falls_back_to_team_schedule_and_sends_limit(self):
        seen = []

        def fake_get(url, headers=None, params=None):
            seen.append((url, params))
            return {"events": []} if url.endswith("/scoreboard") else t112_schedule()
        with mock.patch.object(F, "_get", fake_get):
            fx = F.espn_fixtures(["eng.1"], 0, 36500)
        self.assertEqual(len(fx), 1)
        self.assertEqual(seen[0][1]["limit"], 1000)
        self.assertTrue(any(u.endswith("/schedule") for u, _ in seen))

    def test_both_empty_returns_empty_without_error(self):
        with mock.patch.object(F, "_get", return_value={"events": []}):
            self.assertEqual(F.espn_fixtures(["eng.1"], 0, 30), [])

    def test_fixture_key_same_for_all_providers(self):
        e = F.parse_espn_events(t112.ESPN_SB, "eng.1")[0]
        a = F.parse_apif_fixtures(t112.APIF_FX)[0]
        d = F.parse_fd_matches(t112.FD_M)[0]
        self.assertEqual(F.fixture_key(e), F.fixture_key(a))
        self.assertEqual(F.fixture_key(e), F.fixture_key(d))
        ucl = lambda comp, h: {"comp": comp, "home": h, "away": "Sporting CP"}
        self.assertEqual(F.fixture_key(ucl("Liga Champions", "Manchester United")),
                         F.fixture_key(ucl("UEFA Champions League", "Manchester United FC")))

    def test_old_format_sent_keys_do_not_resend(self):
        fx = F.parse_espn_events(t112.ESPN_SB, "eng.1")
        ko = fx[0]["ts"]
        now = ko - 86400 + 60
        day = datetime.fromtimestamp(ko, WIB).strftime("%Y%m%d")
        st, tg = S.new_state(), t112.RecTG()
        st["matchday"] = {"fixtures": [], "sent": {f"h1|Premier League|Manchester United|Arsenal|{day}": now - 10}}
        matchday.run(tg, st, CFG, now, fixtures_fn=lambda d: ("ESPN", [dict(f) for f in fx]),
                     lineup_fn=lambda f, allow_apif=True: (_ for _ in ()).throw(RuntimeError("belum")), log=lambda *a: None)
        self.assertEqual(tg.sent, [])


def t112_schedule():
    import test_v114 as t114
    return t114.TestEspnFallbackAndErrors.SCHEDULE


class TestStandingsNames(unittest.TestCase):
    def test_names_are_clear_not_cut(self):
        names = ["Arsenal", "Brighton & Hove Albion", "Wolverhampton Wanderers", "AFC Bournemouth", "Manchester United FC",
                 "Tottenham Hotspur", "Nottingham Forest"]
        rows = [{"pos": i + 1, "team": n, "p": 10, "w": 5, "d": 3, "l": 2, "pts": 18, "group": ""} for i, n in enumerate(names)]
        out = F.fmt_standings("Premier League", rows, "ESPN")
        self.assertNotIn("Albi ", out)
        self.assertIn(" Brighton ", out)
        self.assertIn(" Wolves ", out)
        self.assertIn(" Bournemouth ", out)
        self.assertNotIn("AFC", out)
        self.assertIn("Manchester United", out)
        self.assertIn("Tottenham Hotspur", out)
        self.assertIn("Nottingham Forest", out)
        self.assertEqual(F._table_name("Borussia Mönchengladbach")[-1], ".")


class TestHighlightlyDisplayName(unittest.TestCase):
    ST = [{"team": {"name": "Arsenal"}, "statistics": [{"displayName": "Ball possession", "value": "55%"}, {"displayName": "Total shots", "value": 14},
                                                      {"displayName": "Shots on target", "value": 6}, {"displayName": "Corners", "value": 7}]},
          {"team": {"name": "Manchester United"}, "statistics": [{"displayName": "Ball possession", "value": "45%"}, {"displayName": "Total shots", "value": 9},
                                                                 {"displayName": "Shots on target", "value": 3}, {"displayName": "Corners", "value": 4}]}]

    def test_display_name_is_parsed(self):
        rows = {r[0]: r[1:] for r in F.parse_hl_stats(self.ST)["rows"]}
        self.assertEqual(rows["Penguasaan bola"], ("45%", "55%"))
        self.assertEqual((rows["Tembakan"], rows["Tepat sasaran"], rows["Sepak pojok"]), (("9", "14"), ("3", "6"), ("4", "7")))

    def test_shape_shows_stat_keys(self):
        self.assertEqual(F._shape(self.ST), "list[2]: team,statistics | stat: displayName,value")
        self.assertEqual(F._shape({"foo": 1}), "dict: foo")


class TestModelSkipping(unittest.TestCase):
    def setUp(self):
        llm._SKIP.clear()
        llm._STRIKES.clear()

    tearDown = setUp

    def test_groq_404_model_skipped_after_first_try(self):
        calls = []
        ok = {"choices": [{"message": {"content": "Casemiro sepakat kontrak baru dengan Manchester United hingga 2028."}}]}

        def fake_post(url, headers, payload, read=30):
            calls.append(payload["model"])
            return R(404, text="model not found") if payload["model"] == "a" else R(200, ok)
        with mock.patch.object(llm, "_post", fake_post):
            self.assertIsNotNone(llm.call_groq(["a", "b"], "k", "p", lambda *x: None))
            self.assertIsNotNone(llm.call_groq(["a", "b"], "k", "p", lambda *x: None))
        self.assertEqual(calls, ["a", "b", "b"])

    def test_gemini_429_tries_next_model_and_skips_first_afterwards(self):
        calls = []
        ok = {"candidates": [{"content": {"parts": [{"text": f"Casemiro sepakat kontrak baru dengan klub.\n{SEP}\nCasemiro agrees a new contract with the club."}]}}]}

        def fake_post(url, headers, payload, read=30):
            m = url.split("/models/")[1].split(":")[0]
            calls.append(m)
            return R(429, text="quota") if m == "a" else R(200, ok)
        with mock.patch.object(llm, "_post", fake_post):
            self.assertIn(SEP, llm.call_gemini(["a", "b"], "k", "p", lambda *x: None))
            self.assertIn(SEP, llm.call_gemini(["a", "b"], "k", "p", lambda *x: None))
        self.assertEqual(calls, ["a", "b", "b"])

    def test_gemini_timeout_twice_benches_model(self):
        calls = []
        ok = {"candidates": [{"content": {"parts": [{"text": f"Casemiro sepakat kontrak baru dengan klub.\n{SEP}\nCasemiro agrees a new contract with the club."}]}}]}

        def fake_post(url, headers, payload, read=30):
            m = url.split("/models/")[1].split(":")[0]
            calls.append(m)
            if m == "a":
                raise requests.exceptions.ReadTimeout("slow")
            return R(200, ok)
        with mock.patch.object(llm, "_post", fake_post):
            for _ in range(3):
                llm.call_gemini(["a", "b"], "k", "p", lambda *x: None)
        self.assertEqual(calls, ["a", "b", "a", "b", "b"])

    def test_settings_drop_dead_groq_model(self):
        self.assertEqual(CFG["llm"]["groq_models"][0], "openai/gpt-oss-120b")
        self.assertNotIn("llama-3.3-70b-versatile", CFG["llm"]["groq_models"])


if __name__ == "__main__":
    unittest.main()
