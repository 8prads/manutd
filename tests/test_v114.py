import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_v112 as t112  # noqa: E402
from bot import commands as C, football as F, state as S, text as T  # noqa: E402
from bot.models import Item  # noqa: E402

CFG = t112.CFG


def item(title):
    return Item(uid="u", title=title, text=title, url="u", source="s", source_id="s", tier=1, published=0, dedicated=False)


class TestNameCommands(unittest.TestCase):
    def test_add_remove_reset_and_relevance(self):
        st, now = S.new_state(), 1_800_000_000
        rel = lambda: T.build_relevance(CFG, st)
        self.assertFalse(T.is_relevant(item("Zubimendi scores twice"), rel()))
        self.assertTrue(T.is_relevant(item("Rashford scores twice"), rel()))
        self.assertIn("Ditambahkan", C.reply_for("/nama", ["tambah", "Zubimendi"], st, CFG, now))
        self.assertIn("sudah ada", C.reply_for("/nama", ["tambah", "zubimendi"], st, CFG, now))
        self.assertTrue(T.is_relevant(item("Zubimendi scores twice"), rel()))
        self.assertIn("Dikeluarkan", C.reply_for("/nama", ["hapus", "Rashford"], st, CFG, now))
        self.assertFalse(T.is_relevant(item("Rashford scores twice"), rel()))
        self.assertIn("sudah dikeluarkan", C.reply_for("/nama", ["hapus", "rashford"], st, CFG, now))
        self.assertIn("dimasukkan kembali", C.reply_for("/nama", ["tambah", "Rashford"], st, CFG, now))
        self.assertTrue(T.is_relevant(item("Rashford scores twice"), rel()))
        self.assertIn("Dihapus dari tambahan", C.reply_for("/nama", ["hapus", "Zubimendi"], st, CFG, now))
        self.assertIn("tidak ada di daftar", C.reply_for("/nama", ["hapus", "Zubimendi"], st, CFG, now))
        C.reply_for("/nama", ["tambah", "Kobbie", "Mainoo", "Jr"], st, CFG, now)
        lst = C.reply_for("/nama", [], st, CFG, now)
        self.assertIn("Kobbie Mainoo Jr", lst)
        self.assertIn("Casemiro", lst)
        self.assertIn("dibatalkan", C.reply_for("/nama", ["reset"], st, CFG, now))
        self.assertEqual(T.effective_names(CFG, st), CFG["mu_names"])
        self.assertIn("Format", C.reply_for("/nama", ["tambah"], st, CFG, now))

    def test_pipeline_uses_state_names(self):
        import test_pipeline as tp
        pipe, tg = tp.build()
        pipe.st["names_add"] = ["Zubimendi"]
        pipe.rel = T.build_relevance(CFG, pipe.st)
        pipe.ingest([tp.item("Zubimendi agrees Manchester switch", "BBC Sport", dedicated=False, text="Zubimendi has agreed.")])
        self.assertEqual(len(pipe.st["stories"]), 1)


class TestEspnFallbackAndErrors(unittest.TestCase):
    SCHEDULE = {"events": [{"id": "9", "date": "2099-01-10T15:00Z", "competitions": [{"status": {"type": {"state": "pre"}}, "competitors": [
        {"homeAway": "home", "team": {"id": "360", "name": "Manchester United"}, "score": {"value": 0.0, "displayValue": "0"}},
        {"homeAway": "away", "team": {"id": "359", "displayName": "Arsenal"}, "score": {"value": 0.0, "displayValue": "0"}}]}]}]}

    def test_parser_accepts_score_objects_and_name_variants(self):
        fx = F.parse_espn_events(self.SCHEDULE, "eng.1")[0]
        self.assertEqual((fx["home"], fx["away"], fx["score"], fx["state"]), ("Manchester United", "Arsenal", (0, 0), "pre"))

    def test_scoreboard_failure_falls_back_to_team_schedule(self):
        def fake_get(url, headers=None, params=None):
            if url.endswith("/scoreboard"):
                raise RuntimeError("HTTP 400")
            return self.SCHEDULE
        with mock.patch.object(F, "_get", fake_get):
            fx = F.espn_fixtures(["eng.1"], 0, 36500)
        self.assertEqual(len(fx), 1)

    def test_total_failure_reports_reasons(self):
        with mock.patch.object(F, "_get", side_effect=RuntimeError("HTTP 403")):
            with self.assertRaises(RuntimeError) as cm:
                F.espn_fixtures(["eng.1"], 0, 30)
        msg = str(cm.exception)
        self.assertIn("papan skor", msg)
        self.assertIn("jadwal tim", msg)
        self.assertIn("403", msg)


class TestHighlightlyDiagnostics(unittest.TestCase):
    DONE = F._fx(1_794_000_000, "Premier League", "Manchester United", "Arsenal", "", "post", (2, 1))

    def test_stats_error_names_the_reason(self):
        with mock.patch.dict(os.environ, {"HIGHLIGHTLY_API_KEY": "x"}), \
                mock.patch.object(F, "_hl", return_value={"data": []}), \
                mock.patch.object(F, "get_fixtures", return_value=("football-data.org", [self.DONE])):
            with self.assertRaises(RuntimeError) as cm:
                F.get_stats()
        msg = str(cm.exception)
        self.assertIn("pertandingan tidak ditemukan", msg)
        self.assertIn("0 hasil", msg)
        self.assertIn("tanpa id ESPN", msg)

    def test_stats_error_shows_unknown_shape(self):
        def fake_hl(path, **p):
            if path == "/football/matches":
                return {"data": [{"id": 5, "homeTeam": {"name": "Manchester United"}, "awayTeam": {"name": "Arsenal"}}]}
            return {"foo": 1, "bar": 2}
        with mock.patch.dict(os.environ, {"HIGHLIGHTLY_API_KEY": "x"}), mock.patch.object(F, "_hl", fake_hl), \
                mock.patch.object(F, "get_fixtures", return_value=("football-data.org", [self.DONE])):
            with self.assertRaises(RuntimeError) as cm:
                F.get_stats()
        self.assertIn("dict: foo,bar", str(cm.exception))

    def test_failed_lookup_is_cached_to_save_quota(self):
        f = {**self.DONE, "state": "pre", "espn_id": None, "mu_home": True}
        calls = []
        def fake_hl(path, **p):
            calls.append(path)
            return {"data": []}
        with mock.patch.dict(os.environ, {"HIGHLIGHTLY_API_KEY": "x"}), mock.patch.object(F, "_hl", fake_hl):
            with self.assertRaises(RuntimeError):
                F.get_lineup(f)
            n = len(calls)
            with self.assertRaises(RuntimeError):
                F.get_lineup(f)
        self.assertEqual(len(calls), n, "tidak mencari ulang selama 30 menit")

    def test_diagnose_has_statistics_line(self):
        ok = {"data": [{"id": 1}], "plan": {"tier": "BASIC"}}
        with mock.patch.object(F, "_get", side_effect=RuntimeError("net")), mock.patch.object(F, "_apif", side_effect=RuntimeError("k")), \
                mock.patch.object(F, "_fd", side_effect=RuntimeError("k")), mock.patch.object(F, "_hl", return_value=ok), \
                mock.patch.object(F, "get_fixtures", return_value=("x", [self.DONE])):
            out = "\n".join(F.diagnose())
        self.assertIn("OK  Highlightly: paket BASIC; kuota tidak dilaporkan", out)
        self.assertIn("GAGAL  Highlightly statistik: RuntimeError pertandingan tidak ditemukan", out)


if __name__ == "__main__":
    unittest.main()
