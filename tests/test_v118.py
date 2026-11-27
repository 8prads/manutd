import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
from bot import commands as C, digest, draft as D, llm, state as S, text as T  # noqa: E402
from bot.models import DROP, IRRELEVANT, STALE  # noqa: E402

CFG = tp.CFG
ENV = {"GEMINI_API_KEY": "x"}
ARTICLE = ("Manchester United midfielder Casemiro has agreed a new contract until 2028, a deal worth £52m in total, according to "
           "David Ornstein. The club have not yet commented on the report. "
           "Bruno Fernandes told Sky Sports News: \u201cTwo summers ago, three summers ago, last summer, I always had the chance to "
           "leave United and I always chose to be here\u201d. \u201cI've always showed how much I care about the club\u201d. " * 3)


def story(sources=None, **kw):
    s = {"title": "Casemiro agrees new contract", "text": "Manchester United midfielder Casemiro has agreed new terms.",
         "content": ARTICLE, "journalists": [], "verify": False, "official": False, "pub": time.time() - 600, "etype": "other",
         "label_hint": "BERITA", "sources": sources or [{"name": "BBC Sport", "tier": 1, "url": "https://bbc.com/a"}]}
    s.update(kw)
    return s


def draft(**kw):
    d = {"relevan": True, "basi": False, "konflik": False, "jenis": "berita", "kepastian": "dilaporkan", "sumber_klaim": "", "bukti": "",
         "headline_id": "Casemiro sepakat memperpanjang kontrak hingga 2028.",
         "isi_id": "Gelandang Manchester United itu menyetujui kontrak baru, menurut David Ornstein.",
         "headline_en": "Casemiro has agreed a new contract until 2028.",
         "isi_en": "The Manchester United midfielder has agreed a new deal, according to David Ornstein.", "kutipan": None}
    d.update(kw)
    return d


def fake_ai(*responses):
    """Ganti llm.ai_call: tiap panggilan mengambil satu jawaban berurutan (None = penyedia gagal)."""
    queue, calls = list(responses), []

    def f(cfg, env, prompt, log=print, finish=None, role="write", avoid=None):
        calls.append((role, avoid, prompt))
        r = queue.pop(0) if queue else None
        return (r, "gemini" if role == "write" else "groq") if r is not None else (None, None)
    f.calls = calls
    return f


def run(st, ai, **kw):
    summ = llm.make_summarizer(CFG, ENV, log=lambda *a: None)
    with mock.patch.object(llm, "ai_call", ai), mock.patch.object(llm, "fetch_article", return_value=("", None)):
        return summ(st)


class TestDraftHelpers(unittest.TestCase):
    def test_headline_prefix_clip_and_quote_block(self):
        self.assertEqual(D.headline("Doue ruptured ACL", "OFFICIAL:"), "OFFICIAL: Doue ruptured ACL.")
        self.assertEqual(D.headline("OFFICIAL: Doue ruptured ACL.", "OFFICIAL:"), "OFFICIAL: Doue ruptured ACL.")
        self.assertLessEqual(len(D.clip("Kalimat satu. " + "Kalimat dua yang cukup panjang sekali. " * 20, 120)), 120)
        self.assertEqual(D.clip("Pendek saja.", 300), "Pendek saja.")
        self.assertEqual(D.quote_block("Bruno Fernandes", ["a one two three", "b four five six", "c seven eight"], "@SkySportsNews", "en"),
                         "Bruno Fernandes: \u201ca one two three\u201d. \u201cb four five six\u201d, told @SkySportsNews. \u201cc seven eight\u201d.")
        self.assertIn("ujarnya kepada @X", D.quote_block("Nama", ["satu dua tiga empat"], "@X", "id"))

    def test_in_text_ellipsis_and_numbers(self):
        self.assertTrue(D.in_text("I always showed how much I care", "He said \u201cI always showed how much I care about the club.\u201d"))
        self.assertTrue(D.in_text("I always showed ... care about the club", "I always showed how much I care about the club"))
        self.assertFalse(D.in_text("totally invented sentence here", ARTICLE))
        self.assertEqual(D.number_issues("fee of \u00a352.5m for four years", "a \u00a352.5m fee over 4 years, 60 games"), ["angka 60 tidak ada di teks"])

    def test_fake_quotes_are_dropped(self):
        k = {"pembicara": "Bruno Fernandes", "media": "Sky Sports News", "konteks_id": "k", "konteks_en": "c",
             "teks": ["I always chose to be here", "this was never said by anyone"], "terjemahan": ["a", "b"]}
        q = D.verified_quotes(k, ARTICLE)
        self.assertEqual(q["teks"], ["I always chose to be here"])
        self.assertIsNone(D.verified_quotes({**k, "teks": ["never said at all"]}, ARTICLE))


class TestSummarizer(unittest.TestCase):
    def test_normal_story_headline_body_and_limit(self):
        out = run(story(), fake_ai(draft(isi_en="Kalimat. " * 80)))
        idn, en = T.split_bilingual(out)
        self.assertTrue(idn.startswith("Casemiro sepakat memperpanjang kontrak hingga 2028.\n\n"))
        self.assertTrue(en.startswith("Casemiro has agreed a new contract until 2028.\n\n"))
        self.assertLessEqual(len(en.split("\n\n", 1)[1]), 300)

    def test_flags_stale_irrelevant_satire_conflict(self):
        self.assertEqual(run(story(), fake_ai(draft(basi=True))), STALE)
        self.assertEqual(run(story(), fake_ai(draft(relevan=False))), IRRELEVANT)
        st = story()
        self.assertEqual(run(st, fake_ai(draft(jenis="satir"))), DROP)
        self.assertEqual(st["drop_why"], "satir")
        st = story(sources=[{"name": "Daily Mail", "tier": 2, "url": "https://x/a"}])
        self.assertEqual(run(st, fake_ai(draft(konflik=True))), DROP)
        self.assertEqual(st["drop_why"], "bertentangan")
        self.assertIsNotNone(run(story(), fake_ai(draft(konflik=True))))  # sumber golongan A tetap lolos

    def test_journalist_only_sources_need_quoted_evidence(self):
        mail = [{"name": "Daily Mail", "tier": 2, "url": "https://x/a"}]
        st = story(sources=mail)
        self.assertEqual(run(st, fake_ai(draft())), DROP)
        self.assertEqual(st["drop_why"], "tidak kredibel")
        st = story(sources=mail)
        self.assertEqual(run(st, fake_ai(draft(bukti="Casemiro has agreed a new contract until 2028, a deal worth \u00a352m, according to Jamie Jackson."))), DROP)
        st = story(sources=mail)
        ok = draft(sumber_klaim="David Ornstein", bukti="a deal worth \u00a352m in total, according to David Ornstein.")
        self.assertIsNotNone(run(st, fake_ai(ok)))
        self.assertIn("David Ornstein", st["journalists"])

    def test_opinion_becomes_speculation_and_official_gets_prefix(self):
        st = story()
        run(st, fake_ai(draft(jenis="opini")))
        self.assertEqual(st["ai_label"], "SPEKULASI")
        st = story(label_hint="RESMI")
        out = run(st, fake_ai(draft()))
        idn, en = T.split_bilingual(out)
        self.assertTrue(idn.startswith("RESMI: ") and en.startswith("OFFICIAL: "))
        self.assertNotIn("ai_label", st)

    def test_interview_quote_format_in_both_languages(self):
        k = {"pembicara": "Bruno Fernandes", "media": "Sky Sports News", "konteks_id": "Disampaikan kepada Sky Sports News.",
             "konteks_en": "Speaking to Sky Sports News.",
             "teks": ["Two summers ago, three summers ago, last summer, I always had the chance to leave United and I always chose to be here",
                      "I've always showed how much I care about the club", "an invented extra quote nobody said"],
             "terjemahan": ["Dua musim panas lalu, tiga musim panas lalu, musim panas kemarin, saya selalu punya kesempatan pergi", "Saya selalu menunjukkan kepedulian saya", "palsu"]}
        out = run(story(label_hint="INTERVIEW"), fake_ai(draft(jenis="wawancara", kutipan=k)))
        idn, en = T.split_bilingual(out)
        self.assertEqual(en.split("\n\n")[1], "Speaking to Sky Sports News.")
        self.assertTrue(en.split("\n\n")[2].startswith("Bruno Fernandes: \u201cTwo summers ago"))
        self.assertIn("\u201d. \u201cI've always showed how much I care about the club\u201d, told @SkySportsNews.", en)
        self.assertNotIn("invented", en)
        self.assertIn("ujarnya kepada @SkySportsNews", idn)
        self.assertIn("Saya selalu menunjukkan kepedulian saya", idn)

    def test_ai_check_rewrite_and_drop(self):
        risky = lambda: story(etype="transfer")
        ai = fake_ai(draft(), {"ok": True, "masalah": []})
        self.assertIsNotNone(run(risky(), ai))
        self.assertEqual([c[0] for c in ai.calls], ["write", "check"])
        self.assertEqual(ai.calls[1][1], "gemini")  # pemeriksa diminta berbeda dari penulis
        ai = fake_ai(draft(), {"ok": False, "masalah": ["makna terbalik"]}, draft(headline_en="Casemiro has agreed a new deal."), {"ok": True})
        self.assertIsNotNone(run(risky(), ai))
        self.assertIn("makna terbalik", ai.calls[2][2])
        st = risky()
        ai = fake_ai(draft(), {"ok": False, "masalah": ["x"]}, draft(), {"ok": False, "masalah": ["y"]})
        self.assertEqual(run(st, ai), DROP)
        self.assertEqual(st["drop_why"], "gagal periksa")

    def test_check_unavailable_still_sends_and_non_risky_skips_check(self):
        ai = fake_ai(draft())
        self.assertIsNotNone(run(story(etype="transfer"), ai))  # pemeriksa gagal: tetap dikirim
        ai = fake_ai(draft())
        run(story(), ai)
        self.assertEqual([c[0] for c in ai.calls], ["write"])

    def test_number_not_in_article_triggers_rewrite(self):
        ai = fake_ai(draft(headline_en="Casemiro signs for \u00a399m until 2028."), draft())
        out = run(story(), ai)
        self.assertIsNotNone(out)
        self.assertIn("angka 99 tidak ada di teks", ai.calls[1][2])

    def test_time_budget_per_run(self):
        summ = llm.make_summarizer({**CFG, "llm": {**CFG["llm"], "max_seconds_per_run": -1}}, ENV, log=lambda *a: None)
        ai = fake_ai(draft())
        with mock.patch.object(llm, "ai_call", ai), mock.patch.object(llm, "fetch_article", return_value=("", None)):
            self.assertIsNone(summ(story()))
        self.assertEqual(ai.calls, [])

    def test_call_cap_per_run(self):
        summ = llm.make_summarizer({**CFG, "llm": {**CFG["llm"], "max_calls_per_run": 1}}, ENV, log=lambda *a: None)
        ai = fake_ai(draft(), draft())
        with mock.patch.object(llm, "ai_call", ai), mock.patch.object(llm, "fetch_article", return_value=("", None)):
            self.assertIsNotNone(summ(story()))
            self.assertIsNone(summ(story()))
        self.assertEqual(len(ai.calls), 1)


class TestRouter(unittest.TestCase):
    def setUp(self):
        llm._SKIP.clear()
        llm._STRIKES.clear()
        llm._LAST.clear()
        llm.BLOCKS = None
        llm.STATS = None

    tearDown = setUp

    def test_order_missing_keys_and_avoid(self):
        full = {p["key_env"]: "k" for p in CFG["llm"]["providers"].values()}
        full["CLOUDFLARE_ACCOUNT_ID"] = "acc"
        self.assertEqual(llm.providers_for(CFG, full, "write"),
                         ["gemini", "groq", "github", "sambanova", "openrouter", "zai", "nvidia", "cloudflare", "cerebras", "mistral"])
        self.assertEqual(llm.providers_for(CFG, full, "check", avoid="groq"),
                         ["cerebras", "github", "sambanova", "cloudflare", "openrouter", "zai", "nvidia", "gemini", "mistral", "groq"])
        self.assertEqual(llm.providers_for(CFG, {"GROQ_API_KEY": "k"}, "write"), ["groq"])
        self.assertEqual(llm.providers_for(CFG, {"GROQ_API_KEY": "k"}, "check", avoid="groq"), ["groq"])

    def test_falls_through_to_next_provider(self):
        env = {"GEMINI_API_KEY": "k", "CEREBRAS_API_KEY": "k"}
        seen = []

        def fake(name, p, key, prompt, log, finish, env=None):
            seen.append(name)
            return "hasil" if name == "cerebras" else None
        with mock.patch.object(llm, "_call_provider", fake):
            self.assertEqual(llm.ai_call(CFG, env, "p"), ("hasil", "cerebras"))
        self.assertEqual(seen, ["gemini", "cerebras"])

    def test_min_interval_and_daily_cap(self):
        env = {"CEREBRAS_API_KEY": "k"}
        with mock.patch.object(llm, "_call_provider", return_value="ok"):
            self.assertEqual(llm.ai_call(CFG, env, "p")[1], "cerebras")
            self.assertEqual(llm.ai_call(CFG, env, "p"), (None, None))  # jeda 13 detik belum lewat
            llm.STATS = {"openrouter_calls": 45}
            self.assertEqual(llm.ai_call(CFG, {"OPENROUTER_API_KEY": "k"}, "p"), (None, None))

    def _post_429(self, text, calls):
        class R:
            status_code = 429

            def __init__(self):
                self.text = text

        def fake(url, headers, payload, read=30):
            calls.append(payload)
            return R()
        return fake

    def test_daily_quota_block_persists_and_minute_block_is_short(self):
        llm.BLOCKS, calls = {}, []
        with mock.patch.object(llm, "_post", self._post_429("Too many tokens: requests per day exceeded", calls)):
            llm.call_openai_compat("https://x", ["m"], "k", "p", lambda *a: None, tag="cerebras")
            self.assertGreater(llm.BLOCKS["cerebras:m"], time.time() + 60)
            llm.call_openai_compat("https://x", ["m"], "k", "p", lambda *a: None, tag="cerebras")
        self.assertEqual(len(calls), 1)
        llm.BLOCKS, calls = {}, []
        with mock.patch.object(llm, "_post", self._post_429("rate limit, slow down", calls)):
            llm.call_openai_compat("https://x", ["m"], "k", "p", lambda *a: None, tag="groq")
        self.assertLess(llm.BLOCKS["groq:m"], time.time() + 120)

    def test_gemini_reset_is_in_the_future_and_param_name(self):
        self.assertGreater(llm._next_reset("gemini"), time.time())
        self.assertGreater(llm._next_reset("groq"), time.time())
        seen = []

        class R:
            status_code = 200
            text = ""

            def json(self):
                return {"choices": [{"message": {"content": "OK"}}]}

        def fake(url, headers, payload, read=30):
            seen.append(payload)
            return R()
        with mock.patch.object(llm, "_post", fake):
            llm.call_openai_compat("https://x", ["m"], "k", "p", lambda *a: None, lambda t: t, "cerebras", "max_completion_tokens")
        self.assertIn("max_completion_tokens", seen[0])
        self.assertNotIn("max_tokens", seen[0])

    def test_ping_lines(self):
        with mock.patch.object(llm, "_call_provider", return_value="OK"):
            out = llm.ai_ping(CFG, {"GROQ_API_KEY": "k"})
        self.assertIn("OK  AI Groq: membalas", out)
        self.assertIn("LEWATI  AI Cerebras: tanpa kunci CEREBRAS_API_KEY", out)


class TestPipelineCredibility(unittest.TestCase):
    def two(self, text, src=("Football365", "CaughtOffside")):
        return [tp.item("Casemiro agrees new contract", s, tier=2, text=text) for s in src]

    def test_journalist_only_story_is_dropped_and_logged(self):
        pipe, tg = tp.build()
        pipe.ingest(self.two("Manchester United midfielder Casemiro has agreed new terms."))
        pipe.dispatch()
        self.assertEqual(tg.sent, [])
        st = next(iter(pipe.st["stories"].values()))
        self.assertEqual(st["drop"], "tidak kredibel")
        out = C.reply_for("/dibuang", [], pipe.st, CFG, tp.CLOCK.t)
        self.assertIn("[tidak kredibel] Casemiro agrees new contract", out)

    def test_quoting_a_trusted_journalist_passes_and_hides_the_outlet_name(self):
        pipe, tg = tp.build()
        pipe.ingest(self.two("Manchester United midfielder Casemiro has agreed new terms, says Fabrizio Romano."))
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("<i>(Fabrizio Romano)</i>", tg.sent[0][1])
        self.assertEqual(tg.sent[0][1].splitlines()[-1], "<i>(Fabrizio Romano)</i>")

    def test_a_and_b_sources_are_listed_and_j_replaced(self):
        self.assertEqual([T.source_class(n, CFG) for n in ("Sky Sports", "Manchester Evening News", "Football365", "Daily Mail", "ManUtd.com")],
                         ["A", "B", "J", "J", "A"])
        pipe, _ = tp.build()
        pipe.ingest([tp.item("Casemiro agrees new contract", "Sky Sports", text="Manchester United midfielder Casemiro has agreed new terms."),
                     tp.item("Casemiro signs contract extension", "Football365", tier=2, text="Manchester United have tied down Casemiro, per Fabrizio Romano.")])
        self.assertEqual(pipe.source_names(next(iter(pipe.st["stories"].values()))), ["Sky Sports", "Fabrizio Romano"])

    def test_ai_label_and_hint_reach_the_message(self):
        pipe, tg = tp.build()
        seen = {}

        def summ(s):
            seen["hint"] = s["label_hint"]
            s["ai_label"] = "SPEKULASI"
            return "Headline.\n\nIsi.\n###ENGLISH###\nHeadline.\n\nBody."
        pipe.summarize = summ
        pipe.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United midfielder Casemiro has agreed new terms.")])
        pipe.dispatch()
        self.assertTrue(tg.sent[0][1].startswith("<b>[SPEKULASI]</b>"))
        self.assertIn(seen["hint"], ("TRANSFER", "BERITA"))

    def test_no_ai_fallback_only_for_a_or_b_sources(self):
        pipe, tg = tp.build()
        pipe.summarize = lambda s: None
        pipe.ingest(self.two("Manchester United midfielder Casemiro has agreed new terms, says Fabrizio Romano."))
        for _ in range(4):
            pipe.dispatch()
        self.assertEqual(tg.sent, [])
        pipe2, tg2 = tp.build()
        pipe2.summarize = lambda s: None
        pipe2.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United midfielder Casemiro has agreed new terms. More text here.")])
        for _ in range(4):
            pipe2.dispatch()
        self.assertIn("Casemiro agrees new contract\n\nManchester United midfielder", tg2.sent[0][1])

    def test_history_for_ai_lists_sources_and_digest_uses_headline(self):
        pipe, tg = tp.build()
        pipe.summarize = lambda s: "Headline satu kalimat.\n\nIsi berita yang cukup panjang untuk dibaca.\n###ENGLISH###\nHeadline.\n\nBody."
        pipe.ingest([tp.item("Casemiro agrees new contract", "BBC Sport", text="Manchester United midfielder Casemiro has agreed new terms.")])
        pipe.dispatch()
        self.assertIn("(sumber: BBC Sport)", pipe.recent_titles()[0])
        st = next(iter(pipe.st["stories"].values()))
        st["sent_at"] = tp.CLOCK.t - 100

        class TG:
            sent = []

            def send(self, text):
                self.sent.append(text)
                return 1
        tgd = TG()
        from datetime import datetime
        from bot.reminders import WIB
        now = datetime.fromtimestamp(tp.CLOCK.t, WIB)
        digest.run(tgd, pipe.st, CFG, datetime(now.year, now.month, now.day, 23, 0, tzinfo=WIB).timestamp(), pipe)
        self.assertIn("1. [", tgd.sent[0])
        self.assertIn("Headline satu kalimat.", tgd.sent[0])
        self.assertNotIn("Isi berita", tgd.sent[0])


class TestCommandsAndText(unittest.TestCase):
    def test_daftar_lists_players_journalists_and_pundits(self):
        st = S.new_state()
        out = C.reply_for("/daftar", [], st, CFG, 1_800_000_000)
        self.assertIn(f"Pemain dan staf ({len(CFG['mu_names'])})", out)
        self.assertIn(f"Jurnalis tepercaya ({len(CFG['people']['trusted_journalists'])})", out)
        self.assertIn(f"Pundit ({len(CFG['people']['pundits'])})", out)
        self.assertIn("Fabrizio Romano", out)
        self.assertIn("Casemiro", out)

    def test_jurnalis_add_remove_reset_changes_detection(self):
        st, now = S.new_state(), 1_800_000_000
        jr = lambda: T.build_journalist_re(CFG, st)
        self.assertEqual(T.find_journalists("per Jane Doe today", jr()), [])
        self.assertIn("Ditambahkan", C.reply_for("/jurnalis", ["tambah", "Jane", "Doe"], st, CFG, now))
        self.assertIn("sudah ada", C.reply_for("/jurnalis", ["tambah", "jane doe"], st, CFG, now))
        self.assertEqual(T.find_journalists("per Jane Doe today", jr()), ["Jane Doe"])
        self.assertIn("Dikeluarkan", C.reply_for("/jurnalis", ["hapus", "Fabrizio", "Romano"], st, CFG, now))
        self.assertEqual(T.find_journalists("says Romano", jr()), [])
        self.assertIn("Jane Doe", C.reply_for("/jurnalis", [], st, CFG, now))
        self.assertIn("dibatalkan", C.reply_for("/jurnalis", ["reset"], st, CFG, now))
        self.assertEqual(T.effective_journalists(CFG, st), CFG["people"]["trusted_journalists"])
        self.assertIn("Format", C.reply_for("/jurnalis", ["tambah"], st, CFG, now))

    def test_status_shows_each_provider_and_checks(self):
        st = S.new_state()
        st["ai"] = {"day": "2026-11-24", "cerebras_ok": 2, "gemini_fail": 1, "check_ok": 3, "check_issue": 1}
        out = C.reply_for("/status", [], st, CFG, 1_800_000_000)
        self.assertIn("Cerebras 2 ok/0 gagal", out)
        self.assertIn("Gemini 0 ok/1 gagal", out)
        self.assertIn("Pemeriksaan AI: 3 ok, 1 bermasalah, 0 dilewati", out)

    def test_dibuang_empty_and_diagnosa_has_provider_lines(self):
        self.assertIn("Belum ada", C.reply_for("/dibuang", [], S.new_state(), CFG, 1))
        with mock.patch.object(C, "_ai_lines", return_value=["OK  AI Groq: membalas"]), \
                mock.patch("bot.football.diagnose", return_value=["OK  ESPN jadwal: ok"]):
            out = C.reply_for("/diagnosa", [], S.new_state(), CFG, 1_800_000_000)
        self.assertIn("OK  AI Groq: membalas", out)

    def test_x_handle_and_boilerplate(self):
        self.assertEqual(T.x_handle("Sky Sports News", CFG), "@SkySportsNews")
        self.assertEqual(T.x_handle("Some Small Site", CFG), "Some Small Site")
        self.assertEqual(T.x_handle("", CFG), "")
        txt = ("Casemiro signs. The deal runs to 2028. Related articles: Mbeumo scores. Read more about the match.")
        self.assertEqual(T.cut_boilerplate(txt), "Casemiro signs. The deal runs to 2028.")
        self.assertEqual(T.cut_boilerplate("Body text.\nAdvertisement\nOther news"), "Body text.")
        self.assertEqual(T.cut_boilerplate("We read more about it later."), "We read more about it later.")

    def test_configuration_is_consistent(self):
        provs = CFG["llm"]["providers"]
        for role, names in CFG["llm"]["order"].items():
            self.assertTrue(set(names) <= set(provs), role)
        self.assertNotIn("Football365", CFG["tier1_names"])
        self.assertEqual(T.source_class("Football365", CFG), "J")


if __name__ == "__main__":
    unittest.main()
