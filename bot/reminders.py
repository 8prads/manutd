"""Pengingat terjadwal ke Telegram, mis. masa berlaku token GitHub."""
import html
from datetime import date, datetime, time as dtime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember"]


def fmt_date(d):
    return f"{d.day} {BULAN[d.month - 1]} {d.year}"


def _to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v).strip())


def expiry_of(r, state):
    return _to_date(state.get("reminder_dates", {}).get(r["id"], r["kedaluwarsa"]))


def trigger_of(r, expiry):
    h, m = (int(x) for x in str(r.get("jam", "09:00")).split(":"))
    return datetime.combine(expiry - timedelta(days=int(r.get("hari_sebelum", 3))), dtime(h, m), tzinfo=WIB)


def build_message(r, expiry, today):
    isi = r["isi"].format(tanggal=fmt_date(expiry), sisa=(expiry - today).days)
    return f"<b>{html.escape(r['judul'])}</b>: <i>{html.escape(isi)}</i>"


def run(tg, state, cfg, now_ts):
    """Kirim pengingat yang sudah waktunya, satu kali per tanggal kedaluwarsa."""
    now = datetime.fromtimestamp(now_ts, WIB)
    sent = state.setdefault("reminders_sent", {})
    for r in cfg.get("reminders", []):
        expiry = expiry_of(r, state)
        key = f"{r['id']}:{expiry.isoformat()}"
        if key in sent or not (trigger_of(r, expiry) <= now < datetime.combine(expiry + timedelta(days=1), dtime(0, 0), tzinfo=WIB)):
            continue
        if tg.send(build_message(r, expiry, now.date())) is not None:
            sent[key] = now_ts


def command(args, state, cfg, now_ts):
    rems = {r["id"]: r for r in cfg.get("reminders", [])}
    today = datetime.fromtimestamp(now_ts, WIB).date()
    if not args:
        if not rems:
            return "Belum ada pengingat."
        lines = [f"- {i}: kedaluwarsa {fmt_date(expiry_of(r, state))}, "
                 f"pengingat {trigger_of(r, expiry_of(r, state)).strftime('%d/%m/%Y %H:%M')} WIB" for i, r in rems.items()]
        return "<b>Pengingat</b>\n" + "\n".join(lines) + "\n\nUbah: /pengingat token_github 2028-11-10"
    if len(args) != 2 or args[0] not in rems:
        return "Format: /pengingat <id> <TAHUN-BULAN-TANGGAL>\nId tersedia: " + ", ".join(rems)
    try:
        d = date.fromisoformat(args[1])
    except ValueError:
        return "Tanggal tidak valid. Contoh: /pengingat token_github 2028-11-10"
    if d <= today:
        return "Tanggal harus di masa depan."
    state.setdefault("reminder_dates", {})[args[0]] = d.isoformat()
    r = rems[args[0]]
    return (f"Pengingat {args[0]} diatur: kedaluwarsa {fmt_date(d)}, "
            f"dikirim {trigger_of(r, d).strftime('%d/%m/%Y %H:%M')} WIB.")
