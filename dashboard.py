#!/usr/bin/env python3
"""
Polymarket Operations Intelligence Dashboard
============================================
Compliance | Resolution QA | Integrity Monitoring | Daily Ops Alerts

Fetches live data from the Polymarket Gamma API and generates a
self-contained interactive HTML dashboard.

Usage:
    python3 dashboard.py
Output:
    compliance_ops_dashboard.html
"""

import requests
import time
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import warnings
warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

API_BASE  = "https://gamma-api.polymarket.com"
MAX_RECORDS = 300
SLEEP_MS  = 0.4
TODAY     = datetime.now(timezone.utc)

CATEGORY_KEYWORDS = {
    "Politics & Elections":       ["politics","election","president","congress","senate","vote","democrat","republican","trump","biden","harris","white house","ballot","poll","governor","primary","cabinet","legislation"],
    "Sports":                     ["sports","nfl","nba","mlb","nhl","soccer","football","basketball","tennis","golf","f1","formula","ufc","boxing","olympic","championship","world cup","super bowl","playoffs","league","tournament"],
    "Crypto & Blockchain":        ["crypto","bitcoin","ethereum","defi","blockchain","token","btc","eth","solana","nft","web3","dao","stablecoin","altcoin","halving","coinbase","binance"],
    "Economics & Finance":        ["economy","economics","gdp","inflation","fed","federal reserve","interest rate","recession","stock","earnings","unemployment","cpi","treasury","s&p","nasdaq","dow","ipo"],
    "Geopolitics & World Affairs":["war","conflict","nato","ukraine","russia","china","middle east","iran","israel","military","sanctions","diplomat","ceasefire","treaty","taiwan","nuclear","north korea"],
    "Culture & Entertainment":    ["entertainment","oscar","emmy","grammy","music","film","celebrity","box office","award","streaming","netflix","marvel","taylor swift","nba draft","reality tv"],
    "Technology & AI":            ["technology","tech","ai","artificial intelligence","openai","gpt","anthropic","microsoft","apple","google","meta","startup","ipo","semiconductor","chip","spacex"],
    "Science, Health & Env.":     ["science","health","climate","environment","covid","fda","vaccine","space","nasa","hurricane","earthquake","cancer","drug","approval","who","pandemic"],
}

# ═══════════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════════════════════════════

def fetch_events(max_records=300):
    events = []
    limit  = 100
    offset = 0
    print("Fetching Polymarket events...")
    while len(events) < max_records:
        try:
            r = requests.get(
                f"{API_BASE}/events",
                params={"limit": limit, "offset": offset,
                        "active": "true", "order": "volume", "ascending": "false"},
                timeout=30
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            events.extend(batch)
            print(f"  {len(events)} events fetched...", end="\r", flush=True)
            if len(batch) < limit:
                break
            offset += limit
            time.sleep(SLEEP_MS)
        except Exception as exc:
            print(f"\nWarning: {exc}")
            break
    print(f"\nFetched {len(events)} events.")
    return events[:max_records]


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

def parse_event(raw):
    tags = [t.get("label", "") for t in (raw.get("tags") or []) if isinstance(t, dict)]
    return {
        "id":           raw.get("id", ""),
        "title":        raw.get("title", "Untitled"),
        "description":  raw.get("description", "") or "",
        "volume":       _float(raw.get("volume")),
        "volume_24h":   _float(raw.get("volume24hr") or raw.get("volume_24h")),
        "volume_1w":    _float(raw.get("volume1w")   or raw.get("volume_1w")),
        "liquidity":    _float(raw.get("liquidity")),
        "open_interest":_float(raw.get("openInterest") or raw.get("open_interest")),
        "comment_count":_int(raw.get("commentCount")  or raw.get("comment_count")),
        "end_date":     _date(raw.get("endDate")   or raw.get("end_date")),
        "start_date":   _date(raw.get("startDate") or raw.get("creationDate")),
        "active":       bool(raw.get("active", False)),
        "tags":         tags,
    }


def classify(tags, title):
    combined = " ".join(tags).lower() + " " + title.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in kws):
            return cat
    return "Other"


# ═══════════════════════════════════════════════════════════════════════════
# MODULE A — RESOLUTION QA SCORER
# ═══════════════════════════════════════════════════════════════════════════

_RE_URL  = re.compile(r"https?://\S+")
_RE_DATE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"\d{4}-\d{2}-\d{2}|\d{1,2}\s+\w+\s+\d{4})\b", re.I)
_AMBIGUOUS = ["may","might","could","approximately","around","roughly",
              "probably","likely","possibly","perhaps","unclear","uncertain"]

def score_qa(ev):
    desc  = ev["description"]
    score = 100
    flags = []

    if len(desc) < 50:
        score -= 35; flags.append("No resolution criteria found")
    elif len(desc) < 150:
        score -= 15; flags.append("Criteria too brief for independent verification")

    if not _RE_URL.search(desc):
        score -= 20; flags.append("No resolution source URL cited")

    found_amb = [w for w in _AMBIGUOUS if re.search(r"\b" + w + r"\b", desc, re.I)]
    if found_amb:
        score -= 15; flags.append(f"Ambiguous language: {', '.join(found_amb[:3])}")

    if not _RE_DATE.search(desc):
        score -= 10; flags.append("No specific resolution date referenced")

    connectors = len(re.findall(r"\b(and|or|unless|provided that|subject to|except if)\b", desc, re.I))
    if connectors >= 4:
        score -= 10; flags.append(f"Complex multi-condition criteria ({connectors} connectors)")

    score = max(0, score)
    if   score >= 80: grade, color = "PASS",   "#22c55e"
    elif score >= 60: grade, color = "REVIEW", "#f59e0b"
    else:             grade, color = "FAIL",   "#ef4444"
    return score, grade, color, flags


# ═══════════════════════════════════════════════════════════════════════════
# MODULE B — INTEGRITY MONITOR
# ═══════════════════════════════════════════════════════════════════════════

def score_integrity(ev):
    vol      = ev["volume"]
    vol_24h  = ev["volume_24h"]
    liq      = ev["liquidity"]
    oi       = ev["open_interest"]
    comments = ev["comment_count"]
    risk     = 0
    flags    = []

    if vol > 0 and vol_24h / vol > 0.45:
        pct = vol_24h / vol * 100
        risk += 30; flags.append(f"24h volume spike: {pct:.0f}% of all-time volume in last 24h")

    if liq > 0 and oi / liq > 8:
        risk += 25; flags.append(f"OI/Liquidity ratio: {oi/liq:.1f}x — undercollateralised market")

    if liq == 0 and oi > 5000:
        risk += 35; flags.append(f"Zero liquidity with ${oi:,.0f} open interest — exit risk")

    if vol > 50_000 and comments < 3:
        risk += 20; flags.append(f"High volume (${vol:,.0f}) with minimal engagement ({comments} comments)")

    if vol > 10_000 and liq > 0 and liq / vol < 0.01:
        risk += 15; flags.append(f"Liquidity < 1% of volume ({liq/vol*100:.2f}%) — high slippage")

    risk  = min(100, risk)
    score = 100 - risk
    if   score >= 80: level, color = "LOW",    "#22c55e"
    elif score >= 60: level, color = "MEDIUM", "#f59e0b"
    else:             level, color = "HIGH",   "#ef4444"
    return score, level, color, flags


# ═══════════════════════════════════════════════════════════════════════════
# MODULE C — OPS ALERTS
# ═══════════════════════════════════════════════════════════════════════════

def get_alerts(events):
    buckets = dict(expiring_24h=[], expiring_48h=[], expiring_7d=[],
                   overdue=[], low_liquidity=[], zero_volume=[])
    for ev in events:
        end_dt = ev["end_date"]
        active = ev["active"]
        vol    = ev["volume"]
        liq    = ev["liquidity"]

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

def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "N/A"

def time_badge(dt):
    if not dt: return "N/A"
    h = (dt - TODAY).total_seconds() / 3600
    if h < 0:   return f'<span class="tb red">OVERDUE {abs(h):.0f}h ago</span>'
    if h < 24:  return f'<span class="tb red">{h:.1f}h left</span>'
    if h < 48:  return f'<span class="tb yellow">{h:.0f}h left</span>'
    return f'<span class="tb muted">{h/24:.1f}d left</span>'

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')

def flag_pills(flags):
    if not flags:
        return '<span class="ok">✓ No issues</span>'
    return "".join(f'<span class="flag">{esc(f)}</span>' for f in flags)

def qa_rows(events):
    rows = []
    for ev in sorted(events, key=lambda x: x["qa_score"]):
        t = esc(ev["title"][:85] + ("…" if len(ev["title"]) > 85 else ""))
        g, c, s = ev["qa_grade"], ev["qa_color"], ev["qa_score"]
        bar = f'<div class="sbar-w"><div class="sbar" style="width:{s}%;background:{c}"></div><span>{s}</span></div>'
        rows.append(
            f'<tr data-grade="{g}">'
            f'<td class="tc">{t}</td>'
            f'<td><span class="badge" style="background:{c}20;color:{c};border:1px solid {c}50">{g}</span></td>'
            f'<td>{bar}</td>'
            f'<td class="fc">{flag_pills(ev["qa_flags"])}</td>'
            f'<td class="mc">{esc(ev["category"])}</td>'
            f'</tr>'
        )
    return "\n".join(rows)

def integrity_rows(events):
    rows = []
    for ev in sorted(events, key=lambda x: x["int_score"]):
        t  = esc(ev["title"][:85] + ("…" if len(ev["title"]) > 85 else ""))
        lv, c, s = ev["risk_level"], ev["risk_color"], ev["int_score"]
        bar = f'<div class="sbar-w"><div class="sbar" style="width:{s}%;background:{c}"></div><span>{s}</span></div>'
        rows.append(
            f'<tr data-risk="{lv}">'
            f'<td class="tc">{t}</td>'
            f'<td><span class="badge" style="background:{c}20;color:{c};border:1px solid {c}50">{lv}</span></td>'
            f'<td>{bar}</td>'
            f'<td class="vol">{fmt_usd(ev["volume"])}</td>'
            f'<td class="liq">{fmt_usd(ev["liquidity"])}</td>'
            f'<td class="fc">{flag_pills(ev["int_flags"])}</td>'
            f'</tr>'
        )
    return "\n".join(rows)

def alert_rows(evs, col4_fn):
    if not evs:
        return '<tr><td colspan="5" class="empty">No alerts in this category ✓</td></tr>'
    rows = []
    for ev in evs:
        t = esc(ev["title"][:75] + ("…" if len(ev["title"]) > 75 else ""))
        c4 = col4_fn(ev)
        qa_c = ev["qa_color"]
        rows.append(
            f'<tr>'
            f'<td class="tc">{t}</td>'
            f'<td class="vol">{fmt_usd(ev["volume"])}</td>'
            f'<td class="liq">{fmt_usd(ev["liquidity"])}</td>'
            f'<td>{c4}</td>'
            f'<td><span class="badge" style="background:{qa_c}20;color:{qa_c};border:1px solid {qa_c}50">{ev["qa_grade"]}</span></td>'
            f'</tr>'
        )
    return "\n".join(rows)


# ═══════════════════════════════════════════════════════════════════════════
# HTML GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def build_html(events, alerts, stats, generated_at):

    # ── chart data ──────────────────────────────────────────────────────────
    cat_qa = defaultdict(lambda: {"PASS": 0, "REVIEW": 0, "FAIL": 0})
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
    tl_values = [timeline.get(l, 0) for l in tl_labels]

    chart_data = json.dumps({
        "qa":       [stats["qa_pass"], stats["qa_review"], stats["qa_fail"]],
        "risk":     [stats["risk_low"], stats["risk_medium"], stats["risk_high"]],
        "catLabels":top_cats,
        "catPass":  [cat_qa[c]["PASS"]   for c in top_cats],
        "catReview":[cat_qa[c]["REVIEW"] for c in top_cats],
        "catFail":  [cat_qa[c]["FAIL"]   for c in top_cats],
        "tlLabels": tl_labels,
        "tlValues": tl_values,
    })

    # ── table HTML ──────────────────────────────────────────────────────────
    qa_tbl  = qa_rows(events)
    int_tbl = integrity_rows(events)
    a24h    = alert_rows(alerts["expiring_24h"],  lambda ev: time_badge(ev["end_date"]))
    a48h    = alert_rows(alerts["expiring_48h"],  lambda ev: time_badge(ev["end_date"]))
    a7d     = alert_rows(alerts["expiring_7d"],   lambda ev: time_badge(ev["end_date"]))
    aod     = alert_rows(alerts["overdue"],       lambda ev: time_badge(ev["end_date"]))
    aliq    = alert_rows(alerts["low_liquidity"], lambda ev: f'<span class="tb yellow">{fmt_usd(ev["liquidity"])}</span>')
    azv     = alert_rows(alerts["zero_volume"],   lambda ev: f'<span class="mc">{esc(ev["category"])}</span>')

    total_alerts = len(alerts["expiring_24h"]) + len(alerts["overdue"]) + len(alerts["low_liquidity"])

    S = stats
    # badge counts
    def cnt(n, cls):
        return f'<span class="cnt {cls}">{n}</span>'

    HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Polymarket Ops Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f172a;--surf:#1e293b;--surf2:#253047;--bdr:#334155;
  --tx:#e2e8f0;--muted:#94a3b8;
  --green:#22c55e;--yellow:#f59e0b;--red:#ef4444;--blue:#3b82f6;--purple:#a855f7;
}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--tx);font-size:14px;line-height:1.5}

/* ── HEADER ── */
.hdr{background:var(--surf);border-bottom:1px solid var(--bdr);padding:14px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.logo{font-size:18px;font-weight:700;color:var(--blue);letter-spacing:-.4px}
.logo span{color:var(--tx);font-weight:400}
.hdr-meta{font-size:11px;color:var(--muted);margin-top:2px}
.live{display:inline-flex;align-items:center;gap:5px;background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);color:var(--green);padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;letter-spacing:.5px}
.live-dot{width:6px;height:6px;background:var(--green);border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* ── CARDS ── */
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:20px 24px}
.card{background:var(--surf);border:1px solid var(--bdr);border-radius:10px;padding:18px 20px}
.card-lbl{font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:6px}
.card-val{font-size:30px;font-weight:700;line-height:1;margin-bottom:4px}
.card-sub{font-size:12px;color:var(--muted)}

/* ── TABS ── */
.tabs{display:flex;padding:0 24px;border-bottom:1px solid var(--bdr);margin-bottom:20px}
.tab{padding:11px 18px;background:none;border:none;color:var(--muted);cursor:pointer;font-size:14px;font-weight:500;border-bottom:2px solid transparent;margin-bottom:-1px;transition:color .15s,border-color .15s}
.tab:hover{color:var(--tx)}
.tab.active{color:var(--blue);border-bottom-color:var(--blue)}
.panel{display:none;padding:0 24px 48px}
.panel.active{display:block}

/* ── CHARTS ── */
.ch-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.ch-card{background:var(--surf);border:1px solid var(--bdr);border-radius:10px;padding:18px}
.ch-title{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px}
.ch-wrap{position:relative;height:220px}

/* ── TABLES ── */
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
.tc{max-width:360px;font-size:13px}
.fc{max-width:280px}
.mc{font-size:12px;color:var(--muted)}
.vol{color:var(--yellow);white-space:nowrap}
.liq{color:var(--blue);white-space:nowrap}
.empty{text-align:center;padding:24px;color:var(--muted);font-size:13px}

/* ── BADGES / FLAGS ── */
.badge{display:inline-block;padding:3px 8px;border-radius:5px;font-size:11px;font-weight:700;letter-spacing:.5px;white-space:nowrap}
.flag{display:inline-block;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.25);color:var(--yellow);font-size:11px;padding:2px 7px;border-radius:4px;margin:2px 3px 2px 0;white-space:nowrap}
.ok{font-size:12px;color:var(--green)}
.tb{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600}
.tb.red{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3)}
.tb.yellow{background:rgba(245,158,11,.15);color:var(--yellow);border:1px solid rgba(245,158,11,.3)}
.tb.muted{background:rgba(148,163,184,.1);color:var(--muted);border:1px solid rgba(148,163,184,.2)}

/* ── SCORE BAR ── */
.sbar-w{display:flex;align-items:center;gap:8px}
.sbar{height:6px;border-radius:3px;min-width:4px}
.sbar-w span{font-size:12px;color:var(--muted);min-width:22px}

/* ── COUNT BADGE ── */
.cnt{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:22px;border-radius:11px;font-size:11px;font-weight:700;padding:0 6px}
.cnt.red{background:rgba(239,68,68,.2);color:var(--red);border:1px solid rgba(239,68,68,.4)}
.cnt.yellow{background:rgba(245,158,11,.2);color:var(--yellow);border:1px solid rgba(245,158,11,.4)}
.cnt.blue{background:rgba(59,130,246,.2);color:var(--blue);border:1px solid rgba(59,130,246,.4)}
.cnt.gray{background:rgba(100,116,139,.2);color:#64748b;border:1px solid rgba(100,116,139,.4)}

/* ── FILTER ROW ── */
.frow{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.fbtn{padding:5px 14px;border-radius:6px;border:1px solid var(--bdr);background:none;color:var(--muted);cursor:pointer;font-size:12px;font-weight:500;transition:all .15s}
.fbtn:hover{border-color:var(--blue);color:var(--blue)}
.fbtn.active{background:rgba(59,130,246,.15);border-color:var(--blue);color:var(--blue)}

/* ── ALERT GRID ── */
.agrid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}

::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:3px}
</style>
</head>
<body>

<!-- HEADER -->
<div class="hdr">
  <div>
    <div class="logo">Polymarket <span>Ops Intelligence</span></div>
    <div class="hdr-meta">Compliance &nbsp;·&nbsp; Resolution QA &nbsp;·&nbsp; Integrity Monitoring &nbsp;·&nbsp; Daily Ops</div>
  </div>
  <div style="display:flex;align-items:center;gap:16px">
    <div style="text-align:right">
      <div style="font-size:11px;color:var(--muted)">Last updated</div>
      <div style="font-size:12px;font-weight:600">REPLACE_DATE</div>
    </div>
    <div class="live"><div class="live-dot"></div>LIVE DATA</div>
  </div>
</div>

<!-- SUMMARY CARDS -->
<div class="cards">
  <div class="card">
    <div class="card-lbl">Markets Monitored</div>
    <div class="card-val" style="color:var(--blue)">REPLACE_TOTAL</div>
    <div class="card-sub">Active events analysed</div>
  </div>
  <div class="card">
    <div class="card-lbl">Integrity High-Risk</div>
    <div class="card-val" style="color:var(--red)">REPLACE_RISK_HIGH</div>
    <div class="card-sub">REPLACE_RISK_MED medium &nbsp;·&nbsp; REPLACE_RISK_LOW low</div>
  </div>
  <div class="card">
    <div class="card-lbl">QA Issues</div>
    <div class="card-val" style="color:var(--yellow)">REPLACE_QA_FAIL</div>
    <div class="card-sub">REPLACE_QA_REVIEW need review &nbsp;·&nbsp; REPLACE_QA_PASS pass</div>
  </div>
  <div class="card">
    <div class="card-lbl">Active Alerts</div>
    <div class="card-val" style="color:var(--purple)">REPLACE_ALERT_TOTAL</div>
    <div class="card-sub">REPLACE_EXP24 expiring &lt;24h &nbsp;·&nbsp; REPLACE_OVERDUE overdue</div>
  </div>
</div>

<!-- TABS -->
<div class="tabs">
  <button class="tab active" onclick="showTab('overview',this)">📊 Overview</button>
  <button class="tab"        onclick="showTab('ops',this)">🚨 Daily Ops</button>
  <button class="tab"        onclick="showTab('qa',this)">📋 Resolution QA</button>
  <button class="tab"        onclick="showTab('integrity',this)">🔍 Integrity Monitor</button>
</div>

<!-- ════════════════════ TAB: OVERVIEW ════════════════════ -->
<div id="tab-overview" class="panel active">
  <div class="ch-grid">
    <div class="ch-card">
      <div class="ch-title">QA Grade Distribution</div>
      <div class="ch-wrap"><canvas id="cQA"></canvas></div>
    </div>
    <div class="ch-card">
      <div class="ch-title">Integrity Risk Distribution</div>
      <div class="ch-wrap"><canvas id="cRisk"></canvas></div>
    </div>
    <div class="ch-card">
      <div class="ch-title">QA Score by Category</div>
      <div class="ch-wrap"><canvas id="cCat"></canvas></div>
    </div>
    <div class="ch-card">
      <div class="ch-title">Markets Expiring — Next 7 Days</div>
      <div class="ch-wrap"><canvas id="cTL"></canvas></div>
    </div>
  </div>
</div>

<!-- ════════════════════ TAB: DAILY OPS ════════════════════ -->
<div id="tab-ops" class="panel">
  <div class="agrid">
    <div class="tcard">
      <div class="thdr"><div class="ttitle">⏰ Expiring in 24h</div>REPLACE_CNT_24H</div>
      <div class="twrap"><table>
        <thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Time Left</th><th>QA</th></tr></thead>
        <tbody>REPLACE_A24H</tbody>
      </table></div>
    </div>
    <div class="tcard">
      <div class="thdr"><div class="ttitle">⚠️ Overdue (Unresolved)</div>REPLACE_CNT_OD</div>
      <div class="twrap"><table>
        <thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Status</th><th>QA</th></tr></thead>
        <tbody>REPLACE_AOD</tbody>
      </table></div>
    </div>
  </div>
  <div class="agrid">
    <div class="tcard">
      <div class="thdr"><div class="ttitle">🕐 Expiring in 48h</div>REPLACE_CNT_48H</div>
      <div class="twrap"><table>
        <thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Time Left</th><th>QA</th></tr></thead>
        <tbody>REPLACE_A48H</tbody>
      </table></div>
    </div>
    <div class="tcard">
      <div class="thdr"><div class="ttitle">📅 Expiring This Week</div>REPLACE_CNT_7D</div>
      <div class="twrap"><table>
        <thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Time Left</th><th>QA</th></tr></thead>
        <tbody>REPLACE_A7D</tbody>
      </table></div>
    </div>
  </div>
  <div class="agrid">
    <div class="tcard">
      <div class="thdr"><div class="ttitle">💧 Low Liquidity Alert</div>REPLACE_CNT_LIQ</div>
      <div class="twrap"><table>
        <thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Liq. Level</th><th>QA</th></tr></thead>
        <tbody>REPLACE_ALIQ</tbody>
      </table></div>
    </div>
    <div class="tcard">
      <div class="thdr"><div class="ttitle">🚫 Zero Volume Markets</div>REPLACE_CNT_ZV</div>
      <div class="twrap"><table>
        <thead><tr><th>Market</th><th>Volume</th><th>Liquidity</th><th>Category</th><th>QA</th></tr></thead>
        <tbody>REPLACE_AZV</tbody>
      </table></div>
    </div>
  </div>
</div>

<!-- ════════════════════ TAB: RESOLUTION QA ════════════════════ -->
<div id="tab-qa" class="panel">
  <div style="margin-bottom:16px">
    <div style="font-size:15px;font-weight:600;margin-bottom:4px">Resolution Criteria Quality Assessment</div>
    <div style="font-size:12px;color:var(--muted)">Scoring accuracy, clarity, source citation, and verifiability of each market's resolution rules</div>
  </div>
  <div class="frow">
    <button class="fbtn active" onclick="filterQA(null,this)">All (REPLACE_TOTAL)</button>
    <button class="fbtn" style="color:var(--red)"    onclick="filterQA('FAIL',this)">🔴 FAIL (REPLACE_QA_FAIL)</button>
    <button class="fbtn" style="color:var(--yellow)" onclick="filterQA('REVIEW',this)">🟡 REVIEW (REPLACE_QA_REVIEW)</button>
    <button class="fbtn" style="color:var(--green)"  onclick="filterQA('PASS',this)">🟢 PASS (REPLACE_QA_PASS)</button>
  </div>
  <div class="tcard">
    <div class="twrap">
      <table id="tQA">
        <thead><tr>
          <th onclick="sort('tQA',0)">Market ↕</th>
          <th onclick="sort('tQA',1)">Grade ↕</th>
          <th onclick="sort('tQA',2)">Score ↕</th>
          <th>Issues Detected</th>
          <th onclick="sort('tQA',4)">Category ↕</th>
        </tr></thead>
        <tbody>REPLACE_QA_TBL</tbody>
      </table>
    </div>
  </div>
</div>

<!-- ════════════════════ TAB: INTEGRITY MONITOR ════════════════════ -->
<div id="tab-integrity" class="panel">
  <div style="margin-bottom:16px">
    <div style="font-size:15px;font-weight:600;margin-bottom:4px">Market Integrity &amp; Anomaly Detection</div>
    <div style="font-size:12px;color:var(--muted)">Volume spikes, liquidity gaps, open-interest imbalances, and low-engagement anomalies</div>
  </div>
  <div class="frow">
    <button class="fbtn active" onclick="filterInt(null,this)">All (REPLACE_TOTAL)</button>
    <button class="fbtn" style="color:var(--red)"    onclick="filterInt('HIGH',this)">🔴 HIGH (REPLACE_RISK_HIGH)</button>
    <button class="fbtn" style="color:var(--yellow)" onclick="filterInt('MEDIUM',this)">🟡 MEDIUM (REPLACE_RISK_MED)</button>
    <button class="fbtn" style="color:var(--green)"  onclick="filterInt('LOW',this)">🟢 LOW (REPLACE_RISK_LOW)</button>
  </div>
  <div class="tcard">
    <div class="twrap">
      <table id="tInt">
        <thead><tr>
          <th onclick="sort('tInt',0)">Market ↕</th>
          <th onclick="sort('tInt',1)">Risk ↕</th>
          <th onclick="sort('tInt',2)">Score ↕</th>
          <th onclick="sort('tInt',3)">Volume ↕</th>
          <th onclick="sort('tInt',4)">Liquidity ↕</th>
          <th>Anomaly Flags</th>
        </tr></thead>
        <tbody>REPLACE_INT_TBL</tbody>
      </table>
    </div>
  </div>
</div>

<script>
const D = REPLACE_CHART_DATA;

// tabs
function showTab(id, btn) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  btn.classList.add('active');
}

// filter QA table
function filterQA(grade, btn) {
  document.querySelectorAll('#tQA tbody tr').forEach(r => {
    r.style.display = (!grade || r.dataset.grade === grade) ? '' : 'none';
  });
  btn.closest('.frow').querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

// filter integrity table
function filterInt(level, btn) {
  document.querySelectorAll('#tInt tbody tr').forEach(r => {
    r.style.display = (!level || r.dataset.risk === level) ? '' : 'none';
  });
  btn.closest('.frow').querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

// sort table
const _sortState = {};
function sort(tId, col) {
  const tbl  = document.getElementById(tId);
  const rows = Array.from(tbl.querySelectorAll('tbody tr'));
  const key  = tId + '_' + col;
  const asc  = !_sortState[key];
  _sortState[key] = asc;
  rows.sort((a, b) => {
    const av = a.cells[col]?.textContent?.trim() || '';
    const bv = b.cells[col]?.textContent?.trim() || '';
    const an = parseFloat(av.replace(/[$KMBkm%,\s]/gi, ''));
    const bn = parseFloat(bv.replace(/[$KMBkm%,\s]/gi, ''));
    if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
  rows.forEach(r => tbl.querySelector('tbody').appendChild(r));
}

// charts
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';
Chart.defaults.font.family = "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";
Chart.defaults.font.size = 12;

const DONUT_OPTS = {
  responsive:true, maintainAspectRatio:false,
  plugins:{
    legend:{position:'right', labels:{padding:14,boxWidth:11}},
    tooltip:{callbacks:{label:c=>` ${c.label}: ${c.raw}`}}
  },
  cutout:'62%'
};

new Chart(document.getElementById('cQA'), {
  type:'doughnut',
  data:{
    labels:['PASS','REVIEW','FAIL'],
    datasets:[{data:D.qa, backgroundColor:['rgba(34,197,94,.8)','rgba(245,158,11,.8)','rgba(239,68,68,.8)'], borderColor:['#22c55e','#f59e0b','#ef4444'], borderWidth:2}]
  },
  options:DONUT_OPTS
});

new Chart(document.getElementById('cRisk'), {
  type:'doughnut',
  data:{
    labels:['LOW','MEDIUM','HIGH'],
    datasets:[{data:D.risk, backgroundColor:['rgba(34,197,94,.8)','rgba(245,158,11,.8)','rgba(239,68,68,.8)'], borderColor:['#22c55e','#f59e0b','#ef4444'], borderWidth:2}]
  },
  options:DONUT_OPTS
});

new Chart(document.getElementById('cCat'), {
  type:'bar',
  data:{
    labels:D.catLabels,
    datasets:[
      {label:'PASS',   data:D.catPass,   backgroundColor:'rgba(34,197,94,.8)',  borderRadius:3},
      {label:'REVIEW', data:D.catReview, backgroundColor:'rgba(245,158,11,.8)', borderRadius:3},
      {label:'FAIL',   data:D.catFail,   backgroundColor:'rgba(239,68,68,.8)',  borderRadius:3},
    ]
  },
  options:{
    responsive:true, maintainAspectRatio:false,
    plugins:{legend:{position:'top',labels:{padding:10,boxWidth:10}}},
    scales:{
      x:{stacked:true, ticks:{maxRotation:35,font:{size:10}}},
      y:{stacked:true, beginAtZero:true}
    }
  }
});

new Chart(document.getElementById('cTL'), {
  type:'bar',
  data:{
    labels:D.tlLabels,
    datasets:[{
      label:'Expiring',
      data:D.tlValues,
      backgroundColor:'rgba(59,130,246,.7)',
      borderColor:'#3b82f6',
      borderWidth:1,
      borderRadius:4
    }]
  },
  options:{
    responsive:true, maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{
      x:{grid:{display:false}},
      y:{beginAtZero:true, ticks:{stepSize:1}}
    }
  }
});
</script>
</body>
</html>"""

    # ── inject dynamic data ──────────────────────────────────────────────────
    repl = {
        "REPLACE_DATE":         generated_at,
        "REPLACE_TOTAL":        str(S["total"]),
        "REPLACE_RISK_HIGH":    str(S["risk_high"]),
        "REPLACE_RISK_MED":     str(S["risk_medium"]),
        "REPLACE_RISK_LOW":     str(S["risk_low"]),
        "REPLACE_QA_FAIL":      str(S["qa_fail"]),
        "REPLACE_QA_REVIEW":    str(S["qa_review"]),
        "REPLACE_QA_PASS":      str(S["qa_pass"]),
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
        "REPLACE_QA_TBL":       qa_tbl,
        "REPLACE_INT_TBL":      int_tbl,
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
    print("  POLYMARKET OPS INTELLIGENCE DASHBOARD")
    print("=" * 60)

    raw = fetch_events(MAX_RECORDS)
    if not raw:
        print("ERROR: No events fetched. Check API connectivity.")
        sys.exit(1)

    events = [parse_event(e) for e in raw]
    for ev in events:
        ev["category"] = classify(ev["tags"], ev["title"])

    for ev in events:
        s, g, c, f = score_qa(ev)
        ev["qa_score"], ev["qa_grade"], ev["qa_color"], ev["qa_flags"] = s, g, c, f

    for ev in events:
        s, l, c, f = score_integrity(ev)
        ev["int_score"], ev["risk_level"], ev["risk_color"], ev["int_flags"] = s, l, c, f

    alerts = get_alerts(events)

    qa_grades  = [ev["qa_grade"]   for ev in events]
    risk_lvls  = [ev["risk_level"] for ev in events]
    stats = {
        "total":       len(events),
        "qa_pass":     qa_grades.count("PASS"),
        "qa_review":   qa_grades.count("REVIEW"),
        "qa_fail":     qa_grades.count("FAIL"),
        "risk_low":    risk_lvls.count("LOW"),
        "risk_medium": risk_lvls.count("MEDIUM"),
        "risk_high":   risk_lvls.count("HIGH"),
    }

    print(f"\n{'─'*40}")
    print(f"  Markets analysed : {stats['total']}")
    print(f"  QA  — PASS {stats['qa_pass']:>3}  REVIEW {stats['qa_review']:>3}  FAIL {stats['qa_fail']:>3}")
    print(f"  Risk— LOW  {stats['risk_low']:>3}  MED    {stats['risk_medium']:>3}  HIGH {stats['risk_high']:>3}")
    print(f"  Alerts:")
    for k, v in alerts.items():
        if v: print(f"    {k:<22} {len(v)}")
    print(f"{'─'*40}")

    html = build_html(events, alerts, stats, TODAY.strftime("%Y-%m-%d %H:%M UTC"))

    out = "/sessions/nice-modest-clarke/mnt/outputs/polymarket-analysis/compliance_ops_dashboard.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)

    kb = len(html.encode("utf-8")) / 1024
    print(f"\n✓  Saved: compliance_ops_dashboard.html ({kb:.0f} KB)")
    print(f"   Open in any browser — no server required.")
    print("=" * 60)


if __name__ == "__main__":
    main()
