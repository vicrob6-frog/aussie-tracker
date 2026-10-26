#!/usr/bin/env python3
"""Aussie Tracker daily updater (Bzzoiro Sports Data, free API).
Reads data/roster.json, writes docs/players.json. Needs env var BSD_API_KEY."""
import json, os, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROSTER, CACHE, OUT = (os.path.join(ROOT, *p) for p in (("data", "roster.json"), ("data", "cache.json"), ("docs", "players.json")))
KEY, BASE, DELAY, TODAY = os.environ.get("BSD_API_KEY"), "https://sports.bzzoiro.com", 0.3, date.today()
CALENDAR_YEAR = {"MLS", "Eliteserien", "Indian Super League"}  # seasons that run Jan to Dec

def get(path, **q):
    url = f"{BASE}/api/v2{path}?" + urllib.parse.urlencode(q)
    for attempt in range(4):
        time.sleep(DELAY)
        try:
            req = urllib.request.Request(url, headers={"Authorization": "Token " + KEY})
            with urllib.request.urlopen(req, timeout=60) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3: time.sleep(int(e.headers.get("Retry-After") or 20)); continue
            raise RuntimeError(f"{path} {q} -> HTTP {e.code}")

def rows(path, **q):
    out, off = [], 0
    while True:
        d = get(path, limit=200, offset=off, **q)
        res = d.get("results", []) if isinstance(d, dict) else d
        out += res; off += 200
        if not (isinstance(d, dict) and d.get("next")) or not res: return out

def norm(s): return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower().replace("’", "'")
def pick(d, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v is not None and v != "": return v
    return default
def nm(v): return (v.get("name") if isinstance(v, dict) else v) or ""
def ident(v): return v.get("id") if isinstance(v, dict) else v
def load(p, d): return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d
def save(p, o): json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
def img(kind, i): return f"{BASE}/img/{kind}/{i}/" if i else None

AU = ("AU", "AUS", "AUSTRALIA")
shown = set()
def peek(label, obj):  # prints one raw sample of each response type so problems can be diagnosed from the log
    if label not in shown: shown.add(label); print(f"  [debug] {label}: {json.dumps(obj, ensure_ascii=False)[:1500]}")
def squash(s): return norm(s).replace("'", "").replace(" ", "").replace("-", "")

def resolve(p, c):
    """Returns (player_id, team_id_or_None, position_or_None)."""
    if p.get("id"): return p["id"], p.get("team_id"), None
    first, last, club = norm(p["name"].split()[0]), squash(p["name"].split()[-1]), norm(p["club"])
    tail = p["name"].split()[-1].replace("’", "'")
    seen = {}
    for q in dict.fromkeys([p["name"].replace("’", "'"), tail, tail.split("'")[-1]]):
        res = get("/players/", name=q, limit=50)
        for r in (res.get("results", []) if isinstance(res, dict) else res): seen[r["id"]] = r
    scored = []
    for r in seen.values():
        n = norm(nm(r.get("name")))
        if last not in squash(nm(r.get("name"))): continue
        nat = str(nm(pick(r, "nationality_code", "nationality", "country_code", default=""))).upper()
        tm = norm(nm(r.get("current_team")) or nm(r.get("team")) or r.get("team_name") or "")
        scored.append(((n[:1] == first[:1]) * 2 + (nat in AU) * 3 + bool(club and tm and (club in tm or tm in club)) * 4, r))
    scored.sort(key=lambda x: -x[0])
    if not scored: print(f"  ! could not find {p['name']}: add \"id\" to data/roster.json"); return None, None, None
    best = scored[0][1]
    if scored[0][0] < 5 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        print(f"  ? {p['name']}: using id {best['id']}. Candidates: " + "; ".join(
            f"{r['id']} {nm(r.get('name'))} ({pick(r, 'nationality_code', 'nationality', default='?')}, {nm(r.get('current_team')) or '?'}, score {sc})" for sc, r in scored[:5]))
    peek("search hit", best)
    c["ids"][p["name"]] = best["id"]
    return best["id"], pick(best, "current_team_id", "team_id") or ident(best.get("current_team")) or ident(best.get("team")), pick(best, "specific_position", "position")

def team_from(prof):
    for k in ("current_team_id", "team_id", "club_id"):
        if prof.get(k): return prof[k]
    for k in ("current_team", "team", "club"):
        v = prof.get(k)
        if isinstance(v, dict) and v.get("id"): return v["id"]
        if isinstance(v, int): return v
    return None
    
def main():
    if not KEY: sys.exit("Set the BSD_API_KEY environment variable.")
    roster, c = load(ROSTER, []), load(CACHE, {"ids": {}})
    leagues = {x["id"]: x.get("name") for x in rows("/leagues/")}
    events_by_team, players = {}, []
    start_cal, start_eu = date(TODAY.year, 1, 1), date(TODAY.year if TODAY.month >= 7 else TODAY.year - 1, 7, 1)
    for p in roster:
        try:
            pid, tid, apos = resolve(p, c)
            if not pid: continue
            tid = p.get("team_id") or tid
            pos = p.get("pos_fixed") or apos or p["pos"]
            if not tid:
                prof = get(f"/players/{pid}/"); peek("profile", prof); tid = team_from(prof)
            if not tid:
                lg0 = rows(f"/players/{pid}/stats/", date_from=(TODAY - timedelta(days=60)).isoformat())
                peek("stats row", lg0[:1])
                tid = next((pick(r, "team_id") or ident(r.get("team")) for r in lg0 if pick(r, "team_id") or r.get("team")), None)
            if not tid: print(f"  ! no current team for {p['name']}: add \"team_id\" to its entry in data/roster.json"); continue
            if tid not in events_by_team:
                ev = rows("/events/", team_id=tid, status="finished", date_from=(TODAY - timedelta(days=60)).isoformat())
                peek("event", ev[:1])
                events_by_team[tid] = sorted(ev, key=lambda e: e.get("event_date") or "", reverse=True)[:8]
            log = rows(f"/players/{pid}/stats/", team_id=tid, date_from=(start_cal if p["league"] in CALENDAR_YEAR else start_eu).isoformat())
            peek("stats row", log[:1])
            by_ev = {ident(pick(r, "event_id", "event", "match_id")): r for r in log}
            ms, club = [], p["club"]
            for e in events_by_team[tid]:
                hid, aid = pick(e, "home_team_id") or ident(e.get("home_team")), pick(e, "away_team_id") or ident(e.get("away_team"))
                hn, an = nm(e.get("home_team")), nm(e.get("away_team"))
                home = (hid == tid) if hid is not None else (norm(p["club"]) in norm(hn) or norm(hn) in norm(p["club"]))
                oid, opp, mine = (aid, an, hn) if home else (hid, hn, an)
                club = mine or club
                r = by_ev.get(e["id"], {})
                gf, ga = pick(e, "home_score", default=0), pick(e, "away_score", default=0)
                tf, ta = (gf, ga) if home else (ga, gf)
                mn = pick(r, "minutes_played", "minutes", default=0) or 0
                rt = pick(r, "rating")
                lg = e.get("league")
                lid = pick(e, "league_id") or ident(lg)
                ms.append({"date": (e.get("event_date") or "")[:10], "comp": nm(lg) or leagues.get(lid) or "", "compLogo": img("league", lid),
                           "home": home, "team": mine, "teamLogo": img("team", tid), "opp": opp, "oppLogo": img("team", oid), "tf": tf, "ta": ta,
                           "min": mn, "g": pick(r, "goals", default=0) or 0, "a": pick(r, "goal_assist", "goals_assist", "assists", default=0) or 0,
                           "yc": pick(r, "yellow_cards", "yellow_card", "yellow", default=0) or 0, "rc": pick(r, "red_cards", "red_card", "red", default=0) or 0,
                           "sv": pick(r, "saves", "goalkeeper_saves", "total_saves", default=0) or 0, "cs": int(pos == "GK" and mn > 0 and ta == 0),
                           "rt": f"{float(rt):.1f}" if rt else None})
            played = [r for r in log if (pick(r, "minutes_played", "minutes", default=0) or 0) > 0]
            tot = lambda *k: sum(pick(r, *k, default=0) or 0 for r in played)
            players.append({"name": p["name"], "pos": pos, "club": club, "clubLogo": img("team", tid), "photo": img("player", pid),
                            "season": {"apps": len(played), "min": tot("minutes_played", "minutes"), "g": tot("goals"), "a": tot("goal_assist", "goals_assist", "assists"), "sv": tot("saves", "goalkeeper_saves", "total_saves")},
                            "matches": ms})
        except RuntimeError as err:
            print("  !", p["name"], err)
    save(CACHE, c)
    save(OUT, {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "players": players})
    print(f"Wrote {len(players)} of {len(roster)} players.")

if __name__ == "__main__": main()
