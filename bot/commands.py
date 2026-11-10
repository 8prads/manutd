"""Perintah Telegram: /status /pause /resume /cooldown /batas /sumber /bantuan."""
import time
from datetime import datetime, timedelta, timezone

HELP = (
    "<b>Perintah bot</b>\n\n"
    "/status - ringkasan kondisi bot\n"
    "/pause - hentikan pengiriman sementara\n"
    "/resume - lanjutkan pengiriman\n"
    "/cooldown 15 - atur cooldown topik (menit, 1-120)\n"
    "/batas 10 - atur maksimal pesan biasa per jam (1-60)\n"
    "/sumber - daftar sumber bermasalah\n\n"
    "Perintah dibaca setiap siklus (sekitar 5 menit)."
)


def _wib(ts):
    return datetime.fromtimestamp(ts, timezone(timedelta(hours=7))).strftime("%d/%m %H:%M WIB") if ts else "-"


def reply_for(cmd, args, state, cfg, now):
    ov = state["override"]
    if cmd in ("/start", "/bantuan", "/help"):
        return HELP
    if cmd == "/pause":
        state["paused"] = True
        return "Pengiriman dihentikan. Kirim /resume untuk melanjutkan."
    if cmd == "/resume":
        state["paused"] = False
        return "Pengiriman dilanjutkan."
    if cmd in ("/cooldown", "/batas"):
        key, lo, hi, unit = (("cooldown_minutes", 1, 120, "menit") if cmd == "/cooldown"
                             else ("max_per_hour", 1, 60, "pesan per jam"))
        if not args or not args[0].isdigit() or not lo <= int(args[0]) <= hi:
            return f"Format: {cmd} <angka {lo}-{hi}>"
        ov[key] = int(args[0])
        return f"Diatur ke {args[0]} {unit}."
    if cmd == "/sumber":
        bad = [f"- {k} ({v['fails']}x gagal)" for k, v in state["feeds"].items() if v.get("fails", 0) >= 3]
        return "Sumber bermasalah:\n" + "\n".join(bad) if bad else "Semua sumber sehat."
    if cmd == "/status":
        day = now - 86400
        sent = sum(1 for s in state["stories"].values() if s["status"] == "sent" and (s["sent_at"] or 0) >= day)
        pend = sum(1 for s in state["stories"].values() if s["status"] == "pending")
        bad = sum(1 for v in state["feeds"].values() if v.get("fails", 0) >= 3)
        return (f"<b>Status bot</b>\nMode: {'DIJEDA' if state['paused'] else 'aktif'}\n"
                f"Terakhir berjalan: {_wib(state['last_run'])}\n"
                f"Terkirim 24 jam: {sent}\nMenunggu: {pend}\n"
                f"Cooldown: {ov.get('cooldown_minutes', cfg['cooldown']['minutes'])} menit\n"
                f"Batas: {ov.get('max_per_hour', cfg['rate']['max_per_hour'])} pesan/jam\n"
                f"Sumber bermasalah: {bad}")
    return None


def handle(tg, state, cfg, chat_id, log=print):
    for u in tg.updates(state["tg_offset"]):
        state["tg_offset"] = u["update_id"] + 1
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) != str(chat_id):
            continue
        text = (m.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        cmd, *args = text.split()
        resp = reply_for(cmd.split("@")[0].lower(), args, state, cfg, time.time())
        if resp:
            tg.send(resp)
            log(f"perintah {cmd}")
