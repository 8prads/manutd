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
    "/nama - lihat daftar kata kunci pemain/staf; /nama tambah Hojlund; /nama hapus Rashford; /nama reset\n"
    "/jurnalis - lihat daftar jurnalis tepercaya; /jurnalis tambah Nama; /jurnalis hapus Nama; /jurnalis reset\n"
    "/daftar - seluruh nama pemain, staf, jurnalis, dan pundit yang dikenali bot\n"
    "/dibuang - 10 berita terakhir yang dibuang beserta alasannya\n"
    "/ai - status tiap penyedia AI; /ai tutup cerebras 30; /ai buka cerebras (atau semua)\n"
    "/opini - balas (quote) sebuah berita lalu kirim /opini untuk draf opini berpov Anda; "
    "tambahkan arah atau panjang bila perlu, mis. /opini singkat Carrick perlu diberi waktu "
    "(pilihan panjang: singkat, panjang, atau 3 kalimat)\n"
    "/pengingat - lihat atau ubah tanggal pengingat\n\n"
    "Perintah dibaca setiap siklus (sekitar 5 menit)."
)


def _ai_line(state, cfg=None):
    a = state.get("ai") or {}
    if not any(k != "day" for k in a):
        return "AI hari ini: belum ada panggilan"
    from . import llm
    names = list(((cfg or {}).get("llm") or {}).get("providers") or ["gemini", "groq"])
    parts = [f"{llm.label_of(n)} {a.get(n + '_ok', 0)} ok/{a.get(n + '_fail', 0)} gagal" for n in names
             if a.get(n + "_ok", 0) or a.get(n + "_fail", 0)]
    chk = [f"{a.get('check_ok', 0)} ok", f"{a.get('check_issue', 0)} bermasalah", f"{a.get('check_skip', 0)} dilewati"]
    return ("AI hari ini: " + "; ".join(parts or ["belum ada panggilan"]) + f"\nPemeriksaan AI: {', '.join(chk)}"
            f"\nTautan Google News {a.get('decode_ok', 0)} terurai/{a.get('decode_fail', 0)} gagal")


def _wib(ts):
    return datetime.fromtimestamp(ts, timezone(timedelta(hours=7))).strftime("%d/%m %H:%M WIB") if ts else "-"


def _decode_line(state):
    """Uji pengurai Google News pada tautan terbaru yang tersimpan di state."""
    from . import llm
    stories = sorted(state["stories"].values(), key=lambda s: s.get("first_seen", 0), reverse=True)
    urls = [x["url"] for s in stories for x in s["sources"] if "news.google.com" in x.get("url", "")][:1]
    try:
        return f"OK  Google News decode: {llm.decode_check(urls)}"
    except Exception as e:
        return f"GAGAL  Google News decode: {type(e).__name__} {str(e)[:150]}"


def _edit_list(cmd, title, ex_add, ex_del, args, state, add_key, rem_key, base, names):
    """Daftar nama yang bisa diubah lewat Telegram (dipakai /nama dan /jurnalis): tambah, hapus, reset, atau tampilkan."""
    sub, term = (args[0].lower() if args else "daftar"), " ".join(args[1:]).strip()
    add, rem = state.setdefault(add_key, []), state.setdefault(rem_key, [])
    low = lambda xs: [x.lower() for x in xs]
    if sub == "tambah":
        if not term:
            return f"Format: {cmd} tambah <nama>, misalnya {cmd} tambah {ex_add}"
        if term.lower() in low(rem):
            rem[:] = [x for x in rem if x.lower() != term.lower()]
            return f"{html.escape(term)} dimasukkan kembali. Berlaku mulai siklus berikutnya."
        if term.lower() in low(base) + low(add):
            return "Nama itu sudah ada di daftar."
        add.append(term)
        return f"Ditambahkan: {html.escape(term)}. Berlaku mulai siklus berikutnya."
    if sub == "hapus":
        if not term:
            return f"Format: {cmd} hapus <nama>, misalnya {cmd} hapus {ex_del}"
        if term.lower() in low(add):
            add[:] = [x for x in add if x.lower() != term.lower()]
            return f"Dihapus dari tambahan: {html.escape(term)}."
        if term.lower() in low(base):
            if term.lower() in low(rem):
                return "Nama itu sudah dikeluarkan."
            rem.append(term)
            return f"Dikeluarkan: {html.escape(term)}. Berlaku mulai siklus berikutnya."
        return f"Nama itu tidak ada di daftar. Lihat {cmd}."
    if sub == "reset":
        add.clear()
        rem.clear()
        return "Perubahan lewat Telegram dibatalkan; daftar kembali mengikuti config/settings.yaml."
    return (f"<b>{title} ({len(names)})</b>\n" + html.escape(", ".join(names))
            + (f"\n\nDitambah lewat Telegram: {html.escape(', '.join(add))}" if add else "")
            + (f"\nDikeluarkan lewat Telegram: {html.escape(', '.join(rem))}" if rem else "")
            + f"\n\nUbah: {cmd} tambah <nama>, {cmd} hapus <nama>, {cmd} reset")


def _video_line(cfg, state):
    """Uji pemantauan YouTube untuk /diagnosa: kanal yang dikenali dan pemakaian unit."""
    import os
    from . import video
    if not os.environ.get("YOUTUBE_API_KEY"):
        return "LEWATI  YouTube: tanpa kunci YOUTUBE_API_KEY"
    try:
        return f"OK  YouTube: {video.check(cfg, os.environ, state)}"
    except Exception as e:
        return f"GAGAL  YouTube: {type(e).__name__} {str(e)[:150]}"


def _ai_lines(cfg):
    """Uji satu panggilan kecil per penyedia AI untuk /diagnosa."""
    import os
    from . import llm
    return llm.ai_ping(cfg, os.environ)


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
    if cmd == "/nama":
        from . import text as T
        return _edit_list("/nama", "Kata kunci nama", "Hojlund", "Rashford", args, state, "names_add", "names_remove",
                          list(cfg.get("mu_names", [])), T.effective_names(cfg, state))
    if cmd == "/jurnalis":
        from . import text as T
        return _edit_list("/jurnalis", "Jurnalis tepercaya", "Jamie Jackson", "Mike Keegan", args, state,
                          "journalists_add", "journalists_remove", list(cfg["people"]["trusted_journalists"]),
                          T.effective_journalists(cfg, state))
    if cmd == "/daftar":
        from . import text as T
        sec = lambda t, xs: f"<b>{t} ({len(xs)})</b>\n" + html.escape(", ".join(xs))
        return "\n\n".join([sec("Pemain dan staf", T.effective_names(cfg, state)),
                             sec("Jurnalis tepercaya", T.effective_journalists(cfg, state)),
                             sec("Pundit", cfg["people"]["pundits"])])
    if cmd == "/ai":
        import os
        from . import llm
        provs, blocks = cfg["llm"]["providers"], state.setdefault("ai_block", {})
        sub, name = (args[0].lower() if args else ""), (args[1].lower() if len(args) > 1 else "")
        if sub in ("buka", "tutup"):
            if sub == "buka" and name == "semua":
                blocks.clear()
                llm._SKIP.clear()
                return "Semua blokir penyedia AI dibuka."
            if name not in provs:
                return "Format: /ai buka <nama|semua> atau /ai tutup <nama> [hari]. Nama: " + ", ".join(provs)
            if sub == "buka":
                for k in [k for k in blocks if k == name or k.startswith(name + ":")]:
                    del blocks[k]
                return f"{llm.label_of(name)} dibuka kembali."
            days = int(args[2]) if len(args) > 2 and args[2].isdigit() else 30
            blocks[name] = now + days * 86400
            return f"{llm.label_of(name)} ditutup {days} hari. Buka lagi dengan /ai buka {name}."
        return ("<b>Penyedia AI</b>\n" + "\n".join(html.escape(x) for x in llm.ai_status(cfg, os.environ, state))
                + "\n\nUbah: /ai tutup <nama> [hari], /ai buka <nama|semua>")
    if cmd == "/dibuang":
        rows = state.get("dropped_log", [])[:10]
        if not rows:
            return "Belum ada berita yang dibuang."
        return "<b>10 berita terakhir yang dibuang</b>\n\n" + "\n\n".join(
            f"[{html.escape(x['why'])}] {html.escape(x['title'][:90])}\n{_wib(x['t'])} · {html.escape(', '.join(x.get('src', [])))}\n"
            f"{html.escape(x.get('url', ''))}" for x in rows)
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
                return "<b>Diagnosa sumber data</b>\n" + "\n".join(html.escape(x) for x in F.diagnose() + [_decode_line(state)] + [_video_line(cfg, state)] + _ai_lines(cfg))
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
                f"Sumber bermasalah: {bad}\n{_ai_line(state, cfg)}")
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
            from .opini import split_message
            for i, part in enumerate(split_message(resp)):
                tg.send(part, reply_to=mid if i == 0 else None)
            log(f"perintah {cmd}")
    return jobs
