import os
import sys
import tempfile
import time
import unittest
from unittest import mock

import yaml

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
from bot import llm, main as M, sources as SRC, state as S, text as T  # noqa: E402
from bot.models import STALE, Item  # noqa: E402

CFG = tp.CFG


class TestSafeguards(unittest.TestCase):
    def test_stale_story_dropped_not_sent(self):
        tp.CLOCK = tp.Clock()
        tg = tp.FakeTG()
        pipe = tp.Pipeline(CFG, S.new_state(), tg, lambda s: STALE, now=tp.CLOCK, log=lambda *a: None)
        pipe.ingest([tp.item("Bruno Fernandes wins Player of the Month", "BBC Sport",
                             text="Manchester United captain Bruno Fernandes won the award for March.")])
        pipe.dispatch()
        self.assertEqual(tg.sent, [])
        self.assertEqual(list(pipe.st["stories"].values())[0]["drop"], "basi")

    def test_page_date_extraction(self):
        h1 = '<meta property="article:published_time" content="2026-03-12T10:00:00+00:00">'
        h2 = '<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-03-12"}</script>'
        h3 = '<time class="x" datetime="2026-03-12T09:00:00Z">12 March</time>'
        for h in (h1, h2, h3):
            ts = llm.page_date(h)
            self.assertIsNotNone(ts)
            self.assertLess(ts, time.time() - 30 * 86400)
        self.assertIsNone(llm.page_date("<html>tanpa tanggal</html>"))

    def test_google_news_skips_official_publisher_and_undated_flag(self):
        gn = (b'<rss><channel><item><title>Carrick on Yoro - Manchester United</title>'
              b'<link>https://news.google.com/rss/articles/a</link><pubDate>Mon, 09 Nov 2026 09:00:00 GMT</pubDate>'
              b'<source url="https://manutd.com">Manchester United</source></item>'
              b'<item><title>Other story - BBC Sport</title><link>https://news.google.com/rss/articles/b</link>'
              b'<source url="https://bbc.com">BBC Sport</source></item></channel></rss>')
        src = {"id": "gn", "name": "Google News", "type": "gnews_rss", "tier": 2, "dedicated": True}
        items = SRC.feed_items(src, SRC.parse_feed(gn), CFG, 123.0)
        self.assertEqual([i.source for i in items], ["BBC Sport"])
        self.assertTrue(items[0].undated)

    def test_undated_story_needs_verification_flag(self):
        tp.CLOCK = tp.Clock()
        pipe = tp.Pipeline(CFG, S.new_state(), tp.FakeTG(), lambda s: "ok", now=tp.CLOCK, log=lambda *a: None)
        pipe.ingest([tp.item("Tanpa tanggal tentang Casemiro", "Blog", tier=2, undated=True)])
        self.assertTrue(list(pipe.st["stories"].values())[0]["verify"])

    def test_health_alert_is_aggregated_and_quiet_sources_silent(self):
        st = S.new_state()
        for sid in ("a", "b", "c"):
            st["feeds"][sid] = {"fails": 11}
        tg = tp.FakeTG()
        res = {"a": ("gagal", "403"), "b": ("gagal", "404 <x>"), "c": ("gagal", "timeout")}
        M.update_health(res, st, tg, 12, quiet={"c"})
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("- a: 403", tg.sent[0][1])
        self.assertIn("&lt;x&gt;", tg.sent[0][1])
        self.assertNotIn("- c:", tg.sent[0][1])
        M.update_health(res, st, tg, 12, quiet={"c"})
        self.assertEqual(len(tg.sent), 1, "tidak diulang")

    def test_late_source_is_seeded_silently(self):
        path = os.path.join(tempfile.mkdtemp(), "s.json")
        def mk(title, src, text):
            return Item(uid=T.make_uid("https://x/" + src + title), title=title, text=text, url="https://x/" + src + title,
                        source=src, source_id=src, tier=1, published=time.time() - 60)
        old_a = mk("Old story A", "BBC Sport", "Manchester United old story about Casemiro.")
        old_b = mk("Old story B about Amad", "Sky Sports", "Manchester United old story about Amad Diallo.")
        new_b = mk("Amad Diallo signs new Manchester United deal", "Sky Sports", "Manchester United winger Amad Diallo has signed.")
        ok = ("ok", 1)
        env = {"DRY_RUN": "1", "STATE_PATH": path}
        summ = lambda s: "Ringkasan berita Manchester United yang cukup panjang untuk lolos pembersihan."
        with mock.patch.dict(os.environ, env), mock.patch("builtins.print") as pr, \
                mock.patch.object(M, "make_summarizer", return_value=summ), \
                mock.patch.object(M, "load_yaml", side_effect=lambda n: CFG if n == "settings.yaml" else
                                  {"sources": [{"id": "BBC Sport", "name": "BBC Sport", "type": "rss"},
                                               {"id": "Sky Sports", "name": "Sky Sports", "type": "rss"}]}):
            with mock.patch.object(M, "fetch_all", return_value=([old_a], {"BBC Sport": ok, "Sky Sports": ("gagal", "x")})):
                M.main()
            with mock.patch.object(M, "fetch_all", return_value=([old_a, old_b], {"BBC Sport": ok, "Sky Sports": ok})):
                M.main()
            with mock.patch.object(M, "fetch_all", return_value=([old_a, old_b, new_b], {"BBC Sport": ok, "Sky Sports": ok})):
                M.main()
            printed = "\n".join(str(c.args[0]) for c in pr.call_args_list if c.args)
        self.assertNotIn("Old story", printed)
        self.assertEqual(printed.count("<b>[") - printed.count("[BOT AKTIF]"), 1)  # hanya new_b


if __name__ == "__main__":
    unittest.main()
