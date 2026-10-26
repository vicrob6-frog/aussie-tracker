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
    """Returns (player_id, team_id_or_None)."""
    if p.get("id"): return p["id"], p.get("team_id")
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
    if not scored: print(f"  ! could not find {p['name']}: add \"id\" to data/roster.json"); return None, None
    best = scored[0][1]
    if scored[0][0] < 5 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        print(f"  ? {p['name']}: using id {best['id']}. Candidates: " + "; ".join(
            f"{r['id']} {nm(r.get('name'))} ({pick(r, 'nationality_code', 'nationality', default='?')}, {nm(r.get('current_team')) or '?'}, score {sc})" for sc, r in scored[:5]))
    peek("search hit", best)
    c["ids"][p["name"]] = best["id"]
    return best["id"], pick(best, "current_team_id", "team_id") or ident(best.get("current_team")) or ident(best.get("team"))

def team_from(prof):
    for k in ("current_team_id", "team_id", "club_id"):
        if prof.get(k): return prof[k]
    for k in ("current_team", "team", "club"):
        v = prof.get(k)
        if isinstance(v, dict) and v.get("id"): return v["id"]
        if isinstance(v, int): return v
    return None
