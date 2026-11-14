"""Ringkasan pagi: berita terpenting 24 jam terakhir."""
import html
from datetime import datetime

from . import text as T
from .reminders import WIB


def _first(text, limit=170):
    text = " ".join((text or "").split())
    cut = text[:limit]
    return cut if len(text) <= limit else (cut[: cut.rfind(" ")] + "...")


def run(tg, state, cfg, now_ts, pipe):
    d = {**{"hour_wib": 7, "top": 8}, **(cfg.get("digest") or {})}
    now = datetime.fromtimestamp(now_ts, WIB)
    today = now.strftime("%Y-%m-%d")
    if now.hour < d["hour_wib"] or state.get("digest_day") == today:
        return
    state["digest_day"] = today
    sent = [s for s in state["stories"].values() if s["status"] == "sent" and (s["sent_at"] or 0) >= now_ts - 86400]
    if not sent:
        return
    sent.sort(key=lambda s: (-T.rank(s["label"]), -len(s["sources"]), -s["sent_at"]))
    lines = [f"{i}. [{s['label']}] {html.escape(_first(s['body'] or s['title']))}\n   ({html.escape(', '.join(pipe.source_names(s)))})"
             for i, s in enumerate(sent[: d["top"]], 1)]
    tg.send("<b>[RINGKASAN PAGI]</b>\n\n" + "\n\n".join(lines) + "\n\n<i>(Berita terpenting 24 jam terakhir)</i>")
