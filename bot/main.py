"""Titik masuk: satu siklus (ambil, saring, kirim, simpan). Dijalankan GitHub Actions tiap beberapa menit."""
import os
import time
from pathlib import Path

import yaml

from . import commands, state as S
from .llm import make_summarizer
from .pipeline import Pipeline
from .sources import fetch_all
from .telegram import Telegram

ROOT = Path(__file__).resolve().parent.parent


def load_yaml(name):
    with open(ROOT / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def update_health(results, state, tg, threshold):
    for sid, (status, info) in results.items():
        if status == "lewati":
            continue
        rec = state["feeds"].setdefault(sid, {})
        if status == "ok":
            if rec.get("alerted"):
                tg.send(f"<b>[SUMBER PULIH]</b>\n\n{sid} kembali normal.")
            rec.update(fails=0, alerted=False)
        else:
            rec["fails"] = rec.get("fails", 0) + 1
            rec["last_error"] = info
            if rec["fails"] >= threshold and not rec.get("alerted"):
                tg.send(f"<b>[PERINGATAN]</b>\n\nSumber {sid} gagal diakses {rec['fails']} siklus berturut-turut.\n"
                        f"Penyebab terakhir: {info}")
                rec["alerted"] = True


def main():
    env = os.environ
    dry = env.get("DRY_RUN") == "1"
    cfg, srcs = load_yaml("settings.yaml"), load_yaml("sources.yaml")["sources"]
    path = env.get("STATE_PATH", str(ROOT / "data" / "state.json"))
    state = S.load(path)
    tg = Telegram(env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", ""), dry=dry)

    commands.handle(tg, state, cfg, env.get("TELEGRAM_CHAT_ID", ""))
    if state["paused"]:
        print("dijeda")
        state["last_run"] = time.time()
        S.save(path, state)
        return

    items, results = fetch_all(srcs, state, cfg, env)
    update_health(results, state, tg, cfg["health"]["alert_after_failures"])
    pipe = Pipeline(cfg, state, tg, make_summarizer(cfg, env), log=print)

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
    pipe.prune()
    state["last_run"], state["runs"] = time.time(), state["runs"] + 1
    S.save(path, state)


if __name__ == "__main__":
    main()
