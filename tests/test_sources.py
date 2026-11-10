import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bot import sources as SRC  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
CFG = yaml.safe_load(open(os.path.join(ROOT, "config", "settings.yaml"), encoding="utf-8"))

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>Test</title>
<item><title>Casemiro &amp; Bruno extend deals</title><link>https://ex.com/a?utm_source=x</link>
<description>&lt;p&gt;Manchester United &nbsp;midfielder &lt;b&gt;Casemiro&lt;/b&gt; has agreed.&lt;/p&gt;</description>
<pubDate>Mon, 09 Nov 2026 09:00:00 GMT</pubDate></item>
<item><title>Second</title><link>https://ex.com/b</link><dc:date>2026-11-09T08:00:00Z</dc:date></item>
</channel></rss>"""

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom title</title>
<link rel="alternate" href="https://ex.com/atom"/><summary>Ringkas</summary><updated>2026-11-09T07:00:00+00:00</updated></entry></feed>"""

GN = b"""<rss version="2.0"><channel><item><title>Ten Hag fallout deepens - BBC Sport</title>
<link>https://news.google.com/rss/articles/abc</link><description>x</description><pubDate>Mon, 09 Nov 2026 09:00:00 GMT</pubDate>
<source url="https://bbc.com">BBC Sport</source></item></channel></rss>"""


class TestSources(unittest.TestCase):
    def test_rss_parse_with_bad_entity_and_html(self):
        e = SRC.parse_feed(RSS)
        self.assertEqual(len(e), 2)
        src = {"id": "t", "name": "Test", "type": "rss", "tier": 2, "dedicated": True}
        items = SRC.feed_items(src, e, CFG, 0)
        self.assertEqual(items[0].title, "Casemiro & Bruno extend deals")
        self.assertIn("Casemiro has agreed", items[0].text)
        self.assertEqual(items[0].published, 1794214800.0)
        self.assertEqual(items[1].published, 1794211200.0)

    def test_atom(self):
        e = SRC.parse_feed(ATOM)
        self.assertEqual(e[0]["link"], "https://ex.com/atom")

    def test_google_news_source_and_tier(self):
        src = {"id": "gn", "name": "Google News", "type": "gnews_rss", "tier": 2, "dedicated": True}
        it = SRC.feed_items(src, SRC.parse_feed(GN), CFG, 0)[0]
        self.assertEqual((it.source, it.tier, it.title), ("BBC Sport", 1, "Ten Hag fallout deepens"))

    def test_reddit_attribution_and_buckets(self):
        data = {"data": {"children": [
            {"data": {"title": "[Romano] Manchester United agree fee for striker", "score": 900,
                      "created_utc": 1794128400, "permalink": "/r/reddevils/x", "url": "https://twitter.com/x"}},
            {"data": {"title": "Low score post", "score": 10, "created_utc": 1794128400, "permalink": "/r/reddevils/y"}},
            {"data": {"title": "[Sky Sports] Team news", "score": 300, "created_utc": 1794128400,
                      "permalink": "/r/reddevils/z", "url": "https://skysports.com/z"}},
        ]}}
        its = SRC.reddit_items({"id": "r"}, data, CFG, 0)
        self.assertEqual(len(its), 2)
        self.assertEqual((its[0].source, its[0].journalist, its[0].tier), ("Fabrizio Romano", True, 1))
        self.assertEqual(its[1].source, "Sky Sports")
        self.assertTrue(its[0].uid.endswith("r2"))

    def test_fetch_all_isolates_failures(self):
        srcs = [{"id": "a", "name": "A", "type": "rss", "url": "http://invalid.invalid/x", "tier": 2},
                {"id": "b", "name": "B", "type": "guardian", "key_env": "NOPE", "tier": 1}]
        items, res = SRC.fetch_all(srcs, {"feeds": {}}, CFG, {}, log=lambda *a: None)
        self.assertEqual(res["a"][0], "gagal")
        self.assertEqual(res["b"][0], "lewati")


if __name__ == "__main__":
    unittest.main()
