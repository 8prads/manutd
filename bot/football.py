"""Data pertandingan: jadwal, klasemen, statistik, lineup.
Penyedia dicoba berurutan: ESPN (tidak resmi, tanpa kunci) -> API-Football -> football-data.org."""
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
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MUFCNewsBot/1.0)", **(headers or {})},
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
        score = None
        try:
            score = (int(by["home"]["score"]), int(by["away"]["score"]))
        except (KeyError, ValueError, TypeError):
            pass
        out.append(_fx(_ts(ev.get("date", "")), ESPN_NAMES.get(slug, slug), by["home"]["team"]["displayName"],
                       by["away"]["team"]["displayName"], (comp.get("venue") or {}).get("fullName"),
                       ev.get("status", {}).get("type", {}).get("state", "pre"), score, ev.get("id"), slug))
    return out


def espn_fixtures(slugs, days_back, days_fwd):
    now = datetime.now(timezone.utc)
    rng = f"{(now - timedelta(days=days_back)):%Y%m%d}-{(now + timedelta(days=days_fwd)):%Y%m%d}"
    out, errs = [], 0
    for slug in slugs:
        try:
            out += parse_espn_events(_get(f"{ESPN}/{slug}/scoreboard", params={"dates": rng, "limit": 400}), slug)
        except Exception:
            errs += 1
    if errs == len(slugs):
        raise RuntimeError("semua kompetisi gagal")
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
    def espn():
        done = [f for f in espn_fixtures([v[1] for v in LEAGUES.values()][:5], 14, 0) if f["state"] == "post"]
        if not done:
            return None
        f = done[-1]
        res = parse_espn_stats(_espn_summary(f))
        return (f, res) if res else None
    def apif():
        done = [f for f in parse_apif_fixtures(_apif("/fixtures", team=MU_APIF, last=3)) if f["state"] == "post"]
        if not done:
            return None
        f = done[-1]
        res = parse_apif_stats(_apif("/fixtures/statistics", fixture=f["apif_id"]))
        return (f, res) if res else None
    name, (f, res) = chain([("ESPN", espn), ("API-Football", apif)])
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
    return chain([("ESPN", espn), ("API-Football", apif)])


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
    tests = [("ESPN jadwal", lambda: f"{len(espn_fixtures(['eng.1'], 0, 30))} pertandingan PL"),
             ("ESPN klasemen UEL", lambda: f"{len(parse_espn_standings(_get(f'{ESPN_V2}/uefa.europa/standings')))} baris"),
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
    return f"{title}\n\n" + "\n".join(html.escape(fmt_fixture_line(f)) for f in fixtures)


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
