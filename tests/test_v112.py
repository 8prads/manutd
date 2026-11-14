import os
import sys
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
from bot import commands as C, digest, football as F, llm, matchday, state as S, text as T  # noqa: E402
from bot.models import STALE  # noqa: E402
from bot.reminders import WIB  # noqa: E402

CFG = tp.CFG
SEP = T.BILINGUAL_SEP


class RecTG:
    def __init__(self):
        self.sent = []

    def send(self, text, reply_to=None):
        self.sent.append(text)
        return len(self.sent)


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc).timestamp()


def wib(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=WIB).timestamp()


class TestBilingualFormat(unittest.TestCase):
    def test_message_layout(self):
        msg = T.format_message("BERITA", "Isi Indonesia.", ["Sky Sports", "Fabrizio Romano"], "English text.", "https://x.com/a?b=1&c=2")
        self.assertEqual(msg, "<b>[BERITA]</b>\n\nIsi Indonesia.\n──────────\nEnglish text.\n\nSelengkapnya:\nhttps://x.com/a?b=1&amp;c=2"
                              "\n\n<i>(Sky Sports, Fabrizio Romano)</i>")

    def test_finish_parses_both_languages_and_rejects_meta(self):
        ok = llm._finish(f"Manchester United berniat memberhentikan Carrick. Belum ada keputusan final.\n{SEP}\nUnited intend to sack Carrick. No final decision yet.")
        self.assertEqual(T.split_bilingual(ok)[1], "United intend to sack Carrick. No final decision yet.")
        self.assertIsNone(llm._finish(f"Manchester United berniat memberhentikan Carrick sekarang juga.\n{SEP}\nThe article contains only a question."))
        self.assertTrue(llm._finish("Manchester United berniat memberhentikan Carrick sekarang juga.").startswith("Manchester"))
        self.assertEqual(llm._finish("BASI"), STALE)

    def test_pipeline_sends_bilingual_with_link_and_fallback(self):
        pipe, tg = tp.build()
        pipe.summarize = lambda s: f"Casemiro sepakat kontrak baru.\n{SEP}\nCasemiro agrees new contract."
        pipe.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United midfielder Casemiro has agreed.")])
        pipe.dispatch()
        text = tg.sent[0][1]
        self.assertIn("Casemiro sepakat kontrak baru.\n──────────\nCasemiro agrees new contract.", text)
        self.assertIn("Selengkapnya:\nhttps://x/BBC Sport/Casemiro agrees new contract", text)
        pipe2, tg2 = tp.build()
        pipe2.summarize = lambda s: None
        pipe2.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United midfielder Casemiro has agreed new terms. More text here.")])
        for _ in range(4):
            pipe2.dispatch()
        self.assertIn("Terjemahan belum tersedia", tg2.sent[0][1])
        self.assertIn("Casemiro has agreed new terms", tg2.sent[0][1])

    def test_gnews_items_use_shorter_max_age(self):
        pipe, tg = tp.build()
        old = tp.item("Casemiro agrees new contract", "Daily Mail", text="Manchester United Casemiro.", pub=tp.CLOCK.t - 2 * 3600, max_age_hours=1.5)
        pipe.ingest([old])
        self.assertEqual(pipe.st["stories"], {})


class TestBlocks(unittest.TestCase):
    def test_block_commands_and_pipeline(self):
        st, now = S.new_state(), 1_800_000_000
        self.assertIn("30-360", C.reply_for("/blokir", ["10", "bruno"], st, CFG, now))
        self.assertIn("120 menit", C.reply_for("/blokir", ["120", "Bruno", "Contract"], st, CFG, now))
        self.assertIn("permanen", C.reply_for("/blokir", ["basket"], st, CFG, now))
        self.assertIn("bruno contract", C.reply_for("/daftarblokir", [], st, CFG, now))
        pipe, tg = tp.build()
        pipe.st["blocks"] = st["blocks"]
        for b in pipe.st["blocks"]:
            if b["until"]:
                b["until"] = tp.CLOCK.t + 7200
        pipe.ingest([tp.item("Bruno Fernandes contract talks continue", "BBC Sport", text="Manchester United captain Bruno Fernandes."),
                     tp.item("Official: Manchester United announce Bruno Fernandes contract", "ManUtd.com", official=True,
                             text="Manchester United announce Bruno Fernandes contract."),
                     tp.item("Casemiro agrees new contract", "Sky Sports", text="Manchester United Casemiro.")])
        pipe.dispatch()
        sent = " ".join(t for _, t in tg.sent)
        self.assertNotIn("talks continue", sent)
        self.assertIn("[RESMI]", sent)
        self.assertIn("Casemiro", sent)
        tp.CLOCK.adv(7300)
        pipe.prune()
        self.assertEqual([b["phrase"] for b in pipe.st["blocks"]], ["basket"])
        self.assertIn("dibuka", C.reply_for("/buka", ["basket"], st, CFG, now))


class TestDigest(unittest.TestCase):
    def test_morning_digest_once_per_day(self):
        pipe, tg = tp.build()
        pipe.summarize = lambda s: f"Ringkasan {s['title']} yang cukup panjang untuk dibaca.\n{SEP}\nEnglish."
        pipe.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United Casemiro agreed."),
                     tp.item("Mbeumo scores twice in derby", "Sky Sports", text="Manchester United Mbeumo scored twice.")])
        pipe.dispatch()
        pipe.st["stories"] and None
        out = RecTG()
        now = pipe.now()
        d = datetime.fromtimestamp(now, WIB)
        before = datetime(d.year, d.month, d.day, 6, 30, tzinfo=WIB).timestamp()
        after = datetime(d.year, d.month, d.day, 7, 10, tzinfo=WIB).timestamp()
        for s in pipe.st["stories"].values():
            s["sent_at"] = before - 3600
        digest.run(out, pipe.st, CFG, before, pipe)
        self.assertEqual(out.sent, [])
        digest.run(out, pipe.st, CFG, after, pipe)
        digest.run(out, pipe.st, CFG, after + 60, pipe)
        self.assertEqual(len(out.sent), 1)
        self.assertIn("[RINGKASAN PAGI]", out.sent[0])
        self.assertIn("1. [", out.sent[0])


ESPN_SB = {"events": [
    {"id": "401", "date": "2026-11-22T17:30Z", "status": {"type": {"state": "pre"}},
     "competitions": [{"venue": {"fullName": "Old Trafford"}, "competitors": [
         {"homeAway": "home", "score": "0", "team": {"id": "360", "displayName": "Manchester United"}},
         {"homeAway": "away", "score": "0", "team": {"id": "359", "displayName": "Arsenal"}}]}]},
    {"id": "402", "date": "2026-11-22T15:00Z", "status": {"type": {"state": "pre"}},
     "competitions": [{"competitors": [{"homeAway": "home", "team": {"id": "1", "displayName": "A"}},
                                       {"homeAway": "away", "team": {"id": "2", "displayName": "B"}}]}]}]}
ESPN_ST = {"children": [{"name": "League", "standings": {"entries": [
    {"team": {"displayName": "Arsenal"}, "stats": [{"name": "rank", "value": 1}, {"name": "gamesPlayed", "value": 12}, {"name": "wins", "value": 9},
                                                   {"name": "ties", "value": 2}, {"name": "losses", "value": 1}, {"name": "pointDifferential", "value": 15}, {"name": "points", "value": 29}]},
    {"team": {"displayName": "Manchester United"}, "stats": [{"name": "rank", "value": 5}, {"name": "gamesPlayed", "value": 12}, {"name": "wins", "value": 6},
                                                             {"name": "ties", "value": 3}, {"name": "losses", "value": 3}, {"name": "pointDifferential", "value": 4}, {"name": "points", "value": 21}]}]}}]}
ESPN_SUM = {"boxscore": {"teams": [
    {"team": {"id": "359", "displayName": "Arsenal"}, "statistics": [{"name": "possessionPct", "displayValue": "55"}, {"name": "totalShots", "displayValue": "14"}]},
    {"team": {"id": "360", "displayName": "Manchester United"}, "statistics": [{"name": "possessionPct", "displayValue": "45"}, {"name": "totalShots", "displayValue": "9"},
                                                                              {"name": "yellowCards", "displayValue": "2"}]}]},
    "rosters": [{"team": {"id": "360"}, "formation": "4-2-3-1", "roster": [
        {"starter": True, "jersey": str(i), "athlete": {"displayName": f"Pemain {i}"}, "position": {"abbreviation": "M"}} for i in range(1, 12)] + [
        {"starter": False, "jersey": "20", "athlete": {"displayName": "Cadangan A"}, "position": {"abbreviation": "F"}}]}]}
APIF_FX = {"response": [{"fixture": {"id": 900, "date": "2026-11-22T17:30:00+00:00", "venue": {"name": "Old Trafford"}, "status": {"short": "NS"}},
                         "league": {"name": "Premier League"}, "teams": {"home": {"id": 33, "name": "Manchester United"}, "away": {"id": 42, "name": "Arsenal"}},
                         "goals": {"home": None, "away": None}}]}
FD_M = {"matches": [{"utcDate": "2026-11-22T17:30:00Z", "status": "TIMED", "competition": {"name": "Premier League"},
                     "homeTeam": {"id": 66, "name": "Manchester United FC"}, "awayTeam": {"id": 57, "name": "Arsenal FC"},
                     "score": {"fullTime": {"home": None, "away": None}}}]}


class TestFootballParsers(unittest.TestCase):
    def test_espn_parsers(self):
        fx = F.parse_espn_events(ESPN_SB, "eng.1")
        self.assertEqual(len(fx), 1)
        self.assertEqual((fx[0]["home"], fx[0]["away"], fx[0]["mu_home"], fx[0]["comp"], fx[0]["venue"]), ("Manchester United", "Arsenal", True, "Premier League", "Old Trafford"))
        self.assertEqual(fx[0]["ts"], utc(2026, 11, 22, 17, 30))
        rows = F.parse_espn_standings(ESPN_ST)
        self.assertEqual([(r["pos"], r["pts"]) for r in rows], [(1, 29), (5, 21)])
        self.assertIn("&gt; 5 Manchester United", F.fmt_standings("Premier League", rows, "ESPN"))
        stats = F.parse_espn_stats(ESPN_SUM)
        self.assertEqual(stats["rows"][0], ("Penguasaan bola", "45%", "55%"))
        lu = F.parse_espn_lineup(ESPN_SUM)
        self.assertEqual((lu["formation"], len(lu["xi"]), lu["subs"]), ("4-2-3-1", 11, ["Cadangan A"]))

    def test_other_providers_parse_and_line_format(self):
        a = F.parse_apif_fixtures(APIF_FX)[0]
        d = F.parse_fd_matches(FD_M)[0]
        for f in (a, d):
            self.assertTrue(f["mu_home"])
            self.assertEqual(f["ts"], utc(2026, 11, 22, 17, 30))
        self.assertEqual(F.fmt_fixture_line(a), "Sen 23/11 00.30 WIB · Premier League · KANDANG vs Arsenal")

    def test_chain_falls_through_and_reports(self):
        name, res = F.chain([("A", lambda: (_ for _ in ()).throw(RuntimeError("x"))), ("B", lambda: []), ("C", lambda: [1])])
        self.assertEqual((name, res), ("C", [1]))
        with self.assertRaises(RuntimeError) as cm:
            F.chain([("A", lambda: None)])
        self.assertIn("A: kosong", str(cm.exception))

    def test_commands_use_chain_and_handle_errors(self):
        st = S.new_state()
        with mock.patch.object(F, "get_standings", return_value=("ESPN", "Premier League", F.parse_espn_standings(ESPN_ST))):
            self.assertIn("Klasemen Premier League", C.reply_for("/klasemen", [], st, CFG, 1_800_000_000))
        self.assertIn("Kode tersedia", C.reply_for("/klasemen", ["xyz"], st, CFG, 1_800_000_000))
        with mock.patch.object(F, "get_fixtures", side_effect=RuntimeError("semua gagal")):
            self.assertIn("/diagnosa", C.reply_for("/jadwal", [], st, CFG, 1_800_000_000))
        now = 1_800_000_000
        fx = [{**F.parse_espn_events(ESPN_SB, "eng.1")[0], "ts": now + 86400}]
        with mock.patch.object(F, "get_fixtures", return_value=("ESPN", fx)):
            out = C.reply_for("/jadwal", ["7"], st, CFG, now)
        self.assertIn("KANDANG vs Arsenal", out)


class TestMatchday(unittest.TestCase):
    def setUp(self):
        self.fx = F.parse_espn_events(ESPN_SB, "eng.1")
        self.ko = self.fx[0]["ts"]
        self.lu = {"formation": "4-2-3-1", "xi": [(str(i), f"Pemain {i}", "M") for i in range(1, 12)], "subs": ["Cadangan A"]}

    def run_at(self, st, tg, now, lineup=None):
        calls = []
        def fixtures(days):
            return "ESPN", [dict(f) for f in self.fx]
        def lineup_fn(f, allow_apif=True):
            calls.append(1)
            if lineup is None:
                raise RuntimeError("belum")
            return "ESPN", lineup
        matchday.run(tg, st, CFG, now, fixtures_fn=fixtures, lineup_fn=lineup_fn, log=lambda *a: None)
        return calls

    def test_h1_h60_and_lineup_flow(self):
        st, tg = S.new_state(), RecTG()
        self.run_at(st, tg, self.ko - 86400 + 60)
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("Besok:", tg.sent[0])
        self.run_at(st, tg, self.ko - 86400 + 180)
        self.assertEqual(len(tg.sent), 1, "H-1 hanya sekali")
        self.run_at(st, tg, self.ko - 3500)  # 1 jam lagi, lineup belum ada
        self.assertTrue(any("belum diumumkan" in t for t in tg.sent))
        self.run_at(st, tg, self.ko - 3300, lineup=self.lu)
        self.assertTrue(tg.sent[-1].startswith("<b>[LINEUP]</b>"))
        n = len(tg.sent)
        self.run_at(st, tg, self.ko - 3000, lineup=self.lu)
        self.assertEqual(len(tg.sent), n, "lineup hanya sekali")

    def test_monthly_schedule_on_first_of_month_only_once(self):
        self.fx[0]["ts"] = wib(2026, 12, 5, 22, 0)
        st, tg = S.new_state(), RecTG()
        self.run_at(st, tg, wib(2026, 11, 30, 8))
        self.assertEqual(tg.sent, [])
        self.run_at(st, tg, wib(2026, 12, 1, 8))
        self.run_at(st, tg, wib(2026, 12, 1, 9))
        self.assertEqual(len([t for t in tg.sent if "JADWAL BULANAN" in t]), 1)
        self.assertIn("Desember 2026", tg.sent[0])

    def test_schedule_change_detected(self):
        st, tg = S.new_state(), RecTG()
        now = self.ko - 10 * 86400
        self.run_at(st, tg, now)
        self.fx[0]["ts"] += 3600
        self.run_at(st, tg, now + 4 * 3600)
        self.assertTrue(any("JADWAL BERUBAH" in t and "Sebelumnya" in t for t in tg.sent))


class TestStaleContextAndStats(unittest.TestCase):
    def test_prompt_contains_history_and_publish_time(self):
        seen = {}
        summ = llm.make_summarizer(CFG, {"GEMINI_API_KEY": "x"}, log=lambda *a: None,
                                   history=lambda: ["[13/11 21.04 WIB] Manchester United diperkirakan akan memecat Carrick"])
        story = {"title": "Carrick to be sacked", "text": "Carrick to be sacked", "content": "", "journalists": [], "verify": False,
                 "pub": time.time() - 7200, "sources": [{"name": "x", "tier": 2, "url": "https://x.com/a"}]}
        def fake(models, key, prompt, log, finish=None):
            seen["p"] = prompt
            return "BASI"
        with mock.patch.object(llm, "fetch_article", return_value=("", None)), mock.patch.object(llm, "call_gemini", fake):
            self.assertEqual(summ(story), "BASI")
        self.assertIn("Manchester United diperkirakan akan memecat Carrick", seen["p"])
        self.assertIn("2 jam yang lalu", seen["p"])
        self.assertIn(SEP, seen["p"])

    def test_gemini_stats_and_thinking_fallback(self):
        llm.STATS = {}
        class R:
            def __init__(self, code, body, text=""):
                self.status_code, self._b, self.text = code, body, text
            def json(self):
                return self._b
        ok = R(200, {"candidates": [{"content": {"parts": [{"text": f"Casemiro sepakat kontrak baru dengan klub.\n{SEP}\nCasemiro agrees a new contract with the club."}]}}]})
        calls = []
        def fake_post(url, headers, payload, read=30):
            calls.append(payload["generationConfig"])
            return R(400, {}, "thinkingLevel is not supported") if "thinkingConfig" in payload["generationConfig"] else ok
        with mock.patch.object(llm, "_post", fake_post):
            out = llm.call_gemini(["m"], "k", "p", lambda *a: None)
        self.assertIn(SEP, out)
        self.assertEqual(len(calls), 2)
        self.assertEqual(llm.STATS["gemini_ok"], 1)
        st = S.new_state()
        st["ai"] = dict(llm.STATS, decode_ok=3, decode_fail=1)
        self.assertIn("Gemini 1 ok/0 gagal", C.reply_for("/status", [], st, CFG, 1_800_000_000))
        llm.STATS = None


if __name__ == "__main__":
    unittest.main()
