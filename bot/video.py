"""Pantau kanal YouTube: wawancara, konferensi pers, dan siaran langsung pemain atau petinggi Man Utd.
Memakai YouTube Data API v3 (kunci gratis, kuota bawaan 10.000 unit per hari; pencarian punya jatah sendiri).
Pesan dibuat tanpa AI, jadi tidak memakai kuota AI."""
import html
import re
import time

from . import football as F
from . import llm
from .sources import parse_date

API = "https://www.googleapis.com/youtube/v3"
DEFAULTS = {"poll_minutes": 10, "search_every_minutes": 60, "max_search_per_day": 80, "max_units_per_day": 8000,
            "remind_minutes": 30, "max_age_hours": 24, "recheck_hours": 6}
INTERVIEW = re.compile(r"\b(press conference|interview|speaks?|speaking|reacts?|reaction|says|post[- ]match|pre[- ]match|q&a|exclusive|"
                       r"in conversation)\b", re.I)


class ApiError(Exception):
    def __init__(self, status, text):
        super().__init__(f"HTTP {status} {text[:120]}")
        self.status, self.text = status, text


class QuotaLimit(Exception):
    """Batas pemakaian harian buatan sendiri tercapai."""


def _get(path, key, **params):
    import requests
    r = requests.get(f"{API}/{path}", params={**params, "key": key}, timeout=(5, 15))
    if r.status_code != 200:
        raise ApiError(r.status_code, r.text)
    return r.json()


def _state(state):
    vs = state.setdefault("video", {})
    for k in ("channels", "seen", "watch", "sent", "resolve_fail", "last_search"):
        vs.setdefault(k, {})
    return vs


def _spend(vs, c, n=1, search=False):
    day = time.strftime("%Y-%m-%d", time.gmtime())
    for key, cap in (("units", c["max_units_per_day"]), ("searches", c["max_search_per_day"])):
        rec = vs.setdefault(key, {})
        if rec.get("day") != day:
            rec.clear()
            rec.update(day=day, n=0)
    if search:
        if vs["searches"]["n"] >= c["max_search_per_day"]:
            raise QuotaLimit("jatah pencarian harian habis")
        vs["searches"]["n"] += 1
    else:
        if vs["units"]["n"] + n > c["max_units_per_day"]:
            raise QuotaLimit("batas unit harian tercapai")
        vs["units"]["n"] += n


def _title_ok(name, title):
    a, b = name.casefold(), (title or "").casefold()
    return a in b or b in a


def _pack(it):
    cid = it["id"]
    return {"id": cid, "title": it["snippet"]["title"], "uploads": "UU" + cid[2:],
            "subs": int((it.get("statistics") or {}).get("subscriberCount") or 0)}


def resolve_channel(ch, key, vs, c):
    """Cari kanal: handle dulu, lalu pencarian nama (kanal berjudul sama dengan pelanggan terbanyak)."""
    name, items = ch["name"], []
    if ch.get("id") or ch.get("handle"):
        _spend(vs, c)
        params = {"id": ch["id"]} if ch.get("id") else {"forHandle": ch["handle"]}
        items = _get("channels", key, part="snippet,statistics", **params).get("items", [])
        for it in items:
            if _title_ok(name, it["snippet"]["title"]):
                return _pack(it)
    _spend(vs, c, search=True)
    found = _get("search", key, part="snippet", q=name, type="channel", maxResults=5).get("items", [])
    ids = [x["id"]["channelId"] for x in found if (x.get("id") or {}).get("channelId")]
    if not ids:
        return None
    _spend(vs, c)
    cands = _get("channels", key, part="snippet,statistics", id=",".join(ids)).get("items", [])
    pool = [it for it in cands if it["snippet"]["title"].casefold() == name.casefold()] or \
           [it for it in cands if _title_ok(name, it["snippet"]["title"])]
    return _pack(max(pool, key=lambda it: int((it.get("statistics") or {}).get("subscriberCount") or 0))) if pool else None


def ensure_channels(cfg, key, vs, c, now, only_cached=False):
    """Pastikan tiap kanal di config sudah dikenali; yang gagal dicoba lagi setelah recheck_hours."""
    for ch in c.get("channels") or []:
        name = ch["name"]
        if name in vs["channels"] or only_cached:
            continue
        if now - vs["resolve_fail"].get(name, 0) < c["recheck_hours"] * 3600:
            continue
        info = resolve_channel(ch, key, vs, c)
        if info:
            vs["channels"][name] = info
        else:
            vs["resolve_fail"][name] = now


def _uploads(info, key, vs, c):
    _spend(vs, c)
    j = _get("playlistItems", key, part="snippet", playlistId=info["uploads"], maxResults=8)
    return [(it["snippet"]["resourceId"]["videoId"]) for it in j.get("items", []) if (it.get("snippet") or {}).get("resourceId")]


def _upcoming(info, key, vs, c):
    _spend(vs, c, search=True)
    j = _get("search", key, part="snippet", channelId=info["id"], eventType="upcoming", type="video", maxResults=5)
    return [x["id"]["videoId"] for x in j.get("items", []) if (x.get("id") or {}).get("videoId")]


def _details(ids, key, vs, c):
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        _spend(vs, c)
        j = _get("videos", key, part="snippet,liveStreamingDetails", id=",".join(chunk))
        for it in j.get("items", []):
            sn, ls = it.get("snippet") or {}, it.get("liveStreamingDetails") or {}
            out[it["id"]] = {"title": sn.get("title", ""), "desc": sn.get("description", ""), "channel": sn.get("channelTitle", ""),
                             "live": sn.get("liveBroadcastContent", "none"), "published": parse_date(sn.get("publishedAt", "")),
                             "sched": parse_date(ls.get("scheduledStartTime", "")), "start": parse_date(ls.get("actualStartTime", ""))}
    return out


def wanted(v, official, rel):
    """Judul memuat kata wawancara/konferensi pers, dan (kecuali kanal resmi klub) menyebut Man Utd atau nama pemain/stafnya."""
    if not INTERVIEW.search(v["title"]):
        return False
    return bool(official or (rel and rel.search(f"{v['title']} {v['desc'][:400]}")))


def _message(label, vid, v, when=None):
    lines = [f"<b>[{label}]</b>", "", html.escape(" ".join(v["title"].split())), "", f"Kanal: {html.escape(v['channel'])}"]
    if when:
        lines.append("Mulai: " + F.fmt_when(when, True))
    return "\n".join(lines + ["", f"https://www.youtube.com/watch?v={vid}"])


def _cycle(tg, vs, key, cfg, c, now, rel, log):
    ensure_channels(cfg, key, vs, c, now)
    first = not vs.get("init")
    by_name = {ch["name"]: ch for ch in c.get("channels") or []}
    ids = []
    for name, info in vs["channels"].items():
        if name not in by_name:
            continue
        ids += _uploads(info, key, vs, c)
        if by_name[name].get("search_upcoming") and now - vs["last_search"].get(name, 0) >= c["search_every_minutes"] * 60:
            vs["last_search"][name] = now
            ids += _upcoming(info, key, vs, c)
    new = [i for i in dict.fromkeys(ids) if i not in vs["seen"]]
    check = list(dict.fromkeys(new + list(vs["watch"])))
    details = _details(check, key, vs, c) if check else {}
    official = {info["title"].casefold(): by_name[n].get("official") for n, info in vs["channels"].items() if n in by_name}

    def send(kind, vid, v, label, when=None):
        k = f"{vid}:{kind}"
        if k in vs["sent"]:
            return
        vs["sent"][k] = now
        tg.send(_message(label, vid, v, when))
        log(f"video [{label}] {v['title'][:60]}")

    for vid in check:
        v = details.get(vid)
        if v is None:  # video dihapus atau dibatalkan
            vs["watch"].pop(vid, None)
            continue
        if vid in new:
            vs["seen"][vid] = now
        ok = vid in vs["watch"] or wanted(v, official.get(v["channel"].casefold()), rel)
        if not ok:
            continue
        if v["live"] == "upcoming" and v["sched"]:
            vs["watch"].setdefault(vid, {"sched": v["sched"]})["sched"] = v["sched"]
            if v["sched"] > now - 2 * 3600:
                send("sched", vid, v, "SIARAN TERJADWAL", v["sched"])
                if 0 < v["sched"] - now <= c["remind_minutes"] * 60:
                    send("soon", vid, v, "LIVE SEBENTAR LAGI", v["sched"])
        elif v["live"] == "live":
            vs["watch"].setdefault(vid, {"sched": v["sched"] or now})
            send("live", vid, v, "LIVE", v["start"] or now)
        else:  # sudah selesai atau unggahan biasa
            vs["watch"].pop(vid, None)
            fresh = vid in new and not first and v["published"] and now - v["published"] <= c["max_age_hours"] * 3600
            if fresh and not any(f"{vid}:{k}" in vs["sent"] for k in ("sched", "soon", "live")):
                send("video", vid, v, "VIDEO", v["published"])
    for vid in [i for i, w in vs["watch"].items() if now - (w.get("sched") or now) > 48 * 3600]:
        del vs["watch"][vid]
    vs["init"] = True
    for k in ("seen", "sent"):
        for i in [i for i, t in vs[k].items() if now - t > 7 * 86400]:
            del vs[k][i]


def run(tg, state, cfg, env, now_ts, rel=None, log=print):
    """Satu siklus pemantauan; aman dipanggil tiap run (dibatasi poll_minutes)."""
    key = env.get("YOUTUBE_API_KEY")
    c = {**DEFAULTS, **(cfg.get("youtube") or {})}
    if not key or not c.get("channels"):
        return
    vs = _state(state)
    if vs.get("blocked_until", 0) > now_ts or now_ts - vs.get("last_poll", 0) < c["poll_minutes"] * 60:
        return
    vs["last_poll"] = now_ts
    try:
        _cycle(tg, vs, key, cfg, c, now_ts, rel, log)
    except QuotaLimit as e:
        log(f"YouTube: {e}")
    except ApiError as e:
        quota = e.status == 403 and "quota" in e.text.lower()
        vs["blocked_until"] = llm._next_reset("gemini") if quota else now_ts + 6 * 3600
        tg.send("<b>[PERINGATAN]</b>\n\n" + ("Kuota YouTube API habis; pemantauan video lanjut setelah reset." if quota else
                f"YouTube API menolak permintaan ({html.escape(str(e)[:100])}); pemantauan video dijeda 6 jam. Periksa YOUTUBE_API_KEY dan pengaturan API."))
        log(f"YouTube: {e}")


def check(cfg, env, state, now_ts=None):
    """Untuk /diagnosa: kenali kanal yang belum dikenali, lalu ringkas kanal terpilih (nama, pelanggan) dan pemakaian unit hari ini."""
    key = env.get("YOUTUBE_API_KEY")
    c = {**DEFAULTS, **(cfg.get("youtube") or {})}
    if not key:
        raise RuntimeError("tanpa kunci YOUTUBE_API_KEY")
    if not c.get("channels"):
        raise RuntimeError("daftar kanal kosong di config")
    vs = _state(state)
    vs["resolve_fail"].clear()
    ensure_channels(cfg, key, vs, c, now_ts or time.time())
    got = [f"{i['title']} ({i['subs']:,} pelanggan)".replace(",", ".") for i in vs["channels"].values()]
    miss = [ch["name"] for ch in c["channels"] if ch["name"] not in vs["channels"]]
    return (f"{len(got)} kanal: " + "; ".join(got) + (f". Belum ditemukan: {', '.join(miss)}" if miss else "")
            + f". Unit terpakai hari ini: {(vs.get('units') or {}).get('n', 0)}")
