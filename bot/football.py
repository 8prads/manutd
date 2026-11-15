"""Data pertandingan: jadwal, klasemen, statistik, lineup.
Penyedia dicoba berurutan: ESPN (tidak resmi, tanpa kunci) -> Highlightly -> API-Football -> football-data.org."""
import html
import os
import time
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_V2 = "https://site.api.espn.com/apis/v2/sports/soccer"
APIF = "https://v3.football.api-sports.io"
FD = "https://api.football-data.org/v4"
HL = "https://sports.highlightly.net"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MU_ESPN, MU_APIF, MU_FD = 360, 33, 66

# kode: (nama, kode ESPN, id API-Football, kode football-data atau None)
LEAGUES = {
    "pl": ("Premier League", "eng.1", 39, "PL"),
    "ucl": ("Liga Champions", "uefa.champions", 2, "CL"),
    "uel": ("Liga Europa", "uefa.europa", 3, None),
    "facup": ("Piala FA", "eng.fa", 45, None),
    "carabao": ("Piala Liga", "eng.league_cup", 48, None),
    "championship": ("Championship", "eng.2", 40, "ELC"),
    "laliga": ("La Liga", "esp.1", 140, "PD"),
    "seriea": ("Serie A", "ita.1", 135, "SA"),
    "bundesliga": ("Bundesliga", "ger.1", 78, "BL1"),
    "ligue1": ("Ligue 1", "fra.1", 61, "FL1"),
    "eredivisie": ("Eredivisie", "ned.1", 88, "DED"),
}
ESPN_NAMES = {v[1]: v[0] for v in LEAGUES.values()}


def _get(url, headers=None, params=None):
    import requests
    ua = BROWSER_UA if "espn.com" in url else "Mozilla/5.0 (compatible; MUFCNewsBot/1.0)"
    r = requests.get(url, headers={"User-Agent": ua, "Accept": "application/json", **(headers or {})},
                     params=params, timeout=(5, 20))
    r.raise_for_status()
    return r.json()


def _apif(path, **params):
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        raise RuntimeError("tanpa kunci API_FOOTBALL_KEY")
    j = _get(APIF + path, {"x-apisports-key": key}, params)
    if j.get("errors"):
        raise RuntimeError(str(j["errors"])[:120])
    return j


def _hl(path, **params):
    key = os.environ.get("HIGHLIGHTLY_API_KEY")
    if not key:
        raise RuntimeError("tanpa kunci HIGHLIGHTLY_API_KEY")
    return _get(HL + path, {"x-rapidapi-key": key}, params)


def _fd(path, **params):
    key = os.environ.get("FOOTBALL_DATA_API_KEY")
    if not key:
        raise RuntimeError("tanpa kunci FOOTBALL_DATA_API_KEY")
    return _get(FD + path, {"X-Auth-Token": key}, params)


def _ts(s):
    from .sources import parse_date
    return parse_date(s) or 0


def chain(steps):
    """steps = [(nama, fungsi)]. Kembalikan (nama, hasil) pertama yang berisi; gagal semua = RuntimeError."""
    errs = []
    for name, fn in steps:
        try:
            res = fn()
            if res:
                return name, res
            errs.append(f"{name}: kosong")
        except Exception as e:
            errs.append(f"{name}: {type(e).__name__} {str(e)[:70]}")
    raise RuntimeError("; ".join(errs))


# ---------- format ----------
def fmt_when(ts):
    d = datetime.fromtimestamp(ts, WIB)
    return f"{HARI[d.weekday()]} {d.day:02d}/{d.month:02d} {d.hour:02d}.{d.minute:02d} WIB"


def fixture_key(f):
    return f"{f['comp']}|{f['home']}|{f['away']}"


def fmt_fixture_line(f):
    opp = f["away"] if f["mu_home"] else f["home"]
    return f"{fmt_when(f['ts'])} · {f['comp']} · {'KANDANG' if f['mu_home'] else 'TANDANG'} vs {opp}"


def _fx(ts, comp, home, away, venue, state, score=None, espn_id=None, slug=None, mu_home=None):
    return {"ts": ts, "comp": comp, "home": home, "away": away, "venue": venue or "", "state": state,
            "score": score, "espn_id": espn_id, "slug": slug,
            "mu_home": ("manchester united" in home.lower()) if mu_home is None else mu_home}


# ---------- ESPN ----------
def parse_espn_events(j, slug):
    out = []
    for ev in j.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        cps = comp.get("competitors", [])
        ids = {str(c.get("team", {}).get("id")) for c in cps}
        if str(MU_ESPN) not in ids or len(cps) != 2:
            continue
        by = {c.get("homeAway"): c for c in cps}
        if "home" not in by or "away" not in by:
            continue
        out.append(_fx(_ts(ev.get("date", "")), ESPN_NAMES.get(slug, slug), _espn_name(by["home"]), _espn_name(by["away"]),
                       (comp.get("venue") or {}).get("fullName"),
                       (comp.get("status") or ev.get("status") or {}).get("type", {}).get("state", "pre"),
                       _espn_score(by), ev.get("id"), slug))
    return out


def _espn_name(c):
    t = c.get("team") or {}
    return t.get("displayName") or t.get("name") or t.get("shortDisplayName") or "?"


def _espn_score(by):
    try:
        v = lambda c: (c["score"].get("displayValue") or c["score"].get("value")) if isinstance(c["score"], dict) else c["score"]
        return int(float(v(by["home"]))), int(float(v(by["away"])))
    except (KeyError, ValueError, TypeError):
        return None


parse_espn_schedule = parse_espn_events  # jadwal tim memakai struktur peristiwa yang sama


def espn_fixtures(slugs, days_back, days_fwd):
    now = datetime.now(timezone.utc)
    lo, hi = (now - timedelta(days=days_back)).timestamp(), (now + timedelta(days=days_fwd)).timestamp()
    rng = f"{(now - timedelta(days=days_back)):%Y%m%d}-{(now + timedelta(days=days_fwd)):%Y%m%d}"
    out, errs = [], []
    for slug in slugs:
        try:
            out += parse_espn_events(_get(f"{ESPN}/{slug}/scoreboard", params={"dates": rng}), slug)
            continue
        except Exception as e:
            err = f"{slug} papan skor: {type(e).__name__} {str(e)[:50]}"
        try:  # cadangan: jadwal musim milik tim
            out += [f for f in parse_espn_events(_get(f"{ESPN}/{slug}/teams/{MU_ESPN}/schedule"), slug) if lo <= f["ts"] <= hi]
        except Exception as e:
            errs.append(f"{err}; jadwal tim: {type(e).__name__} {str(e)[:50]}")
    if len(errs) == len(slugs):
        raise RuntimeError(" | ".join(errs[:2]))
    return sorted(out, key=lambda f: f["ts"])


def parse_espn_standings(j):
    rows = []
    for ch in j.get("children") or [j]:
        grp = ch.get("name", "") if len(j.get("children") or []) > 1 else ""
        for e in (ch.get("standings") or {}).get("entries", []):
            st = {s.get("name"): s.get("value") for s in e.get("stats", [])}
            if "rank" not in st and "points" not in st:
                continue
            rows.append({"pos": int(st.get("rank") or 0), "team": e["team"]["displayName"], "p": int(st.get("gamesPlayed") or 0),
                         "w": int(st.get("wins") or 0), "d": int(st.get("ties") or 0), "l": int(st.get("losses") or 0),
                         "gd": int(st.get("pointDifferential") or 0), "pts": int(st.get("points") or 0), "group": grp})
    return sorted(rows, key=lambda r: (r["group"], r["pos"]))


def _espn_summary(f):
    return _get(f"{ESPN}/{f['slug']}/summary", params={"event": f["espn_id"]})


def parse_espn_stats(j):
    teams = (j.get("boxscore") or {}).get("teams", [])
    if len(teams) != 2:
        return None
    mu = next((t for t in teams if str(t["team"].get("id")) == str(MU_ESPN)), teams[0])
    op = teams[1] if mu is teams[0] else teams[0]
    val = lambda t: {s.get("name"): s.get("displayValue") for s in t.get("statistics", [])}
    a, b = val(mu), val(op)
    mapping = [("possessionPct", "Penguasaan bola", "%"), ("totalShots", "Tembakan", ""), ("shotsOnTarget", "Tepat sasaran", ""),
               ("wonCorners", "Sepak pojok", ""), ("foulsCommitted", "Pelanggaran", ""), ("yellowCards", "Kartu kuning", ""),
               ("redCards", "Kartu merah", "")]
    rows = [(lab, f"{a[k]}{u}", f"{b.get(k, '-')}{u}") for k, lab, u in mapping if k in a]
    return {"opp": op["team"]["displayName"], "rows": rows} if rows else None


def parse_espn_lineup(j):
    for r in j.get("rosters", []):
        if str(r.get("team", {}).get("id")) != str(MU_ESPN):
            continue
        xi = [(str(p.get("jersey", "")), p["athlete"]["displayName"], (p.get("position") or {}).get("abbreviation", ""))
              for p in r.get("roster", []) if p.get("starter")]
        subs = [p["athlete"]["displayName"] for p in r.get("roster", []) if not p.get("starter")]
        if len(xi) >= 11:
            fm = r.get("formation")
            return {"formation": (fm.get("summary") if isinstance(fm, dict) else fm) or "", "xi": xi, "subs": subs}
    return None


# ---------- API-Football ----------
def parse_apif_fixtures(j):
    out = []
    for x in j.get("response", []):
        fx, lg, tm = x["fixture"], x["league"], x["teams"]
        short = fx.get("status", {}).get("short", "NS")
        state = "pre" if short in ("NS", "TBD", "PST") else ("post" if short in ("FT", "AET", "PEN") else "in")
        g = x.get("goals") or {}
        score = (g["home"], g["away"]) if g.get("home") is not None else None
        out.append(_fx(_ts(fx["date"]), lg["name"], tm["home"]["name"], tm["away"]["name"], (fx.get("venue") or {}).get("name"),
                       state, score, mu_home=tm["home"]["id"] == MU_APIF))
        out[-1]["apif_id"] = fx["id"]
    return out


def parse_apif_standings(j):
    rows = []
    for league in j.get("response", []):
        groups = league["league"]["standings"]
        for gi, grp in enumerate(groups):
            for e in grp:
                a = e["all"]
                rows.append({"pos": e["rank"], "team": e["team"]["name"], "p": a["played"], "w": a["win"], "d": a["draw"],
                             "l": a["lose"], "gd": e.get("goalsDiff", 0), "pts": e["points"],
                             "group": e.get("group", "") if len(groups) > 1 else ""})
    return rows


def parse_apif_stats(j):
    teams = j.get("response", [])
    if len(teams) != 2:
        return None
    mu = next((t for t in teams if t["team"]["id"] == MU_APIF), teams[0])
    op = teams[1] if mu is teams[0] else teams[0]
    val = lambda t: {s["type"]: ("0" if s["value"] is None else str(s["value"])) for s in t["statistics"]}
    a, b = val(mu), val(op)
    mapping = [("Ball Possession", "Penguasaan bola"), ("Total Shots", "Tembakan"), ("Shots on Goal", "Tepat sasaran"),
               ("Corner Kicks", "Sepak pojok"), ("Fouls", "Pelanggaran"), ("Yellow Cards", "Kartu kuning"),
               ("Red Cards", "Kartu merah"), ("expected_goals", "xG")]
    rows = [(lab, a[k], b.get(k, "-")) for k, lab in mapping if k in a]
    return {"opp": op["team"]["name"], "rows": rows} if rows else None


def parse_apif_lineup(j):
    for t in j.get("response", []):
        if t["team"]["id"] == MU_APIF and len(t.get("startXI", [])) >= 11:
            return {"formation": t.get("formation") or "",
                    "xi": [(str(p["player"].get("number", "")), p["player"]["name"], p["player"].get("pos", "")) for p in t["startXI"]],
                    "subs": [p["player"]["name"] for p in t.get("substitutes", [])]}
    return None


# ---------- football-data.org ----------
def parse_fd_matches(j):
    out = []
    for m in j.get("matches", []):
        st = m.get("status", "")
        state = "post" if st == "FINISHED" else ("in" if st in ("IN_PLAY", "PAUSED") else "pre")
        ft = (m.get("score") or {}).get("fullTime") or {}
        score = (ft["home"], ft["away"]) if ft.get("home") is not None else None
        out.append(_fx(_ts(m["utcDate"]), m["competition"]["name"], m["homeTeam"]["name"], m["awayTeam"]["name"], "",
                       state, score, mu_home=m["homeTeam"]["id"] == MU_FD))
    return out


def parse_fd_standings(j):
    rows = []
    for st in j.get("standings", []):
        if st.get("type") != "TOTAL":
            continue
        for e in st.get("table", []):
            rows.append({"pos": e["position"], "team": e["team"]["name"], "p": e["playedGames"], "w": e["won"], "d": e["draw"],
                         "l": e["lost"], "gd": e.get("goalDifference", 0), "pts": e["points"], "group": st.get("group") or ""})
    return rows


# ---------- Highlightly ----------
def _flat(items):
    out = []
    for x in items or []:
        out += _flat(x) if isinstance(x, list) else [x]
    return out


def _shape(j):
    """Ringkasan bentuk JSON untuk pesan galat, mis. 'dict: matchId,teams' atau 'list[2]: team,statistics'."""
    if isinstance(j, dict):
        return "dict: " + ",".join(list(j)[:8])
    if isinstance(j, list):
        return f"list[{len(j)}]: " + (",".join(list(j[0])[:8]) if j and isinstance(j[0], dict) else "")
    return type(j).__name__


def hl_find_match(f, info=None, wide=False):
    """Cari id pertandingan Man Utd di Highlightly lewat tanggal dan nama tim."""
    base = datetime.fromtimestamp(f["ts"], timezone.utc)
    days = [base] + ([base - timedelta(days=1), base + timedelta(days=1)] if wide else [])
    for day in days:
        d = day.strftime("%Y-%m-%d")
        for side in ("homeTeamName", "awayTeamName"):
            j = _hl("/football/matches", date=d, limit=20, **{side: "Manchester United"})
            data = (j.get("data") if isinstance(j, dict) else j) or []
            if info is not None:
                info.append(f"{d} {side[:4]}: {len(data)} hasil")
            for m in data:
                names = (m.get("homeTeam", {}).get("name", ""), m.get("awayTeam", {}).get("name", ""))
                if any("manchester united" in n.lower() for n in names):
                    return m.get("id")
    return None


def parse_hl_lineup(j, mu_home):
    if isinstance(j, list):
        j = j[0] if j else {}
    j = j.get("data", j) if isinstance(j, dict) else {}
    side = j.get("homeTeam" if mu_home else "awayTeam") or {}
    xi = [(str(p.get("number", "")), p.get("name", ""), p.get("position", "")) for p in _flat(side.get("startingXI"))]
    if len(xi) < 11:
        return None
    return {"formation": side.get("formation") or "", "xi": xi, "subs": [p.get("name", "") for p in _flat(side.get("substitutes"))]}


_HL_STATS = [("possession", "Penguasaan bola"), ("shots on target", "Tepat sasaran"), ("shots total", "Tembakan"),
             ("total shots", "Tembakan"), ("shots", "Tembakan"), ("corner", "Sepak pojok"), ("foul", "Pelanggaran"),
             ("yellow", "Kartu kuning"), ("red card", "Kartu merah"), ("expected", "xG")]


def parse_hl_stats(j):
    if isinstance(j, dict):
        j = j.get("data", j)
    teams = (j.get("teams") if isinstance(j, dict) else j) or []
    if len(teams) != 2:
        return None
    def norm(t):
        name = (t.get("team") or {}).get("name") or t.get("name", "")
        return name, [(str(s.get("name", "")).lower(), s.get("value")) for s in (t.get("statistics") or t.get("stats") or [])]
    ent = [norm(t) for t in teams]
    mu = next((e for e in ent if "manchester united" in e[0].lower()), ent[0])
    op = ent[1] if mu is ent[0] else ent[0]
    def pick(stats, key):
        for k, v in stats:
            if key in k and not (key == "shots" and "on target" in k):
                return "-" if v is None else str(v)
        return None
    rows, used = [], set()
    for key, label in _HL_STATS:
        if label in used:
            continue
        a, b = pick(mu[1], key), pick(op[1], key)
        if a is not None:
            used.add(label)
            suffix = "%" if label == "Penguasaan bola" and "%" not in a else ""
            rows.append((label, a + suffix, (b or "-") + (suffix if b and "%" not in b else "")))
    return {"opp": op[0], "rows": rows} if rows else None


# ---------- nama pendek dan format jadwal ----------
SHORT = {"Manchester United": "Man United", "Manchester City": "Man City", "Brighton & Hove Albion": "Brighton",
         "Tottenham Hotspur": "Tottenham", "Wolverhampton Wanderers": "Wolves", "Newcastle United": "Newcastle",
         "West Ham United": "West Ham", "Nottingham Forest": "Nottm Forest", "Leeds United": "Leeds",
         "Sporting Clube de Portugal": "Sporting CP", "Paris Saint-Germain": "PSG"}
COMP_ID = {"UEFA Champions League": "Liga Champions", "UEFA Europa League": "Liga Europa", "FA Cup": "Piala FA",
           "EFL Cup": "Piala Liga", "League Cup": "Piala Liga", "Carabao Cup": "Piala Liga"}


def short_team(name):
    name = (name or "").strip()
    for k, v in SHORT.items():
        if name.startswith(k):
            return v
    for suf in (" FC", " AFC", " CF"):
        if name.endswith(suf):
            name = name[: -len(suf)]
    return name[4:] if name.startswith("AFC ") else name


def fmt_fixture_block(f):
    d = datetime.fromtimestamp(f["ts"], WIB)
    opp = f["away"] if f["mu_home"] else f["home"]
    return (f"<b>{HARI[d.weekday()]} {d.day:02d}/{d.month:02d} · {d.hour:02d}.{d.minute:02d} WIB</b>\n"
            f"{html.escape(short_team(opp))} · {'KANDANG' if f['mu_home'] else 'TANDANG'}\n"
            f"{html.escape(COMP_ID.get(f['comp'], f['comp']))}")


# ---------- operasi bertingkat ----------
def _season():
    d = datetime.now(WIB)
    return d.year if d.month >= 7 else d.year - 1


def get_fixtures(days_fwd=45, days_back=0, slugs=None):
    slugs = slugs or [v[1] for k, v in LEAGUES.items() if k in ("pl", "ucl", "uel", "facup", "carabao")]
    def apif():
        p = {"team": MU_APIF}
        p["next" if not days_back else "last"] = 30 if not days_back else 5
        return parse_apif_fixtures(_apif("/fixtures", **p))
    def fd():
        now = datetime.now(timezone.utc)
        j = _fd(f"/teams/{MU_FD}/matches", dateFrom=(now - timedelta(days=days_back)).strftime("%Y-%m-%d"),
                dateTo=(now + timedelta(days=days_fwd)).strftime("%Y-%m-%d"))
        return parse_fd_matches(j)
    name, res = chain([("ESPN", lambda: espn_fixtures(slugs, days_back, days_fwd)), ("API-Football", apif), ("football-data.org", fd)])
    return name, sorted(res, key=lambda f: f["ts"])


def get_standings(code):
    if code not in LEAGUES:
        raise RuntimeError("kode tidak dikenal")
    title, slug, apif_id, fd_code = LEAGUES[code]
    steps = [("ESPN", lambda: parse_espn_standings(_get(f"{ESPN_V2}/{slug}/standings"))),
             ("API-Football", lambda: parse_apif_standings(_apif("/standings", league=apif_id, season=_season())))]
    if fd_code:
        steps.append(("football-data.org", lambda: parse_fd_standings(_fd(f"/competitions/{fd_code}/standings"))))
    name, rows = chain(steps)
    return name, title, rows


def get_stats():
    """Statistik pertandingan Man Utd terakhir yang sudah selesai: (penyedia, header, hasil)."""
    _, fx = get_fixtures(0, 14)
    done = [f for f in fx if f["state"] == "post"]
    if not done:
        raise RuntimeError("belum ada pertandingan selesai dalam 14 hari terakhir")
    f = done[-1]
    def espn():
        if not (f.get("espn_id") and f.get("slug")):
            raise RuntimeError("jadwal berasal dari penyedia lain (tanpa id ESPN)")
        return parse_espn_stats(_espn_summary(f))
    def hl():
        info = []
        mid = f.get("hl_id") or hl_find_match(f, info, wide=True)
        if not mid:
            raise RuntimeError("pertandingan tidak ditemukan (" + "; ".join(info[:3]) + ")")
        j = _hl(f"/football/statistics/{mid}")
        res = parse_hl_stats(j)
        if not res:
            raise RuntimeError("statistik kosong atau format tidak dikenali (" + _shape(j) + ")")
        return res
    def apif():
        if not f.get("apif_id"):
            raise RuntimeError("tanpa id API-Football")
        return parse_apif_stats(_apif("/fixtures/statistics", fixture=f["apif_id"]))
    name, res = chain([("ESPN", espn), ("Highlightly", hl), ("API-Football", apif)])
    sc = f"{f['score'][0]}-{f['score'][1]}" if f["score"] else "vs"
    return name, f"{f['home']} {sc} {f['away']} ({f['comp']})", res


def get_lineup(f, allow_apif=True):
    """Lineup resmi satu pertandingan: (penyedia, hasil). Belum diumumkan = RuntimeError."""
    def espn():
        if not (f.get("espn_id") and f.get("slug")):
            return None
        return parse_espn_lineup(_espn_summary(f))
    def apif():
        if not allow_apif:
            return None
        d = datetime.fromtimestamp(f["ts"], timezone.utc).strftime("%Y-%m-%d")
        fx = _apif("/fixtures", team=MU_APIF, date=d).get("response", [])
        return parse_apif_lineup(_apif("/fixtures/lineups", fixture=fx[0]["fixture"]["id"])) if fx else None
    def hl():
        if not allow_apif or not os.environ.get("HIGHLIGHTLY_API_KEY"):
            return None
        if f.get("hl_miss", 0) > time.time() - 1800:
            return None  # pencarian id gagal baru-baru ini; jangan boros kuota
        mid = f.get("hl_id") or hl_find_match(f)
        if not mid:
            f["hl_miss"] = time.time()
            return None
        f["hl_id"] = mid
        return parse_hl_lineup(_hl(f"/football/lineups/{mid}"), f["mu_home"])
    return chain([("ESPN", espn), ("Highlightly", hl), ("API-Football", apif)])


def diagnose():
    """Uji tiap penyedia dari server GitHub; satu baris per pengujian."""
    def apif_status():
        j = _apif("/status")
        r = j.get("response", {})
        plan = (r.get("subscription") or {}).get("plan", "?")
        req = (r.get("requests") or {})
        try:
            _apif("/standings", league=39, season=_season())
            season = "musim berjalan terbuka"
        except Exception as e:
            season = f"musim berjalan ditolak ({str(e)[:70]})"
        return f"paket {plan}, {req.get('current', '?')}/{req.get('limit_day', '?')} hari ini, {season}"
    def hl_check():
        j = _hl("/football/matches", date=datetime.now(timezone.utc).strftime("%Y-%m-%d"), limit=1)
        plan = j.get("plan") or {}
        sample = (j.get("data") or [{}])[0]
        info = ", ".join(f"{k}={v}" for k, v in plan.items() if k != "tier")[:80] or "kuota tidak dilaporkan"
        return f"paket {plan.get('tier', '?')}; {info}; kunci contoh: {','.join(list(sample)[:8]) or '-'}"
    def hl_stats_check():
        _, fx = get_fixtures(0, 14)
        done = [x for x in fx if x["state"] == "post"]
        if not done:
            return "tidak ada pertandingan selesai dalam 14 hari terakhir"
        f = done[-1]
        info = []
        mid = hl_find_match(f, info, wide=True)
        if not mid:
            raise RuntimeError("pertandingan tidak ditemukan (" + "; ".join(info[:3]) + ")")
        j = _hl(f"/football/statistics/{mid}")
        res = parse_hl_stats(j)
        if not res:
            raise RuntimeError("statistik kosong atau format tidak dikenali (" + _shape(j) + ")")
        return f"{len(res['rows'])} baris untuk {short_team(f['home'])} vs {short_team(f['away'])}"
    tests = [("ESPN jadwal", lambda: f"{len(espn_fixtures(['eng.1'], 0, 30))} pertandingan PL"),
             ("ESPN klasemen UEL", lambda: f"{len(parse_espn_standings(_get(f'{ESPN_V2}/uefa.europa/standings')))} baris"),
             ("Highlightly", hl_check),
             ("Highlightly statistik", hl_stats_check),
             ("API-Football", apif_status),
             ("football-data klasemen PL", lambda: f"{len(parse_fd_standings(_fd('/competitions/PL/standings')))} baris")]
    out = []
    for name, fn in tests:
        try:
            out.append(f"OK  {name}: {fn()}")
        except Exception as e:
            out.append(f"GAGAL  {name}: {type(e).__name__} {str(e)[:80]}")
    return out


# ---------- teks pesan ----------
def fmt_schedule(fixtures, title):
    if not fixtures:
        return f"{title}\n\nBelum ada pertandingan terjadwal yang terbaca."
    return f"{title}\n\n" + "\n\n".join(fmt_fixture_block(f) for f in fixtures)


def fmt_standings(title, rows, provider):
    out = [f"<b>Klasemen {html.escape(title)}</b>", "<pre>"]
    grp = None
    for r in rows:
        if r["group"] != grp:
            grp = r["group"]
            if grp:
                out.append(html.escape(str(grp)))
        mark = ">" if "manchester united" in r["team"].lower() else " "
        out.append(html.escape(f"{mark}{r['pos']:>2} {r['team'][:20]:<20} {r['p']:>2} {r['w']:>2} {r['d']:>2} {r['l']:>2} {r['pts']:>3}"))
    out += ["</pre>", "Kolom: posisi, tim, main, menang, seri, kalah, poin", f"<i>({provider})</i>"]
    return "\n".join(out)


def fmt_stats(header, res, provider):
    lines = [f"<b>Statistik</b>: {html.escape(header)}", ""]
    lines += [f"{lab}: {a} - {b}" for lab, a, b in res["rows"]]
    lines += ["", f"Man United - {html.escape(res['opp'])}", f"<i>({provider})</i>"]
    return "\n".join(lines)


def fmt_lineup(f, lu, provider):
    opp = f["away"] if f["mu_home"] else f["home"]
    xi = "\n".join(html.escape(f"{n} {name}" + (f" ({pos})" if pos else "")) for n, name, pos in lu["xi"])
    subs = ", ".join(html.escape(s) for s in lu["subs"])
    head = f"Man United vs {html.escape(opp)}" + (f" · Formasi {html.escape(lu['formation'])}" if lu["formation"] else "")
    return f"<b>[LINEUP]</b>\n\n{head}\n\n{xi}" + (f"\n\nCadangan: {subs}" if subs else "") + f"\n\n<i>({provider})</i>"
