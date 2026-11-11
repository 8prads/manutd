import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
from bot import commands as C, llm, opini, state as S, text as T  # noqa: E402
from bot.telegram import Telegram  # noqa: E402

CFG = tp.CFG


class RecTG:
    def __init__(self, updates=()):
        self.ups, self.sent = list(updates), []

    def updates(self, offset):
        return [u for u in self.ups if u["update_id"] >= offset]

    def send(self, text, reply_to=None):
        self.sent.append((text, reply_to))
        return len(self.sent)


def upd(i, text, mid, quoted=None, chat=42):
    m = {"message_id": mid, "chat": {"id": chat}, "text": text}
    if quoted:
        m["reply_to_message"] = quoted
    return {"update_id": i, "message": m}


def pipe_with(summary="Ringkasan."):
    tp.CLOCK = tp.Clock()
    return tp.Pipeline(CFG, S.new_state(), tp.FakeTG(), lambda s: summary, now=tp.CLOCK, log=lambda *a: None)


class TestJournalistSources(unittest.TestCase):
    def test_find_journalists(self):
        jr = T.build_journalist_re(CFG)
        txt = "According to Ornstein and Laurie Whitwell, United intend to act. Fabrizio Romano agrees."
        self.assertEqual(T.find_journalists(txt, jr), ["David Ornstein", "Laurie Whitwell", "Fabrizio Romano"])
        self.assertEqual(T.find_journalists("John Stones returns", jr), [])

    def test_big_platform_plus_journalist(self):
        p = pipe_with()
        p.ingest([
            tp.item("Casemiro agrees new contract", "Sky Sports", tier=1, text="Manchester United midfielder Casemiro has agreed terms."),
            tp.item("Casemiro signs contract extension", "MUFC Latest", tier=2,
                    text="According to Fabrizio Romano, Casemiro has agreed a new Manchester United deal."),
        ])
        s = list(p.st["stories"].values())[0]
        self.assertEqual(p.source_names(s), ["Sky Sports", "Fabrizio Romano"])

    def test_small_platform_replaced_by_journalist_else_kept(self):
        p = pipe_with()
        p.ingest([tp.item("Amad Diallo tipped for start", "MUFC Latest", tier=2,
                          text="Per David Ornstein, Manchester United plan changes.", journalist=False)])
        s1 = list(p.st["stories"].values())[0]
        self.assertEqual(p.source_names(s1), ["David Ornstein"])
        q = pipe_with()
        q.ingest([tp.item("Casemiro agrees deal", "The Peoples Person", tier=2, text="Manchester United midfielder Casemiro agrees.")])
        s2 = list(q.st["stories"].values())[0]
        self.assertEqual(q.source_names(s2), ["The Peoples Person"])

    def test_reddit_attribution_counts_as_journalist(self):
        p = pipe_with()
        p.ingest([tp.item("Manchester United agree fee for striker", "Fabrizio Romano", tier=1, journalist=True)])
        s = list(p.st["stories"].values())[0]
        self.assertEqual(p.source_names(s), ["Fabrizio Romano"])


class TestStyleGuards(unittest.TestCase):
    def test_meta_commentary_rejected(self):
        self.assertIsNone(llm.clean_summary("Berita hanya berisi pertanyaan mengenai apakah Manchester United memutuskan nasib Carrick."))
        self.assertIsNone(llm.clean_summary("Tidak ada informasi tambahan mengenai keputusan tersebut, sumber, atau kutipan."))
        ok = llm.clean_summary("Manchester United berniat memberhentikan Michael Carrick. Belum ada keputusan final.")
        self.assertTrue(ok.startswith("Manchester United"))

    def test_free_cleaner_keeps_long_text(self):
        self.assertTrue(llm.clean_free("**Menurut saya**, Carrick layak diberi waktu karena hasil tiga laga terakhir membaik.").startswith("Menurut saya"))


class TestOpini(unittest.TestCase):
    def test_opini_flow_quotes_command(self):
        st = S.new_state()
        st["stories"]["x"] = {"msg_id": 55, "title": "Carrick fate", "body": "United berniat mengganti Carrick.",
                              "text": "t", "content": "Isi panjang", "sources": [{"name": "Sky Sports", "tier": 1}],
                              "journalists": ["David Ornstein"], "status": "sent"}
        news_msg = {"message_id": 55, "text": "[BERITA] ..."}
        tg = RecTG([upd(1, "/opini Carrick perlu waktu", 70, quoted=news_msg)])
        jobs = C.handle(tg, st, CFG, "42", log=lambda *a: None)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["notes"], "Carrick perlu waktu")
        pipe = tp.Pipeline(CFG, st, tp.FakeTG(), lambda s: "x", now=tp.Clock(), log=lambda *a: None)
        seen = {}
        def fake_generate(cfg, env, prompt, log=print, finish=None):
            seen["prompt"] = prompt
            return "Menurut saya, Carrick layak diberi waktu karena ada perbaikan hasil dalam tiga laga terakhir."
        with mock.patch.object(llm, "generate", fake_generate):
            opini.process(jobs, st, CFG, {}, tg, pipe)
        self.assertIn("Carrick perlu waktu", seen["prompt"])
        self.assertIn("United berniat mengganti Carrick", seen["prompt"])
        text, reply_to = tg.sent[-1]
        self.assertEqual(reply_to, 70)
        self.assertTrue(text.startswith("<b>[OPINI]</b>"))
        self.assertIn("<i>(Sumber berita: Sky Sports, David Ornstein)</i>", text)

    def test_opini_without_quote_gives_hint_and_quotes_command(self):
        tg = RecTG([upd(1, "/opini", 9)])
        jobs = C.handle(tg, S.new_state(), CFG, "42", log=lambda *a: None)
        self.assertEqual(jobs, [])
        self.assertEqual(tg.sent[0][1], 9)
        self.assertIn("Balas (quote)", tg.sent[0][0])

    def test_all_commands_reply_to_the_command_message(self):
        tg = RecTG([upd(1, "/status", 21), upd(2, "/pause", 22)])
        C.handle(tg, S.new_state(), CFG, "42", log=lambda *a: None)
        self.assertEqual([r for _, r in tg.sent], [21, 22])

    def test_long_opinion_split(self):
        parts = opini.split_message("\n\n".join(["a" * 1500] * 4), limit=3800)
        self.assertEqual(len(parts), 2)
        self.assertTrue(all(len(x) <= 3800 for x in parts))

    def test_telegram_payload_has_reply_parameters(self):
        captured = {}
        class R:
            status_code, ok = 200, True
            def json(self):
                return {"result": {"message_id": 9}}
        def fake_post(url, json=None, timeout=None):
            captured["json"] = json
            return R()
        with mock.patch("requests.post", fake_post):
            mid = Telegram("t", "42").send("halo", reply_to=33)
        self.assertEqual(mid, 9)
        self.assertEqual(captured["json"]["reply_parameters"], {"message_id": 33, "allow_sending_without_reply": True})


if __name__ == "__main__":
    unittest.main()
