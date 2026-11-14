"""Pengingat pertandingan: jadwal bulanan, H-1, 1 jam sebelum kick-off, lineup resmi, dan perubahan jadwal."""
import html
from datetime import datetime

from . import football as F
from .reminders import WIB

DEFAULTS = {"refresh_hours": 3, "monthly_hour_wib": 7, "lineup_start_minutes": 90}


def _msg(label, body, provider):
    return f"<b>[{label}]</b>\n\n{body}\n\n<i>({html.escape(provider)})</i>"


def _vs(f):
    return f"{html.escape(f['home'])} vs {html.escape(f['away'])} ({html.escape(f['comp'])})"


def run(tg, state, cfg, now_ts, fixtures_fn=None, lineup_fn=None, log=print):
    c = {**DEFAULTS, **(cfg.get("football") or {})}
    fixtures_fn = fixtures_fn or F.get_fixtures
    lineup_fn = lineup_fn or F.get_lineup
    md = state.setdefault("matchday", {})
    md.setdefault("fixtures", [])
    md.setdefault("sent", {})
    now = datetime.fromtimestamp(now_ts, WIB)

    # 1. perbarui jadwal dan deteksi perubahan jam
    if now_ts - md.get("fetched", 0) >= c["refresh_hours"] * 3600:
        try:
            provider, fx = fixtures_fn(45)
        except Exception as e:
            md["fetched"] = now_ts - c["refresh_hours"] * 3600 + 900  # coba lagi 15 menit kemudian
            md["error"] = str(e)[:150]
            log(f"jadwal gagal diperbarui: {md['error']}")
        else:
            old = {F.fixture_key(f): f["ts"] for f in md["fixtures"]}
            for f in fx:
                k = F.fixture_key(f)
                if k in old and abs(old[k] - f["ts"]) >= 300 and f["ts"] > now_ts:
                    tg.send(_msg("JADWAL BERUBAH", f"{_vs(f)}\nSebelumnya: {F.fmt_when(old[k])}\nSekarang: {F.fmt_when(f['ts'])}", provider))
            md.update(fixtures=fx, fetched=now_ts, provider=provider, error="")
    fixtures, provider = md["fixtures"], md.get("provider", "?")
    sent = md["sent"]

    # 2. jadwal bulanan otomatis tiap tanggal 1
    ym = now.strftime("%Y-%m")
    if now.day == 1 and now.hour >= c["monthly_hour_wib"] and md.get("monthly") != ym and fixtures:
        month = [f for f in fixtures if datetime.fromtimestamp(f["ts"], WIB).strftime("%Y-%m") == ym]
        tg.send(_msg("JADWAL BULANAN", F.fmt_schedule(month, f"{F.BULAN[now.month - 1]} {now.year}"), provider))
        md["monthly"] = ym

    # 3. pengingat dan lineup
    for f in fixtures:
        if f["state"] != "pre" or f["ts"] < now_ts - 600:
            continue
        ko, key = f["ts"], F.fixture_key(f)
        tag = f"{key}|{datetime.fromtimestamp(ko, WIB):%Y%m%d}"
        venue = f" Stadion: {html.escape(f['venue'])}." if f["venue"] else ""
        where = "KANDANG" if f["mu_home"] else "TANDANG"
        if ko - 86400 <= now_ts < ko - 86400 + 14400 and f"h1|{tag}" not in sent:
            tg.send(_msg("PENGINGAT", f"Besok: {_vs(f)}\nKick-off {F.fmt_when(ko)}, {where}.{venue}", provider))
            sent[f"h1|{tag}"] = now_ts
        lineup_ready = f"lineup|{tag}" in sent
        if ko - 3600 <= now_ts < ko - 3600 + 1800 and f"h60|{tag}" not in sent:
            note = "Lineup resmi sudah diumumkan (lihat pesan [LINEUP])." if lineup_ready else "Lineup resmi belum diumumkan; akan dikirim begitu keluar."
            tg.send(_msg("PENGINGAT", f"1 jam lagi: {_vs(f)}\nKick-off {F.fmt_when(ko)}, {where}.\n{note}", provider))
            sent[f"h60|{tag}"] = now_ts
        if ko - c["lineup_start_minutes"] * 60 <= now_ts < ko + 600 and not lineup_ready:
            allow = now_ts - md.get("apif_poll", 0) >= 600
            if allow:
                md["apif_poll"] = now_ts
            try:
                prov, lu = lineup_fn(f, allow_apif=allow)
            except Exception:
                continue  # belum diumumkan
            tg.send(F.fmt_lineup(f, lu, prov))
            sent[f"lineup|{tag}"] = now_ts

    for k in [k for k, v in sent.items() if now_ts - v > 10 * 86400]:
        del sent[k]
