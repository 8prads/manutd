"""Perintah Telegram: /status /pause /resume /cooldown /batas /sumber /bantuan."""
import html
import time
from datetime import datetime, timedelta, timezone

from . import reminders
from .pipeline import Pipeline

HELP = (
    "<b>Perintah bot</b>\n\n"
    "/status - ringkasan kondisi bot\n"
    "/pause - hentikan pengiriman sementara\n"
    "/resume - lanjutkan pengiriman\n"
    "/cooldown 15 - atur cooldown topik (menit, 1-120)\n"
    "/batas 10 - atur maksimal pesan biasa per jam (1-60)\n"
    "/sumber - daftar sumber bermasalah beserta penyebabnya\n"
    "/terakhir - 5 berita terakhir (sumber dan tanggal terbit)\n"
    "/menunggu - berita yang tertahan beserta alasannya\n"
    "/blokir 120 kata - blokir kata 30-360 menit (tanpa angka = permanen); /buka kata; /daftarblokir\n"
    "/jadwal - jadwal 30 hari ke depan; /klasemen pl|ucl|uel|laliga|seriea|bundesliga|ligue1; /statistik - pertandingan terakhir\n"
    "/diagnosa - uji sumber data pertandingan\n"
    "/opini - balas (quote) sebuah berita lalu kirim /opini untuk draf opini berpov Anda; "
    "tambahkan arah atau panjang bila perlu, mis. /opini singkat Carrick perlu diberi waktu "
    "(pilihan panjang: singkat, panjang, atau 3 kalimat)\n"
    "/pengingat - lihat atau ubah tanggal pengingat\n\n"
    "Perintah dibaca setiap siklus (sekitar 5 menit)."
)


def _ai_line(state):
    a = state.get("ai") or {}
    if not any(k != "day" for k in a):
        return "AI hari ini: belum ada panggilan"
    return (f"AI hari ini: Gemini {a.get('gemini_ok', 0)} ok/{a.get('gemini_fail', 0)} gagal; "
            f"Groq {a.get('groq_ok', 0)} ok/{a.get('groq_fail', 0)} gagal; "
            f"tautan Google News {a.get('decode_ok', 0)} terurai/{a.get('decode_fail', 0)} gagal")


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
    if cmd == "/pengingat":
        return reminders.command(args, state, cfg, now)
    if cmd == "/sumber":
        bad = [f"- {k} ({v['fails']}x): {html.escape(str(v.get('last_error', ''))[:80])}"
               for k, v in state["feeds"].items() if v.get("fails", 0) >= 3]
        return "Sumber bermasalah:\n" + "\n".join(bad) if bad else "Semua sumber sehat."
    if cmd == "/blokir":
        minutes = None
        if args and args[0].isdigit():
            minutes, args = int(args[0]), args[1:]
            if not 30 <= minutes <= 360:
                return "Durasi harus 30-360 menit. Contoh: /blokir 120 bruno contract"
        phrase = " ".join(args).lower().strip()
        if not phrase:
            return "Tulis kata yang diblokir. Contoh: /blokir bruno contract (permanen) atau /blokir 120 bruno contract"
        blocks = state.setdefault("blocks", [])
        blocks[:] = [b for b in blocks if b["phrase"] != phrase]
        if len(blocks) >= 50:
            return "Daftar blokir penuh (maksimal 50). Hapus dengan /buka kata."
        blocks.append({"phrase": phrase, "until": now + minutes * 60 if minutes else None})
        return f"Diblokir: {html.escape(phrase)} ({'permanen' if not minutes else f'{minutes} menit'}). Berita [RESMI] tetap dikirim."
    if cmd == "/buka":
        phrase = " ".join(args).lower().strip()
        blocks = state.setdefault("blocks", [])
        before = len(blocks)
        blocks[:] = [b for b in blocks if b["phrase"] != phrase]
        return "Blokir dibuka." if len(blocks) < before else "Frasa itu tidak ada di daftar. Lihat /daftarblokir."
    if cmd == "/daftarblokir":
        act = [b for b in state.get("blocks", []) if not b.get("until") or b["until"] > now]
        if not act:
            return "Tidak ada kata yang diblokir."
        return "<b>Daftar blokir</b>\n" + "\n".join(
            f"- {html.escape(b['phrase'])} ({'permanen' if not b.get('until') else f'{int((b['until'] - now) / 60) + 1} menit lagi'})" for b in act)
    if cmd in ("/jadwal", "/klasemen", "/statistik", "/diagnosa"):
        from . import football as F
        try:
            if cmd == "/diagnosa":
                return "<b>Diagnosa sumber data</b>\n" + "\n".join(html.escape(x) for x in F.diagnose())
            if cmd == "/jadwal":
                days = int(args[0]) if args and args[0].isdigit() else 30
                prov, fx = F.get_fixtures(min(max(days, 1), 60))
                cut = now + min(max(days, 1), 60) * 86400
                fx = [f for f in fx if now - 600 <= f["ts"] <= cut and f["state"] == "pre"]
                return F.fmt_schedule(fx, f"<b>Jadwal {min(max(days, 1), 60)} hari ke depan</b>") + f"\n\n<i>({prov})</i>"
            if cmd == "/klasemen":
                code = (args[0] if args else "pl").lower()
                if code not in F.LEAGUES:
                    return "Kode tersedia: " + ", ".join(F.LEAGUES)
                prov, title, rows = F.get_standings(code)
                return F.fmt_standings(title, rows, prov)
            prov, header, res = F.get_stats()
            return F.fmt_stats(header, res, prov)
        except Exception as e:
            return "Data belum bisa diambil: " + html.escape(str(e)[:300]) + "\nCoba /diagnosa untuk melihat penyebabnya."
    if cmd == "/menunggu":
        rep = Pipeline(cfg, state, None, None, now=lambda: now).pending_report()
        if not rep:
            return "Tidak ada berita yang menunggu."
        return "<b>Berita menunggu</b>\n\n" + "\n\n".join(
            f"[{lab}] {html.escape(t[:80])}\n{age} mnt: {html.escape(reason)}" for t, age, reason, lab in rep)
    if cmd == "/terakhir":
        sent = sorted((s for s in state["stories"].values() if s["status"] == "sent"),
                      key=lambda s: s["sent_at"], reverse=True)[:5]
        if not sent:
            return "Belum ada berita terkirim."
        return "<b>5 berita terakhir</b>\n\n" + "\n\n".join(
            f"[{s['label']}] {html.escape(s['title'][:90])}\nTerbit: {_wib(s['pub'])}\n"
            f"Sumber: {html.escape(', '.join(x['name'] + ' [' + x.get('sid', '?') + ']' for x in s['sources']))}\n"
            f"{html.escape(s['sources'][0]['url'])}"
            for s in sent)
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
                f"Sumber bermasalah: {bad}\n{_ai_line(state)}")
    return None


def handle(tg, state, cfg, chat_id, log=print):
    """Proses perintah masuk. Kembalikan daftar pekerjaan /opini untuk diproses main."""
    jobs = []
    for u in tg.updates(state["tg_offset"]):
        state["tg_offset"] = u["update_id"] + 1
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) != str(chat_id):
            continue
        text = (m.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        cmd, _, notes = text.partition(" ")
        c, mid = cmd.split("@")[0].lower(), m.get("message_id")
        if c == "/opini":
            q = m.get("reply_to_message")
            if not q or not (q.get("text") or q.get("caption")):
                tg.send("Balas (quote) pesan berita yang ingin dibuatkan opini, lalu kirim /opini. "
                        "Tambahkan arah opini bila perlu, misalnya: /opini Carrick perlu diberi waktu.", reply_to=mid)
            else:
                jobs.append({"cmd_id": mid, "quoted": q, "notes": notes.strip()})
                log("perintah /opini")
            continue
        resp = reply_for(c, notes.split(), state, cfg, time.time())
        if resp:
            tg.send(resp, reply_to=mid)
            log(f"perintah {cmd}")
    return jobs
