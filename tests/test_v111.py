import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
from bot import commands as C, main as M, sources as SRC, state as S, text as T  # noqa: E402

CFG = tp.CFG


class TestV111(unittest.TestCase):
    def test_quota_skip_clears_stale_failure_counts(self):
        st = S.new_state()
        st["feeds"]["gnews_api"] = {"fails": 612, "alerted": True, "last_error": "403"}
        M.update_health({"gnews_api": ("lewati", "kuota habis")}, st, tp.FakeTG(), 12, quiet={"gnews_api"})
        self.assertEqual(st["feeds"]["gnews_api"]["fails"], 0)
        self.assertIn("sehat", C.reply_for("/sumber", [], st, CFG, 1_800_000_000))

    def test_pending_report_reasons(self):
        pipe, tg = tp.build()
        pipe.ingest([tp.item("Amad Diallo tipped for surprise start against Brighton", "MUFC Latest", tier=2)])
        self.assertIn("dukungan", pipe.pending_report()[0][2])
        pipe2, _ = tp.build()
        pipe2.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United midfielder Casemiro has agreed new terms.")])
        pipe2.dispatch()
        tp.CLOCK.adv(300)
        pipe2.ingest([tp.item("Casemiro could leave in January as Manchester United weigh options for midfield rebuild after Brazilian struggles",
                              "Sky Sports", pub=tp.CLOCK.t - 30,
                              text="Manchester United are considering whether Casemiro could leave in January.")])
        pipe2.dispatch()
        rep = pipe2.pending_report()
        self.assertEqual(len(rep), 1)
        self.assertIn("cooldown", rep[0][2])
        out = C.reply_for("/menunggu", [], pipe2.st, CFG, tp.CLOCK.t)
        self.assertIn("cooldown topik", out)

    def test_rumor_not_promoted_to_breaking_by_source_count(self):
        pipe, tg = tp.build()
        pipe.ingest([
            tp.item("Papers: Bruno rejects second Man Utd contract offer", "Sky Sports", text="Manchester United contract news from the papers."),
            tp.item("Bruno Fernandes rejects second contract offer says report", "Manchester Evening News", text="Manchester United captain Bruno Fernandes contract."),
            tp.item("Bruno Fernandes second contract offer rejected claims paper", "ESPN", text="Manchester United and Bruno Fernandes contract."),
        ])
        pipe.dispatch()
        self.assertIn("[RUMOR]", tg.sent[0][1])
        self.assertTrue(T.RE_HEDGE.search("Papers: Bruno rejects second Man Utd contract offer"))

    def test_source_alias_for_the_athletic(self):
        gn = (b'<rss><channel><item><title>Pochettino to sign - The New York Times</title>'
              b'<link>https://news.google.com/rss/articles/a</link><pubDate>Mon, 09 Nov 2026 09:00:00 GMT</pubDate>'
              b'<source url="https://nytimes.com">The New York Times</source></item></channel></rss>')
        src = {"id": "gn", "name": "Google News", "type": "gnews_rss", "tier": 2, "dedicated": True}
        it = SRC.feed_items(src, SRC.parse_feed(gn), CFG, 1.0)[0]
        self.assertEqual((it.source, it.tier), ("The Athletic", 1))


if __name__ == "__main__":
    unittest.main()
