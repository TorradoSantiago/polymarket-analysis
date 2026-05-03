#!/usr/bin/env python3
"""Polymarket Ops Intelligence Dashboard v4 — imports HTML renderer from build_html.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from build_html import write_dashboard, TODAY

import requests, time, re, warnings
from datetime import datetime, timezone
from collections import defaultdict
warnings.filterwarnings("ignore")

GAMMA_API = "https://gamma-api.polymarket.com"
PS_API    = "https://gzydspfquuaudqeztorw.supabase.co/functions/v1/agent-api"
AGENT_ID  = "polymarket-ops-dashboard-v4"
MAX_GAMMA = 300
MAX_PS    = 500

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
        if any(kw in combined for kw in kws): return cat
    return "Other"

COUNTRY_KEYWORDS = {
    "USA":["trump","biden","harris","congress","senate","white house","federal reserve","us election","american","washington","democrat","republican","us government","pentagon","us president","nasdaq","s&p"],
    "GBR":["uk ","britain","british","sunak","keir starmer","labour","conservative","parliament","london","scotland"],
    "RUS":["russia","russian","putin","moscow","kremlin","ruble"],
    "CHN":["china","chinese","xi jinping","beijing","ccp","hong kong","yuan"],
    "UKR":["ukraine","ukrainian","kyiv","zelensky"],
    "ISR":["israel","israeli","netanyahu","tel aviv","idf"],
    "PSE":["gaza","hamas","palestin","west bank"],
    "IRN":["iran","iranian","tehran","khamenei","irgc"],
    "FRA":["france","french","macron","paris","le pen"],
    "DEU":["germany","german","berlin","scholz","merz","bundestag","afd"],
    "BRA":["brazil","brazilian","lula","bolsonaro","brasilia"],
    "IND":["india","indian","modi","delhi","mumbai"],
    "PRK":["north korea","kim jong","pyongyang","dprk"],
    "TUR":["turkey","turkish","erdogan","ankara"],
    "VEN":["venezuela","maduro","caracas"],
    "ARG":["argentina","milei","buenos aires"],
    "MEX":["mexico","mexican","sheinbaum"],
    "JPN":["japan","japanese","tokyo","yen jpy","bank of japan"],
    "KOR":["south korea","korean","seoul"],
    "TWN":["taiwan","taiwanese","taipei"],
    "SAU":["saudi","riyadh","bin salman","aramco","opec"],
    "SYR":["syria","syrian","damascus"],
    "PAK":["pakistan","islamabad","karachi"],
    "CAN":["canada","canadian","trudeau","carney","ottawa"],
    "AUS":["australia","australian","sydney","albanese"],
    "ESP":["spain","spanish","madrid","sanchez"],
    "ITA":["italy","italian","rome","meloni"],
    "POL":["poland","polish","warsaw","tusk"],
    "NGA":["nigeria","lagos","abuja"],
    "ZAF":["south africa","johannesburg"],
    "NLD":["netherlands","dutch","amsterdam","wilders"],
    "SWE":["sweden","swedish","stockholm"],
    "NOR":["norway","norwegian","oslo"],
}
def detect_country(ev):
    combined = ev["title"].lower() + " " + " ".join(ev.get("tags",[])).lower()
    for iso, kws in COUNTRY_KEYWORDS.items():
        if any(kw in combined for kw in kws): return iso
    return None

def _float(v):
    try: return float(v or 0)
    except: return 0.0
def _int(v):
    try: return int(v or 0)
    except: return 0
def _date(v):
    if not v: return None
    try:
        s = str(v).replace("Z","+00:00")
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except: return None

def fetch_gamma(max_records=300):
    events, limit, offset = [], 100, 0
    print("1/2 Fetching Gamma API...")
    while len(events) < max_records:
        try:
            r = requests.get(f"{GAMMA_API}/events",
                params={"limit":limit,"offset":offset,"active":"true","order":"volume","ascending":"false"},
                timeout=30)
            r.raise_for_status()
            batch = r.json()
            if not batch: break
            events.extend(batch)
            print(f"  {len(events)}...", end="\r", flush=True)
            if len(batch) < limit: break
            offset += limit; time.sleep(0.4)
        except Exception as e:
            print(f"\nGamma warning: {e}"); break
    print(f"\n  → {len(events)} events")
    return events[:max_records]

def fetch_ps(max_records=500):
    markets, limit, offset = [], 100, 0
    print("2/2 Fetching PolymarketScan...")
    while len(markets) < max_records:
        try:
            r = requests.get(PS_API,
                params={"action":"markets","limit":limit,"offset":offset,"sort":"volume_usd","order":"desc","agent_id":AGENT_ID},
                timeout=30)
            r.raise_for_status()
            data = r.json()
            if not data.get("ok") or not data.get("data"): break
            markets.extend(data["data"])
            print(f"  {len(markets)}...", end="\r", flush=True)
            if len(data["data"]) < limit: break
            offset += limit; time.sleep(0.5)
        except Exception as e:
            print(f"\nPS warning: {e}"); break
    print(f"\n  → {len(markets)} PS markets")
    return markets[:max_records]

def parse_gamma(raw):
    tags = [t.get("label","") for t in (raw.get("tags") or []) if isinstance(t,dict)]
    sub = raw.get("markets",[]) or []
    outcomes_data = []
    for m in sub:
        outs = m.get("outcomes") or []
        prices = m.get("outcomePrices") or []
        if outs and prices and len(outs)==len(prices):
            try:
                pairs = [(str(o), _float(p)) for o,p in zip(outs,prices)]
                outcomes_data.append({"question":m.get("question",""),"pairs":pairs})
            except: pass
    return {
        "id": raw.get("id",""), "title": raw.get("title","Untitled"),
        "description": raw.get("description","") or "",
        "volume": _float(raw.get("volume")),
        "volume_24h": _float(raw.get("volume24hr") or raw.get("volume_24h")),
        "liquidity": _float(raw.get("liquidity")),
        "open_interest": _float(raw.get("openInterest") or raw.get("open_interest")),
        "comment_count": _int(raw.get("commentCount") or raw.get("comment_count")),
        "end_date": _date(raw.get("endDate") or raw.get("end_date")),
        "active": bool(raw.get("active",False)),
        "tags": tags, "outcomes_data": outcomes_data,
        "ps_rules_arb":None,"ps_controversy":None,"ps_smart_money":None,
        "ps_whale_count":None,"ps_is_resolved":None,"ps_winner":None,"ps_matched":False,
    }

def _norm(t):
    t = t.lower().strip()
    t = re.sub(r"[^\w\s]"," ",t)
    return re.sub(r"\s+"," ",t)

def enrich_events(events, ps_markets):
    idx = {_norm(m.get("title","")): m for m in ps_markets}
    matched = 0
    for ev in events:
        nt = _norm(ev["title"])
        m  = idx.get(nt)
        if not m:
            w1 = set(nt.split())
            best, bm = 0, None
            for key, cand in idx.items():
                w2 = set(key.split())
                if len(w1)<3 or len(w2)<3: continue
                ov = len(w1&w2)/min(len(w1),len(w2))
                if ov > best: best, bm = ov, cand
            if best > 0.72: m = bm
        if m:
            ev["ps_rules_arb"]   = m.get("rules_arb_score")
            ev["ps_controversy"] = m.get("controversy_score")
            ev["ps_smart_money"] = m.get("smart_money_bias")
            ev["ps_whale_count"] = m.get("whale_count")
            ev["ps_is_resolved"] = m.get("is_resolved")
            ev["ps_winner"]      = m.get("winner")
            ev["ps_matched"]     = True
            matched += 1
    print(f"  → {matched}/{len(events)} matched to PS")
    return events

_RE_URL  = re.compile(r"https?://\S+")
_RE_DATE = re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b",re.I)
_AMBIG   = ["may","might","could","approximately","around","roughly","probably","likely","possibly","perhaps","unclear","uncertain"]

def score_qa(ev):
    ps_resolved = ev.get("ps_is_resolved")
    end_dt = ev.get("end_date")
    is_expired = (end_dt is not None and end_dt < TODAY)
    if ps_resolved is True or (is_expired and ps_resolved is not False):
        return 100,"RESOLVED","#94a3b8",[]
    desc = ev["description"]; score,flags = 100,[]
    if len(desc)<50:   score-=35; flags.append("No resolution criteria")
    elif len(desc)<150: score-=15; flags.append("Criteria too brief")
    if not _RE_URL.search(desc): score-=20; flags.append("No resolution source URL")
    found=[w for w in _AMBIG if re.search(r"\b"+w+r"\b",desc,re.I)]
    if found: score-=15; flags.append(f"Ambiguous language: {', '.join(found[:3])}")
    if not _RE_DATE.search(desc): score-=10; flags.append("No resolution date")
    n_conn=len(re.findall(r"\b(and|or|unless|provided that|subject to)\b",desc,re.I))
    if n_conn>=4: score-=10; flags.append(f"Multi-condition ({n_conn} connectors)")
    score=max(0,score)
    if score>=80: return score,"PASS","#22c55e",flags
    elif score>=60: return score,"REVIEW","#f59e0b",flags
    else: return score,"FAIL","#ef4444",flags

def score_integrity(ev):
    vol,vol24,liq = ev["volume"],ev["volume_24h"],ev["liquidity"]
    oi,comments   = ev["open_interest"],ev["comment_count"]
    risk,flags = 0,[]
    if vol>0 and vol24/vol>0.45:  risk+=30; flags.append(f"24h spike: {vol24/vol*100:.0f}% of lifetime vol")
    if liq>0 and oi/liq>8:       risk+=25; flags.append(f"OI/Liq: {oi/liq:.1f}x undercollateralised")
    if liq==0 and oi>5000:       risk+=35; flags.append(f"Zero liquidity, ${oi:,.0f} OI")
    if vol>50_000 and comments<3: risk+=20; flags.append(f"High volume, low engagement ({comments})")
    if vol>10_000 and liq>0 and liq/vol<0.01: risk+=15; flags.append("Liquidity <1% of volume")
    controversy = ev.get("ps_controversy") or 0
    if controversy>70: risk+=10; flags.append(f"High controversy: {controversy}")
    sm = ev.get("ps_smart_money") or 0
    if abs(sm)>0.6: risk+=5; flags.append(f"Strong smart money {'bull' if sm>0 else 'bear'}: {sm:.2f}")
    risk=min(100,risk); score=100-risk
    if score>=80: return score,"LOW","#22c55e",flags
    elif score>=60: return score,"MEDIUM","#f59e0b",flags
    else: return score,"HIGH","#ef4444",flags

COMPLIANCE_RULES = [
    (["assassin","killed","death of","dies in office","murdered","suicide"],35,"🔴 Personal safety / death market"),
    (["convicted","arrested","indicted","found guilty","sentenced","charged with","acquitted","impeach"],25,"Legal proceeding — named individual"),
    (["election","ballot","primary","vote","presidential","senate race"],20,"Electoral market — regulatory risk"),
    (["interest rate","fed rate","bps","basis points","cpi report","treasury yield"],20,"Mirrors a regulated financial instrument"),
    (["fda approve","fda reject","drug approval","clinical trial","phase 3"],18,"Pharma regulatory — insider risk"),
    (["invade","invasion","military strike","airstrike","nuclear","weapons","attack on"],15,"Military/conflict market"),
    (["sanctioned","ofac","banned","restricted jurisdiction"],20,"Sanctions / jurisdiction flag"),
]
def score_compliance(ev):
    combined=(ev["title"]+" "+ev["description"]).lower()
    risk,flags=0,[]
    for kws,penalty,desc in COMPLIANCE_RULES:
        if any(kw in combined for kw in kws): risk+=penalty; flags.append(desc)
    risk=min(100,risk); score=100-risk
    if score>=80: return score,"LOW","#22c55e",flags
    elif score>=60: return score,"MEDIUM","#f59e0b",flags
    else: return score,"HIGH","#ef4444",flags

def composite_risk(ev):
    score=100-((100-ev["qa_score"])*.40+(100-ev["int_score"])*.35+(100-ev["comp_score"])*.25)
    score=max(0,min(100,score))
    if score>=75: return round(score),"LOW","#22c55e"
    elif score>=55: return round(score),"MEDIUM","#f59e0b"
    elif score>=35: return round(score),"HIGH","#ef4444"
    else: return round(score),"CRITICAL","#dc2626"

def main():
    raw = fetch_gamma(MAX_GAMMA)
    ps  = fetch_ps(MAX_PS)
    events = [parse_gamma(r) for r in raw]
    events = enrich_events(events, ps)
    for ev in events:
        ev["category"] = classify(ev["tags"], ev["title"])
        ev["country"]  = detect_country(ev)
        qs,qg,qc,qf   = score_qa(ev)
        is_,il,ic,iff = score_integrity(ev)
        cs,cl,cc,cf   = score_compliance(ev)
        ev.update({"qa_score":qs,"qa_grade":qg,"qa_color":qc,"qa_flags":qf,
                   "int_score":is_,"int_level":il,"int_color":ic,"int_flags":iff,
                   "comp_score":cs,"comp_level":cl,"comp_color":cc,"comp_flags":cf})
        os_,ol,oc = composite_risk(ev)
        ev["ops_score"]=os_; ev["ops_level"]=ol; ev["ops_color"]=oc
    out="/sessions/nice-modest-clarke/mnt/outputs/polymarket-analysis/compliance_ops_dashboard.html"
    write_dashboard(events, out)
    import os
    print(f"\n✓  {out}  ({os.path.getsize(out)//1024} KB)")
    print(f"   {len(events)} markets | ${sum(e['volume'] for e in events)/1e9:.1f}B volume")
    print(f"   QA: {sum(1 for e in events if e['qa_grade']=='PASS')} pass / {sum(1 for e in events if e['qa_grade']=='FAIL')} fail / {sum(1 for e in events if e['qa_grade']=='RESOLVED')} resolved")
    print(f"   Elections: {sum(1 for e in events if any(k in e['title'].lower() for k in ['election','president','will win']))}")

if __name__=="__main__":
    main()
