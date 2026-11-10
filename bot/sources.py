"""Pengambil berita: RSS, Google News, Reddit, dan API gratis. Semua mengembalikan daftar Item."""
import calendar
import email.utils
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote_plus

from . import text as T
from .models import Item

UA = "Mozilla/5.0 (compatible; MUFCNewsBot/1.0; personal news digest)"
TIMEOUT = (5, 15)


def http_get(url, headers=None, params=None, timeout=None):
    import requests
    return requests.get(url, headers={"User-Agent": UA, **(headers or {})}, params=params, timeout=timeout or TIMEOUT)


# ---------- Parser RSS/Atom (tanpa dependensi tambahan) ----------
_BAD_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    dt = None
    try:
        dt = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        pass
    if dt is None:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_feed(data):
    """Kembalikan list dict: title, link, summary, content, pub, source."""
    s = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    s = _CTRL.sub("", _BAD_AMP.sub("&amp;", re.sub(r"^\s*<\?xml[^>]*\?>", "", s)))
    root = ET.fromstring(s)
    out = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        d = {"title": "", "link": "", "summary": "", "content": "", "pub": None, "source": ""}
        for ch in el:
            t, txt = _local(ch.tag), (ch.text or "").strip()
            if t == "title":
                d["title"] = txt
            elif t == "link":
                href = ch.get("href")
                if href and ch.get("rel", "alternate") == "alternate":
                    d["link"] = d["link"] or href
                elif txt:
                    d["link"] = txt
            elif t in ("description", "summary"):
                d["summary"] = txt
            elif t in ("encoded", "content"):
                d["content"] = txt
            elif t in ("pubdate", "published", "updated", "date"):
                d["pub"] = d["pub"] or parse_date(txt)
            elif t == "source":
                d["source"] = txt
            elif t == "guid" and not d["link"] and txt.startswith("http"):
                d["link"] = txt
        out.append(d)
    return out


def _tier_for(name, cfg, default=2):
    return 1 if name.strip().lower() in {n.lower() for n in cfg["tier1_names"]} else default


def feed_items(src, entries, cfg, now):
    items = []
    for e in entries[:40]:
        title, link = T.clean_html(e["title"]), e["link"].strip()
        if not title or not link:
            continue
        summary = T.clean_html(e["summary"])[:800]
        content = T.clean_html(e["content"])
        name, tier, text = src["name"], src["tier"], summary
        if src["type"] == "gnews_rss":
            name = e["source"] or (title.rsplit(" - ", 1)[1] if " - " in title else "Google News")
            if " - " in title:
                title = title.rsplit(" - ", 1)[0].strip()
            if name.strip().lower() in {n.lower() for n in cfg.get("skip_publishers", [])}:
                continue  # tanggal Google News untuk situs resmi sering tidak akurat; feed resmi sudah dibaca langsung
            tier = _tier_for(name, cfg)
            text = "" if summary.startswith(title[:40]) else summary[:400]
            content = ""
        items.append(Item(
            uid=T.make_uid(link, title), title=title, text=text or title, url=link, source=name,
            source_id=src["id"], tier=tier, published=e["pub"] or now, official=bool(src.get("official")),
            dedicated=src.get("dedicated", True), content=content if len(content) > 600 else "",
            undated=e["pub"] is None))
    return items


# ---------- Fetcher per jenis ----------
def fetch_rss(src, state, cfg, env):
    st = state["feeds"].setdefault(src["id"], {})
    headers = {}
    if st.get("etag"):
        headers["If-None-Match"] = st["etag"]
    if st.get("modified"):
        headers["If-Modified-Since"] = st["modified"]
    url = src.get("url")
    if src["type"] == "gnews_rss":
        url = f"https://news.google.com/rss/search?q={quote_plus(src['query'] + ' when:1d')}&hl=en-GB&gl=GB&ceid=GB:en"
        headers = {}
    r = http_get(url, headers)
    if r.status_code == 304:
        return []
    r.raise_for_status()
    st["etag"], st["modified"] = r.headers.get("ETag"), r.headers.get("Last-Modified")
    return feed_items(src, parse_feed(r.content), cfg, time.time())


def reddit_items(src, data, cfg, now):
    trusted = cfg["people"]["trusted_journalists"]
    min_score = cfg["trend"]["reddit_min_score"]
    items = []
    for ch in data.get("data", {}).get("children", []):
        d = ch.get("data", {})
        if d.get("stickied") or not d.get("title"):
            continue
        score = int(d.get("score", 0))
        if score < min_score // 2:
            continue
        title, name, tier, journalist = d["title"].strip(), "Reddit", 2, False
        m = re.match(r"^\s*\[([^\]]{2,40})\]\s*(.+)$", title)
        if m:
            tag, title = m.group(1).strip(), m.group(2).strip()
            hit = next((t for t in trusted if t.lower() in tag.lower() or t.split()[-1].lower() in tag.lower()), None)
            if hit:
                name, journalist, tier = hit, True, 1
            else:
                name, tier = tag, _tier_for(tag, cfg)
        link = d.get("url_overridden_by_dest") or d.get("url") or ""
        if "reddit.com" in link or not link:
            link = "https://www.reddit.com" + d.get("permalink", "")
        bucket = 0 if score < min_score else (1 if score < min_score * 3 else 2)
        items.append(Item(
            uid=T.make_uid(link) + f"r{bucket}", title=title, text=T.clean_html(d.get("selftext", ""))[:500] or title,
            url=link, source=name, source_id=src["id"], tier=tier, published=float(d.get("created_utc", now)),
            dedicated=True, journalist=journalist, score=score))
    return items


def fetch_reddit(src, state, cfg, env):
    r = http_get(src["url"])
    r.raise_for_status()
    return reddit_items(src, r.json(), cfg, time.time())


def fetch_guardian(src, state, cfg, env):
    r = http_get("https://content.guardianapis.com/search", params={
        "q": '"Manchester United"', "section": "football", "order-by": "newest", "page-size": 20,
        "show-fields": "trailText,bodyText", "api-key": env[src["key_env"]]})
    r.raise_for_status()
    items = []
    for x in r.json()["response"]["results"]:
        f = x.get("fields", {})
        items.append(Item(
            uid=T.make_uid(x["webUrl"]), title=x["webTitle"], text=T.clean_html(f.get("trailText", ""))[:600] or x["webTitle"],
            url=x["webUrl"], source="The Guardian", source_id=src["id"], tier=1,
            published=parse_date(x["webPublicationDate"]) or time.time(), content=f.get("bodyText", "")[:6000]))
    return items


def fetch_gdelt(src, state, cfg, env):
    r = http_get("https://api.gdeltproject.org/api/v2/doc/doc", params={
        "query": '"Manchester United" sourcelang:english', "mode": "artlist", "format": "json",
        "maxrecords": 75, "timespan": "2h", "sort": "datedesc"}, timeout=(5, 40))
    r.raise_for_status()
    try:
        arts = r.json().get("articles", [])
    except ValueError:
        return []
    items = []
    for a in arts:
        ts = None
        try:
            ts = calendar.timegm(time.strptime(a["seendate"], "%Y%m%dT%H%M%SZ"))
        except (KeyError, ValueError):
            pass
        items.append(Item(
            uid=T.make_uid(a["url"]), title=a.get("title", ""), text=a.get("title", ""), url=a["url"],
            source=a.get("domain", "GDELT"), source_id=src["id"], tier=3, published=ts or time.time(),
            signal_only=True))
    return items


def fetch_gnews_api(src, state, cfg, env):
    r = http_get("https://gnews.io/api/v4/search", params={
        "q": '"Manchester United"', "lang": "en", "max": 10, "sortby": "publishedAt", "apikey": env[src["key_env"]]})
    r.raise_for_status()
    return [Item(
        uid=T.make_uid(a["url"]), title=a["title"], text=(a.get("description") or a["title"])[:600], url=a["url"],
        source=(a.get("source") or {}).get("name", "GNews"), source_id=src["id"], tier=3,
        published=parse_date(a.get("publishedAt", "")) or time.time()) for a in r.json().get("articles", [])]


def fetch_newsdata(src, state, cfg, env):
    r = http_get("https://newsdata.io/api/1/latest", params={
        "apikey": env[src["key_env"]], "q": "Manchester United", "language": "en"})
    r.raise_for_status()
    return [Item(
        uid=T.make_uid(a["link"]), title=a["title"], text=(a.get("description") or a["title"])[:600], url=a["link"],
        source=a.get("source_name") or a.get("source_id") or "NewsData", source_id=src["id"], tier=3,
        published=parse_date(a.get("pubDate", "")) or time.time()) for a in r.json().get("results", [])]


FETCHERS = {
    "rss": fetch_rss, "gnews_rss": fetch_rss, "reddit": fetch_reddit, "guardian": fetch_guardian,
    "gdelt": fetch_gdelt, "gnews_api": fetch_gnews_api, "newsdata": fetch_newsdata,
}


def fetch_all(sources, state, cfg, env, log=print):
    """Ambil semua sumber paralel. Return (items, hasil) dengan hasil[id] = ('ok'|'gagal'|'lewati', info)."""
    results, items = {}, []

    def work(src):
        if src.get("enabled") is False:
            return src["id"], "lewati", "nonaktif", []
        if src.get("key_env") and not env.get(src["key_env"]):
            return src["id"], "lewati", "tanpa kunci API", []
        try:
            got = FETCHERS[src["type"]](src, state, cfg, env)
            return src["id"], "ok", len(got), got
        except Exception as e:  # satu sumber gagal tidak boleh menghentikan yang lain
            return src["id"], "gagal", f"{type(e).__name__}: {str(e)[:120]}", []

    with ThreadPoolExecutor(max_workers=12) as ex:
        for sid, status, info, got in ex.map(work, sources):
            results[sid] = (status, info)
            items.extend(got)
    ok = sum(1 for v in results.values() if v[0] == "ok")
    log(f"sumber: {ok} ok, {sum(1 for v in results.values() if v[0] == 'gagal')} gagal, "
        f"{sum(1 for v in results.values() if v[0] == 'lewati')} dilewati, {len(items)} item")
    return items, results
