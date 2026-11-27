import os
import re
import sys
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
import test_v118 as t118  # noqa: E402
from bot import commands as C, llm, state as S, text as T, video  # noqa: E402

CFG = tp.CFG
UTC = timezone.utc
NOW = datetime(2026, 11, 24, 10, 30, tzinfo=UTC).timestamp()
ENV = {"YOUTUBE_API_KEY": "k"}
REL = re.compile(r"\b(?:manchester united|man utd|pochettino|carrick|bruno fernandes)\b", re.I)
YT = {"youtube": {"poll_minutes": 10, "search_every_minutes": 60, "remind_minutes": 30,
                  "channels": [{"name": "Manchester United", "handle": "@manutd", "official": True, "search_upcoming": True},
                               {"name": "Sky Sports Football", "handle": "@SkySportsFootball"}]}}


class R:
    def __init__(self, code, text=""):
        self.status_code, self.text = code, text

    def json(self):
        return {"choices": [{"message": {"content": "OK"}}]}


class TG:
    def __init__(self):
        self.sent = []

    def send(self, text, reply_to=None):
        self.sent.append(text)
        return len(self.sent)


def chan(cid, title, subs="1000"):
    return {"id": cid, "snippet": {"title": title}, "statistics": {"subscriberCount": subs}}


def vid(vid_id, title, channel="Manchester United", live="none", sched=None, start=None, published="2026-11-24T10:00:00Z", desc=""):
    d = {"id": vid_id, "snippet": {"title": title, "description": desc, "channelTitle": channel, "liveBroadcastContent": live,
                                   "publishedAt": published}}
    ls = {k: v for k, v in (("scheduledStartTime", sched), ("actualStartTime", start)) if v}
    if ls:
        d["liveStreamingDetails"] = ls
    return d


def api(channels, uploads, videos, upcoming=None):
    calls = []

    def f(path, key, **p):
        calls.append((path, p))
        if path == "channels":
            if "forHandle" in p:
                it = channels.get(p["forHandle"])
                return {"items": [it] if it else []}
            return {"items": [c for c in channels.values() if c["id"] in p["id"].split(",")]}
        if path == "playlistItems":
            return {"items": [{"snippet": {"resourceId": {"videoId": v}}} for v in uploads.get(p["playlistId"], [])]}
        if path == "videos":
            return {"items": [videos[i] for i in p["id"].split(",") if i in videos]}
        if path == "search":
            if p.get("type") == "channel":
                return {"items": [{"id": {"channelId": c["id"]}} for c in channels.values() if p["q"].lower() in c["snippet"]["title"].lower()]}
            return {"items": [{"id": {"videoId": v}} for v in (upcoming or {}).get(p["channelId"], [])]}
        raise AssertionError(path)
    f.calls = calls
    return f


CHANNELS = {"@manutd": chan("UCmu", "Manchester United", "5000000"), "@SkySportsFootball": chan("UCsky", "Sky Sports Football", "7000000")}


def step(state, tg, fake, at, cfg=YT):
    with mock.patch.object(video, "_get", fake):
        video.run(tg, state, cfg, ENV, at, REL, log=lambda *a: None)


class TestVideoMonitor(unittest.TestCase):
    def test_first_run_is_silent_then_new_interview_announced_once(self):
        st, tg = S.new_state(), TG()
        uploads = {"UUmu": ["v1"], "UUsky": []}
        videos = {"v1": vid("v1", "Pochettino press conference")}
        step(st, tg, api(CHANNELS, uploads, videos), NOW)
        self.assertEqual(tg.sent, [])
        uploads["UUmu"] = ["v2", "v1"]
        videos["v2"] = vid("v2", "Carrick interview: the derby")
        step(st, tg, api(CHANNELS, uploads, videos), NOW + 11 * 60)
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("<b>[VIDEO]</b>", tg.sent[0])
        self.assertIn("Carrick interview: the derby", tg.sent[0])
        self.assertIn("Kanal: Manchester United", tg.sent[0])
        self.assertIn("https://www.youtube.com/watch?v=v2", tg.sent[0])
        step(st, tg, api(CHANNELS, uploads, videos), NOW + 22 * 60)
        self.assertEqual(len(tg.sent), 1)

    def test_filters_by_interview_words_and_man_utd_mention(self):
        st, tg = S.new_state(), TG()
        uploads = {"UUmu": [], "UUsky": ["s0"]}
        videos = {"s0": vid("s0", "Old", "Sky Sports Football")}
        step(st, tg, api(CHANNELS, uploads, videos), NOW)
        uploads.update(UUmu=["a", "b"], UUsky=["c", "d", "e", "s0"])
        videos.update({
            "a": vid("a", "Training ground: behind the scenes"),                                            # kanal resmi, bukan wawancara
            "b": vid("b", "Amad Diallo speaks after the win"),                                              # kanal resmi + kata wawancara
            "c": vid("c", "Match highlights", "Sky Sports Football", desc="Manchester United"),             # bukan wawancara
            "d": vid("d", "Bruno Fernandes interview", "Sky Sports Football", desc="Speaking about Manchester United"),
            "e": vid("e", "Salah interview", "Sky Sports Football", desc="Liverpool forward"),              # tidak menyebut Man Utd
        })
        step(st, tg, api(CHANNELS, uploads, videos), NOW + 11 * 60)
        titles = " ".join(tg.sent)
        self.assertIn("Amad Diallo speaks", titles)
        self.assertIn("Bruno Fernandes interview", titles)
        self.assertEqual(len(tg.sent), 2)

    def test_scheduled_soon_live_flow(self):
        st, tg = S.new_state(), TG()
        sched = datetime(2026, 11, 24, 13, 30, tzinfo=UTC)
        videos = {"u1": vid("u1", "LIVE: Pochettino press conference", live="upcoming", sched="2026-11-24T13:30:00Z")}
        fake = lambda: api(CHANNELS, {"UUmu": [], "UUsky": []}, videos, upcoming={"UCmu": ["u1"]})
        step(st, tg, fake(), NOW)
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("[SIARAN TERJADWAL]", tg.sent[0])
        self.assertIn("Mulai: Sel 24/11 20.30 WIB (Sel 24/11 13.30 GMT)", tg.sent[0])
        step(st, tg, fake(), sched.timestamp() - 20 * 60)
        self.assertIn("[LIVE SEBENTAR LAGI]", tg.sent[1])
        videos["u1"] = vid("u1", "LIVE: Pochettino press conference", live="live", sched="2026-11-24T13:30:00Z", start="2026-11-24T13:31:00Z")
        step(st, tg, fake(), sched.timestamp() + 2 * 60)
        self.assertIn("<b>[LIVE]</b>", tg.sent[2])
        videos["u1"] = vid("u1", "LIVE: Pochettino press conference", live="none")
        step(st, tg, fake(), sched.timestamp() + 4000)
        self.assertEqual(len(tg.sent), 3)
        self.assertEqual(st["video"]["watch"], {})

    def test_throttle_and_quota_block(self):
        st, tg = S.new_state(), TG()
        fake = api(CHANNELS, {"UUmu": [], "UUsky": []}, {})
        step(st, tg, fake, NOW)
        n = len(fake.calls)
        step(st, tg, fake, NOW + 60)
        self.assertEqual(len(fake.calls), n)  # belum lewat poll_minutes
        boom = mock.Mock(side_effect=video.ApiError(403, '{"error": {"errors": [{"reason": "quotaExceeded"}]}}'))
        with mock.patch.object(video, "_get", boom):
            video.run(tg, st, YT, ENV, NOW + 20 * 60, REL, log=lambda *a: None)
        self.assertGreater(st["video"]["blocked_until"], NOW)
        self.assertIn("Kuota YouTube API habis", tg.sent[-1])
        calls = boom.call_count
        with mock.patch.object(video, "_get", boom):
            video.run(tg, st, YT, ENV, NOW + 40 * 60, REL, log=lambda *a: None)
        self.assertEqual(boom.call_count, calls)

    def test_no_key_or_channels_does_nothing(self):
        tg, st = TG(), S.new_state()
        fake = api(CHANNELS, {}, {})
        with mock.patch.object(video, "_get", fake):
            video.run(tg, st, YT, {}, NOW, REL)
            video.run(tg, st, {"youtube": {"channels": []}}, ENV, NOW, REL)
        self.assertEqual(fake.calls, [])

    def test_resolve_falls_back_to_name_search_and_picks_exact_most_subscribed(self):
        channels = {"a": chan("UC1", "Manchester United", "5000000"), "b": chan("UC2", "Manchester United", "2000"),
                    "c": chan("UC3", "Manchester United Fans", "9000000")}
        fake = api(channels, {}, {})
        c = {**video.DEFAULTS, "channels": []}
        with mock.patch.object(video, "_get", fake):
            info = video.resolve_channel({"name": "Manchester United", "handle": "@salah"}, "k", {}, c)
        self.assertEqual((info["id"], info["uploads"]), ("UC1", "UU1"))

    def test_check_summary_for_diagnosa(self):
        st = S.new_state()
        with mock.patch.object(video, "_get", api(CHANNELS, {}, {})):
            out = video.check(YT, ENV, st, NOW)
        self.assertIn("2 kanal: Manchester United (5.000.000 pelanggan); Sky Sports Football (7.000.000 pelanggan)", out)
        with self.assertRaises(RuntimeError):
            video.check(YT, {}, st)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIn("LEWATI  YouTube: tanpa kunci", C._video_line(YT, st))


class TestProviderHandling(unittest.TestCase):
    def setUp(self):
        llm._SKIP.clear()
        llm._STRIKES.clear()
        llm._LAST.clear()
        llm.NOTICES.clear()
        llm.BLOCKS = {}
        llm.STATS = None

    def tearDown(self):
        llm.BLOCKS = None
        llm.NOTICES.clear()

    def call(self, response, calls, **kw):
        def fake(url, headers, payload, read=30):
            calls.append((url, payload))
            return response
        with mock.patch.object(llm, "_post", fake):
            return llm.call_openai_compat("https://x/v1", ["m1", "m2"], "k", "p", lambda *a: None, lambda t: t, kw.pop("tag", "cerebras"), **kw)

    def test_credit_exhausted_closes_provider_for_30_days_and_notifies(self):
        for resp in (R(402, "Payment Required"), R(429, '{"code": "insufficient_quota"}'), R(403, "denied")):
            llm.BLOCKS, llm.NOTICES[:] = {}, []
            calls = []
            self.assertIsNone(self.call(resp, calls, credit_based=True))
            self.assertEqual(len(calls), 1)  # model kedua tidak dicoba
            self.assertGreater(llm.BLOCKS["cerebras"], time.time() + 29 * 86400)
            self.assertIn("Cerebras dinonaktifkan 30 hari", llm.NOTICES[0])
            self.assertIn("/ai buka cerebras", llm.NOTICES[0])
        llm.BLOCKS, llm.NOTICES[:] = {}, []
        self.call(R(403, "denied"), [])  # bukan penyedia berbasis kredit: hanya model yang ditutup
        self.assertNotIn("cerebras", llm.BLOCKS)
        self.assertIn("cerebras:m1", llm.BLOCKS)

    def test_closed_provider_is_skipped_by_router(self):
        llm.BLOCKS["cerebras"] = time.time() + 1000
        calls = []
        with mock.patch.object(llm, "_post", lambda *a, **k: calls.append(1)):
            self.assertEqual(llm.ai_call(CFG, {"CEREBRAS_API_KEY": "k"}, "p"), (None, None))
        self.assertEqual(calls, [])

    def test_bad_key_and_missing_model_are_remembered(self):
        calls = []
        self.call(R(401, "unauthorized"), calls)
        self.assertGreater(llm.BLOCKS["cerebras"], time.time() + 5 * 3600)
        self.assertIn("ditolak", llm.NOTICES[0])
        llm.BLOCKS, llm.NOTICES[:] = {}, []
        calls = []
        self.call(R(404, "model not found"), calls)
        self.assertEqual(len(calls), 2)  # tiap model dicoba sekali
        self.assertGreater(llm.BLOCKS["cerebras:m1"], time.time() + 23 * 3600)
        calls.clear()
        self.call(R(404, "model not found"), calls)
        self.assertEqual(calls, [])

    def test_extra_payload_url_template_and_usability(self):
        calls = []
        self.call(R(200), calls, extra={"thinking": {"type": "disabled"}})
        self.assertEqual(calls[0][1]["thinking"], {"type": "disabled"})
        p = CFG["llm"]["providers"]["cloudflare"]
        self.assertEqual(llm._url(p, {"CLOUDFLARE_ACCOUNT_ID": "abc"}),
                         "https://api.cloudflare.com/client/v4/accounts/abc/ai/v1/chat/completions")
        self.assertFalse(llm._usable("cloudflare", p, {"CLOUDFLARE_API_TOKEN": "k"}))
        self.assertTrue(llm._usable("cloudflare", p, {"CLOUDFLARE_API_TOKEN": "k", "CLOUDFLARE_ACCOUNT_ID": "abc"}))
        self.assertFalse(llm._usable("cohere", CFG["llm"]["providers"]["cohere"], {"COHERE_API_KEY": "k"}))
        base = {"key_env": "K", "models": ["m"], "url": "u"}
        self.assertFalse(llm._usable("x", {**base, "active_until": "2000-01-01"}, {"K": "k"}))
        self.assertTrue(llm._usable("x", {**base, "active_until": "2999-01-01"}, {"K": "k"}))

    def test_ai_command_status_close_and_open(self):
        st, now = S.new_state(), 1_800_000_000
        llm.BLOCKS = st["ai_block"]
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k", "CEREBRAS_API_KEY": "k"}, clear=True):
            out = C.reply_for("/ai", [], st, CFG, now)
            self.assertIn("Groq: aktif", out)
            self.assertIn("Mistral: tanpa kunci", out)
            self.assertIn("Cohere: nonaktif di config", out)
            self.assertIn("ditutup 5 hari", C.reply_for("/ai", ["tutup", "cerebras", "5"], st, CFG, now))
            self.assertGreater(st["ai_block"]["cerebras"], now + 4 * 86400)
            self.assertIn("Cerebras: DITUTUP sampai", "\n".join(llm.ai_status(CFG, os.environ, {"ai_block": {"cerebras": time.time() + 1000}})))
            self.assertIn("dibuka kembali", C.reply_for("/ai", ["buka", "cerebras"], st, CFG, now))
            self.assertNotIn("cerebras", st["ai_block"])
            st["ai_block"]["groq:x"] = now + 5
            self.assertIn("Semua blokir", C.reply_for("/ai", ["buka", "semua"], st, CFG, now))
            self.assertEqual(st["ai_block"], {})
            self.assertIn("Format", C.reply_for("/ai", ["tutup", "tidakada"], st, CFG, now))

    def test_main_flushes_notices(self):
        from bot import main as M
        tg = TG()
        llm.NOTICES[:] = ["<b>[PERINGATAN]</b>\n\ntes"]
        M.flush_notices(tg)
        self.assertEqual(tg.sent, ["<b>[PERINGATAN]</b>\n\ntes"])
        self.assertEqual(llm.NOTICES, [])


class TestInterviewOnlyQuotes(unittest.TestCase):
    K = {"pembicara": "Bruno Fernandes", "media": "Sky Sports News", "konteks_id": "Disampaikan kepada Sky Sports News.",
         "konteks_en": "Speaking to Sky Sports News.",
         "teks": ["Two summers ago, three summers ago, last summer, I always had the chance to leave United and I always chose to be here"],
         "terjemahan": ["Dua musim panas lalu, tiga musim panas lalu, musim panas kemarin, saya selalu punya kesempatan pergi"]}

    def run_(self, label, **kw):
        st = t118.story(label_hint=label)
        return st, t118.run(st, t118.fake_ai(t118.draft(kutipan=self.K, **kw)))

    def test_news_with_incidental_quotes_uses_normal_format(self):
        st, out = self.run_("INTERVIEW", jenis="berita")
        idn, en = T.split_bilingual(out)
        self.assertNotIn("told @SkySportsNews", en)
        self.assertTrue(en.startswith("Casemiro has agreed a new contract until 2028.\n\n"))
        self.assertEqual(st["ai_label"], "BERITA")  # judul berkata "says", tetapi isinya bukan wawancara

    def test_interview_content_uses_quote_format_and_label(self):
        st, out = self.run_("TRANSFER", jenis="wawancara")
        self.assertIn("Bruno Fernandes: \u201cTwo summers ago", T.split_bilingual(out)[1])
        self.assertEqual(st["ai_label"], "INTERVIEW")
        st, out = self.run_("PUNDIT", jenis="wawancara")
        self.assertNotIn("ai_label", st)
        self.assertIn("told @SkySportsNews", T.split_bilingual(out)[1])

    def test_very_short_quotes_do_not_make_an_interview(self):
        k = {**self.K, "teks": ["I always chose to be here"], "terjemahan": ["x"]}
        st = t118.story(label_hint="INTERVIEW")
        out = t118.run(st, t118.fake_ai(t118.draft(jenis="wawancara", kutipan=k)))
        self.assertNotIn("told @", T.split_bilingual(out)[1])

    def test_broadcast_announcements_get_their_own_label(self):
        pr = T.build_pundit_re(CFG)
        c = lambda title: T.classify(title, title, True, True, 1, T.event_type(title), pr)
        self.assertEqual(c("Pochettino press conference: watch live on MUTV"), "SIARAN")
        self.assertEqual(c("How to watch Liverpool v Man Utd"), "SIARAN")
        self.assertEqual(c("Pochettino press conference: Amad Diallo can leave"), "INTERVIEW")


if __name__ == "__main__":
    unittest.main()
