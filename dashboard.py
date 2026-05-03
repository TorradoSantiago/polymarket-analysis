#!/usr/bin/env python3
"""
Polymarket Operations Intelligence Dashboard  v2
=================================================
Ops Risk  |  Resolution QA  |  Compliance  |  Integrity  |  World Map

Data sources:
  - Polymarket Gamma API   (events + descriptions)
  - PolymarketScan API     (rules_arb_score, is_resolved, controversy,
                            smart_money_bias, whale_count)

Superador angle vs PolymarketScan:
  - Composite Ops Risk score per market (QA + Integrity + Compliance)
  - Regulatory compliance layer (PolymarketScan has none)
  - Cross-validation: our QA vs PS rules_arb_score
  - Geographic market distribution (world map)
  - Operational triage: prioritised "act today" queue

Usage:  python3 dashboard.py
Output: compliance_ops_dashboard.html
"""

import requests, time, json, re, sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import warnings
warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

GAMMA_API = "https://gamma-api.polymarket.com"
PS_API    = "https://gzydspfquuaudqeztorw.supabase.co/functions/v1/agent-api"
AGENT_ID  = "polymarket-ops-dashboard-v2"
MAX_GAMMA = 300
MAX_PS    = 500
TODAY     = datetime.now(timezone.utc)

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

CATEGORY_KEYWORDS = {
    "Politics & Elections":        ["politics","election","president","congress","senate","vote","democrat","republican","trump","biden","harris","white house","ballot","governor","primary"],
    "Sports":                      ["nfl","nba","mlb","nhl","soccer","football","basketball","tennis","golf","f1","formula","ufc","boxing","olympic","championship","world cup","super bowl","playoffs"],
    "Crypto & Blockchain":         ["crypto","bitcoin","ethereum","defi","blockchain","token","btc","eth","solana","nft","web3","dao","stablecoin","coinbase","binance"],
    "Economics & Finance":         ["gdp","inflation","fed","federal reserve","interest rate","recession","earnings","unemployment","cpi","treasury","s&p","nasdaq","ipo"],
    "Geopolitics & World Affairs": ["war","conflict","nato","ukraine","russia","china","middle east","iran","israel","military","sanctions","ceasefire","treaty","nuclear"],
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
    "USA":    ["trump","biden","harris","congress","senate","white house","federal reserve","us election","american","washington","democrat","republican","us government","pentagon","us president","us house","nasdaq","s&p","dow jones","us gdp","us inflation","government shutdown","us senate","us congress","us supreme court"],
    "GBR":    ["uk ","britain","british","boris","sunak","keir starmer","labour","conservative","parliament","prime minister uk","london","scotland","wales","england"],
    "RUS":    ["russia","russian","putin","moscow","kremlin","ruble"],
    "CHN":    ["china","chinese","xi jinping","beijing","ccp","hong kong","pla","yuan"],
    "UKR":    ["ukraine","ukrainian","kyiv","zelensky","kharkiv","zaporizhzhia"],
    "ISR":    ["israel","israeli","netanyahu","tel aviv","idf"],
    "PSE":    ["gaza","hamas","palestin","west bank"],
    "IRN":    ["iran","iranian","tehran","khamenei","irgc"],
    "FRA":    ["france","french","macron","paris","elysee"],
    "DEU":    ["germany","german","berlin","scholz","bundesbank","bundestag"],
    "BRA":    ["brazil","brazilian","lula","bolsonaro","brasilia","real brl"],
    "IND":    ["india","indian","modi","delhi","mumbai","rupee inr"],
    "PRK":    ["north korea","kim jong","pyongyang","dprk"],
    "TUR":    ["turkey","turkish","erdogan","ankara","lira try"],
    "VEN":    ["venezuela","maduro","caracas"],
    "ARG":    ["argentina","milei","buenos aires","peso ars"],
    "MEX":    ["mexico","mexican","sheinbaum","mexico city","peso mxn"],
    "JPN":    ["japan","japanese","tokyo","yen jpy","bank of japan","boj"],
    "KOR":    ["south korea","korean","seoul","won krw"],
    "TWN":    ["taiwan","taiwanese","taipei"],
    "SAU":    ["saudi","riyadh","bin salman","aramco","opec"],
    "SYR":    ["syria","syrian","damascus","assad"],
    "PAK":    ["pakistan","islamabad","karachi"],
    "AFG":    ["afghanistan","kabul","taliban"],
    "NGA":    ["nigeria","lagos","abuja"],
    "ZAF":    ["south africa","johannesburg","cape town","rand zar"],
    "CAN":    ["canada","canadian","trudeau","ottawa","toronto","cad dollar"],
    "AUS":    ["australia","australian","sydney","melbourne","aud dollar"],
    "ESP":    ["spain","spanish","madrid","barcelona"],
    "ITA":    ["italy","italian","rome","milan","draghi"],
    "NLD":    ["netherlands","dutch","amsterdam","holland"],
    "POL":    ["poland","polish","warsaw"],
    "SWE":    ["sweden","swedish","stockholm"],
    "NOR":    ["norway","norwegian","oslo"],
}

def detect_country(event):
    combined = event["title"].lower() + " " + " ".join(event.get("tags", [])).lower()
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
    "PAK":"Pakistan","AFG":"Afghanistan","NGA":"Nigeria","ZAF":"South Africa",
    "CAN":"Canada","AUS":"Australia","ESP":"Spain","ITA":"Italy","NLD":"Netherlands",
    "POL":"Poland","SWE":"Sweden","NOR":"Norway",
}

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
    return {
        "id":           raw.get("id",""),
        "title":        raw.get("title","Untitled"),
        "description":  raw.get("description","") or "",
        "volume":       _float(raw.get("volume")),
        "volume_24h":   _float(raw.get("volume24hr") or raw.get("volume_24h")),
        "liquidity":    _float(raw.get("liquidity")),
        "open_interest":_float(raw.get("openInterest") or raw.get("open_interest")),
        "comment_count":_int(raw.get("commentCount") or raw.get("comment_count")),
        "end_date":     _date(raw.get("endDate") or raw.get("end_date")),
        "active":       bool(raw.get("active", False)),
        "tags":         tags,
        # PS enrichment defaults
        "ps_rules_arb":     None,
        "ps_controversy":   None,
        "ps_smart_money":   None,
        "ps_whale_count":   None,
        "ps_is_resolved":   None,
        "ps_winner":        None,
        "ps_matched":       False,
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

def build_ps_index(ps_markets):
    idx = {}
    for m in ps_markets:
        key = _norm(m.get("title",""))
        idx[key] = m
    return idx

def enrich_events(events, ps_index):
    matched = 0
    for ev in events:
        norm_title = _norm(ev["title"])
        # Try exact match first
        m = ps_index.get(norm_title)
        if not m:
            # Word-overlap fuzzy match
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
    # PolymarketScan signals
    controversy = ev.get("ps_controversy") or 0
    if controversy > 70:
        risk += 10; flags.append(f"High controversy score: {controversy}")
    smart_money = ev.get("ps_smart_money") or 0
    if abs(smart_money) > 0.6:
        direction = "bullish" if smart_money > 0 else "bearish"
        risk += 5;  flags.append(f"Strong smart-money bias {direction}: {smart_money:.2f}")
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
     35, "🔴 High-sensitivity personal safety market"),
    (["convicted","arrested","indicted","found guilty","sentenced","charged with","acquitted","impeach"],
     25, "Legal proceeding / named individual outcome"),
    (["election","ballot","primary","vote","will win the","presidential","senate race","governor race"],
     20, "Electoral market — CFTC/regulated jurisdiction risk"),
    (["interest rate","fed rate","bps","basis points","cpi report","gdp","nonfarm","treasury yield"],
     20, "Mirrors a regulated financial instrument"),
    (["fda approve","fda reject","drug approval","clinical trial","phase 3","ema approve"],
     18, "Pharma regulatory event — potential insider trading sensitivity"),
    (["invade","invasion","military strike","airstrike","nuclear","weapons","attack on"],
     15, "Geopolitical conflict / military action market"),
    (["sanctioned","ofac","banned","restricted jurisdiction"],
     20, "Sanctions / compliance jurisdiction flag"),
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
# COMPOSITE OPS RISK SCORE
# ═══════════════════════════════════════════════════════════════════════════

def composite_risk(ev):
    """Weighted composite of QA + Integrity + Compliance risk."""
    qa_risk   = 100 - ev["qa_score"]
    int_risk  = 100 - ev["int_score"]
    comp_risk = 100 - ev["comp_score"]
    # Weights: QA 40%, Integrity 35%, Compliance 25%
    score = 100 - (qa_risk * 0.40 + int_risk * 0.35 + comp_risk * 0.25)
    score = max(0, min(100, score))
    if   score >= 75: level, color = "LOW",      "#22c55e"
    elif score >= 55: level, color = "MEDIUM",   "#f59e0b"
    elif score >= 35: level, color = "HIGH",     "#ef4444"
    else:             level, color = "CRITICAL", "#dc2626"
    return round(score), level, color

# ═══════════════════════════════════════════════════════════════════════════
# MODULE D — OPS ALERTS
# ═══════════════════════════════════════════════════════════════════════════

def get_alerts(events):
    buckets = dict(expiring_24h=[], expiring_48h=[], expiring_7d=[],
                   overdue=[], low_liquidity=[], zero_volume=[])
    for ev in events:
        end_dt = ev["end_date"]
        # Use PolymarketScan is_resolved to filter false positives
        ps_resolved = ev.get("ps_is_resolved")
        is_resolved = ps_resolved is True
        active = ev["active"] and not is_resolved
        vol, liq = ev["volume"], ev["liquidity"]
        if end_dt:
            delta_h = (end_dt - TODAY).total_seconds() / 3600
            if active and delta_h < 0:
                buckets["overdue"].append(ev)
            elif 0 <= delta_h < 24:
                buckets["expiring_24h"].append(ev)
            elif 24 <= delta_h < 48:
                buckets["expiring_48h"].append(ev)
            elif 48 <= delta_h < 168:
                buckets["expiring_7d"].append(ev)
        if active and liq < 1_000 and vol > 25_000:
            buckets["low_liquidity"].append(ev)
        if active and vol == 0:
            buckets["zero_volume"].append(ev)
    return buckets

# ═══════════════════════════════════════════════════════════════════════════
# HTML HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def fmt_usd(v):
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    if v >= 1e6:  return f"${v/1e6:.1f}M"
    if v >= 1e3:  return f"${v/1e3:.0f}K"
    return f"${v:.0f}"

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')

def flag_pills(flags):
    if not flags: return '<span class="ok">✓ No issues</span>'
    return "".join(f'<span class="flag">{esc(f)}</span>' for f in flags)

def time_badge(dt):
    if not dt: return "N/A"
    h = (dt - TODAY).total_seconds() / 3600
    if h < 0:  return f'<span class="tb red">OVERDUE {abs(h):.0f}h ago</span>'
    if h < 24: return f'<span class="tb red">{h:.1f}h left</span>'
    if h < 48: return f'<span class="tb yellow">{h:.0f}h left</span>'
    return f'<span class="tb muted">{h/24:.1f}d left</span>'

def ps_arb_cell(ev):
    v = ev.get("ps_rules_arb")
    if v is None:
        return '<span class="muted-text">—</span>'
    if v > 50:   c = "#ef4444"
    elif v > 25: c = "#f59e0b"
    else:        c = "#22c55e"
    return f'<span style="color:{c};font-weight:600">{v}</span>'

def ps_controversy_cell(ev):
    v = ev.get("ps_controversy")
    if v is None: return '<span class="muted-text">—</span>'
    if v > 70: return f'<span class="tb red">{v}</span>'
    if v > 40: return f'<span class="tb yellow">{v}</span>'
    return f'<span class="muted-text">{v}</span>'

def ps_smart_money_cell(ev):
    v = ev.get("ps_smart_money")
    if v is None: return '<span class="muted-text">—</span>'
    if abs(v) > 0.5:
        direction = "↑ BULL" if v > 0 else "↓ BEAR"
        color = "#22c55e" if v > 0 else "#ef4444"
        return f'<span style="color:{color};font-weight:600">{direction} {abs(v):.2f}</span>'
    return f'<span class="muted-text">{v:.2f}</span>'

def composite_badge(ev):
    s, l, c = ev["ops_score"], ev["ops_level"], ev["ops_color"]
    return f'<span class="badge" style="background:{c}20;color:{c};border:1px solid {c}50">{l} ({s})</span>'

def sbar(score, color):
    return f'<div class="sbar-w"><div class="sbar" style="width:{score}%;background:{color}"></div><span>{score}</span></div>'

def cnt(n, cls):
    return f'<span class="cnt {cls}">{n}</span>'

# ═══════════════════════════════════════════════════════════════════════════
# TABLE BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def triage_rows(events):
    top = sorted(events, key=lambda x: x["ops_score"])[:50]
    rows = []
    for ev in top:
        t = esc(ev["title"][:80] + ("…" if len(ev["title"])>80 else ""))
        rows.append(
            f'<tr>'
            f'<td class="tc">{t}</td>'
            f'<td>{composite_badge(ev)}</td>'
            f'<td>{sbar(ev["qa_score"], ev["qa_color"])}</td>'
            f'<td>{sbar(ev["int_score"], ev["risk_color"])}</td>'
            f'<td>{sbar(ev["comp_score"], ev["comp_color"])}</td>'
            f'<td class="mc">{esc(ev["category"])}</td>'
            f'</tr>'
        )
    return "\n".join(rows)

def qa_rows(events):
    rows = []
    for ev in sorted(events, key=lambda x: x["qa_score"]):
        t = esc(ev["title"][:80] + ("…" if len(ev["title"])>80 else ""))
        g, c, s = ev["qa_grade"], ev["qa_color"], ev["qa_score"]
        cross = ps_arb_cell(ev)
        agree = ""
        ps_v = ev.get("ps_rules_arb")
        if ps_v is not None:
            if g == "FAIL" and ps_v > 30:   agree = '<span class="tag-confirm">✓ Confirmed</span>'
            elif g == "PASS" and ps_v < 20:  agree = '<span class="tag-confirm">✓ Confirmed</span>'
            elif g == "FAIL" and ps_v < 15:  agree = '<span class="tag-gap">Data gap</span>'
        rows.append(
            f'<tr data-grade="{g}">'
            f'<td class="tc">{t}</td>'
            f'<td><span class="badge" style="background:{c}20;color:{c};border:1px solid {c}50">{g}</span></td>'
            f'<td>{sbar(s,c)}</td>'
            f'<td>{cross} {agree}</td>'
            f'<td class="fc">{flag_pills(ev["qa_flags"])}</td>'
            f'<td class="mc">{esc(ev["category"])}</td>'
            f'</tr>'
        )
    return "\n".join(rows)

def integrity_rows(events):
    rows = []
    for ev in sorted(events, key=lambda x: x["int_score"]):
        t  = esc(ev["title"][:75] + ("…" if len(ev["title"])>75 else ""))
        lv, c, s = ev["risk_level"], ev["risk_color"], ev["int_score"]
        rows.append(
            f'<tr data-risk="{lv}">'
            f'<td class="tc">{t}</td>'
            f'<td><span class="badge" style="background:{c}20;color:{c};border:1px solid {c}50">{lv}</span></td>'
            f'<td>{sbar(s,c)}</td>'
            f'<td class="vol">{fmt_usd(ev["volume"])}</td>'
            f'<td>{ps_controversy_cell(ev)}</td>'
            f'<td>{ps_smart_money_cell(ev)}</td>'
            f'<td class="vol">{ev.get("ps_whale_count") or "—"}</td>'
            f'<td class="fc">{flag_pills(ev["int_flags"])}</td>'
            f'</tr>'
        )
    return "\n".join(rows)

def compliance_rows(events):
    rows = []
    for ev in sorted(events, key=lambda x: x["comp_score"]):
        t = esc(ev["title"][:80] + ("…" if len(ev["title"])>80 else ""))
        lv, c, s = ev["comp_level"], ev["comp_color"], ev["comp_score"]
        rows.append(
            f'<tr data-comp="{lv}">'
            f'<td class="tc">{t}</td>'
            f'<td><span class="badge" style="background:{c}20;color:{c};border:1px solid {c}50">{lv}</span></td>'
            f'<td>{sbar(s,c)}</td>'
            f'<td class="vol">{fmt_usd(ev["volume"])}</td>'
            f'<td class="mc">{esc(ev["category"])}</td>'
            f'<td class="fc">{flag_pills(ev["comp_flags"])}</td>'
            f'</tr>'
        )
    return "\n".join(rows)

def alert_rows(evs, col4_fn):
    if not evs:
        return '<tr><td colspan="5" class="empty">No alerts ✓</td></tr>'
    rows = []
    for ev in evs[:30]:
        t = esc(ev["title"][:75] + ("…" if len(ev["title"])>75 else ""))
        qa_c = ev["qa_color"]
        rows.append(
            f'<tr>'
            f'<td class="tc">{t}</td>'
            f'<td class="vol">{fmt_usd(ev["volume"])}</td>'
            f'<td class="liq">{fmt_usd(ev["liquidity"])}</td>'
            f'<td>{col4_fn(ev)}</td>'
            f'<td><span class="badge" style="background:{qa_c}20;color:{qa_c};border:1px solid {qa_c}50">{ev["qa_grade"]}</span></td>'
            f'</tr>'
        )
    return "\n".join(rows)

# ═══════════════════════════════════════════════════════════════════════════
# HTML GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def build_html(events, alerts, stats, generated_at):

    # Chart data
    cat_qa = defaultdict(lambda: {"PASS":0,"REVIEW":0,"FAIL":0})
    for ev in events:
        cat_qa[ev["category"]][ev["qa_grade"]] += 1
    top_cats = sorted(cat_qa, key=lambda c: sum(cat_qa[c].values()), reverse=True)[:8]

    timeline = defaultdict(int)
    for ev in events:
        ed = ev["end_date"]
        if ed:
            d = (ed - TODAY).days
            if 0 <= d < 7:
                timeline[(TODAY + timedelta(days=d)).strftime("%a %m/%d")] += 1
    tl_labels = [(TODAY + timedelta(days=i)).strftime("%a %m/%d") for i in range(7)]
    tl_values = [timeline.get(l,0) for l in tl_labels]

    # Ops risk distribution
    ops_counts = {"LOW":0,"MEDIUM":0,"HIGH":0,"CRITICAL":0}
    for ev in events: ops_counts[ev["ops_level"]] = ops_counts.get(ev["ops_level"],0) + 1

    # World map data
    country_stats = defaultdict(lambda: {"count":0,"volume":0.0})
    for ev in events:
        iso = ev.get("country_iso")
        if iso and iso in COUNTRY_NAMES:
            country_stats[iso]["count"] += 1
            country_stats[iso]["volume"] += ev["volume"]

    map_isos    = list(country_stats.keys())
    map_counts  = [country_stats[c]["count"] for c in map_isos]
    map_volumes = [round(country_stats[c]["volume"]/1e6, 2) for c in map_isos]
    map_names   = [COUNTRY_NAMES.get(c, c) for c in map_isos]
    map_text    = [f"{COUNTRY_NAMES.get(c,c)}<br>Markets: {country_stats[c]['count']}<br>Volume: ${country_stats[c]['volume']/1e6:.0f}M"
                   for c in map_isos]

    chart_data = json.dumps({
        "qa":       [stats["qa_pass"], stats["qa_review"], stats["qa_fail"]],
        "risk":     [stats["risk_low"], stats["risk_medium"], stats["risk_high"]],
        "ops":      [ops_counts.get("LOW",0), ops_counts.get("MEDIUM",0),
                     ops_counts.get("HIGH",0), ops_counts.get("CRITICAL",0)],
        "comp":     [stats["comp_low"], stats["comp_medium"], stats["comp_high"]],
        "catLabels":top_cats,
        "catPass":  [cat_qa[c]["PASS"]   for c in top_cats],
        "catReview":[cat_qa[c]["REVIEW"] for c in top_cats],
        "catFail":  [cat_qa[c]["FAIL"]   for c in top_cats],
        "tlLabels": tl_labels,
        "tlValues": tl_values,
        "mapIsos":  map_isos,
        "mapCounts":map_counts,
        "mapVols":  map_volumes,
        "mapNames": map_names,
        "mapText":  map_text,
    })

    # Tables
    triage_tbl    = triage_rows(events)
    qa_tbl        = qa_rows(events)
    int_tbl       = integrity_rows(events)
    comp_tbl      = compliance_rows(events)
    a24h  = alert_rows(alerts["expiring_24h"],  lambda ev: time_badge(ev["end_date"]))
    a48h  = alert_rows(alerts["expiring_48h"],  lambda ev: time_badge(ev["end_date"]))
    a7d   = alert_rows(alerts["expiring_7d"],   lambda ev: time_badge(ev["end_date"]))
    aod   = alert_rows(alerts["overdue"],       lambda ev: time_badge(ev["end_date"]))
    aliq  = alert_rows(alerts["low_liquidity"],
                       lambda ev: f'<span class="tb yellow">{fmt_usd(ev["liquidity"])}</span>')
    azv   = alert_rows(alerts["zero_volume"],
                       lambda ev: f'<span class="mc">{esc(ev["category"])}</span>')

    total_alerts = (len(alerts["expiring_24h"]) + len(alerts["overdue"]) +
                    len(alerts["low_liquidity"]))
    ps_match_pct = round(sum(1 for e in events if e["ps_matched"]) / len(events) * 100)

    HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Polymarket Ops Intelligence v2</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f172a;--surf:#1e293b;--bdr:#334155;
  --tx:#e2e8f0;--muted:#94a3b8;
  --green:#22c55e;--yellow:#f59e0b;--red:#ef4444;--blue:#3b82f6;--purple:#a855f7;--cyan:#22d3ee;
}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--tx);font-size:14px;line-height:1.5}
.hdr{background:var(--surf);border-bottom:1px solid var(--bdr);padding:14px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.logo{font-size:18px;font-weight:700;color:var(--blue);letter-spacing:-.4px}
.logo span{color:var(--tx);font-weight:400}
.hdr-meta{font-size:11px;color:var(--muted);margin-top:2px}
.v2{display:inline-block;background:rgba(168,85,247,.15);color:var(--purple);border:1px solid rgba(168,85,247,.3);padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;margin-left:8px}
.live{display:inline-flex;align-items:center;gap:5px;background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);color:var(--green);padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;letter-spacing:.5px}
.live-dot{width:6px;height:6px;background:var(--green);border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;padding:18px 24px}
.card{background:var(--surf);border:1px solid var(--bdr);border-radius:10px;padding:16px 18px}
.card-lbl{font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:5px}
.card-val{font-size:28px;font-weight:700;line-height:1;margin-bottom:3px}
.card-sub{font-size:12px;color:var(--muted)}
.tabs{display:flex;padding:0 24px;border-bottom:1px solid var(--bdr);margin-bottom:20px}
.tab{padding:11px 16px;background:none;border:none;color:var(--muted);cursor:pointer;font-size:13px;font-weight:500;border-bottom:2px solid transparent;margin-bottom:-1px;transition:color .15s,border-color .15s;white-space:nowrap}
.tab:hover{color:var(--tx)}
.tab.active{color:var(--blue);border-bottom-color:var(--blue)}
.panel{display:none;padding:0 24px 48px}
.panel.active{display:block}
.ch-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.ch-card{background:var(--surf);border:1px solid var(--bdr);border-radius:10px;padding:18px}
.ch-title{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px}
.ch-wrap{position:relative;height:210px}
.tcard{background:var(--surf);border:1px solid var(--bdr);border-radius:10px;overflow:hidden;margin-bottom:16px}
.thdr{padding:13px 18px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between}
.ttitle{font-size:13px;font-weight:600}
.twrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{padding:9px 14px;text-align:left;font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--bdr);cursor:pointer;white-space:nowrap;user-select:none}
th:hover{color:var(--tx)}
td{padding:9px 14px;border-bottom:1px solid rgba(51,65,85,.5);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.02)}
.tc{max-width:340px;font-size:13px}
.fc{max-width:280px}
.mc{font-size:12px;color:var(--muted)}
.vol{color:var(--yellow);white-space:nowrap}
.liq{color:var(--blue);white-space:nowrap}
.muted-text{color:var(--muted);font-size:12px}
.empty{text-align:center;padding:24px;color:var(--muted);font-size:13px}
.badge{display:inline-block;padding:3px 8px;border-radius:5px;font-size:11px;font-weight:700;letter-spacing:.5px;white-space:nowrap}
.flag{display:inline-block;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.25);color:var(--yellow);font-size:11px;padding:2px 7px;border-radius:4px;margin:2px 3px 2px 0;white-space:nowrap}
.ok{font-size:12px;color:var(--green)}
.tb{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600}
.tb.red{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3)}
.tb.yellow{background:rgba(245,158,11,.15);color:var(--yellow);border:1px solid rgba(245,158,11,.3)}
.tb.muted{background:rgba(148,163,184,.1);color:var(--muted);border:1px solid rgba(148,163,184,.2)}
.sbar-w{display:flex;align-items:center;gap:8px}
.sbar{height:6px;border-radius:3px;min-width:4px}
.sbar-w span{font-size:12px;color:var(--muted);min-width:22px}
.cnt{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:22px;border-radius:11px;font-size:11px;font-weight:700;padding:0 6px}
.cnt.red{background:rgba(239,68,68,.2);color:var(--red);border:1px solid rgba(239,68,68,.4)}
.cnt.yellow{background:rgba(245,158,11,.2);color:var(--yellow);border:1px solid rgba(245,158,11,.4)}
.cnt.blue{background:rgba(59,130,246,.2);color:var(--blue);border:1px solid rgba(59,130,246,.4)}
.cnt.gray{background:rgba(100,116,139,.2);color:#64748b;border:1px solid rgba(100,116,139,.4)}
.frow{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.fbtn{padding:5px 14px;border-radius:6px;border:1px solid var(--bdr);background:none;color:var(--muted);cursor:pointer;font-size:12px;font-weight:500;transition:all .15s}
.fbtn:hover,.fbtn.active{background:rgba(59,130,246,.15);border-color:var(--blue);color:var(--blue)}
.agrid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.tag-confirm{display:inline-block;background:rgba(34,197,94,.1);color:var(--green);border:1px solid rgba(34,197,94,.3);font-size:10px;padding:1px 6px;border-radius:3px;margin-left:4px}
.tag-gap{display:inline-block;background:rgba(59,130,246,.1);color:var(--blue);border:1px solid rgba(59,130,246,.3);font-size:10px;padding:1px 6px;border-radius:3px;margin-left:4px}
.ps-banner{background:rgba(168,85,247,.08);border:1px solid rgba(168,85,247,.2);border-radius:8px;padding:10px 16px;margin-bottom:18px;font-size:12px;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap}
.ps-banner strong{color:var(--purple)}
#worldmap{background:var(--surf);border-radius:10px;border:1px solid var(--bdr)}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:3px}
</style>
</head>
<body>

<div class="hdr">
  <div>
    <div class="logo">Polymarket <span>Ops Intelligence</span><span class="v2">v2</span></div>
    <div class="hdr-meta">Ops Risk &nbsp;·&nbsp; Resolution QA &nbsp;·&nbsp; Compliance &nbsp;·&nbsp; Integrity &nbsp;·&nbsp; World Map</div>
  </div>
  <div style="display:flex;align-items:center;gap:16px">
    <div style="text-align:right">
      <div style="font-size:11px;color:var(--muted)">Last updated</div>
      <div style="font-size:12px;font-weight:600">REPLACE_DATE</div>
    </div>
    <div class="live"><div class="live-dot"></div>LIVE DATA</div>
  </div>
</div>

<div class="cards">
  <div class="card">
    <div class="card-lbl">Markets Monitored</div>
    <div class="card-val" style="color:var(--blue)">REPLACE_TOTAL</div>
    <div class="card-sub">REPLACE_PS_PCT% matched to PolymarketScan</div>
  </div>
  <div class="card">
    <div class="card-lbl">Ops Risk — Critical/High</div>
    <div class="card-val" style="color:var(--red)">REPLACE_OPS_HIGH</div>
    <div class="card-sub">Composite QA + Integrity + Compliance</div>
  </div>
  <div class="card">
    <div class="card-lbl">QA Issues</div>
    <div class="card-val" style="color:var(--yellow)">REPLACE_QA_FAIL</div>
    <div class="card-sub">REPLACE_QA_REVIEW review &nbsp;·&nbsp; REPLACE_QA_PASS pass</div>
  </div>
  <div class="card">
    <div class="card-lbl">Compliance Flags</div>
    <div class="card-val" style="color:var(--purple)">REPLACE_COMP_HIGH</div>
    <div class="card-sub">REPLACE_COMP_MED medium risk markets</div>
  </div>
  <div class="card">
    <div class="card-lbl">Active Alerts</div>
    <div class="card-val" style="color:var(--cyan)">REPLACE_ALERT_TOTAL</div>
    <div class="card-sub">REPLACE_EXP24 expiring &lt;24h &nbsp;·&nbsp; REPLACE_OVERDUE overdue</div>
  </div>
</div>

<div class="tabs">
  <button class="tab active" onclick="showTab('overview',this)">📊 Overview</button>
  <button class="tab"        onclick="showTab('triage',this)">🎯 Ops Triage</button>
  <button class="tab"        onclick="showTab('ops',this)">🚨 Daily Ops</button>
  <button class="tab"        onclick="showTab('qa',this)">📋 Resolution QA</button>
  <button class="tab"        onclick="showTab('integrity',this)">🔍 Integrity</button>
  <button class="tab"        onclick="showTab('compliance',this)">⚖️ Compliance</button>
  <button class="tab"        onclick="showTab('map',this)">🌍 World Map</button>
</div>

<!-- OVERVIEW -->
<div id="tab-overview" class="panel active">
  <div class="ps-banner">
    <div><strong>Data sources:</strong> Polymarket Gamma API + PolymarketScan enrichment (REPLACE_PS_PCT% match rate)</div>
    <div><strong>Superador vs PolymarketScan:</strong> Composite ops risk score · Compliance layer · Cross-validation · Geographic distribution</div>
  </div>
  <div class="ch-grid">
    <div class="ch-card"><div class="ch-title">Composite Ops Risk Distribution</div><div class="ch-wrap"><canvas id="cOps"></canvas></div></div>
    <div class="ch-card"><div class="ch-title">QA Grade Distribution</div><div class="ch-wrap"><canvas id="cQA"></canvas></div></div>
    <div class="ch-card"><div class="ch-title">QA Score by Category</div><div class="ch-wrap"><canvas id="cCat"></canvas></div></div>
    <div class="ch-card"><div class="ch-title">Markets Expiring — Next 7 Days</div><div class="ch-wrap"><canvas id="cTL"></canvas></div></div>
  </div>
</div>

<!-- OPS TRIAGE -->
<div id="tab-triage" class="panel">
  <div style="margin-bottom:16px">
    <div style="font-size:15px;font-weight:600;margin-bottom:4px">Ops Triage — Composite Risk Ranking</div>
    <div style="font-size:12px;color:var(--muted)">Markets ranked by weighted composite score: QA (40%) + Integrity (35%) + Compliance (25%). Top 50 shown — lowest score = highest ops priority.</div>
  </div>
  <div class="tcard">
    <div class="twrap">
      <table id="tTriage">
        <thead><tr>
          <th onclick="sort('tTriage',0)">Market ↕</th>
          <th onclick="sort('tTriage',1)">Ops Risk ↕</th>
          <th onclick="sort('tTriage',2)">QA Score ↕</th>
          <th onclick="sort('tTriage',3)">Integrity ↕</th>
          <th onclick="sort('tTriage',4)">Compliance ↕</th>
          <th onclick="sort('tTriage',5)">Category ↕</th>
        </tr></thead>
        <tbody>REPLACE_TRIAGE_TBL</tbody>
      </table>
    </div>
  </div>
</div>

<!-- DAILY OPS -->
<div id="tab-ops" class="panel">
  <div class="agrid">
    <div class="tcard"><div class="thdr"><div class="ttitle">⏰ Expiring in 24h</div>REPLACE_CNT_24H</div>
      <div class="twrap"><table><thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Time Left</th><th>QA</th></tr></thead><tbody>REPLACE_A24H</tbody></table></div></div>
    <div class="tcard"><div class="thdr"><div class="ttitle">⚠️ Overdue (Unresolved)</div>REPLACE_CNT_OD</div>
      <div class="twrap"><table><thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Status</th><th>QA</th></tr></thead><tbody>REPLACE_AOD</tbody></table></div></div>
  </div>
  <div class="agrid">
    <div class="tcard"><div class="thdr"><div class="ttitle">🕐 Expiring in 48h</div>REPLACE_CNT_48H</div>
      <div class="twrap"><table><thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Time Left</th><th>QA</th></tr></thead><tbody>REPLACE_A48H</tbody></table></div></div>
    <div class="tcard"><div class="thdr"><div class="ttitle">📅 Expiring This Week</div>REPLACE_CNT_7D</div>
      <div class="twrap"><table><thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Time Left</th><th>QA</th></tr></thead><tbody>REPLACE_A7D</tbody></table></div></div>
  </div>
  <div class="agrid">
    <div class="tcard"><div class="thdr"><div class="ttitle">💧 Low Liquidity</div>REPLACE_CNT_LIQ</div>
      <div class="twrap"><table><thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Liq. Level</th><th>QA</th></tr></thead><tbody>REPLACE_ALIQ</tbody></table></div></div>
    <div class="tcard"><div class="thdr"><div class="ttitle">🚫 Zero Volume</div>REPLACE_CNT_ZV</div>
      <div class="twrap"><table><thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Category</th><th>QA</th></tr></thead><tbody>REPLACE_AZV</tbody></table></div></div>
  </div>
</div>

<!-- RESOLUTION QA -->
<div id="tab-qa" class="panel">
  <div style="margin-bottom:12px">
    <div style="font-size:15px;font-weight:600;margin-bottom:4px">Resolution QA · Cross-validated with PolymarketScan</div>
    <div style="font-size:12px;color:var(--muted)">Our score vs PS Rules Arb Score. "Confirmed" = both systems flag the same market. "Data gap" = our FAIL but PS shows low ambiguity (Gamma API missing description).</div>
  </div>
  <div class="frow">
    <button class="fbtn active" onclick="filterQA(null,this)">All (REPLACE_TOTAL)</button>
    <button class="fbtn" style="color:var(--red)"    onclick="filterQA('FAIL',this)">🔴 FAIL (REPLACE_QA_FAIL)</button>
    <button class="fbtn" style="color:var(--yellow)" onclick="filterQA('REVIEW',this)">🟡 REVIEW (REPLACE_QA_REVIEW)</button>
    <button class="fbtn" style="color:var(--green)"  onclick="filterQA('PASS',this)">🟢 PASS (REPLACE_QA_PASS)</button>
  </div>
  <div class="tcard"><div class="twrap">
    <table id="tQA">
      <thead><tr>
        <th onclick="sort('tQA',0)">Market ↕</th>
        <th onclick="sort('tQA',1)">Grade ↕</th>
        <th onclick="sort('tQA',2)">Score ↕</th>
        <th>PS Rules Arb ↕</th>
        <th>Issues Detected</th>
        <th onclick="sort('tQA',5)">Category ↕</th>
      </tr></thead>
      <tbody>REPLACE_QA_TBL</tbody>
    </table>
  </div></div>
</div>

<!-- INTEGRITY -->
<div id="tab-integrity" class="panel">
  <div style="margin-bottom:12px">
    <div style="font-size:15px;font-weight:600;margin-bottom:4px">Market Integrity Monitor</div>
    <div style="font-size:12px;color:var(--muted)">Volume anomalies, liquidity gaps, PolymarketScan controversy score, smart-money bias, and whale activity — all in one view.</div>
  </div>
  <div class="frow">
    <button class="fbtn active" onclick="filterInt(null,this)">All (REPLACE_TOTAL)</button>
    <button class="fbtn" style="color:var(--red)"    onclick="filterInt('HIGH',this)">🔴 HIGH (REPLACE_RISK_HIGH)</button>
    <button class="fbtn" style="color:var(--yellow)" onclick="filterInt('MEDIUM',this)">🟡 MEDIUM (REPLACE_RISK_MED)</button>
    <button class="fbtn" style="color:var(--green)"  onclick="filterInt('LOW',this)">🟢 LOW (REPLACE_RISK_LOW)</button>
  </div>
  <div class="tcard"><div class="twrap">
    <table id="tInt">
      <thead><tr>
        <th onclick="sort('tInt',0)">Market ↕</th>
        <th onclick="sort('tInt',1)">Risk ↕</th>
        <th onclick="sort('tInt',2)">Score ↕</th>
        <th onclick="sort('tInt',3)">Volume ↕</th>
        <th>Controversy ↕</th>
        <th>Smart Money</th>
        <th>🐳 Whales</th>
        <th>Anomaly Flags</th>
      </tr></thead>
      <tbody>REPLACE_INT_TBL</tbody>
    </table>
  </div></div>
</div>

<!-- COMPLIANCE -->
<div id="tab-compliance" class="panel">
  <div style="margin-bottom:12px">
    <div style="font-size:15px;font-weight:600;margin-bottom:4px">Compliance Risk Assessment</div>
    <div style="font-size:12px;color:var(--muted)">Flags markets with regulatory exposure: electoral markets (CFTC), financial instrument mirrors, personal safety, legal proceedings, sanctions. PolymarketScan does not provide this layer.</div>
  </div>
  <div class="frow">
    <button class="fbtn active" onclick="filterComp(null,this)">All (REPLACE_TOTAL)</button>
    <button class="fbtn" style="color:var(--red)"    onclick="filterComp('HIGH',this)">🔴 HIGH (REPLACE_COMP_HIGH)</button>
    <button class="fbtn" style="color:var(--yellow)" onclick="filterComp('MEDIUM',this)">🟡 MEDIUM (REPLACE_COMP_MED)</button>
    <button class="fbtn" style="color:var(--green)"  onclick="filterComp('LOW',this)">🟢 LOW (REPLACE_COMP_LOW)</button>
  </div>
  <div class="tcard"><div class="twrap">
    <table id="tComp">
      <thead><tr>
        <th onclick="sort('tComp',0)">Market ↕</th>
        <th onclick="sort('tComp',1)">Risk Level ↕</th>
        <th onclick="sort('tComp',2)">Score ↕</th>
        <th onclick="sort('tComp',3)">Volume ↕</th>
        <th onclick="sort('tComp',4)">Category ↕</th>
        <th>Compliance Flags</th>
      </tr></thead>
      <tbody>REPLACE_COMP_TBL</tbody>
    </table>
  </div></div>
</div>

<!-- WORLD MAP -->
<div id="tab-map" class="panel">
  <div style="margin-bottom:16px">
    <div style="font-size:15px;font-weight:600;margin-bottom:4px">Global Market Distribution</div>
    <div style="font-size:12px;color:var(--muted)">Each market classified by the country/region it references. Bubble size = number of markets. Color intensity = total USD volume. Hover for details.</div>
  </div>
  <div style="display:flex;gap:12px;margin-bottom:14px">
    <button class="fbtn active" id="mapBtn1" onclick="switchMap('count',this)">Market Count</button>
    <button class="fbtn"        id="mapBtn2" onclick="switchMap('volume',this)">USD Volume</button>
  </div>
  <div id="worldmap" style="height:520px;width:100%"></div>
</div>

<script>
const D = REPLACE_CHART_DATA;

function showTab(id, btn) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  btn.classList.add('active');
  if (id === 'map') renderMap('count');
}

function filterQA(grade, btn) {
  document.querySelectorAll('#tQA tbody tr').forEach(r => {
    r.style.display = (!grade || r.dataset.grade === grade) ? '' : 'none';
  });
  btn.closest('.frow').querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}
function filterInt(level, btn) {
  document.querySelectorAll('#tInt tbody tr').forEach(r => {
    r.style.display = (!level || r.dataset.risk === level) ? '' : 'none';
  });
  btn.closest('.frow').querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}
function filterComp(level, btn) {
  document.querySelectorAll('#tComp tbody tr').forEach(r => {
    r.style.display = (!level || r.dataset.comp === level) ? '' : 'none';
  });
  btn.closest('.frow').querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

const _sortState = {};
function sort(tId, col) {
  const tbl = document.getElementById(tId), rows = Array.from(tbl.querySelectorAll('tbody tr'));
  const key = tId+'_'+col, asc = !_sortState[key];
  _sortState[key] = asc;
  rows.sort((a,b) => {
    const av = a.cells[col]?.textContent?.trim()||'', bv = b.cells[col]?.textContent?.trim()||'';
    const an = parseFloat(av.replace(/[$KMBkm%,\s]/gi,'')), bn = parseFloat(bv.replace(/[$KMBkm%,\s]/gi,''));
    if(!isNaN(an)&&!isNaN(bn)) return asc?an-bn:bn-an;
    return asc?av.localeCompare(bv):bv.localeCompare(av);
  });
  rows.forEach(r => tbl.querySelector('tbody').appendChild(r));
}

Chart.defaults.color='#94a3b8'; Chart.defaults.borderColor='#334155';
Chart.defaults.font.family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";
Chart.defaults.font.size=12;

const DONUT = {responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{padding:12,boxWidth:11}},tooltip:{callbacks:{label:c=>` ${c.label}: ${c.raw}`}}},cutout:'60%'};

new Chart(document.getElementById('cOps'),{type:'doughnut',data:{labels:['LOW','MEDIUM','HIGH','CRITICAL'],datasets:[{data:D.ops,backgroundColor:['rgba(34,197,94,.8)','rgba(245,158,11,.8)','rgba(239,68,68,.8)','rgba(220,38,38,.9)'],borderColor:['#22c55e','#f59e0b','#ef4444','#dc2626'],borderWidth:2}]},options:DONUT});
new Chart(document.getElementById('cQA'),{type:'doughnut',data:{labels:['PASS','REVIEW','FAIL'],datasets:[{data:D.qa,backgroundColor:['rgba(34,197,94,.8)','rgba(245,158,11,.8)','rgba(239,68,68,.8)'],borderColor:['#22c55e','#f59e0b','#ef4444'],borderWidth:2}]},options:DONUT});
new Chart(document.getElementById('cCat'),{type:'bar',data:{labels:D.catLabels,datasets:[{label:'PASS',data:D.catPass,backgroundColor:'rgba(34,197,94,.8)',borderRadius:3},{label:'REVIEW',data:D.catReview,backgroundColor:'rgba(245,158,11,.8)',borderRadius:3},{label:'FAIL',data:D.catFail,backgroundColor:'rgba(239,68,68,.8)',borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top',labels:{padding:10,boxWidth:10}}},scales:{x:{stacked:true,ticks:{maxRotation:35,font:{size:10}}},y:{stacked:true,beginAtZero:true}}}});
new Chart(document.getElementById('cTL'),{type:'bar',data:{labels:D.tlLabels,datasets:[{label:'Expiring',data:D.tlValues,backgroundColor:'rgba(59,130,246,.7)',borderColor:'#3b82f6',borderWidth:1,borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,ticks:{stepSize:1}}}}});

// World Map (Plotly)
let mapRendered = false;
function renderMap(mode) {
  const z    = mode === 'count' ? D.mapCounts : D.mapVols;
  const ctitle = mode === 'count' ? 'Number of markets' : 'Volume (USD millions)';
  const colorscale = mode === 'count'
    ? [[0,'#1e3a5f'],[0.25,'#1d4ed8'],[0.5,'#3b82f6'],[0.75,'#60a5fa'],[1,'#bfdbfe']]
    : [[0,'#3b1a5f'],[0.25,'#7c3aed'],[0.5,'#a855f7'],[0.75,'#c084fc'],[1,'#e9d5ff']];
  Plotly.react('worldmap',[{
    type:'choropleth', locationmode:'ISO-3',
    locations:D.mapIsos, z:z, text:D.mapText,
    hoverinfo:'text', colorscale:colorscale,
    marker:{line:{color:'#334155',width:0.5}},
    colorbar:{title:{text:ctitle,font:{color:'#94a3b8',size:11}},tickfont:{color:'#94a3b8'},bgcolor:'rgba(0,0,0,0)',bordercolor:'#334155'}
  }],{
    geo:{showframe:false,showcoastlines:true,coastlinecolor:'#334155',showland:true,landcolor:'#1e293b',showocean:true,oceancolor:'#0f172a',showlakes:false,projection:{type:'natural earth'},bgcolor:'rgba(0,0,0,0)'},
    paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
    margin:{t:10,b:10,l:10,r:10},
    font:{color:'#94a3b8',family:"-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"}
  },{responsive:true,displayModeBar:false});
  mapRendered = true;
}
function switchMap(mode, btn) {
  document.querySelectorAll('.frow .fbtn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderMap(mode);
}
</script>
</body>
</html>"""

    S = stats
    repl = {
        "REPLACE_DATE":         generated_at,
        "REPLACE_TOTAL":        str(S["total"]),
        "REPLACE_PS_PCT":       str(ps_match_pct),
        "REPLACE_OPS_HIGH":     str(S["ops_critical"] + S["ops_high"]),
        "REPLACE_QA_FAIL":      str(S["qa_fail"]),
        "REPLACE_QA_REVIEW":    str(S["qa_review"]),
        "REPLACE_QA_PASS":      str(S["qa_pass"]),
        "REPLACE_COMP_HIGH":    str(S["comp_high"]),
        "REPLACE_COMP_MED":     str(S["comp_medium"]),
        "REPLACE_COMP_LOW":     str(S["comp_low"]),
        "REPLACE_RISK_HIGH":    str(S["risk_high"]),
        "REPLACE_RISK_MED":     str(S["risk_medium"]),
        "REPLACE_ALERT_TOTAL":  str(total_alerts),
        "REPLACE_EXP24":        str(len(alerts["expiring_24h"])),
        "REPLACE_OVERDUE":      str(len(alerts["overdue"])),
        "REPLACE_CNT_24H":      cnt(len(alerts["expiring_24h"]),   "red"),
        "REPLACE_CNT_48H":      cnt(len(alerts["expiring_48h"]),   "yellow"),
        "REPLACE_CNT_7D":       cnt(len(alerts["expiring_7d"]),    "blue"),
        "REPLACE_CNT_OD":       cnt(len(alerts["overdue"]),        "red"),
        "REPLACE_CNT_LIQ":      cnt(len(alerts["low_liquidity"]), "yellow"),
        "REPLACE_CNT_ZV":       cnt(len(alerts["zero_volume"]),   "gray"),
        "REPLACE_A24H":         a24h,
        "REPLACE_A48H":         a48h,
        "REPLACE_A7D":          a7d,
        "REPLACE_AOD":          aod,
        "REPLACE_ALIQ":         aliq,
        "REPLACE_AZV":          azv,
        "REPLACE_TRIAGE_TBL":   triage_tbl,
        "REPLACE_QA_TBL":       qa_tbl,
        "REPLACE_INT_TBL":      int_tbl,
        "REPLACE_COMP_TBL":     comp_tbl,
        "REPLACE_CHART_DATA":   chart_data,
    }
    for k, v in repl.items():
        HTML = HTML.replace(k, v)
    return HTML

# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  POLYMARKET OPS INTELLIGENCE DASHBOARD  v2")
    print("=" * 60)

    raw_gamma = fetch_gamma(MAX_GAMMA)
    if not raw_gamma:
        print("ERROR: No Gamma events fetched."); sys.exit(1)

    ps_raw = fetch_ps(MAX_PS)
    ps_index = build_ps_index(ps_raw) if ps_raw else {}

    events = [parse_gamma(e) for e in raw_gamma]
    if ps_index:
        events = enrich_events(events, ps_index)

    for ev in events:
        ev["category"]    = classify(ev["tags"], ev["title"])
        ev["country_iso"] = detect_country(ev)
        s,g,c,f = score_qa(ev)
        ev["qa_score"], ev["qa_grade"], ev["qa_color"], ev["qa_flags"] = s,g,c,f
        s,l,c,f = score_integrity(ev)
        ev["int_score"], ev["risk_level"], ev["risk_color"], ev["int_flags"] = s,l,c,f
        s,l,c,f = score_compliance(ev)
        ev["comp_score"], ev["comp_level"], ev["comp_color"], ev["comp_flags"] = s,l,c,f
        ops_s, ops_l, ops_c = composite_risk(ev)
        ev["ops_score"], ev["ops_level"], ev["ops_color"] = ops_s, ops_l, ops_c

    alerts = get_alerts(events)

    qa_grades  = [ev["qa_grade"]   for ev in events]
    risk_lvls  = [ev["risk_level"] for ev in events]
    comp_lvls  = [ev["comp_level"] for ev in events]
    ops_lvls   = [ev["ops_level"]  for ev in events]

    stats = {
        "total":        len(events),
        "qa_pass":      qa_grades.count("PASS"),
        "qa_review":    qa_grades.count("REVIEW"),
        "qa_fail":      qa_grades.count("FAIL"),
        "risk_low":     risk_lvls.count("LOW"),
        "risk_medium":  risk_lvls.count("MEDIUM"),
        "risk_high":    risk_lvls.count("HIGH"),
        "comp_low":     comp_lvls.count("LOW"),
        "comp_medium":  comp_lvls.count("MEDIUM"),
        "comp_high":    comp_lvls.count("HIGH"),
        "ops_low":      ops_lvls.count("LOW"),
        "ops_medium":   ops_lvls.count("MEDIUM"),
        "ops_high":     ops_lvls.count("HIGH"),
        "ops_critical": ops_lvls.count("CRITICAL"),
    }

    print(f"\n{'─'*40}")
    print(f"  Markets:        {stats['total']}")
    print(f"  QA:  PASS {stats['qa_pass']:>3}  REVIEW {stats['qa_review']:>3}  FAIL {stats['qa_fail']:>3}")
    print(f"  INT: LOW  {stats['risk_low']:>3}  MED    {stats['risk_medium']:>3}  HIGH {stats['risk_high']:>3}")
    print(f"  CMP: LOW  {stats['comp_low']:>3}  MED    {stats['comp_medium']:>3}  HIGH {stats['comp_high']:>3}")
    print(f"  OPS: LOW  {stats['ops_low']:>3}  MED    {stats['ops_medium']:>3}  HIGH {stats['ops_high']:>3}  CRIT {stats['ops_critical']:>3}")
    print(f"  Alerts: {sum(len(v) for v in alerts.values())}")
    countries = [ev["country_iso"] for ev in events if ev["country_iso"]]
    print(f"  Countries detected: {len(set(countries))} ({len(countries)} markets mapped)")
    print(f"{'─'*40}")

    html = build_html(events, alerts, stats, TODAY.strftime("%Y-%m-%d %H:%M UTC"))
    out  = "/sessions/nice-modest-clarke/mnt/outputs/polymarket-analysis/compliance_ops_dashboard.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    kb = len(html.encode("utf-8")) / 1024
    print(f"\n✓  compliance_ops_dashboard.html  ({kb:.0f} KB)")
    print("=" * 60)

if __name__ == "__main__":
    main()
