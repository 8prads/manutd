"""Fungsi teks: normalisasi, kemiripan, jenis kejadian, label, format pesan."""
import hashlib
import html
import math
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

STOP = set("""a an the and or but if of to in on at for from by with as is are was were be been being it its
this that these those he she they we you i his her their our your not no yes will would could should can may might
must has have had do does did than then so such into over after before about up out off again more most also just
who whom what which when where why how new latest news report reports reported says say said claim claims according
amid ahead against during while still back now""".split())
GENERIC = set("manchester united man utd mufc old trafford red devils club premier league football".split())

_WORD = re.compile(r"[a-z0-9£$€]+(?:'[a-z]+)?")


def stem(w):
    for suf in ("ing", "ed", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def tokens(text):
    out, seen = [], set()
    for w in _WORD.findall((text or "").lower()):
        w = w.split("'")[0]
        if len(w) < 3 or w in STOP or w in GENERIC:
            continue
        w = stem(w)
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


BASE_N = 300
PRIOR_DF = {w: 300 for w in """contract sign agre extension deal transfer fee loan injury injur rule week season player
striker midfielder defender goalkeeper manager boss update confirm official announc win defeat game match league cup
window move bid offer talk interest future return start lineup team squad coach target plan want leave join month year
report claim source fan goal score half training session press conference preview""".split()}
NOT_NAMES = set("""january february march april may june july august september october november december monday tuesday
wednesday thursday friday saturday sunday premier league champions europa conference cup england english british""".split())


def idf(tok, df, n):
    """Bobot kelangkaan kata. Kata umum sepak bola diberi bobot rendah sejak awal (PRIOR_DF)."""
    return math.log((n + BASE_N + 2) / (df.get(tok, 0) + PRIOR_DF.get(tok, 0) + 1)) + 1


def wjaccard(a, b, df, n):
    sa, sb = set(a), set(b)
    inter = sa & sb
    if not inter:
        return 0.0
    num = sum(idf(t, df, n) for t in inter)
    den = sum(idf(t, df, n) for t in sa | sb)
    return num / den if den else 0.0


def topic_tokens(toks, df, n, k=2):
    cand = [t for t in toks if not t.isdigit()]
    cand.sort(key=lambda t: -idf(t, df, n))
    return cand[:k]


# ---------- Entitas (nama pemain/klub) ----------
_W = re.compile(r"[A-Za-z][A-Za-z'’]*")


def learn_caps(caps, title, text):
    """Pelajari kata yang sering berhuruf kapital di tengah kalimat = nama diri."""
    for chunk, is_title in ((title, True), (text, False)):
        if not chunk:
            continue
        if is_title:
            long = [m.group() for m in _W.finditer(chunk) if len(m.group()) >= 4]
            if long and sum(w[0].isupper() for w in long) / len(long) > 0.7:
                continue  # judul Title Case tidak informatif
        for m in _W.finditer(chunk):
            w = m.group().split("'")[0].split("’")[0]
            if len(w) < 3:
                continue
            prefix = chunk[: m.start()].rstrip()
            initial = (not prefix) or prefix[-1] in '.!?:"“”—–-('
            rec = caps.setdefault(stem(w.lower()), [0, 0])
            if w[0].isupper():
                if not initial:
                    rec[0] += 1
            elif w.islower():
                rec[1] += 1
    if len(caps) > 8000:
        for k in [k for k, v in caps.items() if v[0] + v[1] < 2]:
            del caps[k]


def is_name(t, caps):
    c, low = caps.get(t, (0, 0))
    return c >= 1 and c > 2 * low


def entities(toks, caps, seed, df, n, k=6):
    ents = [t for t in toks if t not in NOT_NAMES and not t.isdigit() and (t in seed or is_name(t, caps))]
    return ents[:k] if ents else topic_tokens(toks, df, n, 2)


# ---------- URL ----------
_TRACK = ("utm_", "fbclid", "gclid", "ocid", "ito", "cmpid", "ref", "source", "cid", "xtor")


def canonical_url(url):
    try:
        p = urlparse(url.strip())
        q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(_TRACK)]
        path = p.path.rstrip("/")
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", urlencode(q), ""))
    except Exception:
        return url


def make_uid(url, title=""):
    base = canonical_url(url) if url else title
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:16]


def clean_html(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- Relevansi ----------
def build_relevance(cfg):
    keys = [re.escape(k) for k in list(cfg["filter"]["keywords"]) + list(cfg.get("mu_names", []))]
    excl = [re.escape(k) for k in cfg["filter"]["exclude"]]
    return (
        re.compile(r"\b(?:%s)\b" % "|".join(keys), re.I) if keys else None,
        re.compile(r"\b(?:%s)\b" % "|".join(excl), re.I) if excl else None,
    )


def is_relevant(item, rel):
    keys, excl = rel
    blob = f"{item.title} {item.text[:400]}"
    if excl and excl.search(blob):
        return False
    if item.dedicated:
        return True
    return bool(keys and keys.search(blob))


# ---------- Jenis kejadian ----------
TYPES = [
    ("injury", r"\b(injur\w*|ruled out|hamstring|surgery|sidelined|fitness (?:doubt|test|concern)|out for (?:weeks|months|the season))\b"),
    ("manager", r"\b(sack\w*|appoint\w*|interim|dismiss\w*|relieved of)\b"),
    ("transfer", r"\b(transfer\w*|sign(?:s|ed|ing)?|bid|fee|loan\w*|contract|medical|deal|agree[sd]?|here we go|release clause|swap|joins?|leave[sd]?|exit|target\w*|eyeing|eyes|linked with|interest in|swoop|approach|pursuit|move for|move to)\b"),
    ("match", r"\b(line-?up|team news|preview|match report|player ratings|predicted xi|starting xi|kick-?off|fixture|referee|var)\b|\b\d{1,2}\s?[-–]\s?\d{1,2}\b"),
    ("quote", r"\b(says?|said|told|interview|press conference|admits?|reveals?|insists?|speaks?|warns?|slams?|hits? out)\b"),
]
_TYPES = [(n, re.compile(p, re.I)) for n, p in TYPES]
STRONG_TYPES = {"injury", "manager", "transfer"}
FACT_TYPES = {"transfer", "injury", "manager"}


def event_type(text):
    for name, rx in _TYPES:
        if rx.search(text):
            return name
    return "other"


_FACTS = [
    re.compile(r"[£€$]\s?\d+(?:[.,]\d+)?\s?(?:m|million|bn|billion|k)?", re.I),
    re.compile(r"\b\d{1,2}\s?[-–]\s?\d{1,2}\b"),
    re.compile(r"\b\d+[- ]?(?:year|years|month|months|week|weeks|game|games|match|matches)\b", re.I),
    re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}\b", re.I),
]


def facts(text):
    out = set()
    for rx in _FACTS:
        for m in rx.findall(text or ""):
            out.add(re.sub(r"\s+", "", m.lower()))
    return out


# ---------- Label ----------
RE_HEDGE = re.compile(
    r"\b(linked|interested|eyeing|eyes|eye|considering|consider|could|may|might|set to|poised|reportedly|claims?|"
    r"understood to|sources?|tipped|target(?:s|ing)?|lined up|in talks|monitoring|keen|plans?|plotting|wants?|"
    r"open to|prepared to|ready to|close to|nearing|battle|race for|chasing|rumou?rs?|paper talk|gossip)\b"
    r"|\bpapers?:", re.I)
RE_OFFICIAL = re.compile(
    r"\b(official(?:ly)?|club statement|here we go|done deal|completes? (?:the )?(?:signing|transfer|move)|"
    r"announces?|confirm(?:s|ed)? (?:the )?(?:signing|departure|appointment|exit))\b", re.I)
RE_BREAKING = re.compile(r"\b(breaking|just in|bombshell|sacked|relieved of his duties|passed away|dies)\b", re.I)
RE_QUOTE = re.compile(r"\b(says?|said|told|interview|press conference|pre-match|post-match|admits?|reveals?|insists?|speaks?|warns?)\b", re.I)
RE_DRAMA = re.compile(
    r"\b(row|clash|bust[- ]?up|feud|rift|fallout|unhappy|tension|furious|frozen out|dressing room|protest|backlash|"
    r"slam(?:s|med)?|blast(?:s|ed)?|criticis\w+)\b", re.I)

LABEL_RANK = {"RUMOR": 1, "BREAKING NEWS": 3, "RESMI": 4}


def rank(label):
    return LABEL_RANK.get(label, 2)


def build_pundit_re(cfg):
    names = [re.escape(n) for n in cfg["people"]["pundits"]]
    names.append("pundit")
    return re.compile(r"\b(?:%s)\b" % "|".join(names), re.I)


def classify(title, text, official, strong_source, sources_count, etype, pundit_re):
    blob = f"{title}. {text[:400]}"
    if official and etype != "match" and not RE_QUOTE.search(title):
        return "RESMI"
    if strong_source and RE_OFFICIAL.search(title) and not RE_HEDGE.search(title):
        return "RESMI"
    if RE_BREAKING.search(title) or (sources_count >= 3 and strong_source and etype in FACT_TYPES):
        return "BREAKING NEWS"
    if pundit_re.search(blob):
        return "PUNDIT"
    if etype == "transfer" and RE_HEDGE.search(blob):
        return "RUMOR"
    if RE_QUOTE.search(title):
        return "INTERVIEW"
    if etype == "injury":
        return "CEDERA"
    if RE_DRAMA.search(blob):
        return "DRAMA"
    if etype == "transfer":
        return "TRANSFER"
    if etype == "match":
        return "PERTANDINGAN"
    return "BERITA"


# ---------- Format pesan Telegram ----------
DIVIDER = "──────────"
BILINGUAL_SEP = "###ENGLISH###"


def split_bilingual(raw):
    """Pisahkan keluaran AI menjadi (Indonesia, Inggris). Tanpa penanda, Inggris kosong."""
    raw = raw or ""
    if BILINGUAL_SEP in raw:
        a, b = raw.split(BILINGUAL_SEP, 1)
        return a.strip(), b.strip()
    return raw.strip(), ""


def _cut(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut[: cut.rfind(". ") + 1] if ". " in cut else cut


def format_message(label, body, sources, en="", link=""):
    """[LABEL] / isi Indonesia / garis / isi Inggris / Selengkapnya: tautan / (sumber)."""
    esc = html.escape
    body, en = _cut((body or "").strip(), 1700), _cut((en or "").strip(), 1700)
    parts = [f"<b>[{esc(label)}]</b>", "", esc(body)]
    if en:
        parts += [DIVIDER, esc(en)]
    if link:
        parts += ["", "Selengkapnya:", esc(link)]
    parts += ["", f"<i>({esc(', '.join(sources))})</i>"]
    return "\n".join(parts)


# ---------- Jurnalis ----------
def build_journalist_re(cfg):
    p = cfg["people"]
    aliases = p.get("journalist_aliases", {})
    out = []
    for name in p["trusted_journalists"]:
        forms = sorted([name] + list(aliases.get(name, [])), key=len, reverse=True)
        out.append((name, re.compile(r"\b(?:%s)\b" % "|".join(re.escape(f) for f in forms), re.I)))
    return out


def find_journalists(text, jr):
    """Nama jurnalis tepercaya yang disebut di teks, urut kemunculan pertama."""
    hits = []
    for name, rx in jr:
        m = rx.search(text or "")
        if m:
            hits.append((m.start(), name))
    return [n for _, n in sorted(hits)]
