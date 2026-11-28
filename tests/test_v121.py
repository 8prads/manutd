import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import test_pipeline as tp  # noqa: E402
import test_v17 as t17  # noqa: E402
from bot import commands as C, llm, opini, state as S, text as T  # noqa: E402

CFG = tp.CFG
SEP = T.BILINGUAL_SEP
ARTICLE = "Manchester United face up to 13 potential absentees. " + "Bruno Fernandes, Amad, Ugarte, Sesko, Rashford and Baleba are out. " * 8
NEWS = {"message_id": 55, "text": "[CEDERA] ..."}


def story():
    return {"msg_id": 55, "title": "Man Utd injury news", "body": "Ringkasan.", "body_en": "Summary.", "text": "t",
            "content": ARTICLE, "link": "https://mnews.example/a", "status": "sent",
            "sources": [{"name": "Manchester Evening News", "tier": 1}], "journalists": []}


def run(text, quoted=NEWS, st=None, answer=None):
    st = st or S.new_state()
    tg = t17.RecTG([t17.upd(1, text, 70, quoted=quoted)])
    jobs = C.handle(tg, st, CFG, "42", log=lambda *a: None)
    pipe = tp.Pipeline(CFG, st, tp.FakeTG(), lambda s: "x", now=tp.Clock(), log=lambda *a: None)
    seen = {}

    def fake_generate(cfg, env, prompt, log=print, finish=None):
        seen["prompt"], seen["finish"] = prompt, finish
        return answer

    with mock.patch.object(llm, "generate", fake_generate):
        opini.process(jobs, st, CFG, {}, tg, pipe)
    return jobs, tg, seen


class TestAskCommand(unittest.TestCase):
    def test_ask_and_alias_create_jobs_with_kind(self):
        for cmd in ("/ask siapa saja 13 pemain itu?", "/tanya siapa saja 13 pemain itu?"):
            tg = t17.RecTG([t17.upd(1, cmd, 70, quoted=NEWS)])
            jobs = C.handle(tg, S.new_state(), CFG, "42", log=lambda *a: None)
            self.assertEqual((jobs[0]["kind"], jobs[0]["notes"]), ("ask", "siapa saja 13 pemain itu?"))
        tg = t17.RecTG([t17.upd(1, "/opini Carrick perlu waktu", 70, quoted=NEWS)])
        self.assertEqual(C.handle(tg, S.new_state(), CFG, "42", log=lambda *a: None)[0]["kind"], "opini")

    def test_hints_without_quote_or_question(self):
        st = S.new_state()
        tg = t17.RecTG([t17.upd(1, "/ask apa itu?", 9), t17.upd(2, "/ask", 10, quoted=NEWS)])
        self.assertEqual(C.handle(tg, st, CFG, "42", log=lambda *a: None), [])
        self.assertIn("Balas (quote)", tg.sent[0][0])
        self.assertIn("Tulis pertanyaannya", tg.sent[1][0])
        self.assertEqual([r for _, r in tg.sent], [9, 10])

    def test_help_lists_ask(self):
        self.assertIn("/ask", C.HELP)


class TestAskAnswer(unittest.TestCase):
    ANS = "Enam nama disebut: Bruno Fernandes, Amad, Ugarte, Sesko, Rashford, Baleba. Artikel tidak menyebut tujuh sisanya.\n" \
          f"{SEP}\nSix names are mentioned: Bruno Fernandes, Amad, Ugarte, Sesko, Rashford, Baleba. The article does not name the other seven."

    def test_answer_is_bilingual_with_divider_link_and_sources(self):
        st = S.new_state()
        st["stories"]["x"] = story()
        jobs, tg, seen = run("/ask siapa saja 13 pemain itu?", st=st, answer=self.ANS)
        text, reply_to = tg.sent[-1]
        self.assertEqual(reply_to, 70)
        self.assertTrue(text.startswith("<b>[JAWABAN]</b>"))
        lines = text.split("\n")
        i = lines.index(T.DIVIDER)
        self.assertEqual((lines[i - 1], lines[i + 1]), ("", ""))
        self.assertIn("Enam nama disebut", text)
        self.assertIn("Six names are mentioned", text)
        self.assertIn("https://mnews.example/a", text)
        self.assertIn("<i>(Manchester Evening News)</i>", text)
        self.assertIn("siapa saja 13 pemain itu?", seen["prompt"])
        self.assertIn("Bruno Fernandes, Amad, Ugarte", seen["prompt"])  # isi artikel dikirim ke AI

    def test_short_article_is_flagged_and_unknown_story_uses_quoted_text(self):
        st = S.new_state()
        s = story()
        s["content"] = ""
        st["stories"]["x"] = s
        _, _, seen = run("/ask apa isinya?", st=st, answer=self.ANS)
        self.assertIn("tidak tersedia", seen["prompt"])
        _, tg, seen = run("/ask apa isinya?", quoted={"message_id": 999, "text": "Kutipan berita saja"}, answer=self.ANS)
        self.assertIn("Kutipan berita saja", seen["prompt"])
        self.assertIn("<i>(pesan yang dikutip)</i>", tg.sent[-1][0])

    def test_failure_message_and_separator_required(self):
        _, tg, _ = run("/ask apa?", answer=None)
        self.assertIn("belum bisa dijawab", tg.sent[-1][0])
        self.assertIsNone(opini.finish_ask("Hanya satu bahasa tanpa pemisah di sini."))
        self.assertIsNone(opini.finish_ask(f"pendek\n{SEP}\nshort"))
        ok = opini.finish_ask(f"**Jawaban** lengkap dalam Indonesia.\n{SEP}\n**English** answer in full.")
        self.assertIn(SEP, ok)
        self.assertNotIn("**", ok)

    def test_answer_is_clipped_per_language(self):
        long = ("Kalimat. " * 300) + f"\n{SEP}\n" + ("Sentence. " * 300)
        _, tg, _ = run("/ask apa?", answer=long)
        idn, en = [p.strip() for p in tg.sent[-1][0].split(T.DIVIDER)]
        self.assertLessEqual(len(idn), opini.ASK_MAX + 40)
        self.assertLessEqual(len(en.split("\n\n")[0]), opini.ASK_MAX)


class TestOpiniPersona(unittest.TestCase):
    def test_prompt_persona_and_300_char_limit(self):
        _, tg, seen = run("/opini Carrick perlu waktu", answer="Menurut saya Carrick perlu waktu. " * 30)
        self.assertIn("fans Manchester United sepuh", seen["prompt"])
        self.assertIn("280 karakter", seen["prompt"])
        self.assertIn("Carrick perlu waktu", seen["prompt"])
        body = tg.sent[-1][0].split("\n\n", 1)[1]
        self.assertLessEqual(len(body), opini.OPINI_MAX)
        self.assertTrue(tg.sent[-1][0].startswith("<b>[OPINI]</b>"))

    def test_polish_removes_dashes_and_wrapping_quotes(self):
        self.assertEqual(opini.polish('"Saya setuju \u2014 tapi hati-hati."'), "Saya setuju, tapi hati-hati.")


if __name__ == "__main__":
    unittest.main()
