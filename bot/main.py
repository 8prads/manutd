"""Titik masuk: satu siklus (ambil, saring, kirim, simpan). Dijalankan GitHub Actions tiap beberapa menit."""
import html
import os
import time
from pathlib import Path

import yaml

from . import commands, opini, reminders, state as S
from .llm import make_summarizer
from .pipeline import Pipeline
from .sources import fetch_all
from .telegram import Telegram

ROOT = Path(__file__).resolve().parent.parent


def load_yaml(name):
    with open(ROOT / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def update_health(results, state, tg, threshold, quiet=()):
    """Peringatan digabung dalam satu pesan. Sumber opsional (quiet) tidak memicu peringatan."""
    failed, recovered = [], []
    for sid, (status, info) in results.items():
        if status == "lewati":
            if sid in state["feeds"]:
                state["feeds"][sid].update(fails=0, alerted=False)  # bukan kegagalan: bersihkan hitungan lama
            continue
        rec = state["feeds"].setdefault(sid, {})
        if status == "ok":
            if rec.get("alerted") and sid not in quiet:
                recovered.append(sid)
            rec.update(fails=0, alerted=False)
        else:
            rec["fails"] = rec.get("fails", 0) + 1
            rec["last_error"] = info
            if rec["fails"] >= threshold and not rec.get("alerted"):
                rec["alerted"] = True
                if sid not in quiet:
                    failed.append((sid, info))
    if failed:
        lines = "\n".join(f"- {sid}: {html.escape(str(info)[:90])}" for sid, info in failed)
        tg.send(f"<b>[PERINGATAN]</b>\n\nSumber berikut gagal diakses {threshold} siklus berturut-turut:\n{lines}")
    if recovered:
        tg.send("<b>[SUMBER PULIH]</b>\n\nKembali normal: " + ", ".join(recovered))


def main():
    env = os.environ
    dry = env.get("DRY_RUN") == "1"
    cfg, srcs = load_yaml("settings.yaml"), load_yaml("sources.yaml")["sources"]
    path = env.get("STATE_PATH", str(ROOT / "data" / "state.json"))
    state = S.load(path)
    tg = Telegram(env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", ""), dry=dry)

    pipe = Pipeline(cfg, state, tg, make_summarizer(cfg, env), log=print)
    jobs = commands.handle(tg, state, cfg, env.get("TELEGRAM_CHAT_ID", ""))
    if jobs:
        opini.process(jobs, state, cfg, env, tg, pipe)
    reminders.run(tg, state, cfg, time.time())
    if state["paused"]:
        print("dijeda")
        state["last_run"] = time.time()
        S.save(path, state)
        return

    active = {x["id"] for x in srcs if x.get("enabled") is not False}
    state["feeds"] = {k: v for k, v in state["feeds"].items() if k in active}
    items, results = fetch_all(srcs, state, cfg, env)
    quiet = {x["id"] for x in srcs if x.get("quiet")}
    update_health(results, state, tg, cfg["health"]["alert_after_failures"], quiet)

    # Sumber yang baru pertama kali terbaca dicatat diam-diam (mencegah berita lama membanjir)
    feeds = state["feeds"]
    if state["init"] and not any(v.get("seeded") for v in feeds.values()):
        for v in feeds.values():  # migrasi dari versi lama
            v["seeded"] = True
    fresh = {sid for sid, (st, _) in results.items() if st == "ok" and not feeds.setdefault(sid, {}).get("seeded")}
    if state["init"] and fresh:
        pipe.bootstrap([i for i in items if i.source_id in fresh])
        items = [i for i in items if i.source_id not in fresh]

    if not state["init"]:
        pipe.bootstrap(items)
        state["init"] = True
        okc = sum(1 for v in results.values() if v[0] == "ok")
        tg.send(f"<b>[BOT AKTIF]</b>\n\nBot berita Man Utd berjalan. {okc} dari {len(results)} sumber terbaca. "
                "Berita yang ada saat ini dicatat sebagai sudah dilihat, dan hanya berita baru yang akan dikirim.\n\n"
                "<i>(Kirim /bantuan untuk daftar perintah)</i>")
    else:
        pipe.ingest(items)
        pipe.dispatch()
        pipe.refresh_edits()
    for sid in fresh:
        feeds[sid]["seeded"] = True
    pipe.prune()
    state["last_run"], state["runs"] = time.time(), state["runs"] + 1
    S.save(path, state)


if __name__ == "__main__":
    main()
