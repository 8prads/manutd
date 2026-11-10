import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bot import main as M  # noqa: E402
from bot import state as S  # noqa: E402
from bot import text as T  # noqa: E402
from bot.models import Item  # noqa: E402


def it(title, src, tier, text, official=False):
    return Item(uid=T.make_uid("https://x/" + src + title), title=title, text=text, url="https://x/" + src + title,
                source=src, source_id=src, tier=tier, published=time.time() - 60, official=official)


class TestIntegration(unittest.TestCase):
    def test_two_cycles_bootstrap_then_send(self):
        path = os.path.join(tempfile.mkdtemp(), "state.json")
        env = {"DRY_RUN": "1", "STATE_PATH": path}
        old = it("Old story already published", "BBC Sport", 1, "Manchester United old story about Casemiro.")
        new1 = it("Casemiro agrees new contract", "BBC Sport", 1, "Manchester United midfielder Casemiro has agreed new terms.")
        new2 = it("Casemiro signs contract extension", "Sky Sports", 1, "Manchester United have tied down Casemiro with an extension.")
        ok = {"bbc": ("ok", 1)}
        with mock.patch.dict(os.environ, env), mock.patch("builtins.print") as pr:
            with mock.patch.object(M, "fetch_all", return_value=([old], ok)):
                M.main()
            self.assertTrue(S.load(path)["init"])
            with mock.patch.object(M, "fetch_all", return_value=([old, new1, new2], ok)), \
                    mock.patch.object(M, "make_summarizer", return_value=lambda s: "Casemiro menyepakati kontrak baru bersama Manchester United."):
                M.main()
            printed = "\n".join(str(c.args[0]) for c in pr.call_args_list if c.args)
        self.assertIn("[BOT AKTIF]", printed)
        self.assertEqual(printed.count("<b>[TRANSFER]</b>"), 1)
        self.assertNotIn("Old story", printed)
        self.assertIn("(BBC Sport, Sky Sports)", printed)


if __name__ == "__main__":
    unittest.main()
