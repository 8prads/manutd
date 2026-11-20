import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_v112 as t112  # noqa: E402
from bot import football as F  # noqa: E402

HL_MATCHES = {"data": [{"id": 55, "homeTeam": {"name": "Manchester United"}, "awayTeam": {"name": "Arsenal"}}]}
HL_LU = {"matchId": 55, "homeTeam": {"formation": "4-2-3-1", "startingXI": [{"id": i, "name": f"P{i}", "number": i, "position": "M"} for i in range(1, 12)],
                                      "substitutes": [{"name": "Sub A"}]},
         "awayTeam": {"formation": "4-4-2", "startingXI": [], "substitutes": []}}
HL_ST = {"matchId": 55, "teams": [
    {"team": {"name": "Arsenal"}, "statistics": [{"name": "Ball possession", "value": "55"}, {"name": "Total shots", "value": 14}, {"name": "Shots on target", "value": 6},
                                                  {"name": "Corners", "value": 7}, {"name": "Yellow cards", "value": 1}]},
    {"team": {"name": "Manchester United"}, "statistics": [{"name": "Ball possession", "value": "45"}, {"name": "Total shots", "value": 9}, {"name": "Shots on target", "value": 3},
                                                           {"name": "Corners", "value": 4}, {"name": "Yellow cards", "value": 2}]}]}


class TestScheduleFormat(unittest.TestCase):
    def test_short_names_and_blocks(self):
        self.assertEqual([F.short_team(n) for n in ("Liverpool FC", "AFC Bournemouth", "Brighton & Hove Albion FC", "Manchester United", "Sporting Clube de Portugal")],
                         ["Liverpool", "Bournemouth", "Brighton", "Man United", "Sporting CP"])
        fx = F.parse_espn_events(t112.ESPN_SB, "eng.1")[0]
        self.assertEqual(F.fmt_fixture_block(fx), "<b>Sen 23/11 · 00.30 WIB</b>\nMin 22/11 · 17.30 GMT\nArsenal · KANDANG\nPremier League")
        away = {**fx, "mu_home": False, "home": "Liverpool FC", "away": "Manchester United", "comp": "UEFA Champions League"}
        self.assertEqual(F.fmt_fixture_block(away).splitlines()[2:], ["Liverpool · TANDANG", "Liga Champions"])
        out = F.fmt_schedule([fx, away], "<b>Jadwal</b>")
        self.assertEqual(out.count("\n\n"), 2)


class TestHighlightly(unittest.TestCase):
    def test_parsers(self):
        lu = F.parse_hl_lineup(HL_LU, True)
        self.assertEqual((lu["formation"], len(lu["xi"]), lu["subs"]), ("4-2-3-1", 11, ["Sub A"]))
        self.assertIsNone(F.parse_hl_lineup(HL_LU, False))
        st = F.parse_hl_stats(HL_ST)
        rows = {r[0]: r[1:] for r in st["rows"]}
        self.assertEqual(st["opp"], "Arsenal")
        self.assertEqual(rows["Penguasaan bola"], ("45%", "55%"))
        self.assertEqual((rows["Tembakan"], rows["Tepat sasaran"], rows["Sepak pojok"], rows["Kartu kuning"]), (("9", "14"), ("3", "6"), ("4", "7"), ("2", "1")))

    def test_lineup_chain_uses_highlightly_and_caches_match_id(self):
        f = {**F.parse_espn_events(t112.ESPN_SB, "eng.1")[0], "espn_id": None}
        calls = []
        def fake_hl(path, **p):
            calls.append(path)
            return HL_MATCHES if path == "/football/matches" else HL_LU
        with mock.patch.dict(os.environ, {"HIGHLIGHTLY_API_KEY": "x"}), mock.patch.object(F, "_hl", fake_hl):
            prov, lu = F.get_lineup(f)
            self.assertEqual((prov, f["hl_id"], len(lu["xi"])), ("Highlightly", 55, 11))
            calls.clear()
            F.get_lineup(f)
            self.assertEqual(calls, ["/football/lineups/55"], "id pertandingan dipakai ulang")
            with self.assertRaises(RuntimeError):
                F.get_lineup(f, allow_apif=False)

    def test_stats_chain(self):
        done = F._fx(1_794_000_000, "Premier League", "Manchester United", "Arsenal", "", "post", (2, 1))
        def fake_hl(path, **p):
            return HL_MATCHES if path == "/football/matches" else HL_ST
        with mock.patch.dict(os.environ, {"HIGHLIGHTLY_API_KEY": "x"}), mock.patch.object(F, "_hl", fake_hl), \
                mock.patch.object(F, "get_fixtures", return_value=("football-data.org", [done])):
            prov, header, res = F.get_stats()
        self.assertEqual((prov, header), ("Highlightly", "Manchester United 2-1 Arsenal (Premier League)"))
        self.assertIn("Penguasaan bola: 45% - 55%", F.fmt_stats(header, res, prov))

    def test_diagnose_reports_highlightly_and_keys(self):
        ok = {"data": [{"id": 1, "date": "x", "homeTeam": {}}], "plan": {"tier": "free", "requestLimit": 100, "requestCount": 3}}
        with mock.patch.object(F, "_get", side_effect=RuntimeError("net")), mock.patch.object(F, "_apif", side_effect=RuntimeError("k")), \
                mock.patch.object(F, "_fd", side_effect=RuntimeError("k")), mock.patch.object(F, "_hl", return_value=ok):
            out = "\n".join(F.diagnose())
        self.assertIn("OK  Highlightly: paket free; requestLimit=100, requestCount=3; kunci contoh: id,date,homeTeam", out)
        self.assertIn("GAGAL  ESPN jadwal", out)

    def test_espn_requests_use_browser_user_agent(self):
        seen = []
        class R:
            def raise_for_status(self):
                pass
            def json(self):
                return {}
        def fake_get(url, headers=None, params=None, timeout=None):
            seen.append(headers["User-Agent"])
            return R()
        with mock.patch("requests.get", fake_get):
            F._get("https://site.api.espn.com/x")
            F._get("https://api.football-data.org/x")
        self.assertIn("Chrome", seen[0])
        self.assertIn("MUFCNewsBot", seen[1])


if __name__ == "__main__":
    unittest.main()
