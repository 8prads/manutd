"""Menyusun draf pesan dari keluaran AI: parsing JSON, panjang, kutipan verbatim, dan pemeriksaan oleh kode."""
import json
import re

NUM_WORDS = {"ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15",
             "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19", "twenty": "20"}
_CURLY = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " "})
_ELLIPSIS = re.compile(r"\.{3}|\u2026")
_NUM = re.compile(r"\d[\d.,]*\d|\d")


def norm(s):
    """Normalisasi untuk membandingkan teks: tanda kutip dan strip dilurus-kan, spasi dirapatkan, huruf kecil."""
    return re.sub(r"\s+", " ", (s or "").translate(_CURLY).lower()).strip()


def in_text(piece, content):
    """True bila potongan (boleh memuat '...') ada persis di teks, mengabaikan tanda baca di ujung."""
    n = norm(content)
    parts = [norm(p).strip(" .,;:!?\"'") for p in _ELLIPSIS.split(piece or "")]
    parts = [p for p in parts if len(p) >= 8]
    return bool(parts) and all(p in n for p in parts)


def parse_json(raw):
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(s[i:j + 1])
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def valid_draft(d):
    return all(isinstance(d.get(k), str) and len(d[k].strip()) >= 8 for k in ("headline_id", "isi_id", "headline_en", "isi_en"))


def one_line(s):
    return " ".join(str(s or "").split())


def headline(s, prefix=""):
    """Satu kalimat; awalan (mis. OFFICIAL:) ditambahkan bila belum ada."""
    h = re.sub(r"^(headline|judul)\s*:\s*", "", one_line(s).strip(" \"'"), flags=re.I)
    if prefix and not re.match(r"^(official|resmi)\b", h, re.I):
        h = f"{prefix} {h}"
    if h and h[-1] not in ".!?":
        h += "."
    return h


def clip(text, limit):
    """Potong di akhir kalimat terakhir yang masih muat dalam batas karakter."""
    t = one_line(text)
    if len(t) <= limit:
        return t
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", t) if m.end() <= limit]
    if ends:
        return t[:ends[-1]]
    return t[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "."


def numbers(text):
    out = set()
    for m in _NUM.findall(text or ""):
        d = re.sub(r"[.,]", "", m)
        if len(d) >= 2:
            out.add(d)
    return out


def number_issues(content, text):
    """Angka (2 digit atau lebih) di draf yang tidak ada di teks artikel."""
    base = norm(content)
    for w, d in NUM_WORDS.items():
        base = re.sub(rf"\b{w}\b", d, base)
    have = numbers(base)
    return [f"angka {n} tidak ada di teks" for n in sorted(numbers(text)) if n not in have][:3]


def verified_quotes(k, content):
    """Kutipan yang benar-benar ada di artikel; None bila tidak ada satu pun atau pembicara kosong."""
    if not isinstance(k, dict):
        return None
    texts = [t for t in (k.get("teks") or []) if isinstance(t, str)]
    tr = k.get("terjemahan") or []
    keep, keep_tr = [], []
    for i, t in enumerate(texts[:6]):
        if in_text(t, content):
            keep.append(t.strip())
            keep_tr.append(str(tr[i]).strip() if i < len(tr) and tr[i] else "")
    speaker = one_line(k.get("pembicara"))
    if not keep or not speaker:
        return None
    return {"pembicara": speaker, "media": one_line(k.get("media")), "konteks_id": one_line(k.get("konteks_id")),
            "konteks_en": one_line(k.get("konteks_en")), "teks": keep, "terjemahan": keep_tr}


def quote_block(speaker, quotes, who, lang, max_chars=1200):
    """Nama: “k1”. “k2”, told @Media. “k3”.  (atribusi setelah dua kutipan pertama)"""
    qs = ["\u201c" + q.strip().rstrip(" .,;:") + "\u201d" for q in quotes]
    while True:
        cut = min(2, len(qs))
        att = (f", told {who}" if lang == "en" else f", ujarnya kepada {who}") if who else ""
        text = f"{speaker}: " + ". ".join(qs[:cut]) + att + "."
        if qs[cut:]:
            text += " " + ". ".join(qs[cut:]) + "."
        if len(text) <= max_chars or len(qs) == 1:
            return text
        qs.pop()


def assemble(d, label, limit, who_fn, content):
    """Susun (teks_id, teks_en, jumlah_kutipan) dari JSON AI: headline, lalu isi (atau konteks + kutipan)."""
    p_en, p_id = ("OFFICIAL:", "RESMI:") if label == "RESMI" else ("", "")
    h_en, h_id = headline(d["headline_en"], p_en), headline(d["headline_id"], p_id)
    q = verified_quotes(d.get("kutipan"), content) if label in ("INTERVIEW", "PUNDIT") else None
    if q:
        who = who_fn(q["media"])
        tr = q["terjemahan"] if all(q["terjemahan"]) else q["teks"]
        en = [h_en] + ([q["konteks_en"]] if q["konteks_en"] else []) + [quote_block(q["pembicara"], q["teks"], who, "en")]
        idn = [h_id] + ([q["konteks_id"]] if q["konteks_id"] else []) + [quote_block(q["pembicara"], tr, who, "id")]
        return "\n\n".join(idn), "\n\n".join(en), len(q["teks"])
    return (f"{h_id}\n\n{clip(d['isi_id'], limit)}", f"{h_en}\n\n{clip(d['isi_en'], limit)}", 0)
