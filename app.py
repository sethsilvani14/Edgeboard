import math
import os
import re
from datetime import datetime, timezone, timedelta
from difflib import get_close_matches

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="EdgeBoard V3", page_icon="📊", layout="centered")

st.markdown("""
<style>
.block-container {max-width: 780px; padding-top: 1rem; padding-bottom: 5rem;}
.bet-card {border:1px solid rgba(128,128,128,.28); border-radius:16px; padding:14px; margin-bottom:12px;}
.pill {font-size:.82rem; font-weight:700; padding:4px 8px; border-radius:999px; border:1px solid rgba(128,128,128,.35); display:inline-block; margin-right:5px;}
.small {font-size:.86rem; opacity:.78;}
.metric-row {display:flex; gap:18px; flex-wrap:wrap; margin-top:10px;}
.metric-box {min-width:95px;}
.metric-label {font-size:.70rem; opacity:.62;}
.metric-val {font-size:1.02rem; font-weight:650;}
.stButton>button {border-radius:12px; width:100%;}
[data-testid="stMetricValue"] {font-size:1.25rem;}
</style>
""", unsafe_allow_html=True)

RUNDOWN_BASE = "https://therundown.io/api/v2"
CFBD_BASE = "https://api.collegefootballdata.com"
MODEL_VERSION = "CFB baseline 0.4 • TheRundown free stack"
HOME_FIELD = 2.5
MARGIN_SD = 14.0
TOTAL_SD = 17.0


def secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return value or os.getenv(name, "")


def season_year() -> int:
    now = datetime.now()
    return now.year if now.month >= 7 else now.year - 1


def american_implied(odds: float) -> float:
    if odds is None or pd.isna(odds):
        return float("nan")
    odds = float(odds)
    return 100 / (odds + 100) if odds > 0 else (-odds) / ((-odds) + 100)


def profit_per_dollar(odds: float) -> float:
    odds = float(odds)
    return odds / 100 if odds > 0 else 100 / abs(odds)


def ev_pct(prob: float, odds: float) -> float:
    return 100 * (prob * profit_per_dollar(odds) - (1 - prob))


def normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def grade_for_ev(ev: float):
    if ev >= 6:
        return "A", "0.75u"
    if ev >= 4.5:
        return "A-", "0.50u"
    if ev >= 3:
        return "B+", "0.35u"
    if ev >= 1.5:
        return "B", "0.25u"
    return "PASS", "0u"


def fmt_odds(v):
    if v is None or pd.isna(v):
        return "—"
    v = int(round(float(v)))
    return f"+{v}" if v > 0 else str(v)


def fmt_point(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{float(v):+g}"


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_rundown_catalogs(api_key: str):
    """Reference catalogs are free. Discover IDs instead of assuming them."""
    headers = {"X-TheRundown-Key": api_key}
    def get(path):
        r = requests.get(f"{RUNDOWN_BASE}/{path}", headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()

    sports = get("sports")
    markets = get("markets")
    affiliates = get("affiliates")
    return sports, markets, affiliates


def _items(payload, key=None):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if key and isinstance(payload.get(key), list):
            return payload[key]
        for k in ("data", "response", "items"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def discover_rundown_ids(sports_payload, markets_payload, affiliates_payload):
    sports = _items(sports_payload, "sports")
    markets = _items(markets_payload, "markets")
    affiliates = _items(affiliates_payload, "affiliates")

    # Find the current college-football/NCAAF sport entry from the provider catalog.
    scored = []
    for x in sports:
        text = " ".join(str(x.get(k, "")) for k in ("name", "sport_name", "description", "league_name")).lower()
        score = 0
        if "ncaaf" in text: score += 10
        if "college" in text and "football" in text: score += 8
        if "ncaa" in text and "football" in text: score += 7
        if score:
            scored.append((score, x))
    if not scored:
        raise RuntimeError("TheRundown catalog did not expose an NCAAF/college-football sport entry.")
    sport = sorted(scored, key=lambda z: z[0], reverse=True)[0][1]
    sport_id = sport.get("sport_id", sport.get("id"))

    wanted_markets = {}
    for x in markets:
        name = str(x.get("name", "")).lower().replace(" ", "")
        mid = x.get("market_id", x.get("id"))
        period = x.get("period_id", 0)
        if period not in (None, 0):
            continue
        if "moneyline" in name or "moneyline" == name:
            wanted_markets["h2h"] = mid
        elif "spread" in name and "live" not in name:
            wanted_markets["spreads"] = mid
        elif ("total" in name or "over/under" in name) and "team" not in name and "live" not in name:
            wanted_markets["totals"] = mid
    # Official V2 core-market fallback if catalog naming changes unexpectedly.
    wanted_markets.setdefault("h2h", 1)
    wanted_markets.setdefault("spreads", 2)
    wanted_markets.setdefault("totals", 3)

    preferred = ["DraftKings", "FanDuel", "BetMGM"]
    aff_map = {}
    for x in affiliates:
        name = str(x.get("name", x.get("affiliate_name", "")))
        aid = x.get("affiliate_id", x.get("id"))
        if aid is not None:
            aff_map[name.lower()] = (str(aid), name)
    chosen = []
    for pref in preferred:
        for low, pair in aff_map.items():
            if pref.lower() in low:
                chosen.append(pair)
                break
    if not chosen:
        raise RuntimeError("TheRundown affiliate catalog did not return a usable free sportsbook.")
    return str(sport_id), wanted_markets, chosen[:3]


def quota_from_rundown(headers):
    lower = {str(k).lower(): v for k, v in headers.items()}
    return {
        "used": lower.get("x-datapoints-used") or lower.get("x-datapoints"),
        "remaining": lower.get("x-datapoints-remaining"),
        "limit": lower.get("x-datapoints-limit"),
        "delay": lower.get("x-data-delay-seconds"),
    }


def normalize_rundown_event(raw, market_ids, affiliate_pairs):
    teams = raw.get("teams") or []
    away_obj = next((t for t in teams if t.get("is_away")), teams[0] if teams else {})
    home_obj = next((t for t in teams if t.get("is_home")), teams[1] if len(teams) > 1 else {})
    away, home = away_obj.get("name"), home_obj.get("name")
    if not away or not home:
        return None

    affiliate_names = {str(a): n for a, n in affiliate_pairs}
    books = {str(a): {"key": str(a), "title": n, "markets": []} for a, n in affiliate_pairs}
    key_by_id = {str(v): k for k, v in market_ids.items()}

    # Build each book's markets from the normalized V2 hierarchy.
    per_book_market = {(aid, mk): [] for aid in books for mk in market_ids}
    for market in raw.get("markets", []) or []:
        mk = key_by_id.get(str(market.get("market_id")))
        if not mk or market.get("period_id", 0) not in (None, 0):
            continue
        for participant in market.get("participants", []) or []:
            pname = participant.get("name")
            for line in participant.get("lines", []) or []:
                line_value = line.get("value")
                for aid, price_obj in (line.get("prices") or {}).items():
                    aid = str(aid)
                    if aid not in books or not price_obj or price_obj.get("is_main_line") is False:
                        continue
                    price = price_obj.get("price")
                    if price in (None, 0.0001, "0.0001"):
                        continue
                    try: price = float(price)
                    except Exception: continue
                    outcome = {"name": pname, "price": price}
                    if mk in ("spreads", "totals"):
                        try: outcome["point"] = float(line_value)
                        except Exception: continue
                    per_book_market[(aid, mk)].append(outcome)

    for aid, book in books.items():
        for mk in ("h2h", "spreads", "totals"):
            outcomes = per_book_market.get((aid, mk), [])
            if outcomes:
                book["markets"].append({"key": mk, "outcomes": outcomes})

    return {
        "id": raw.get("event_id"), "home_team": home, "away_team": away,
        "commence_time": raw.get("event_date"),
        "bookmakers": [b for b in books.values() if b["markets"]],
    }


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_rundown_board(api_key: str, sport_id: str, market_items, affiliate_pairs, days=7):
    """Pregame snapshots only. Six-hour cache keeps the free data-point budget comfortable."""
    headers = {"X-TheRundown-Key": api_key}
    market_ids = dict(market_items)
    affiliate_pairs = list(affiliate_pairs)
    mids = ",".join(str(v) for v in market_ids.values())
    aids = ",".join(str(a) for a, _ in affiliate_pairs)
    today = datetime.now(timezone.utc).date()
    out, usage = [], {"used": 0, "remaining": None, "limit": None, "delay": None, "requests": 0}

    for offset in range(days + 1):
        day = today + timedelta(days=offset)
        r = requests.get(
            f"{RUNDOWN_BASE}/sports/{sport_id}/events/{day.isoformat()}",
            params={"market_ids": mids, "affiliate_ids": aids, "main_line": "true", "hide_closed": "true"},
            headers=headers, timeout=30,
        )
        if r.status_code == 429:
            raise RuntimeError("TheRundown rate/quota limit was reached. Wait and try again later.")
        r.raise_for_status()
        q = quota_from_rundown(r.headers)
        usage["requests"] += 1
        try: usage["used"] += int(q.get("used") or 0)
        except Exception: pass
        for k in ("remaining", "limit", "delay"):
            if q.get(k) is not None: usage[k] = q[k]
        payload = r.json()
        for raw in _items(payload, "events"):
            event = normalize_rundown_event(raw, market_ids, affiliate_pairs)
            if event:
                out.append(event)
    return out, usage


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cfbd_games(api_key: str, year: int):
    r = requests.get(
        f"{CFBD_BASE}/games",
        params={"year": year, "seasonType": "regular", "classification": "fbs"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_srs(api_key: str, year: int):
    r = requests.get(
        f"{CFBD_BASE}/ratings/srs",
        params={"year": year},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def build_team_stats(games):
    rows = []
    for g in games:
        hp, ap = g.get("homePoints"), g.get("awayPoints")
        if hp is None or ap is None or not g.get("completed", False):
            continue
        rows.append((g.get("homeTeam"), hp, ap))
        rows.append((g.get("awayTeam"), ap, hp))

    if not rows:
        return {}, 27.0

    df = pd.DataFrame(rows, columns=["team", "pf", "pa"]).dropna()
    nat = float(df["pf"].mean())
    stats = {}
    for team, grp in df.groupby("team"):
        n = len(grp)
        pf = (grp["pf"].sum() + 3 * nat) / (n + 3)
        pa = (grp["pa"].sum() + 3 * nat) / (n + 3)
        stats[team] = {"pf": float(pf), "pa": float(pa), "games": int(n)}
    return stats, nat


def build_srs_map(ratings):
    out = {}
    for r in ratings:
        team = r.get("team")
        rating = r.get("rating")
        if team and rating is not None:
            out[team] = float(rating)
    return out


def match_team(name: str, candidates):
    if name in candidates:
        return name
    aliases = {
        "Miami Hurricanes": "Miami", "Miami (FL)": "Miami", "Ole Miss Rebels": "Ole Miss",
        "UMass Minutemen": "Massachusetts", "UConn Huskies": "Connecticut", "UTSA Roadrunners": "UTSA",
        "UCF Knights": "UCF", "USC Trojans": "USC", "LSU Tigers": "LSU", "BYU Cougars": "BYU",
        "SMU Mustangs": "SMU", "TCU Horned Frogs": "TCU",
    }
    if name in aliases and aliases[name] in candidates:
        return aliases[name]
    matches = get_close_matches(name, list(candidates), n=1, cutoff=0.72)
    return matches[0] if matches else None


def project_game(home, away, stats, srs, nat_avg):
    candidates = set(stats) | set(srs)
    h = match_team(home, candidates)
    a = match_team(away, candidates)
    if not h or not a:
        return None

    hs = stats.get(h, {"pf": nat_avg, "pa": nat_avg, "games": 0})
    as_ = stats.get(a, {"pf": nat_avg, "pa": nat_avg, "games": 0})
    raw_home = (hs["pf"] + as_["pa"]) / 2 + HOME_FIELD / 2
    raw_away = (as_["pf"] + hs["pa"]) / 2 - HOME_FIELD / 2
    score_margin = raw_home - raw_away
    total = max(24.0, raw_home + raw_away)

    if h in srs and a in srs:
        srs_margin = srs[h] - srs[a] + HOME_FIELD
        margin = 0.55 * srs_margin + 0.45 * score_margin
        srs_note = f"SRS margin {srs_margin:+.1f}"
    else:
        margin = score_margin
        srs_note = "SRS unavailable; scoring model only"

    home_pts = (total + margin) / 2
    away_pts = (total - margin) / 2
    return {
        "home_match": h, "away_match": a, "home_points": home_pts, "away_points": away_pts,
        "margin": margin, "total": total, "home_games": hs["games"], "away_games": as_["games"],
        "note": srs_note,
    }


def get_market(bookmaker, market_key):
    for m in bookmaker.get("markets", []):
        if m.get("key") == market_key:
            return m
    return None


def price_row(event, proj, bookmaker, market_key, outcome):
    price = outcome.get("price")
    if price is None:
        return None
    home, away = event["home_team"], event["away_team"]
    name, point = outcome.get("name"), outcome.get("point")

    if market_key == "spreads":
        if point is None or name not in (home, away):
            return None
        sel_mu = proj["margin"] if name == home else -proj["margin"]
        prob = 1 - normal_cdf(((-float(point)) - sel_mu) / MARGIN_SD)
        market_name = "Spread"
        selection_key = name
        selection = f"{name} {float(point):+g}"
        model_display = f"Fair {-sel_mu:+.1f}"
    elif market_key == "totals":
        if point is None or name not in ("Over", "Under"):
            return None
        z = (float(point) - proj["total"]) / TOTAL_SD
        prob = 1 - normal_cdf(z) if name == "Over" else normal_cdf(z)
        market_name = "Total"
        selection_key = name
        selection = f"{name} {float(point):g}"
        model_display = f"{proj['total']:.1f} total"
    elif market_key == "h2h":
        if name not in (home, away):
            return None
        home_prob = 1 - normal_cdf((0 - proj["margin"]) / MARGIN_SD)
        prob = home_prob if name == home else 1 - home_prob
        market_name = "Moneyline"
        selection_key = name
        selection = f"{name} ML"
        fair_decimal = 1 / max(prob, 0.0001)
        fair_american = (fair_decimal - 1) * 100 if fair_decimal >= 2 else -100 / (fair_decimal - 1)
        model_display = f"Fair {fmt_odds(fair_american)}"
    else:
        return None

    ev = ev_pct(prob, price)
    grade, stake = grade_for_ev(ev)
    return {
        "event_id": event.get("id"), "commence_time": event.get("commence_time"),
        "game": f"{away} @ {home}", "home": home, "away": away, "market": market_name,
        "market_key": market_key, "selection_key": selection_key, "selection": selection,
        "book": bookmaker.get("title", bookmaker.get("key", "Book")), "book_key": bookmaker.get("key"),
        "price": float(price), "point": point, "prob": float(prob), "implied": float(american_implied(price)),
        "ev": float(ev), "grade": grade, "stake": stake, "model": model_display,
        "proj_home": proj["home_points"], "proj_away": proj["away_points"], "proj_margin": proj["margin"],
        "proj_total": proj["total"], "model_note": proj["note"],
        "sample": f"{proj['away_match']} {proj['away_games']} g • {proj['home_match']} {proj['home_games']} g",
    }


def build_board(events, stats, srs, nat_avg):
    rows, unmatched = [], []
    for event in events:
        proj = project_game(event.get("home_team", ""), event.get("away_team", ""), stats, srs, nat_avg)
        if proj is None:
            unmatched.append(f"{event.get('away_team')} @ {event.get('home_team')}")
            continue
        for bookmaker in event.get("bookmakers", []):
            for market_key in ("h2h", "spreads", "totals"):
                market = get_market(bookmaker, market_key)
                if not market:
                    continue
                for outcome in market.get("outcomes", []):
                    row = price_row(event, proj, bookmaker, market_key, outcome)
                    if row:
                        rows.append(row)
    return pd.DataFrame(rows), unmatched


def novig_moneyline_probs(group):
    """Return per-book no-vig probabilities for each team in a moneyline group."""
    records = []
    for book, grp in group.groupby("book"):
        if grp["selection_key"].nunique() < 2:
            continue
        implied = grp.set_index("selection_key")["implied"].to_dict()
        denom = sum(implied.values())
        if denom <= 0:
            continue
        for sel, p in implied.items():
            records.append({"book": book, "selection_key": sel, "novig_prob": p / denom})
    return pd.DataFrame(records)


def market_consensus(board):
    """Aggregate all returned books into one market view per side/outcome."""
    if board.empty:
        return pd.DataFrame()

    out = []
    for (event_id, market, selection_key), grp in board.groupby(["event_id", "market", "selection_key"], sort=False):
        grp = grp.copy()
        # Best available offer is whichever line+price yields the highest model EV.
        best = grp.sort_values(["ev", "price"], ascending=[False, False]).iloc[0]
        books = grp["book"].nunique()

        if market in ("Spread", "Total"):
            points = pd.to_numeric(grp["point"], errors="coerce").dropna()
            consensus_point = float(points.median()) if not points.empty else float("nan")
            dispersion = float(points.max() - points.min()) if len(points) > 1 else 0.0
            if dispersion <= 0.5:
                market_conf = "Tight"
            elif dispersion <= 1.5:
                market_conf = "Normal"
            else:
                market_conf = "Wide"

            if market == "Spread":
                sel_mu = best["proj_margin"] if selection_key == best["home"] else -best["proj_margin"]
                model_edge = sel_mu + consensus_point
                consensus_text = f"{selection_key} {consensus_point:+g}"
                edge_text = f"{model_edge:+.1f} pts vs consensus"
            else:
                consensus_text = f"O/U {consensus_point:g}"
                raw_edge = best["proj_total"] - consensus_point
                model_edge = raw_edge if selection_key == "Over" else -raw_edge
                edge_text = f"{model_edge:+.1f} pts vs consensus"
            consensus_prob = float("nan")
        else:
            event_ml = board[(board.event_id == event_id) & (board.market == "Moneyline")]
            nv = novig_moneyline_probs(event_ml)
            vals = nv.loc[nv.selection_key == selection_key, "novig_prob"] if not nv.empty else pd.Series(dtype=float)
            consensus_prob = float(vals.mean()) if not vals.empty else float("nan")
            dispersion = float(vals.max() - vals.min()) * 100 if len(vals) > 1 else 0.0
            if dispersion <= 1.5:
                market_conf = "Tight"
            elif dispersion <= 3.5:
                market_conf = "Normal"
            else:
                market_conf = "Wide"
            consensus_text = f"{consensus_prob*100:.1f}% no-vig" if not math.isnan(consensus_prob) else "—"
            model_edge = (best["prob"] - consensus_prob) * 100 if not math.isnan(consensus_prob) else float("nan")
            edge_text = f"{model_edge:+.1f}% prob vs consensus" if not math.isnan(model_edge) else "—"
            consensus_point = float("nan")

        row = best.to_dict()
        row.update({
            "books_count": int(books), "consensus_point": consensus_point,
            "consensus_prob": consensus_prob, "consensus": consensus_text,
            "market_confidence": market_conf, "dispersion": dispersion,
            "consensus_edge": model_edge, "edge": edge_text,
        })
        out.append(row)

    return pd.DataFrame(out)


# ---------- Header ----------
left, right = st.columns([3, 1])
with left:
    st.title("📊 EdgeBoard")
    st.caption(f"V3.2 • {MODEL_VERSION} • consensus-market architecture")
with right:
    st.write("")
    st.write("")
    if st.button("↻ Refresh view"):
        st.rerun()

rundown_key = secret("THERUNDOWN_API_KEY")
cfbd_key = secret("CFBD_API_KEY")
ready = bool(rundown_key and cfbd_key)
year = season_year()

if "my_bets" not in st.session_state:
    st.session_state.my_bets = []

if not ready:
    st.warning("V3.2 is installed, but live mode needs two API keys in Streamlit Secrets: THERUNDOWN_API_KEY and CFBD_API_KEY.")
    st.info("Open the **Setup** tab below. Once the keys are added, EdgeBoard switches to live CFB automatically.")

board = pd.DataFrame()
consensus = pd.DataFrame()
unmatched, quota = [], {}
load_error = None
stats, srs, nat_avg = {}, {}, 27.0

if ready:
    try:
        with st.spinner("Loading CFB market + model data…"):
            games = fetch_cfbd_games(cfbd_key, year)
            ratings = fetch_srs(cfbd_key, year)
            stats, nat_avg = build_team_stats(games)
            srs = build_srs_map(ratings)
            sports_cat, markets_cat, affiliates_cat = fetch_rundown_catalogs(rundown_key)
            sport_id, market_ids, affiliate_pairs = discover_rundown_ids(sports_cat, markets_cat, affiliates_cat)
            normalized_events, quota = fetch_rundown_board(
                rundown_key, sport_id, tuple(market_ids.items()), tuple(affiliate_pairs), days=7
            )
            board, unmatched = build_board(normalized_events, stats, srs, nat_avg)
            consensus = market_consensus(board)
    except Exception as exc:
        load_error = str(exc)
        st.error("Live data did not load. EdgeBoard did not fabricate replacement picks.")
        st.code(load_error)

best_tab, games_tab, market_tab, track_tab, model_tab, setup_tab = st.tabs(
    ["🔥 Best", "🏟 Games", "📈 Market", "🧾 My Bets", "🧠 Model", "⚙️ Setup"]
)

with best_tab:
    st.subheader("CFB consensus board")
    if not ready:
        st.write("Add the two keys in **Setup** to activate this board.")
    elif load_error:
        st.write("Fix the connection issue shown above, then refresh.")
    elif consensus.empty:
        st.info("No priced CFB markets matched the model right now.")
    else:
        min_ev = st.slider("Minimum estimated EV at best available price", 0.0, 10.0, 1.5, 0.5)
        mode = st.segmented_control("Show", ["A/B plays", "Positive EV", "All"], default="A/B plays")
        view = consensus[consensus.ev >= min_ev].copy()
        if mode == "A/B plays":
            view = view[view.grade != "PASS"]
        elif mode == "Positive EV":
            view = view[view.ev > 0]
        view = view.sort_values(["ev", "prob"], ascending=False)

        c1, c2, c3 = st.columns(3)
        c1.metric("Plays", len(view))
        c2.metric("Games", consensus.event_id.nunique())
        c3.metric("Books seen", board.book.nunique())
        if quota.get("remaining"):
            st.caption(f"TheRundown datapoints remaining: {quota['remaining']} • this cached snapshot used {quota.get('used', '—')} datapoints")

        if view.empty:
            st.info("Nothing clears that filter. PASS is an acceptable answer.")

        for idx, row in view.iterrows():
            start = pd.to_datetime(row.commence_time, utc=True, errors="coerce")
            start_txt = start.tz_convert("America/New_York").strftime("%a %I:%M %p ET") if pd.notna(start) else "Time TBD"
            best_selection = row.selection
            st.markdown(f"""
            <div class="bet-card">
              <div class="small">CFB • {row.game} • {row.market} • {start_txt}</div>
              <h3 style="margin:.35rem 0 .25rem 0">{best_selection} &nbsp; {fmt_odds(row.price)}</h3>
              <span class="pill">{row.grade}</span><span class="pill">{row.stake}</span><span class="pill">{row.market_confidence} market</span>
              <div class="metric-row">
                <div class="metric-box"><div class="metric-label">CONSENSUS</div><div class="metric-val">{row.consensus}</div></div>
                <div class="metric-box"><div class="metric-label">MODEL</div><div class="metric-val">{row.model}</div></div>
                <div class="metric-box"><div class="metric-label">EST. EV</div><div class="metric-val">{row.ev:+.1f}%</div></div>
              </div>
              <div class="small" style="margin-top:8px">{row.edge} • {row.books_count} books • projected score: {row.away} {row.proj_away:.1f} — {row.home} {row.proj_home:.1f}</div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("Market + best available price"):
                st.write(f"**Market consensus:** {row.consensus}")
                st.write(f"**Model edge:** {row.edge}")
                st.write(f"**Best available offer:** {row.selection} {fmt_odds(row.price)} at **{row.book}**")
                st.write(f"**Model win/cover probability:** {row.prob*100:.1f}%")
                st.write(f"**Model basis:** {row.model_note}; current-season scoring is shrunk toward the national average early in the year.")
                st.write(f"**Sample:** {row['sample']}")
                same = board[(board.event_id == row.event_id) & (board.market == row.market) & (board.selection_key == row.selection_key)]
                if not same.empty:
                    show = same[["book", "selection", "price", "point", "ev"]].copy()
                    show["price"] = show["price"].map(fmt_odds)
                    show["ev"] = show["ev"].map(lambda x: f"{x:+.1f}%")
                    st.dataframe(show.sort_values("ev", ascending=False), hide_index=True, use_container_width=True)
                st.caption("Consensus is built from the free TheRundown sportsbook prices returned for each game. The book is a price source, not the model's identity.")

            if st.button("＋ Track bet", key=f"track_{idx}_{row.event_id}_{row.market}_{row.selection_key}"):
                item = row.to_dict()
                item["tracked_at"] = datetime.now(timezone.utc).isoformat()
                st.session_state.my_bets.append(item)
                st.toast("Added to My Bets")

with games_tab:
    st.subheader("Game projections")
    if consensus.empty:
        st.info("Live projections appear here once data is connected and available.")
    else:
        for event_id, grp in consensus.groupby("event_id", sort=False):
            first = grp.iloc[0]
            with st.expander(f"{first.game} • model {first.away} {first.proj_away:.1f} – {first.home} {first.proj_home:.1f}"):
                display = grp[["market", "selection_key", "consensus", "model", "edge", "price", "book", "ev"]].copy()
                display = display.rename(columns={"selection_key": "side", "book": "best book", "price": "best price"})
                display["best price"] = display["best price"].map(fmt_odds)
                display["ev"] = display["ev"].map(lambda x: f"{x:+.1f}%")
                st.dataframe(display, hide_index=True, use_container_width=True)

with market_tab:
    st.subheader("Market consensus")
    st.caption("This is the sportsbook-agnostic layer: what the available market is saying before we care which book posted it.")
    if consensus.empty:
        st.info("Consensus data appears here once live data is connected.")
    else:
        market_filter = st.segmented_control("Market", ["All", "Spread", "Moneyline", "Total"], default="All")
        m = consensus.copy()
        if market_filter != "All":
            m = m[m.market == market_filter]
        show = m[["game", "market", "selection_key", "consensus", "market_confidence", "books_count", "model", "edge"]].copy()
        show = show.rename(columns={"selection_key": "side", "market_confidence": "market", "books_count": "books"})
        st.dataframe(show, hide_index=True, use_container_width=True)

with track_tab:
    st.subheader("My Bets")
    st.caption("Session-only in V3. Persistent history/database comes next.")
    if not st.session_state.my_bets:
        st.info("Tap Track bet on a recommendation.")
    else:
        for i, item in enumerate(list(st.session_state.my_bets)):
            st.markdown(f"**{item['selection']} {fmt_odds(item['price'])}**  \n{item['game']} • best available via {item['book']} • model EV {item['ev']:+.1f}%")
            c1, c2 = st.columns(2)
            c1.number_input("Wager $", min_value=0.0, step=5.0, key=f"amt_{i}")
            c2.selectbox("Result", ["Pending", "Win", "Loss", "Push"], key=f"res_{i}")
            if st.button("Remove", key=f"remove_{i}"):
                st.session_state.my_bets.pop(i)
                st.rerun()
            st.divider()

with model_tab:
    st.subheader("What V3 actually does")
    st.markdown(f"""
**V3 is sportsbook-agnostic. The market comes first; the book only matters when it offers the best executable price.**

For each live CFB game, EdgeBoard:

1. Pulls delayed pregame **moneyline, spread and total** markets from TheRundown for upcoming college-football games.
2. Builds a **consensus market**: median spread/total, and average no-vig moneyline probability.
3. Measures market agreement so a tightly clustered market is distinguishable from a scattered one.
4. Pulls current-season FBS results and **SRS ratings** from CollegeFootballData.
5. Builds a projected score/margin and converts it into win/cover probabilities.
6. Compares **Model → Consensus** to measure the actual handicapping disagreement.
7. Separately scans all available offers for the **best line/price** and calculates EV there.

Current constants: **home field {HOME_FIELD:.1f} pts**, **margin SD {MARGIN_SD:.0f}**, **total SD {TOTAL_SD:.0f}**.
    """)
    st.warning("V3 is still a baseline research model, not a proven profitable system. Backtesting, calibration, closing-line tracking and out-of-sample validation come before trusting stake sizes.")
    if unmatched:
        with st.expander(f"Unmatched provider team names ({len(unmatched)})"):
            st.write(unmatched)

with setup_tab:
    st.subheader("Connect live data")
    if ready:
        st.success("Both API keys are detected. Live mode is on.")
    else:
        st.write("EdgeBoard needs **two API keys**. Do not paste them into GitHub — your repository is public.")
        st.markdown("""
**1. TheRundown** → current pregame sportsbook odds (free tier is delayed).  
**2. CollegeFootballData (CFBD)** → current-season game results and team ratings.

Then in Streamlit Community Cloud open your app → **Manage app → Settings → Secrets** and paste:

```toml
THERUNDOWN_API_KEY = "your-rundown-key"
CFBD_API_KEY = "your-cfbd-api-key"
```

Save the secrets and reboot/refresh the app.
        """)
    st.markdown("#### Free-tier data budget")
    st.info("TheRundown free tier currently includes delayed pregame odds from three sportsbooks with a datapoint allowance. EdgeBoard requests only full-game moneyline, spread and total, then caches the seven-day board for 6 hours. The Refresh view button normally reuses that cache.")
    st.markdown("#### Architecture")
    st.info("EdgeBoard does not depend on one sportsbook. It uses TheRundown’s available free-tier books to construct consensus, then identifies the best available offer separately. Props/live odds remain out of scope on the free tier.")
    st.markdown("#### V3 → V4")
    st.write("Next: historical backtest + calibration, persistent model/bet records, closing-line value, line movement, and richer efficiency inputs such as EPA/PPA/success rate.")

st.caption("EdgeBoard V3.2 • CFB baseline • TheRundown free stack • consensus first • never fabricates missing odds")
