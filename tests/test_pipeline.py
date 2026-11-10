import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bot import state as S  # noqa: E402
from bot import text as T  # noqa: E402
from bot.models import Item  # noqa: E402
from bot.pipeline import Pipeline  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml"), encoding="utf-8"))


class FakeTG:
    def __init__(self):
        self.sent, self.edits, self._id = [], [], 100

    def send(self, text):
        self._id += 1
        self.sent.append((self._id, text))
        return self._id

    def edit(self, mid, text):
        self.edits.append((mid, text))
        return True


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t

    def adv(self, sec):
        self.t += sec


def item(title, source, tier=1, text="", pub=None, uid=None, **kw):
    return Item(uid=uid or T.make_uid(f"https://x/{source}/{title}"), title=title, text=text or title,
                url=f"https://x/{source}/{title}", source=source, source_id=source, tier=tier,
                published=pub if pub is not None else CLOCK.t - 60, **kw)


def build():
    global CLOCK
    CLOCK = Clock()
    tg = FakeTG()
    pipe = Pipeline(CFG, S.new_state(), tg, lambda s: "Ringkasan: " + s["title"], now=CLOCK, log=lambda *a: None)
    return pipe, tg


class TestPipeline(unittest.TestCase):
    def test_duplicate_story_sent_once_and_sources_merged(self):
        pipe, tg = build()
        pipe.ingest([
            item("Casemiro agrees new Manchester United contract", "BBC Sport",
                 text="Manchester United midfielder Casemiro has agreed a new contract at Old Trafford."),
            item("Casemiro signs new contract extension at Man Utd", "Sky Sports",
                 text="Manchester United have tied down Casemiro with a contract extension."),
            item("Man Utd confirm Casemiro contract extension", "Manchester Evening News",
                 text="The club have confirmed that Casemiro has extended his contract."),
        ])
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 1)
        self.assertIn("<i>(BBC Sport, Sky Sports, Manchester Evening News)</i>", tg.sent[0][1])
        CLOCK.adv(300)
        pipe.ingest([item("Casemiro extends Manchester United contract", "ESPN", pub=CLOCK.t - 30,
                         text="Manchester United midfielder Casemiro has extended his contract.")])
        pipe.dispatch()
        pipe.refresh_edits()
        self.assertEqual(len(tg.sent), 1)
        self.assertEqual(len(tg.edits), 1)
        self.assertIn("ESPN", tg.edits[0][1])

    def test_blog_needs_support_then_sent(self):
        pipe, tg = build()
        pipe.ingest([item("Amad Diallo tipped for surprise start against Brighton", "MUFC Latest", tier=2)])
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 0)
        pipe.ingest([item("Amad Diallo expected to start against Brighton", "RedMancunian", tier=2)])
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 1)

    def test_blog_dropped_if_no_support(self):
        pipe, tg = build()
        pipe.ingest([item("Random fan theory about summer plans", "Red Rants", tier=2)])
        pipe.dispatch()
        CLOCK.adv(50 * 60)
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 0)
        self.assertEqual(list(pipe.st["stories"].values())[0]["status"], "dropped")

    def test_cooldown_defers_same_topic_then_sends(self):
        pipe, tg = build()
        pipe.ingest([item("Casemiro agrees new contract", "BBC Sport",
                          text="Manchester United midfielder Casemiro has agreed new terms.")])
        pipe.dispatch()
        CLOCK.adv(300)
        pipe.ingest([item("Casemiro could leave in January as Manchester United weigh options for midfield "
                          "rebuild after Brazilian struggles", "Sky Sports", pub=CLOCK.t - 30,
                          text="Manchester United are considering whether Casemiro could leave in January.")])
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 1, "harus tertahan oleh cooldown")
        CLOCK.adv(11 * 60)
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 2, "terkirim setelah cooldown 15 menit")

    def test_escalation_bypasses_cooldown(self):
        pipe, tg = build()
        pipe.ingest([item("Manchester United linked with Joao Silva transfer", "Sky Sports",
                          text="Manchester United have been linked with Joao Silva, say reports.")])
        pipe.dispatch()
        self.assertIn("[RUMOR]", tg.sent[0][1])
        CLOCK.adv(180)
        pipe.ingest([item("Official: Manchester United announce signing of Joao Silva", "ManUtd.com",
                          official=True, pub=CLOCK.t - 20, text="The club announce the signing of Joao Silva.")])
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 2)
        self.assertIn("[RESMI]", tg.sent[1][1])

    def test_hourly_cap_with_breaking_unlimited(self):
        pipe, tg = build()
        names = ["Zebra Alpha", "Kilo Bravo", "Delta Echo", "Foxtrot Golf", "Hotel India", "Juliet Lima",
                 "Mike Oscar", "Papa Quebec", "Romeo Sierra", "Tango Victor", "Whiskey Xray", "Yankee Zulu"]
        pipe.ingest([item(f"{n} wins Manchester United academy award", "BBC Sport") for n in names])
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 10)
        pipe.ingest([item("BREAKING: Manchester United manager sacked after defeat", "Sky Sports")])
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 11)
        self.assertIn("[BREAKING NEWS]", tg.sent[-1][1])

    def test_old_and_irrelevant_items_ignored(self):
        pipe, tg = build()
        pipe.ingest([
            item("Chelsea sign striker", "BBC Sport", dedicated=False),
            item("Manchester United midfielder returns", "BBC Sport", dedicated=False, pub=CLOCK.t - 10 * 3600),
            item("Fantasy Premier League tips for Manchester United players", "BBC Sport"),
        ])
        pipe.dispatch()
        self.assertEqual(len(tg.sent), 0)

    def test_format_and_labels(self):
        msg = T.format_message("RUMOR", "A & B <x>", ["BBC Sport", "Sky Sports"])
        self.assertEqual(msg, "<b>[RUMOR]</b>\n\nA &amp; B &lt;x&gt;\n\n<i>(BBC Sport, Sky Sports)</i>")
        pr = T.build_pundit_re(CFG)
        c = lambda title, **k: T.classify(title, title, k.get("o", False), k.get("s", True), 1, T.event_type(title), pr)
        self.assertEqual(c("Gary Neville says United must change"), "PUNDIT")
        self.assertEqual(c("Amorim says he is unhappy with the attitude"), "INTERVIEW")
        self.assertEqual(c("Midfielder ruled out for six weeks with hamstring injury"), "CEDERA")
        self.assertEqual(c("Man Utd eyeing move for striker"), "RUMOR")
        self.assertEqual(c("Man Utd complete signing of defender"), "RESMI")
        self.assertEqual(c("Dressing room row after training ground bust-up"), "DRAMA")

    def test_state_roundtrip(self):
        import tempfile
        pipe, _ = build()
        pipe.ingest([item("Casemiro agrees new contract", "BBC Sport")])
        path = os.path.join(tempfile.mkdtemp(), "s.json")
        S.save(path, pipe.st)
        self.assertEqual(S.load(path)["n_docs"], pipe.st["n_docs"])


if __name__ == "__main__":
    unittest.main()
