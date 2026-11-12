import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bot import sources as SRC  # noqa: E402

T0 = 1_800_000_000.0  # 2027-01-15 ~ tengah hari UTC


class Err(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.response = type("R", (), {"status_code": code})()


def run(src, state, now, fetcher=None):
    fetcher = fetcher or (lambda s, st, c, e: [])
    with mock.patch.object(SRC.time, "time", return_value=now), mock.patch.dict(SRC.FETCHERS, {"gnews_api": fetcher}):
        _, res = SRC.fetch_all([src], state, {}, {"K": "x"}, log=lambda *a: None)
    return res[src["id"]]


class TestThrottle(unittest.TestCase):
    def setUp(self):
        self.src = {"id": "g", "type": "gnews_api", "key_env": "K", "tier": 3, "min_interval_minutes": 20}

    def test_min_interval(self):
        st = {"feeds": {}}
        self.assertEqual(run(self.src, st, T0)[0], "ok")
        self.assertEqual(run(self.src, st, T0 + 5 * 60)[0], "lewati")
        self.assertEqual(run(self.src, st, T0 + 21 * 60)[0], "ok")

    def test_daily_cap_resets_next_day(self):
        src = {**self.src, "min_interval_minutes": 0, "max_per_day": 2}
        st = {"feeds": {}}
        self.assertEqual([run(src, st, T0 + i)[0] for i in range(3)], ["ok", "ok", "lewati"])
        self.assertEqual(run(src, st, T0 + 86400)[0], "ok")

    def test_quota_error_backs_off_until_tomorrow_without_failure(self):
        st = {"feeds": {}}
        def boom(s, stt, c, e):
            raise Err(429)
        status, info = run(self.src, st, T0, boom)
        self.assertEqual((status, info), ("lewati", "kuota habis"))
        self.assertEqual(run(self.src, st, T0 + 3600)[0], "lewati")
        self.assertEqual(run(self.src, st, T0 + 86400 + 60)[0], "ok")

    def test_other_errors_still_count_as_failure(self):
        st = {"feeds": {}}
        def boom(s, stt, c, e):
            raise Err(500)
        self.assertEqual(run(self.src, st, T0, boom)[0], "gagal")

    def test_active_hours_wib(self):
        # 2027-01-15 05:00 UTC = 12:00 WIB; 2027-01-15 14:00 UTC = 21:00 WIB; 2027-01-15 23:00 UTC = 06:00 WIB (16 Jan)
        day = T0 - (T0 % 86400)
        self.assertTrue(SRC._in_hours("12-6", day + 5 * 3600))
        self.assertTrue(SRC._in_hours("12-6", day + 14 * 3600))
        self.assertFalse(SRC._in_hours("12-6", day + 23 * 3600))
        self.assertFalse(SRC._in_hours("12-6", day + 3 * 3600))  # 10:00 WIB


if __name__ == "__main__":
    unittest.main()
