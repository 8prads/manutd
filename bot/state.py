"""Penyimpanan state (JSON). Di GitHub Actions disimpan di branch `state`."""
import json
import os


def new_state():
    return {
        "version": 1, "init": False, "paused": False, "override": {},
        "tg_offset": 0, "seen": {}, "df": {}, "n_docs": 0,
        "stories": {}, "topics": [], "caps": {}, "sent_log": [], "feeds": {},
        "last_run": 0, "runs": 0, "reminders_sent": {}, "reminder_dates": {}, "blocks": [], "ai": {}, "matchday": {}, "digest_day": "",
    }


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        base = new_state()
        base.update(data)
        return base
    except (FileNotFoundError, ValueError):
        return new_state()


def save(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
