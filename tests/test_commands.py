import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bot import commands as C  # noqa: E402
from bot import llm  # noqa: E402
from bot import state as S  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml"), encoding="utf-8"))


class FakeTG:
    def __init__(self, ups):
        self.ups, self.out = ups, []

    def updates(self, offset):
        return [u for u in self.ups if u["update_id"] >= offset]

    def send(self, t):
        self.out.append(t)
        return 1


def upd(i, text, chat=42):
    return {"update_id": i, "message": {"chat": {"id": chat}, "text": text}}


class TestCommands(unittest.TestCase):
    def test_commands_and_authorization(self):
        st = S.new_state()
        tg = FakeTG([upd(1, "/cooldown 20"), upd(2, "/batas 5"), upd(3, "/pause"), upd(4, "/pause", chat=7),
                     upd(5, "/cooldown 999"), upd(6, "halo")])
        C.handle(tg, st, CFG, "42", log=lambda *a: None)
        self.assertEqual(st["override"], {"cooldown_minutes": 20, "max_per_hour": 5})
        self.assertTrue(st["paused"])
        self.assertEqual(len(tg.out), 4)  # /cooldown, /batas, /pause, /cooldown 999 (format salah)
        self.assertEqual(st["tg_offset"], 7)

    def test_status_text(self):
        st = S.new_state()
        self.assertIn("aktif", C.reply_for("/status", [], st, CFG, 1_800_000_000))

    def test_clean_summary_and_extract(self):
        self.assertIsNone(llm.clean_summary("pendek"))
        out = llm.clean_summary("**Ringkasan:** Manchester United menyepakati kontrak baru dengan Casemiro hingga 2028.")
        self.assertTrue(out.startswith("Manchester United"))
        html_doc = "<html><body><p>" + "Kalimat panjang tentang berita. " * 5 + "</p><p>kecil</p></body></html>"
        self.assertIn("Kalimat panjang", llm.extract_text(html_doc))


if __name__ == "__main__":
    unittest.main()
