#!/usr/bin/env python3
"""
Polymarket Operations Intelligence Dashboard  v3
=================================================
Simple, universally readable ops + political intelligence view.

Tabs: Overview | World Map | Elections & Politics | Daily Ops | QA Review | Compliance

Data sources:
  - Polymarket Gamma API  (events + outcomes + descriptions)
  - PolymarketScan API    (rules_arb_score, is_resolved, controversy, smart_money)
"""

import requests, time, json, re, sys
from datetime import datetime, timezone
from collections import defaultdict
import warnings
warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

GAMMA_API = "https://gamma-api.polymarket.com"
PS_API    = "https://gzydspfquuaudqeztorw.supabase.co/functions/v1/agent-api"
AGENT_ID  = "polymarket-ops-dashboard-v3"
MAX_GAMMA = 300
MAX_PS    = 500
TODAY     = datetime.now(timezone.utc)

# Categories shown in map popups
MAP_CATEGORIES = {"Politics & Elections", "Economics & Finance", "Geopolitics & World Affairs"}

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

CATEGORY_KEYWORDS = {
    "Politics & Elections":        ["politics","election","president","congress","senate","vote","democrat","republican","trump","biden","harris","white house","ballot","governor","primary","chancellor","prime minister","parliament","referendum"],
    "Geopolitics & World Affairs": ["war","conflict","nato","ukraine","russia","china","middle east","iran","israel","military","sanctions","ceasefire","treaty","nuclear","invasion","airstrike","troops","coup","regime"],
    "Economics & Finance":         ["gdp","inflation","fed","federal reserve","interest rate","recession","earnings","unemployment","cpi","treasury","s&p","nasdaq","ipo","rate cut","rate hike","deficit","debt ceiling"],
    "Sports":                      ["nfl","nba","mlb","nhl","soccer","football","basketball","tennis","golf","f1","formula","ufc","boxing","olympic","championship","world cup","super bowl","playoffs","league"],
    "Crypto & Blockchain":         ["crypto","bitcoin","ethereum","defi","blockchain","token","btc","eth","solana","nft","web3","dao","stablecoin","coinbase","binance"],
    "Culture & Entertainment":     ["oscar","emmy","grammy","music","film","celebrity","box office","award","streaming","netflix","marvel"],
    "Technology & AI":             ["artificial intelligence","openai","gpt","anthropic","microsoft","apple","google","meta","startup","semiconductor"],
    "Science, Health & Env.":      ["climate","environment","covid","fda","vaccine","space","nasa","hurricane","cancer","drug approval","who","pandemic"],
}

def classify(tags, title):
    combined = " ".join(tags).lower() + " " + title.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in kws):
            return cat
    return "Other"

# ═══════════════════════════════════════════════════════════════════════════
# COUNTRY DETECTION
# ═══════════════════════════════════════════════════════════════════════════

COUNTRY_KEYWORDS = {
    "USA":    ["trump","biden","harris","congress","senate","white house","federal reserve","us election","american","washington","democrat","republican","us government","pentagon","us president","us house","nasdaq","s&p","dow jones","us gdp","us inflation","government shutdown"],
    "GBR":    ["uk ","britain","british","boris","sunak","keir starmer","labour","conservative","parliament","prime minister uk","london","scotland","wales","england"],
    "RUS":    ["russia","russian","putin","moscow","kremlin","ruble"],
    "CHN":    ["china","chinese","xi jinping","beijing","ccp","hong kong","pla","yuan"],
    "UKR":    ["ukraine","ukrainian","kyiv","zelensky","kharkiv"],
    "ISR":    ["israel","israeli","netanyahu","tel aviv","idf"],
    "PSE":    ["gaza","hamas","palestin","west bank"],
    "IRN":    ["iran","iranian","tehran","khamenei","irgc"],
    "FRA":    ["france","french","macron","paris","elysee","le pen"],
    "DEU":    ["germany","german","berlin","scholz","bundesbank","bundestag","merz","afd"],
    "BRA":    ["brazil","brazilian","lula","bolsonaro","brasilia","real brl"],
    "IND":    ["india","indian","modi","delhi","mumbai","rupee"],
    "PRK":    ["north korea","kim jong","pyongyang","dprk"],
    "TUR":    ["turkey","turkish","erdogan","ankara"],
    "VEN":    ["venezuela","maduro","caracas"],
    "ARG":    ["argentina","milei","buenos aires","peso ars"],
    "MEX":    ["mexico","mexican","sheinbaum","mexico city"],
    "JPN":    ["japan","japanese","tokyo","yen jpy","bank of japan","boj"],
    "KOR":    ["south korea","korean","seoul"],
    "TWN":    ["taiwan","taiwanese","taipei"],
    "SAU":    ["saudi","riyadh","bin salman","aramco","opec"],
    "SYR":    ["syria","syrian","damascus"],
    "PAK":    ["pakistan","islamabad","karachi"],
    "CAN":    ["canada","canadian","trudeau","carney","ottawa","toronto"],
    "AUS":    ["australia","australian","sydney","melbourne","albanese"],
    "ESP":    ["spain","spanish","madrid","barcelona","sanchez"],
    "ITA":    ["italy","italian","rome","milan","meloni"],
    "POL":    ["poland","polish","warsaw","tusk"],
    "UZB":    ["uzbekistan"],
    "NGA":    ["nigeria","lagos","abuja"],
    "ZAF":    ["south africa","johannesburg","cape town"],
    "NLD":    ["netherlands","dutch","amsterdam","wilders"],
    "SWE":    ["sweden","swedish","stockholm"],
    "NOR":    ["norway","norwegian","oslo"],
}

def detect_country(ev):
    combined = ev["title"].lower() + " " + " ".join(ev.get("tags", [])).lower()
    for iso, kws in COUNTRY_KEYWORDS.items():
        if any(kw in combined for kw in kws):
            return iso
    return None

COUNTRY_NAMES = {
    "USA":"United States","GBR":"United Kingdom","RUS":"Russia","CHN":"China",
    "UKR":"Ukraine","ISR":"Israel","PSE":"Palestine/Gaza","IRN":"Iran",
    "FRA":"France","DEU":"Germany","BRA":"Brazil","IND":"India","PRK":"North Korea",
    "TUR":"Turkey","VEN":"Venezuela","ARG":"Argentina","MEX":"Mexico","JPN":"Japan",
    "KOR":"South Korea","TWN":"Taiwan","SAU":"Saudi Arabia","SYR":"Syria",
    "PAK":"Pakistan","CAN":"Canada","AUS":"Australia","ESP":"Spain","ITA":"Italy",
    "POL":"Poland","NGA":"Nigeria","ZAF":"South Africa","NLD":"Netherlands",
    "SWE":"Sweden","NOR":"Norway","AFG":"Afghanistan","UZB":"Uzbekistan",
}

# ═══════════════════════════════════════════════════════════════════════════
# CANDIDATE PROFILES (for Elections tab)
# ═══════════════════════════════════════════════════════════════════════════

CANDIDATE_PROFILES = {
    "trump":      {"ideology": "Conservative",   "party": "Republican",        "clr": "#ef4444", "status": "Former president"},
    "harris":     {"ideology": "Progressive",    "party": "Democrat",          "clr": "#3b82f6", "status": "Vice President"},
    "biden":      {"ideology": "Center-left",    "party": "Democrat",          "clr": "#3b82f6", "status": "President"},
    "desantis":   {"ideology": "Conservative",   "party": "Republican",        "clr": "#f97316", "status": "Governor"},
    "haley":      {"ideology": "Conservative",   "party": "Republican",        "clr": "#f97316", "status": "Former Gov."},
    "kennedy":    {"ideology": "Independent",    "party": "Independent",       "clr": "#a855f7", "status": "Independent"},
    "macron":     {"ideology": "Centrist",       "party": "Renaissance",       "clr": "#a855f7", "status": "President"},
    "le pen":     {"ideology": "Right-wing",     "party": "National Rally",    "clr": "#ef4444", "status": "Opposition"},
    "melenchon":  {"ideology": "Left-wing",      "party": "La France",         "clr": "#ef4444", "status": "Opposition"},
    "meloni":     {"ideology": "Right-wing",     "party": "Fratelli d'Italia", "clr": "#ef4444", "status": "PM"},
    "scholz":     {"ideology": "Center-left",    "party": "SPD",               "clr": "#ef4444", "status": "Chancellor"},
    "merz":       {"ideology": "Conservative",   "party": "CDU",               "clr": "#3b82f6", "status": "Chancellor"},
    "lula":       {"ideology": "Left-wing",      "party": "PT",                "clr": "#ef4444", "status": "President"},
    "bolsonaro":  {"ideology": "Right-wing",     "party": "PL",                "clr": "#22c55e", "status": "Former President"},
    "milei":      {"ideology": "Libertarian",    "party": "La Libertad Avanza","clr": "#f59e0b", "status": "President"},
    "zelensky":   {"ideology": "Center",         "party": "Servant of People", "clr": "#22c55e", "status": "President"},
    "putin":      {"ideology": "Nationalist",    "party": "United Russia",     "clr": "#ef4444", "status": "President"},
    "xi jinping": {"ideology": "Communist",      "party": "CCP",               "clr": "#ef4444", "status": "Leader"},
    "netanyahu":  {"ideology": "Right-wing",     "party": "Likud",             "clr": "#3b82f6", "status": "PM"},
    "modi":       {"ideology": "Nationalist",    "party": "BJP",               "clr": "#f97316", "status": "PM"},
    "sunak":      {"ideology": "Conservative",   "party": "Conservative",      "clr": "#3b82f6", "status": "Former PM"},
    "starmer":    {"ideology": "Center-left",    "party": "Labour",            "clr": "#ef4444", "status": "PM"},
    "erdogan":    {"ideology": "Islamist-right", "party": "AKP",               "clr": "#ef4444", "status": "President"},
    "trudeau":    {"ideology": "Center-left",    "party": "Liberal",           "clr": "#ef4444", "status": "Former PM"},
    "carney":     {"ideology": "Center",         "party": "Liberal",           "clr": "#3b82f6", "status": "PM"},
    "poilievre":  {"ideology": "Conservative",   "party": "Conservative",      "clr": "#3b82f6", "status": "Opposition"},
    "albanese":   {"ideology": "Center-left",    "party": "ALP",               "clr": "#ef4444", "status": "PM"},
    "sheinbaum":  {"ideology": "Left-wing",      "party": "Morena",            "clr": "#ef4444", "status": "President"},
    "sanchez":    {"ideology": "Center-left",    "party": "PSOE",              "clr": "#ef4444", "status": "PM"},
    "tusk":       {"ideology": "Center-right",   "party": "KO",                "clr": "#f97316", "status": "PM"},
    "wilders":    {"ideology": "Right-wing",     "party": "PVV",               "clr": "#ef4444", "status": "Opposition"},
    "bin salman": {"ideology": "Monarchist",     "party": "Royal Family",      "clr": "#22c55e", "status": "Crown Prince"},
    "maduro":     {"ideology": "Socialist",      "party": "PSUV",              "clr": "#ef4444", "status": "President"},
}

ELECTION_KEYWORDS = ["election","president","prime minister","chancellor","governor","who will win","win the","will win","lead the","party win","majority","seat","ballot","referendum","will be elected","sworn in"]

def is_election_market(title):
    t = title.lower()
    return any(kw in t for kw in ELECTION_KEYWORDS)

def detect_candidates(title):
    """Return list of candidate names found in title."""
    t = title.lower()
    found = []
    for name in CANDIDATE_PROFILES:
        if name in t:
            found.append(name)
    return found

# ═══════════════════════════════════════════════════════════════════════════
# DATA FETCHING — GAMMA API
# ═══════════════════════════════════════════════════════════════════════════

def _float(v):
    try:    return float(v or 0)
    except: return 0.0

def _int(v):
    try:    return int(v or 0)
    except: return 0

def _date(v):
    if not v: return None
    try:
        s = str(v).replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except: return None

def fetch_gamma(max_records=300):
    events, limit, offset = [], 100, 0
    print("1/2 Fetching Gamma API events...")
    while len(events) < max_records:
        try:
            r = requests.get(f"{GAMMA_API}/events",
                params={"limit": limit, "offset": offset,
                        "active": "true", "order": "volume", "ascending": "false"},
                timeout=30)
            r.raise_for_status()
            batch = r.json()
            if not batch: break
            events.extend(batch)
            print(f"  {len(events)} events...", end="\r", flush=True)
            if len(batch) < limit: break
            offset += limit
            time.sleep(0.4)
        except Exception as e:
            print(f"\nGamma warning: {e}"); break
    print(f"\n  → {len(events)} Gamma events fetched.")
    return events[:max_records]

def parse_gamma(raw):
    tags = [t.get("label","") for t in (raw.get("tags") or []) if isinstance(t, dict)]
    # Parse sub-markets for outcome probabilities
    sub_markets = raw.get("markets", []) or []
    outcomes_data = []
    for m in sub_markets:
        outs = m.get("outcomes") or []
        prices = m.get("outcomePrices") or []
        question = m.get("question","") or raw.get("title","")
        if outs and prices and len(outs) == len(prices):
            try:
                pairs = [(str(o), _float(p)) for o, p in zip(outs, prices)]
                outcomes_data.append({"question": question, "pairs": pairs})
            except: pass
    return {
        "id":            raw.get("id",""),
        "title":         raw.get("title","Untitled"),
        "description":   raw.get("description","") or "",
        "volume":        _float(raw.get("volume")),
        "volume_24h":    _float(raw.get("volume24hr") or raw.get("volume_24h")),
        "liquidity":     _float(raw.get("liquidity")),
        "open_interest": _float(raw.get("openInterest") or raw.get("open_interest")),
        "comment_count": _int(raw.get("commentCount") or raw.get("comment_count")),
        "end_date":      _date(raw.get("endDate") or raw.get("end_date")),
        "active":        bool(raw.get("active", False)),
        "tags":          tags,
        "outcomes_data": outcomes_data,
        # PS enrichment defaults
        "ps_rules_arb":  None,
        "ps_controversy":None,
        "ps_smart_money":None,
        "ps_whale_count":None,
        "ps_is_resolved":None,
        "ps_winner":     None,
        "ps_matched":    False,
    }

# ═══════════════════════════════════════════════════════════════════════════
# DATA FETCHING — POLYMARKETSCAN API
# ═══════════════════════════════════════════════════════════════════════════

def fetch_ps(max_records=500):
    markets, limit, offset = [], 100, 0
    print("2/2 Fetching PolymarketScan enrichment data...")
    while len(markets) < max_records:
        try:
            r = requests.get(PS_API,
                params={"action":"markets","limit":limit,"offset":offset,
                        "sort":"volume_usd","order":"desc","agent_id":AGENT_ID},
                timeout=30)
            r.raise_for_status()
            data = r.json()
            if not data.get("ok") or not data.get("data"): break
            markets.extend(data["data"])
            print(f"  {len(markets)} PS markets...", end="\r", flush=True)
            if len(data["data"]) < limit: break
            offset += limit
            time.sleep(0.5)
        except Exception as e:
            print(f"\nPS warning: {e}"); break
    print(f"\n  → {len(markets)} PolymarketScan markets fetched.")
    return markets[:max_records]

def _norm(t):
    t = t.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t

def enrich_events(events, ps_markets):
    ps_index = {}
    for m in ps_markets:
        key = _norm(m.get("title",""))
        ps_index[key] = m
    matched = 0
    for ev in events:
        norm_title = _norm(ev["title"])
        m = ps_index.get(norm_title)
        if not m:
            words1 = set(norm_title.split())
            best_score, best_m = 0, None
            for key, candidate in ps_index.items():
                words2 = set(key.split())
                if len(words1) < 3 or len(words2) < 3: continue
                overlap = len(words1 & words2) / min(len(words1), len(words2))
                if overlap > best_score:
                    best_score, best_m = overlap, candidate
            if best_score > 0.72:
                m = best_m
        if m:
            ev["ps_rules_arb"]   = m.get("rules_arb_score")
            ev["ps_controversy"] = m.get("controversy_score")
            ev["ps_smart_money"] = m.get("smart_money_bias")
            ev["ps_whale_count"] = m.get("whale_count")
            ev["ps_is_resolved"] = m.get("is_resolved")
            ev["ps_winner"]      = m.get("winner")
            ev["ps_matched"]     = True
            matched += 1
    print(f"  → {matched}/{len(events)} events matched to PolymarketScan.")
    return events

# ═══════════════════════════════════════════════════════════════════════════
# MODULE A — RESOLUTION QA
# ═══════════════════════════════════════════════════════════════════════════

_RE_URL  = re.compile(r"https?://\S+")
_RE_DATE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"\d{4}-\d{2}-\d{2}|\d{1,2}\s+\w+\s+\d{4})\b", re.I)
_AMBIG = ["may","might","could","approximately","around","roughly",
          "probably","likely","possibly","perhaps","unclear","uncertain"]

def score_qa(ev):
    # Skip resolved or expired markets — they're done, not a QA problem
    ps_resolved = ev.get("ps_is_resolved")
    end_dt = ev.get("end_date")
    is_expired = (end_dt is not None and end_dt < TODAY)
    is_resolved = (ps_resolved is True)
    if is_resolved or (is_expired and ps_resolved is not False):
        return 100, "RESOLVED", "#94a3b8", []

    desc = ev["description"]
    score, flags = 100, []
    if len(desc) < 50:
        score -= 35; flags.append("No resolution criteria found")
    elif len(desc) < 150:
        score -= 15; flags.append("Criteria too brief")
    if not _RE_URL.search(desc):
        score -= 20; flags.append("No resolution source URL")
    found = [w for w in _AMBIG if re.search(r"\b"+w+r"\b", desc, re.I)]
    if found:
        score -= 15; flags.append(f"Ambiguous language: {', '.join(found[:3])}")
    if not _RE_DATE.search(desc):
        score -= 10; flags.append("No resolution date referenced")
    n_conn = len(re.findall(r"\b(and|or|unless|provided that|subject to)\b", desc, re.I))
    if n_conn >= 4:
        score -= 10; flags.append(f"Multi-condition criteria ({n_conn} connectors)")
    score = max(0, score)
    if   score >= 80: grade, color = "PASS",   "#22c55e"
    elif score >= 60: grade, color = "REVIEW", "#f59e0b"
    else:             grade, color = "FAIL",   "#ef4444"
    return score, grade, color, flags

# ═══════════════════════════════════════════════════════════════════════════
# MODULE B — INTEGRITY MONITOR
# ═══════════════════════════════════════════════════════════════════════════

def score_integrity(ev):
    vol, vol24, liq = ev["volume"], ev["volume_24h"], ev["liquidity"]
    oi, comments    = ev["open_interest"], ev["comment_count"]
    risk, flags     = 0, []
    if vol > 0 and vol24 / vol > 0.45:
        risk += 30; flags.append(f"24h spike: {vol24/vol*100:.0f}% of lifetime volume")
    if liq > 0 and oi / liq > 8:
        risk += 25; flags.append(f"OI/Liquidity: {oi/liq:.1f}x — undercollateralised")
    if liq == 0 and oi > 5000:
        risk += 35; flags.append(f"Zero liquidity, ${oi:,.0f} OI — exit risk")
    if vol > 50_000 and comments < 3:
        risk += 20; flags.append(f"High volume, minimal engagement ({comments} comments)")
    if vol > 10_000 and liq > 0 and liq/vol < 0.01:
        risk += 15; flags.append(f"Liquidity < 1% of volume — high slippage")
    controversy = ev.get("ps_controversy") or 0
    if controversy > 70:
        risk += 10; flags.append(f"High controversy score: {controversy}")
    smart_money = ev.get("ps_smart_money") or 0
    if abs(smart_money) > 0.6:
        direction = "bullish" if smart_money > 0 else "bearish"
        risk += 5;  flags.append(f"Strong smart-money {direction}: {smart_money:.2f}")
    risk  = min(100, risk)
    score = 100 - risk
    if   score >= 80: level, color = "LOW",    "#22c55e"
    elif score >= 60: level, color = "MEDIUM", "#f59e0b"
    else:             level, color = "HIGH",   "#ef4444"
    return score, level, color, flags

# ═══════════════════════════════════════════════════════════════════════════
# MODULE C — COMPLIANCE RISK
# ═══════════════════════════════════════════════════════════════════════════

COMPLIANCE_RULES = [
    (["assassin","killed","death of","dies in office","murdered","suicide"],
     35, "🔴 Personal safety / death market"),
    (["convicted","arrested","indicted","found guilty","sentenced","charged with","acquitted","impeach"],
     25, "Legal proceeding — named individual"),
    (["election","ballot","primary","vote","presidential","senate race","governor race"],
     20, "Electoral market — regulatory risk"),
    (["interest rate","fed rate","bps","basis points","cpi report","gdp","nonfarm","treasury yield"],
     20, "Mirrors a regulated financial instrument"),
    (["fda approve","fda reject","drug approval","clinical trial","phase 3","ema approve"],
     18, "Pharma regulatory — potential insider risk"),
    (["invade","invasion","military strike","airstrike","nuclear","weapons","attack on"],
     15, "Military/conflict market"),
    (["sanctioned","ofac","banned","restricted jurisdiction"],
     20, "Sanctions / jurisdiction flag"),
]

def score_compliance(ev):
    combined = (ev["title"] + " " + ev["description"]).lower()
    risk, flags = 0, []
    for kws, penalty, desc in COMPLIANCE_RULES:
        if any(kw in combined for kw in kws):
            risk += penalty; flags.append(desc)
    risk  = min(100, risk)
    score = 100 - risk
    if   score >= 80: level, color = "LOW",    "#22c55e"
    elif score >= 60: level, color = "MEDIUM", "#f59e0b"
    else:             level, color = "HIGH",   "#ef4444"
    return score, level, color, flags

# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITE RISK
# ═══════════════════════════════════════════════════════════════════════════

def composite_risk(ev):
    qa_risk   = 100 - ev["qa_score"]
    int_risk  = 100 - ev["int_score"]
    comp_risk = 100 - ev["comp_score"]
    score = 100 - (qa_risk * 0.40 + int_risk * 0.35 + comp_risk * 0.25)
    score = max(0, min(100, score))
    if   score >= 75: level, color = "LOW",      "#22c55e"
    elif score >= 55: level, color = "MEDIUM",   "#f59e0b"
    elif score >= 35: level, color = "HIGH",     "#ef4444"
    else:             level, color = "CRITICAL", "#dc2626"
    return round(score), level, color

# ═══════════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════════

def fmt_usd(v):
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    if v >= 1e6:  return f"${v/1e6:.1f}M"
    if v >= 1e3:  return f"${v/1e3:.0f}K"
    return f"${v:.0f}"

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')

def fmt_date(dt):
    if not dt: return "—"
    d = (dt - TODAY).total_seconds() / 3600
    if d < 0:   return "Expired"
    if d < 24:  return f"{d:.0f}h"
    return dt.strftime("%b %d")

def badge(text, color):
    return f'<span style="background:{color}22;color:{color};border:1px solid {color}44;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{esc(text)}</span>'

# ═══════════════════════════════════════════════════════════════════════════
# ELECTIONS DATA BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def build_elections(events):
    """Extract political/election markets, group by country, detect candidates."""
    results = []
    for ev in events:
        if not is_election_market(ev["title"]):
            continue
        country = detect_country(ev)
        if not country:
            country = "INTL"
        candidates = detect_candidates(ev["title"])
        # Get probability data
        prob_data = []
        if ev["outcomes_data"]:
            for od in ev["outcomes_data"][:1]:  # first sub-market
                for name, prob in od["pairs"]:
                    if prob > 0.01:
                        cp = None
                        for cname, cdata in CANDIDATE_PROFILES.items():
                            if cname in name.lower():
                                cp = (cname, cdata)
                                break
                        prob_data.append({
                            "name": name,
                            "prob": prob,
                            "profile": cp[1] if cp else None,
                        })
        # Fall back to binary Yes/No
        if not prob_data and candidates:
            # If we found a name in title and it's a Yes/No market
            for cname in candidates[:1]:
                prob_data.append({
                    "name": cname.title(),
                    "prob": 0.5,
                    "profile": CANDIDATE_PROFILES.get(cname),
                })
        results.append({
            "title":      ev["title"],
            "country":    country,
            "cname":      COUNTRY_NAMES.get(country, country),
            "volume":     ev["volume"],
            "end_date":   ev["end_date"],
            "category":   ev["category"],
            "candidates": prob_data,
            "candidates_raw": candidates,
        })
    # Sort by volume desc
    results.sort(key=lambda x: x["volume"], reverse=True)
    return results

# ═══════════════════════════════════════════════════════════════════════════
# WORLD MAP DATA BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def build_map_data(events):
    by_country = defaultdict(lambda: {"count": 0, "volume": 0.0, "markets": []})
    for ev in events:
        iso = detect_country(ev)
        if not iso: continue
        cat = ev.get("category","Other")
        by_country[iso]["count"]  += 1
        by_country[iso]["volume"] += ev["volume"]
        # Popup only shows relevant categories
        if cat in MAP_CATEGORIES:
            by_country[iso]["markets"].append({
                "title":   ev["title"][:90],
                "vol":     fmt_usd(ev["volume"]),
                "cat":     cat,
                "end":     fmt_date(ev["end_date"]),
                "prob":    _get_top_prob(ev),
            })
    # Sort popup markets by volume
    for iso in by_country:
        by_country[iso]["markets"].sort(key=lambda x: x["vol"], reverse=False)  # already fmt
    return dict(by_country)

def _get_top_prob(ev):
    if ev.get("outcomes_data"):
        od = ev["outcomes_data"][0]
        if od["pairs"]:
            top = max(od["pairs"], key=lambda x: x[1])
            return f"{top[0]}: {top[1]*100:.0f}%"
    return ""

# ═══════════════════════════════════════════════════════════════════════════
# HTML GENERATION
# ═══════════════════════════════════════════════════════════════════════════

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0f172a; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }
.header { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-bottom: 1px solid #1e3a5f; padding: 20px 28px; display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-size: 20px; font-weight: 700; color: white; }
.header h1 span { color: #3b82f6; }
.header .meta { font-size: 12px; color: #64748b; }
.tabs { display: flex; gap: 4px; padding: 14px 28px 0; background: #0f172a; border-bottom: 1px solid #1e293b; overflow-x: auto; }
.tab { padding: 9px 18px; border-radius: 6px 6px 0 0; cursor: pointer; font-size: 13px; font-weight: 500; color: #64748b; border: 1px solid transparent; border-bottom: none; white-space: nowrap; transition: all .15s; }
.tab:hover { color: #94a3b8; background: #1e293b; }
.tab.active { color: #3b82f6; background: #1e293b; border-color: #334155; }
.content { display: none; padding: 24px 28px; }
.content.active { display: block; }
.kpi-row { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 24px; }
.kpi { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 18px 22px; min-width: 140px; flex: 1; }
.kpi .val { font-size: 28px; font-weight: 700; color: white; }
.kpi .lbl { font-size: 11px; color: #64748b; margin-top: 4px; text-transform: uppercase; letter-spacing: .5px; }
.kpi .sub { font-size: 12px; color: #94a3b8; margin-top: 6px; }
.section-title { font-size: 15px; font-weight: 600; color: #e2e8f0; margin-bottom: 12px; }
.card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 18px; margin-bottom: 14px; }
.tbl-wrap { overflow-x: auto; border-radius: 8px; border: 1px solid #334155; }
table { width: 100%; border-collapse: collapse; }
th { background: #1a2744; color: #94a3b8; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; padding: 10px 14px; text-align: left; white-space: nowrap; cursor: pointer; user-select: none; }
th:hover { color: #e2e8f0; }
th .sort-icon { opacity: .4; font-size: 10px; }
th.sorted .sort-icon { opacity: 1; }
td { padding: 10px 14px; border-top: 1px solid #1e293b; vertical-align: middle; }
tr:hover td { background: #1a2744; }
.market-title { font-weight: 500; color: #e2e8f0; max-width: 340px; }
.market-title small { display: block; color: #64748b; font-size: 11px; margin-top: 2px; font-weight: 400; }
.pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
.pill-green { background: #22c55e22; color: #22c55e; }
.pill-yellow { background: #f59e0b22; color: #f59e0b; }
.pill-red { background: #ef444422; color: #ef4444; }
.pill-gray { background: #94a3b822; color: #94a3b8; }
.pill-blue { background: #3b82f622; color: #3b82f6; }
.muted { color: #64748b; }
.flag-list { display: flex; flex-wrap: wrap; gap: 4px; }
.flag-chip { font-size: 10px; background: #ef444411; color: #f87171; border: 1px solid #ef444433; padding: 1px 6px; border-radius: 3px; }
.ok-chip  { font-size: 10px; background: #22c55e11; color: #4ade80; border: 1px solid #22c55e33; padding: 1px 6px; border-radius: 3px; }
/* Elections */
.elec-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.elec-card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; }
.elec-card .country { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
.elec-card .title { font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 12px; line-height: 1.4; }
.cand-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.cand-bar-wrap { flex: 1; background: #0f172a; border-radius: 4px; height: 22px; overflow: hidden; position: relative; }
.cand-bar { height: 100%; border-radius: 4px; display: flex; align-items: center; padding-left: 8px; font-size: 11px; font-weight: 600; color: white; white-space: nowrap; transition: width .5s; min-width: 40px; }
.cand-name { font-size: 12px; font-weight: 600; min-width: 90px; }
.cand-pct  { font-size: 12px; color: #94a3b8; min-width: 38px; text-align: right; }
.cand-tags { display: flex; gap: 4px; margin-top: 2px; }
.ideology-tag { font-size: 9px; padding: 1px 5px; border-radius: 3px; font-weight: 600; }
.elec-footer { margin-top: 10px; font-size: 11px; color: #475569; display: flex; justify-content: space-between; }
/* Map */
#map-container { position: relative; display: flex; gap: 20px; }
#plotly-map { flex: 1; min-height: 520px; }
#map-panel { width: 340px; background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; display: none; flex-direction: column; }
#map-panel.visible { display: flex; }
#map-panel .panel-country { font-size: 16px; font-weight: 700; color: white; margin-bottom: 12px; }
#map-panel .panel-market { background: #0f172a; border-radius: 6px; padding: 10px; margin-bottom: 8px; }
#map-panel .panel-market .pm-title { font-size: 12px; font-weight: 600; color: #e2e8f0; margin-bottom: 4px; }
#map-panel .panel-market .pm-meta { font-size: 11px; color: #64748b; display: flex; gap: 10px; }
#map-panel .panel-market .pm-prob { font-size: 11px; color: #22c55e; font-weight: 600; }
#map-panel .empty-state { color: #64748b; font-size: 13px; text-align: center; margin: 40px 0; }
.close-panel { float: right; cursor: pointer; color: #64748b; font-size: 18px; line-height: 1; }
.close-panel:hover { color: white; }
/* Progress bars */
.pb-wrap { background: #0f172a; border-radius: 4px; height: 6px; overflow: hidden; }
.pb { height: 100%; border-radius: 4px; }
"""

JS_SORT = """
function sortTable(tbl, col) {
  var rows = Array.from(tbl.querySelectorAll('tbody tr'));
  var ths  = tbl.querySelectorAll('th');
  var dir  = tbl.dataset.sortCol == col && tbl.dataset.sortDir == '1' ? -1 : 1;
  tbl.dataset.sortCol = col;
  tbl.dataset.sortDir = dir;
  ths.forEach(function(th,i){ th.classList.toggle('sorted', i==col); });
  rows.sort(function(a,b){
    var av = a.cells[col] ? a.cells[col].dataset.val || a.cells[col].innerText : '';
    var bv = b.cells[col] ? b.cells[col].dataset.val || b.cells[col].innerText : '';
    var an = parseFloat(av.replace(/[$,BMK%]/g,''));
    var bn = parseFloat(bv.replace(/[$,BMK%]/g,''));
    if (!isNaN(an) && !isNaN(bn)) return dir*(an-bn);
    return dir*av.localeCompare(bv);
  });
  var tb = tbl.querySelector('tbody');
  rows.forEach(function(r){ tb.appendChild(r); });
}
function initSort(tblId) {
  var tbl = document.getElementById(tblId);
  if (!tbl) return;
  tbl.querySelectorAll('th').forEach(function(th,i){
    th.innerHTML += ' <span class="sort-icon">⇅</span>';
    th.addEventListener('click', function(){ sortTable(tbl, i); });
  });
}
function showTab(id) {
  document.querySelectorAll('.tab').forEach(function(t){ t.classList.remove('active'); });
  document.querySelectorAll('.content').forEach(function(c){ c.classList.remove('active'); });
  document.querySelector('[data-tab="'+id+'"]').classList.add('active');
  document.getElementById(id).classList.add('active');
}
"""

def build_html(events):
    now_str = TODAY.strftime("%B %d, %Y  %H:%M UTC")

    # ── Aggregate stats ──────────────────────────────────────────────────
    total_vol     = sum(e["volume"] for e in events)
    total_oi      = sum(e["open_interest"] for e in events)
    active_count  = len(events)
    matched_ps    = sum(1 for e in events if e["ps_matched"])

    qa_pass   = sum(1 for e in events if e["qa_grade"] == "PASS")
    qa_review = sum(1 for e in events if e["qa_grade"] == "REVIEW")
    qa_fail   = sum(1 for e in events if e["qa_grade"] == "FAIL")
    qa_resolved = sum(1 for e in events if e["qa_grade"] == "RESOLVED")

    int_high  = sum(1 for e in events if e["int_level"] == "HIGH")
    comp_high = sum(1 for e in events if e["comp_level"] == "HIGH")

    # ── Category breakdown ───────────────────────────────────────────────
    cat_counts = defaultdict(int)
    cat_vols   = defaultdict(float)
    for ev in events:
        cat_counts[ev["category"]] += 1
        cat_vols[ev["category"]]   += ev["volume"]
    top_cats = sorted(cat_counts.items(), key=lambda x: cat_vols[x[0]], reverse=True)[:8]

    # ── Elections ────────────────────────────────────────────────────────
    election_markets = build_elections(events)

    # ── Map data ─────────────────────────────────────────────────────────
    map_data = build_map_data(events)
    isos     = list(map_data.keys())
    counts   = [map_data[i]["count"]  for i in isos]
    volumes  = [map_data[i]["volume"] for i in isos]
    names    = [COUNTRY_NAMES.get(i, i) for i in isos]

    # Popup data (only political/economic/geopolitical markets)
    popup_data = {}
    for iso, d in map_data.items():
        popup_data[iso] = {
            "name": COUNTRY_NAMES.get(iso, iso),
            "count": d["count"],
            "volume": fmt_usd(d["volume"]),
            "markets": d["markets"][-12:],  # top 12 relevant markets
        }
    popup_json = json.dumps(popup_data)

    # ── Daily ops table ──────────────────────────────────────────────────
    # Active markets sorted by volume, with expiry
    daily_sorted = sorted(events, key=lambda x: x["volume"], reverse=True)

    # ── QA table ─────────────────────────────────────────────────────────
    qa_issues = [e for e in events if e["qa_grade"] in ("FAIL","REVIEW")]
    qa_issues.sort(key=lambda x: x["qa_score"])

    # ── Compliance table ─────────────────────────────────────────────────
    comp_flagged = [e for e in events if e["comp_level"] in ("HIGH","MEDIUM")]
    comp_flagged.sort(key=lambda x: x["comp_score"])

    # ── Category chart data (for overview) ───────────────────────────────
    cat_labels  = json.dumps([c[0] for c in top_cats])
    cat_vol_data = json.dumps([round(cat_vols[c[0]]/1e6,1) for c in top_cats])
    cat_cnt_data = json.dumps([c[1] for c in top_cats])

    # ════════════════════════════════════════════════════════════════════
    # TAB 1 — OVERVIEW
    # ════════════════════════════════════════════════════════════════════

    overview_kpis = f"""
    <div class="kpi-row">
      <div class="kpi"><div class="val">{active_count}</div><div class="lbl">Active Markets</div><div class="sub">{matched_ps} cross-validated with PolymarketScan</div></div>
      <div class="kpi"><div class="val">{fmt_usd(total_vol)}</div><div class="lbl">Total Volume Traded</div><div class="sub">All-time across fetched markets</div></div>
      <div class="kpi"><div class="val">{fmt_usd(total_oi)}</div><div class="lbl">Open Interest</div><div class="sub">Money currently at stake</div></div>
      <div class="kpi"><div class="val" style="color:#f59e0b">{qa_fail}</div><div class="lbl">QA Issues</div><div class="sub">{qa_review} under review · {qa_pass} passing</div></div>
      <div class="kpi"><div class="val" style="color:#ef4444">{int_high}</div><div class="lbl">Integrity Alerts</div><div class="sub">Markets with unusual activity patterns</div></div>
      <div class="kpi"><div class="val" style="color:#a855f7">{comp_high}</div><div class="lbl">Compliance Flags</div><div class="sub">High regulatory risk markets</div></div>
    </div>"""

    # Category breakdown rows
    cat_rows = ""
    for cat, cnt_val in top_cats:
        v = cat_vols[cat]
        pct = v / total_vol * 100 if total_vol > 0 else 0
        cat_rows += f"""<tr>
          <td class="market-title">{esc(cat)}</td>
          <td data-val="{cnt_val}">{cnt_val}</td>
          <td data-val="{v}">{fmt_usd(v)}</td>
          <td><div class="pb-wrap"><div class="pb" style="width:{min(pct,100):.0f}%;background:#3b82f6"></div></div></td>
        </tr>"""

    overview_html = overview_kpis + f"""
    <div class="section-title">Volume by Category</div>
    <div class="tbl-wrap">
    <table id="tbl-cat">
      <thead><tr><th>Category</th><th>Markets</th><th>Volume</th><th>Share</th></tr></thead>
      <tbody>{cat_rows}</tbody>
    </table></div>"""

    # ════════════════════════════════════════════════════════════════════
    # TAB 2 — WORLD MAP
    # ════════════════════════════════════════════════════════════════════

    map_html = f"""
    <div style="margin-bottom:14px;color:#64748b;font-size:13px">
      Click any country on the map to see active political, economic &amp; geopolitical bets.
    </div>
    <div id="map-container">
      <div id="plotly-map"></div>
      <div id="map-panel">
        <div>
          <span class="close-panel" onclick="closePanel()">✕</span>
          <div class="panel-country" id="panel-country">—</div>
        </div>
        <div style="font-size:11px;color:#64748b;margin-bottom:10px" id="panel-stats"></div>
        <div id="panel-markets" style="overflow-y:auto;flex:1"></div>
      </div>
    </div>
    <div style="margin-top:12px;display:flex;gap:12px">
      <button onclick="setMapLayer('count')" id="btn-count" style="background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:7px 16px;border-radius:6px;cursor:pointer;font-size:12px">Market Count</button>
      <button onclick="setMapLayer('volume')" id="btn-vol" style="background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:7px 16px;border-radius:6px;cursor:pointer;font-size:12px">USD Volume</button>
    </div>"""

    map_js = """
var MAP_ISOS    = REPLACE_MAP_ISOS;
var MAP_COUNTS  = REPLACE_MAP_COUNTS;
var MAP_VOLUMES = REPLACE_MAP_VOLUMES;
var MAP_NAMES   = REPLACE_MAP_NAMES;
var POPUP_DATA  = REPLACE_POPUP_DATA;
var mapLayer    = 'count';

function renderMap() {
  var z    = mapLayer === 'count' ? MAP_COUNTS  : MAP_VOLUMES.map(function(v){ return v/1e6; });
  var text = MAP_NAMES.map(function(n,i){
    return n + '<br>' + MAP_COUNTS[i] + ' markets<br>$' + (MAP_VOLUMES[i]/1e6).toFixed(1) + 'M volume';
  });
  var data = [{
    type: 'choropleth',
    locations: MAP_ISOS,
    z: z,
    text: text,
    hoverinfo: 'text',
    locationmode: 'ISO-3',
    colorscale: [
      [0,'#1e293b'],[0.2,'#1e3a5f'],[0.4,'#1d4ed8'],
      [0.7,'#3b82f6'],[1,'#93c5fd']
    ],
    showscale: true,
    colorbar: {
      title: mapLayer === 'count' ? 'Markets' : 'Vol ($M)',
      titlefont: {color:'#94a3b8',size:11},
      tickfont: {color:'#94a3b8',size:10},
      bgcolor: '#1e293b',
      bordercolor: '#334155',
      len: 0.6,
    }
  }];
  var layout = {
    paper_bgcolor: '#0f172a',
    plot_bgcolor:  '#0f172a',
    geo: {
      showframe: false,
      showcoastlines: true, coastlinecolor: '#334155',
      showland: true,       landcolor:      '#1e293b',
      showocean: true,      oceancolor:     '#0f172a',
      showcountries: true,  countrycolor:   '#334155',
      showlakes: false,
      bgcolor: '#0f172a',
      projection: { type: 'natural earth' }
    },
    margin: { t:0, b:0, l:0, r:0 },
    height: 520,
  };
  Plotly.react('plotly-map', data, layout, {responsive:true, displayModeBar:false});
  document.getElementById('plotly-map').on('plotly_click', function(d) {
    var iso = d.points[0].location;
    openPanel(iso);
  });
}

function openPanel(iso) {
  var info = POPUP_DATA[iso];
  if (!info) return;
  document.getElementById('panel-country').textContent = info.name;
  document.getElementById('panel-stats').textContent =
    info.count + ' total markets · ' + info.volume + ' traded';
  var html = '';
  if (!info.markets || info.markets.length === 0) {
    html = '<div class="empty-state">No political/economic<br>markets for this country.</div>';
  } else {
    info.markets.forEach(function(m) {
      var catColor = m.cat === 'Politics & Elections' ? '#a855f7'
                   : m.cat === 'Geopolitics & World Affairs' ? '#ef4444'
                   : '#3b82f6';
      var probHtml = m.prob ? '<span class="pm-prob">' + m.prob + '</span>' : '';
      html += '<div class="panel-market">' +
        '<div class="pm-title">' + m.title + '</div>' +
        '<div class="pm-meta">' +
          '<span style="color:' + catColor + ';font-size:10px">' + m.cat + '</span>' +
          '<span>' + m.vol + '</span>' +
          '<span>exp ' + m.end + '</span>' +
          probHtml +
        '</div></div>';
    });
  }
  document.getElementById('panel-markets').innerHTML = html;
  document.getElementById('map-panel').classList.add('visible');
}
function closePanel() {
  document.getElementById('map-panel').classList.remove('visible');
}
function setMapLayer(layer) {
  mapLayer = layer;
  document.getElementById('btn-count').style.borderColor = layer==='count' ? '#3b82f6' : '#334155';
  document.getElementById('btn-vol').style.borderColor   = layer==='volume'? '#3b82f6' : '#334155';
  renderMap();
}
renderMap();
""".replace("REPLACE_MAP_ISOS",    json.dumps(isos))\
   .replace("REPLACE_MAP_COUNTS",  json.dumps(counts))\
   .replace("REPLACE_MAP_VOLUMES", json.dumps(volumes))\
   .replace("REPLACE_MAP_NAMES",   json.dumps(names))\
   .replace("REPLACE_POPUP_DATA",  popup_json)

    # ════════════════════════════════════════════════════════════════════
    # TAB 3 — ELECTIONS & POLITICS
    # ════════════════════════════════════════════════════════════════════

    # Group by country
    by_country = defaultdict(list)
    for em in election_markets:
        by_country[em["country"]].append(em)

    elec_cards = ""
    for country, markets in sorted(by_country.items(), key=lambda x: sum(m["volume"] for m in x[1]), reverse=True):
        for em in markets[:3]:  # max 3 per country
            cands_html = ""
            if em["candidates"]:
                for c in sorted(em["candidates"], key=lambda x: x["prob"], reverse=True)[:5]:
                    pct = int(c["prob"]*100)
                    prof = c.get("profile") or {}
                    clr  = prof.get("clr","#3b82f6")
                    ideo = prof.get("ideology","")
                    party = prof.get("party","")
                    status = prof.get("status","")
                    ideo_html = ""
                    if ideo:
                        ideo_html = f'<span class="ideology-tag" style="background:{clr}22;color:{clr}">{esc(ideo)}</span>'
                    if party:
                        ideo_html += f' <span class="ideology-tag" style="background:#1e293b;color:#64748b;border:1px solid #334155">{esc(party)}</span>'
                    cands_html += f"""
                    <div class="cand-row">
                      <div class="cand-name">{esc(c["name"][:18])}</div>
                      <div class="cand-bar-wrap">
                        <div class="cand-bar" style="width:{max(pct,8)}%;background:linear-gradient(90deg,{clr}cc,{clr}66)">{pct}%</div>
                      </div>
                      <div class="cand-pct">{pct}%</div>
                    </div>
                    <div class="cand-tags">{ideo_html}</div>"""
            else:
                cands_html = '<div class="muted" style="font-size:12px">Probability data unavailable</div>'

            vol_str = fmt_usd(em["volume"])
            exp_str = fmt_date(em["end_date"])
            elec_cards += f"""
            <div class="elec-card">
              <div class="country">{esc(COUNTRY_NAMES.get(em["country"], em["country"]))}</div>
              <div class="title">{esc(em["title"][:80])}</div>
              {cands_html}
              <div class="elec-footer">
                <span>Vol: {vol_str}</span>
                <span>Expires: {exp_str}</span>
              </div>
            </div>"""

    elec_html = f"""
    <div style="margin-bottom:16px;color:#64748b;font-size:13px">
      {len(election_markets)} active political markets · bars show current betting probability.
      Candidate ideology and party based on known profiles.
    </div>
    <div class="elec-grid">{elec_cards or '<div class="muted">No election markets found in current batch.</div>'}</div>"""

    # ════════════════════════════════════════════════════════════════════
    # TAB 4 — DAILY OPS
    # ════════════════════════════════════════════════════════════════════

    ops_rows = ""
    for ev in daily_sorted[:150]:
        t = esc(ev["title"][:75] + ("…" if len(ev["title"])>75 else ""))
        cat = ev.get("category","Other")
        end = ev["end_date"]
        exp_str = fmt_date(end)
        # Expiry color
        if end:
            h = (end - TODAY).total_seconds()/3600
            if h < 0:   exp_badge = f'<span class="pill pill-gray">Expired</span>'
            elif h < 24: exp_badge = f'<span class="pill pill-red">{exp_str}</span>'
            elif h < 168: exp_badge = f'<span class="pill pill-yellow">{exp_str}</span>'
            else:         exp_badge = f'<span class="muted">{exp_str}</span>'
        else:
            exp_badge = '<span class="muted">—</span>'
        risk_lv = ev["ops_level"]
        risk_pill = (f'<span class="pill pill-red">{risk_lv}</span>' if risk_lv in ("HIGH","CRITICAL")
                     else f'<span class="pill pill-yellow">{risk_lv}</span>' if risk_lv=="MEDIUM"
                     else f'<span class="pill pill-green">{risk_lv}</span>')
        ops_rows += f"""<tr>
          <td class="market-title">{t}<small>{esc(cat)}</small></td>
          <td data-val="{ev['volume']}">{fmt_usd(ev['volume'])}</td>
          <td data-val="{ev['volume_24h']}">{fmt_usd(ev['volume_24h'])}</td>
          <td data-val="{ev['liquidity']}">{fmt_usd(ev['liquidity'])}</td>
          <td data-val="{ev['end_date'].timestamp() if ev['end_date'] else 9e9}">{exp_badge}</td>
          <td data-val="{ev['ops_score']}">{risk_pill}</td>
        </tr>"""

    ops_html = f"""
    <div style="margin-bottom:14px;color:#64748b;font-size:13px">
      All active markets. Click any column header to sort.
    </div>
    <div class="tbl-wrap">
    <table id="tbl-ops">
      <thead><tr>
        <th>Market</th><th>Total Volume</th><th>24h Volume</th><th>Liquidity</th>
        <th>Expiry</th><th>Risk Level</th>
      </tr></thead>
      <tbody>{ops_rows}</tbody>
    </table></div>"""

    # ════════════════════════════════════════════════════════════════════
    # TAB 5 — QA REVIEW
    # ════════════════════════════════════════════════════════════════════

    qa_rows = ""
    for ev in qa_issues[:80]:
        t = esc(ev["title"][:70] + ("…" if len(ev["title"])>70 else ""))
        grade_pill = (f'<span class="pill pill-red">{ev["qa_grade"]}</span>' if ev["qa_grade"]=="FAIL"
                      else f'<span class="pill pill-yellow">{ev["qa_grade"]}</span>')
        flags_html = "".join(f'<span class="flag-chip">{esc(f)}</span>' for f in ev["qa_flags"]) or '<span class="ok-chip">No issues</span>'
        arb = ev.get("ps_rules_arb")
        arb_str = f'<span style="color:{"#ef4444" if arb and arb>50 else "#f59e0b" if arb and arb>25 else "#22c55e"}">{arb}</span>' if arb is not None else '<span class="muted">—</span>'
        qa_rows += f"""<tr>
          <td class="market-title">{t}<small>{esc(ev.get('category',''))}</small></td>
          <td data-val="{ev['qa_score']}">{grade_pill} {ev['qa_score']}</td>
          <td><div class="flag-list">{flags_html}</div></td>
          <td data-val="{arb or 0}">{arb_str}</td>
          <td data-val="{ev['volume']}">{fmt_usd(ev['volume'])}</td>
        </tr>"""

    qa_html = f"""
    <div class="kpi-row" style="margin-bottom:20px">
      <div class="kpi"><div class="val" style="color:#22c55e">{qa_pass}</div><div class="lbl">PASS</div></div>
      <div class="kpi"><div class="val" style="color:#f59e0b">{qa_review}</div><div class="lbl">REVIEW</div></div>
      <div class="kpi"><div class="val" style="color:#ef4444">{qa_fail}</div><div class="lbl">FAIL</div></div>
      <div class="kpi"><div class="val" style="color:#64748b">{qa_resolved}</div><div class="lbl">RESOLVED</div><div class="sub">Correctly excluded from QA</div></div>
    </div>
    <div class="section-title">Markets Needing Review ({len(qa_issues)})</div>
    <div class="tbl-wrap">
    <table id="tbl-qa">
      <thead><tr><th>Market</th><th>Score</th><th>Issues Found</th><th>PS Arb Score</th><th>Volume</th></tr></thead>
      <tbody>{qa_rows}</tbody>
    </table></div>"""

    # ════════════════════════════════════════════════════════════════════
    # TAB 6 — COMPLIANCE
    # ════════════════════════════════════════════════════════════════════

    comp_rows = ""
    for ev in comp_flagged[:60]:
        t = esc(ev["title"][:70] + ("…" if len(ev["title"])>70 else ""))
        level_pill = (f'<span class="pill pill-red">{ev["comp_level"]}</span>' if ev["comp_level"]=="HIGH"
                      else f'<span class="pill pill-yellow">{ev["comp_level"]}</span>')
        flags_html = "".join(f'<span class="flag-chip">{esc(f)}</span>' for f in ev["comp_flags"])
        comp_rows += f"""<tr>
          <td class="market-title">{t}</td>
          <td data-val="{ev['comp_score']}">{level_pill}</td>
          <td><div class="flag-list">{flags_html}</div></td>
          <td data-val="{ev['volume']}">{fmt_usd(ev['volume'])}</td>
        </tr>"""

    comp_html = f"""
    <div class="kpi-row" style="margin-bottom:20px">
      <div class="kpi"><div class="val" style="color:#ef4444">{comp_high}</div><div class="lbl">HIGH Risk</div></div>
      <div class="kpi"><div class="val" style="color:#f59e0b">{sum(1 for e in events if e['comp_level']=='MEDIUM')}</div><div class="lbl">MEDIUM Risk</div></div>
      <div class="kpi"><div class="val" style="color:#22c55e">{sum(1 for e in events if e['comp_level']=='LOW')}</div><div class="lbl">LOW Risk</div></div>
    </div>
    <div class="section-title">Flagged Markets ({len(comp_flagged)})</div>
    <div class="tbl-wrap">
    <table id="tbl-comp">
      <thead><tr><th>Market</th><th>Risk Level</th><th>Flags</th><th>Volume</th></tr></thead>
      <tbody>{comp_rows}</tbody>
    </table></div>"""

    # ════════════════════════════════════════════════════════════════════
    # ASSEMBLE
    # ════════════════════════════════════════════════════════════════════

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polymarket Ops Intelligence</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>{CSS}</style>
</head><body>
<div class="header">
  <div>
    <h1>Polymarket <span>Ops Intelligence</span></h1>
    <div class="meta">v3 · {now_str} · {active_count} markets · {fmt_usd(total_vol)} volume</div>
  </div>
</div>
<div class="tabs">
  <div class="tab active" data-tab="tab-overview" onclick="showTab('tab-overview')">📊 Overview</div>
  <div class="tab" data-tab="tab-map"      onclick="showTab('tab-map')">🗺️ World Map</div>
  <div class="tab" data-tab="tab-elections" onclick="showTab('tab-elections')">🗳️ Elections</div>
  <div class="tab" data-tab="tab-ops"      onclick="showTab('tab-ops')">📋 Daily Ops</div>
  <div class="tab" data-tab="tab-qa"       onclick="showTab('tab-qa')">🔍 QA Review</div>
  <div class="tab" data-tab="tab-comp"     onclick="showTab('tab-comp')">⚖️ Compliance</div>
</div>

<div id="tab-overview" class="content active">{overview_html}</div>
<div id="tab-map"      class="content">{map_html}</div>
<div id="tab-elections" class="content">{elec_html}</div>
<div id="tab-ops"      class="content">{ops_html}</div>
<div id="tab-qa"       class="content">{qa_html}</div>
<div id="tab-comp"     class="content">{comp_html}</div>

<script>
{JS_SORT}
// Init sortable tables
initSort('tbl-cat');
initSort('tbl-ops');
initSort('tbl-qa');
initSort('tbl-comp');
// Map script (loads when tab shown)
document.querySelector('[data-tab="tab-map"]').addEventListener('click', function() {{
  setTimeout(function() {{ {map_js} }}, 50);
}});
</script>
</body></html>"""

    return html

# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    raw_events = fetch_gamma(MAX_GAMMA)
    ps_markets = fetch_ps(MAX_PS)

    events = [parse_gamma(r) for r in raw_events]
    events = enrich_events(events, ps_markets)

    # Classify & score every event
    for ev in events:
        ev["category"]   = classify(ev["tags"], ev["title"])
        ev["country"]    = detect_country(ev)
        qa_score, qa_grade, qa_color, qa_flags     = score_qa(ev)
        int_score, int_level, int_color, int_flags = score_integrity(ev)
        comp_score, comp_level, comp_color, comp_flags = score_compliance(ev)
        ev.update({
            "qa_score":qa_score,"qa_grade":qa_grade,"qa_color":qa_color,"qa_flags":qa_flags,
            "int_score":int_score,"int_level":int_level,"int_color":int_color,"int_flags":int_flags,
            "comp_score":comp_score,"comp_level":comp_level,"comp_color":comp_color,"comp_flags":comp_flags,
        })
        ops_score, ops_level, ops_color = composite_risk(ev)
        ev["ops_score"] = ops_score
        ev["ops_level"] = ops_level
        ev["ops_color"] = ops_color

    html = build_html(events)
    out  = "/sessions/nice-modest-clarke/mnt/outputs/polymarket-analysis/compliance_ops_dashboard.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = len(html) // 1024
    print(f"\n✓  Dashboard saved: {out}  ({size_kb} KB)")
    print(f"   Markets: {len(events)}  |  Volume: ${sum(e['volume'] for e in events)/1e9:.1f}B")
    qa_f = sum(1 for e in events if e['qa_grade']=='FAIL')
    qa_r = sum(1 for e in events if e['qa_grade']=='RESOLVED')
    print(f"   QA: {sum(1 for e in events if e['qa_grade']=='PASS')} PASS / {sum(1 for e in events if e['qa_grade']=='REVIEW')} REVIEW / {qa_f} FAIL / {qa_r} RESOLVED (excluded)")
    elec = sum(1 for e in events if is_election_market(e['title']))
    print(f"   Election markets: {elec}")

if __name__ == "__main__":
    main()
