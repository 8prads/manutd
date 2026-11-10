import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bot import reminders as R  # noqa: E402
from bot import state as S  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml"), encoding="utf-8"))
WIB = timezone(timedelta(hours=7))


class TG:
    def __init__(self):
        self.out = []

    def send(self, t):
        self.out.append(t)
        return 1


def ts(y, m, d, h=9, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=WIB).timestamp()


class TestReminders(unittest.TestCase):
    def test_sent_once_three_days_before(self):
        st, tg = S.new_state(), TG()
        R.run(tg, st, CFG, ts(2027, 11, 6, 23, 59))
        self.assertEqual(tg.out, [])
        R.run(tg, st, CFG, ts(2027, 11, 7, 8, 59))
        self.assertEqual(tg.out, [])
        R.run(tg, st, CFG, ts(2027, 11, 7, 9, 5))
        self.assertEqual(len(tg.out), 1)
        self.assertTrue(tg.out[0].startswith("<b>Token GitHub akan kedaluwarsa</b>: <i>"))
        self.assertIn("10 November 2027 (3 hari lagi)", tg.out[0])
        R.run(tg, st, CFG, ts(2027, 11, 8, 9, 5))
        self.assertEqual(len(tg.out), 1)
        R.run(tg, st, CFG, ts(2027, 11, 12))
        self.assertEqual(len(tg.out), 1)

    def test_change_date_by_command_resets(self):
        st, tg = S.new_state(), TG()
        now = ts(2026, 11, 10)
        self.assertIn("diatur", R.command(["token_github", "2028-11-10"], st, CFG, now))
        R.run(tg, st, CFG, ts(2027, 11, 7, 10))
        self.assertEqual(tg.out, [])
        R.run(tg, st, CFG, ts(2028, 11, 7, 10))
        self.assertEqual(len(tg.out), 1)
        self.assertIn("10 November 2028", tg.out[0])

    def test_command_validation_and_list(self):
        st = S.new_state()
        now = ts(2026, 11, 10)
        self.assertIn("token_github", R.command([], st, CFG, now))
        self.assertIn("Format", R.command(["salah", "2028-11-10"], st, CFG, now))
        self.assertIn("tidak valid", R.command(["token_github", "10-11-2028"], st, CFG, now))
        self.assertIn("masa depan", R.command(["token_github", "2020-01-01"], st, CFG, now))


if __name__ == "__main__":
    unittest.main()
