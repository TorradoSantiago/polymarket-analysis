"""HTML generation for Polymarket Ops Intelligence Dashboard v5 — ops-focused"""
import json, math, re
from collections import defaultdict
from datetime import datetime, timezone

TODAY = datetime.now(timezone.utc)
_RE_URL = re.compile(r"https?://\S+")

def fmt_usd(v):
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    if v >= 1e6:  return f"${v/1e6:.1f}M"
    if v >= 1e3:  return f"${v/1e3:.0f}K"
    return f"${v:.0f}"

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')

def fmt_date(dt):
    if not dt: return "—"
    h = (dt - TODAY).total_seconds() / 3600
    if h < 0: return "Expired"
    if h < 24: return f"{h:.0f}h"
    return dt.strftime("%b %d")

COUNTRY_NAMES = {
    "USA":"United States","GBR":"United Kingdom","RUS":"Russia","CHN":"China",
    "UKR":"Ukraine","ISR":"Israel","PSE":"Palestine/Gaza","IRN":"Iran",
    "FRA":"France","DEU":"Germany","BRA":"Brazil","IND":"India","PRK":"North Korea",
    "TUR":"Turkey","VEN":"Venezuela","ARG":"Argentina","MEX":"Mexico","JPN":"Japan",
    "KOR":"South Korea","TWN":"Taiwan","SAU":"Saudi Arabia","SYR":"Syria",
    "PAK":"Pakistan","CAN":"Canada","AUS":"Australia","ESP":"Spain","ITA":"Italy",
    "POL":"Poland","NGA":"Nigeria","ZAF":"South Africa","NLD":"Netherlands",
    "SWE":"Sweden","NOR":"Norway",
}
MAP_CATEGORIES = {"Politics & Elections", "Economics & Finance", "Geopolitics & World Affairs"}

def _get_top_prob(ev):
    if ev.get("outcomes_data"):
        od = ev["outcomes_data"][0]
        if od.get("pairs"):
            top = max(od["pairs"], key=lambda x: x[1])
            return f"{top[0]}: {top[1]*100:.0f}%"
    return ""

# ── RESOLUTION QUEUE ─────────────────────────────────────────────────────────

def _enrich_rq_item(ev, bucket):
    """Shared enrichment for both resolution queue buckets."""
    end = ev.get("end_date")
    h = (end - TODAY).total_seconds() / 3600 if end else 0
    implied_yes = None
    top_outcome, top_prob = None, None
    if ev.get("outcomes_data"):
        for od in ev["outcomes_data"][:1]:
            pairs = od.get("pairs", [])
            if pairs:
                for name, prob in pairs:
                    if "yes" in name.lower():
                        implied_yes = prob; break
                best = max(pairs, key=lambda x: x[1])
                top_outcome, top_prob = best[0], best[1]
    if implied_yes is not None:
        if   implied_yes >= 0.80: conf, conf_clr = "Resolves YES", "#22c55e"
        elif implied_yes <= 0.20: conf, conf_clr = "Resolves NO",  "#ef4444"
        else:                     conf, conf_clr = "Contested",    "#f59e0b"
    elif top_prob is not None:
        if top_prob >= 0.80: conf, conf_clr = f"→ {top_outcome[:14]}", "#22c55e"
        else:                conf, conf_clr = "Contested", "#f59e0b"
    else:
        conf, conf_clr = "Unknown", "#64748b"
    desc = ev.get("description","")
    has_source   = bool(_RE_URL.search(desc))
    desc_ok      = len(desc) >= 150
    is_contested = conf == "Contested"
    return {
        "ev": ev, "hours_left": h, "bucket": bucket,
        "implied_yes": implied_yes, "top_outcome": top_outcome, "top_prob": top_prob,
        "conf": conf, "conf_clr": conf_clr,
        "has_source": has_source, "desc_ok": desc_ok, "is_contested": is_contested,
    }

def build_resolution_queue(events):
    """Two buckets: overdue (expired + PS unresolved) and expiring soon (≤30 days)."""
    overdue, upcoming = [], []
    for ev in events:
        end = ev.get("end_date")
        if not end: continue
        h = (end - TODAY).total_seconds() / 3600
        # BUCKET 1: Expired + PS explicitly marks as unresolved
        if h < 0 and ev.get("ps_is_resolved") is False:
            item = _enrich_rq_item(ev, "overdue")
            # Priority: contested first, then by volume descending
            item["priority"] = (1 if item["is_contested"] else 0)
            item["sort_key"] = (item["priority"], -ev["volume"])
            overdue.append(item)
        # BUCKET 2: Active markets expiring in next 30 days
        elif 0 < h <= 30 * 24 and ev.get("active"):
            item = _enrich_rq_item(ev, "upcoming")
            item["priority"] = (0 if h < 24 else 1 if h < 72 else 2)
            item["sort_key"] = (item["priority"], h)
            upcoming.append(item)
    overdue.sort(key=lambda x: x["sort_key"])
    upcoming.sort(key=lambda x: x["sort_key"])
    return overdue, upcoming


# ── ELECTIONS ─────────────────────────────────────────────────────────────────

CANDIDATE_PROFILES = {
    "trump":{"ideology":"Conservative","party":"Republican","clr":"#ef4444"},
    "harris":{"ideology":"Progressive","party":"Democrat","clr":"#3b82f6"},
    "biden":{"ideology":"Center-left","party":"Democrat","clr":"#3b82f6"},
    "desantis":{"ideology":"Conservative","party":"Republican","clr":"#f97316"},
    "macron":{"ideology":"Centrist","party":"Renaissance","clr":"#a855f7"},
    "le pen":{"ideology":"Right-wing","party":"National Rally","clr":"#ef4444"},
    "meloni":{"ideology":"Right-wing","party":"FdI","clr":"#ef4444"},
    "scholz":{"ideology":"Center-left","party":"SPD","clr":"#ef4444"},
    "merz":{"ideology":"Conservative","party":"CDU","clr":"#3b82f6"},
    "lula":{"ideology":"Left-wing","party":"PT","clr":"#ef4444"},
    "bolsonaro":{"ideology":"Right-wing","party":"PL","clr":"#22c55e"},
    "milei":{"ideology":"Libertarian","party":"LLA","clr":"#f59e0b"},
    "zelensky":{"ideology":"Center","party":"Servant","clr":"#22c55e"},
    "putin":{"ideology":"Nationalist","party":"United Russia","clr":"#ef4444"},
    "netanyahu":{"ideology":"Right-wing","party":"Likud","clr":"#3b82f6"},
    "modi":{"ideology":"Nationalist","party":"BJP","clr":"#f97316"},
    "starmer":{"ideology":"Center-left","party":"Labour","clr":"#ef4444"},
    "sunak":{"ideology":"Conservative","party":"Conservative","clr":"#3b82f6"},
    "erdogan":{"ideology":"Islamist","party":"AKP","clr":"#ef4444"},
    "carney":{"ideology":"Center","party":"Liberal","clr":"#60a5fa"},
    "poilievre":{"ideology":"Conservative","party":"CPC","clr":"#3b82f6"},
    "albanese":{"ideology":"Center-left","party":"ALP","clr":"#ef4444"},
    "sheinbaum":{"ideology":"Left-wing","party":"Morena","clr":"#ef4444"},
    "wilders":{"ideology":"Right-wing","party":"PVV","clr":"#ef4444"},
    "maduro":{"ideology":"Socialist","party":"PSUV","clr":"#ef4444"},
}
ELECTION_KW = ["election","president","prime minister","chancellor","who will win","will win the","win the","party win","ballot","referendum","will be elected"]
def is_election(title):
    t = title.lower()
    return any(k in t for k in ELECTION_KW)

def build_elections(events):
    res = []
    for ev in events:
        if not is_election(ev["title"]): continue
        country = ev.get("country") or "INTL"
        prob_data = []
        if ev.get("outcomes_data"):
            for od in ev["outcomes_data"][:1]:
                for name, prob in od.get("pairs",[]):
                    if prob > 0.01:
                        cp = next(((k,v) for k,v in CANDIDATE_PROFILES.items() if k in name.lower()), None)
                        prob_data.append({"name":name,"prob":prob,"profile":cp[1] if cp else None})
        res.append({"title":ev["title"],"country":country,"cname":COUNTRY_NAMES.get(country,country),
                    "volume":ev["volume"],"end_date":ev["end_date"],"candidates":prob_data})
    res.sort(key=lambda x: x["volume"], reverse=True)
    return res

def build_map_data(events):
    by_country = defaultdict(lambda: {"count":0,"volume":0.0,"markets":[]})
    for ev in events:
        iso = ev.get("country")
        if not iso: continue
        cat = ev.get("category","Other")
        by_country[iso]["count"]  += 1
        by_country[iso]["volume"] += ev["volume"]
        if cat in MAP_CATEGORIES:
            by_country[iso]["markets"].append({
                "title": ev["title"][:88], "vol": fmt_usd(ev["volume"]),
                "cat": cat, "end": fmt_date(ev["end_date"]), "prob": _get_top_prob(ev),
            })
    return dict(by_country)


# ── MAIN WRITER ──────────────────────────────────────────────────────────────

def write_dashboard(events, out_path):
    now_str = TODAY.strftime("%b %d %Y, %H:%M UTC")
    n = len(events)
    total_vol = sum(e["volume"] for e in events)
    total_oi  = sum(e["open_interest"] for e in events)

    qa_pass   = sum(1 for e in events if e["qa_grade"]=="PASS")
    qa_review = sum(1 for e in events if e["qa_grade"]=="REVIEW")
    qa_fail   = sum(1 for e in events if e["qa_grade"]=="FAIL")
    qa_res    = sum(1 for e in events if e["qa_grade"]=="RESOLVED")
    int_high  = sum(1 for e in events if e["int_level"]=="HIGH")
    int_med   = sum(1 for e in events if e["int_level"]=="MEDIUM")
    comp_high = sum(1 for e in events if e["comp_level"]=="HIGH")
    comp_med  = sum(1 for e in events if e["comp_level"]=="MEDIUM")
    comp_low  = sum(1 for e in events if e["comp_level"]=="LOW")

    # Resolution queue
    rq_overdue, rq_upcoming = build_resolution_queue(events)
    rq = rq_overdue + rq_upcoming
    rq_today     = [x for x in rq_upcoming if x["hours_left"] < 24]
    rq_tomorrow  = [x for x in rq_upcoming if 24 <= x["hours_left"] < 72]
    rq_week      = [x for x in rq_upcoming if 72 <= x["hours_left"] <= 30*24]
    rq_contested = [x for x in rq if x["is_contested"]]
    rq_no_source = [x for x in rq_overdue if not x["has_source"]]

    # Category chart
    cat_vol = defaultdict(float); cat_cnt = defaultdict(int)
    for e in events:
        cat_vol[e["category"]] += e["volume"]
        cat_cnt[e["category"]] += 1
    top_cats = sorted(cat_vol.items(), key=lambda x: x[1], reverse=True)[:8]
    chart_labels = json.dumps([c[0].replace("Science, Health & Env.","Sci/Health") for c,_ in top_cats])
    chart_vols   = json.dumps([round(cat_vol[c]/1e6, 1) for c,_ in top_cats])

    # Map
    map_data = build_map_data(events)
    isos     = list(map_data.keys())
    counts   = [map_data[i]["count"] for i in isos]
    volumes  = [map_data[i]["volume"] for i in isos]
    names    = [COUNTRY_NAMES.get(i,i) for i in isos]
    log_counts  = [round(math.log10(v+1),3) for v in counts]
    log_volumes = [round(math.log10(v/1e4+1),3) for v in volumes]
    popup_data  = {iso:{"name":COUNTRY_NAMES.get(iso,iso),"count":d["count"],
                        "volume":fmt_usd(d["volume"]),"markets":d["markets"][-15:]}
                   for iso,d in map_data.items()}

    # Elections
    elec_markets = build_elections(events)
    by_country_e = defaultdict(list)
    for em in elec_markets: by_country_e[em["country"]].append(em)

    # Tables
    daily_sorted = sorted(events, key=lambda x: x["volume"], reverse=True)
    qa_issues    = sorted([e for e in events if e["qa_grade"] in ("FAIL","REVIEW")], key=lambda x: x["qa_score"])
    comp_flagged = sorted([e for e in events if e["comp_level"] in ("HIGH","MEDIUM")], key=lambda x: x["comp_score"])

    # ── WRITE HTML ──────────────────────────────────────────────────────
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Polymarket Ops Intelligence</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#060d1a;--bg2:#0d1827;--bg3:#111e30;--bg4:#1a2744;--border:#1e3a5f;--text:#e2e8f0;--muted:#64748b;--blue:#3b82f6;--green:#22c55e;--yellow:#f59e0b;--red:#ef4444;--purple:#a855f7;--cyan:#22d3ee;--orange:#f97316}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px}
.hdr{background:linear-gradient(90deg,#0a1628,#060d1a);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between}
.hdr h1{font-size:16px;font-weight:700;color:#fff}.hdr h1 em{color:var(--blue);font-style:normal}
.hdr-r{display:flex;gap:14px;align-items:center}
.live{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.hdr-meta{font-size:11px;color:var(--muted)}
/* BRIEF BANNER */
.brief{background:var(--bg2);border-bottom:1px solid var(--border);padding:10px 24px;display:flex;gap:20px;align-items:center;overflow-x:auto}
.brief-item{display:flex;align-items:center;gap:7px;white-space:nowrap;font-size:12px;color:var(--muted)}
.brief-item .n{font-size:15px;font-weight:700;color:#fff}
.brief-item .n.red{color:var(--red)}.brief-item .n.yellow{color:var(--yellow)}.brief-item .n.green{color:var(--green)}.brief-item .n.purple{color:var(--purple)}
.brief-div{width:1px;height:24px;background:var(--border)}
/* TABS */
.tabs{display:flex;gap:0;background:var(--bg2);border-bottom:1px solid var(--border);overflow-x:auto;padding:0 24px}
.tab{padding:10px 16px;cursor:pointer;font-size:12px;font-weight:500;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap;transition:all .15s}
.tab:hover{color:var(--text)}.tab.on{color:var(--blue);border-bottom-color:var(--blue);background:rgba(59,130,246,.06)}
/* PANES */
.pane{display:none;padding:20px 24px}.pane.on{display:block}
/* KPI */
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:20px}
.kpi{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px 16px}
.kpi .v{font-size:24px;font-weight:700;color:#fff;line-height:1}
.kpi .l{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-top:5px}
.kpi .s{font-size:10px;color:#94a3b8;margin-top:4px}
/* CHARTS */
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}
.cc{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px}
.cc h3{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px}
.cw{position:relative;height:200px}
/* RESOLUTION QUEUE */
.rq-filters{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.rq-btn{background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:5px 12px;border-radius:20px;cursor:pointer;font-size:11px;transition:all .15s}
.rq-btn:hover{color:var(--text)}.rq-btn.on{border-color:var(--blue);color:var(--blue);background:rgba(59,130,246,.1)}
.rq-card{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:10px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:start;transition:border-color .15s}
.rq-card:hover{border-color:#334155}
.rq-card.urgent{border-left:3px solid var(--red)}
.rq-card.today{border-left:3px solid var(--yellow)}
.rq-card.week{border-left:3px solid var(--blue)}
.rq-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:6px;line-height:1.4}
.rq-cat{font-size:10px;color:var(--muted);margin-bottom:8px}
.rq-checks{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.rq-check{font-size:10px;padding:1px 6px;border-radius:3px;font-weight:600}
.chk-ok{background:#22c55e12;color:#22c55e;border:1px solid #22c55e28}
.chk-warn{background:#f59e0b12;color:#f59e0b;border:1px solid #f59e0b28}
.chk-err{background:#ef444412;color:#ef4444;border:1px solid #ef444428}
.rq-right{text-align:right;min-width:110px}
.rq-timer{font-size:20px;font-weight:700;line-height:1}
.rq-timer.red{color:var(--red)}.rq-timer.yellow{color:var(--yellow)}.rq-timer.blue{color:var(--blue)}
.rq-vol{font-size:11px;color:var(--muted);margin-top:3px}
.rq-conf{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-top:6px}
.rq-prob{font-size:12px;color:#94a3b8;margin-top:4px}
/* TABLES */
.tbl-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.tbl-hdr h3{font-size:13px;font-weight:600}
.srch{background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:5px 11px;font-size:12px;width:200px;outline:none}
.srch::placeholder{color:var(--muted)}.srch:focus{border-color:var(--blue)}
.tbl-wrap{border:1px solid var(--border);border-radius:8px;overflow:hidden;overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{background:#09142a;color:var(--muted);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:8px 12px;text-align:left;white-space:nowrap;cursor:pointer;user-select:none}
th:hover{color:var(--text)}th.srt{color:var(--blue)}
td{padding:9px 12px;border-top:1px solid #0d1827;vertical-align:middle}
tr:hover td{background:#0d1827}
.mt{font-weight:500;max-width:300px;color:var(--text)}
.mt small{display:block;color:var(--muted);font-size:10px;margin-top:1px;font-weight:400}
.b{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;white-space:nowrap}
.b-g{background:#22c55e18;color:#22c55e;border:1px solid #22c55e30}
.b-y{background:#f59e0b18;color:#f59e0b;border:1px solid #f59e0b30}
.b-r{background:#ef444418;color:#ef4444;border:1px solid #ef444430}
.b-p{background:#a855f718;color:#a855f7;border:1px solid #a855f730}
.b-m{background:#94a3b818;color:#94a3b8;border:1px solid #94a3b830}
.b-b{background:#3b82f618;color:#3b82f6;border:1px solid #3b82f630}
.b-o{background:#f9731618;color:#f97316;border:1px solid #f9731630}
.flags{display:flex;flex-wrap:wrap;gap:3px}
.fc{font-size:9px;background:#ef444410;color:#f87171;border:1px solid #ef444428;padding:1px 5px;border-radius:3px}
.ok{font-size:9px;background:#22c55e10;color:#4ade80;border:1px solid #22c55e28;padding:1px 5px;border-radius:3px}
/* ELECTIONS */
.e-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(295px,1fr));gap:12px}
.e-card{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px}
.e-card .ec{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px}
.e-card .et{font-size:12px;font-weight:600;color:var(--text);margin-bottom:11px;line-height:1.4}
.crow{display:flex;align-items:center;gap:7px;margin-bottom:5px}
.cn{font-size:11px;font-weight:600;min-width:80px;color:var(--text)}
.cbw{flex:1;background:#060d1a;border-radius:3px;height:18px;overflow:hidden}
.cb{height:100%;display:flex;align-items:center;padding-left:6px;font-size:9px;font-weight:700;color:#fff;min-width:24px;border-radius:3px}
.cpct{font-size:10px;color:var(--muted);min-width:30px;text-align:right}
.ctags{display:flex;gap:3px;margin-bottom:3px}
.ctag{font-size:9px;padding:1px 4px;border-radius:2px;font-weight:600}
.ef{display:flex;justify-content:space-between;margin-top:8px;font-size:10px;color:#475569;border-top:1px solid #1a2744;padding-top:7px}
/* MAP */
#map-wrap{display:flex;gap:14px;min-height:520px}
#pm{flex:1}
#mp{width:310px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px;display:none;flex-direction:column;max-height:580px}
#mp.on{display:flex}
.mp-cn{font-size:14px;font-weight:700;color:#fff;margin-bottom:2px}
.mp-st{font-size:11px;color:var(--muted);margin-bottom:10px}
.mp-mkts{overflow-y:auto;flex:1}
.pmk{background:#09142a;border-radius:6px;padding:8px;margin-bottom:6px;border:1px solid var(--border)}
.pmk-t{font-size:11px;font-weight:600;color:var(--text);margin-bottom:3px}
.pmk-m{display:flex;gap:6px;flex-wrap:wrap;font-size:10px;color:var(--muted)}
.pmk-p{color:var(--green);font-weight:600}
.emp{color:var(--muted);font-size:12px;text-align:center;padding:30px 0}
.close-mp{float:right;cursor:pointer;color:var(--muted);font-size:16px;line-height:1}.close-mp:hover{color:#fff}
.map-btns{margin-top:10px;display:flex;gap:8px}
.mbtn{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:5px 12px;border-radius:6px;cursor:pointer;font-size:11px;transition:border-color .15s}
.mbtn.on{border-color:var(--blue);color:var(--blue)}
.mini-bar-w{height:3px;background:#1e293b;border-radius:2px;margin-top:3px}
.mini-bar{height:100%;border-radius:2px;background:var(--blue)}
</style></head><body>
""")

        # HEADER
        f.write(f"""<div class="hdr">
  <div style="display:flex;align-items:center;gap:10px">
    <div class="live"></div>
    <h1>Polymarket <em>Ops Intelligence</em> <span style="font-size:11px;color:var(--muted);font-weight:400">v5</span></h1>
  </div>
  <div class="hdr-r">
    <span class="hdr-meta">{n} markets · {fmt_usd(total_vol)} total volume · {now_str}</span>
  </div>
</div>
""")

        # TODAY'S BRIEF BANNER
        f.write(f"""<div class="brief">
  <span style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px">Today's Brief</span>
  <div class="brief-div"></div>
  <div class="brief-item"><span class="n {'red' if rq_overdue else 'green'}">{len(rq_overdue)}</span> pending resolution</div>
  <div class="brief-div"></div>
  <div class="brief-item"><span class="n {'yellow' if rq_upcoming else 'green'}">{len(rq_upcoming)}</span> expiring soon</div>
  <div class="brief-div"></div>
  <div class="brief-item"><span class="n {'yellow' if rq_contested else 'green'}">{len(rq_contested)}</span> contested outcomes</div>
  <div class="brief-div"></div>
  <div class="brief-item"><span class="n {'red' if qa_fail else 'green'}">{qa_fail}</span> QA failures</div>
  <div class="brief-div"></div>
  <div class="brief-item"><span class="n {'purple' if comp_high else 'muted'}">{comp_high}</span> compliance flags</div>
  <div class="brief-div"></div>
  <div class="brief-item"><span class="n {'yellow' if int_high else 'green'}">{int_high}</span> integrity alerts</div>
</div>
""")

        # TABS
        f.write("""<div class="tabs">
  <div class="tab on" data-t="t0" onclick="showTab('t0')">📋 Resolution Queue</div>
  <div class="tab" data-t="t1" onclick="showTab('t1')">📊 Overview</div>
  <div class="tab" data-t="t2" onclick="showTab('t2')">🗺️ World Map</div>
  <div class="tab" data-t="t3" onclick="showTab('t3')">🗳️ Elections</div>
  <div class="tab" data-t="t4" onclick="showTab('t4')">📁 All Markets</div>
  <div class="tab" data-t="t5" onclick="showTab('t5')">🔍 Listing QA</div>
  <div class="tab" data-t="t6" onclick="showTab('t6')">⚖️ Compliance</div>
</div>
""")

        # ═══════════════════════════════════════════════════════════
        # TAB 0 — RESOLUTION QUEUE  (first tab — the daily ops tool)
        # ═══════════════════════════════════════════════════════════
        f.write('<div id="t0" class="pane on">\n')
        f.write(f"""<p style="color:var(--muted);font-size:12px;margin-bottom:14px">
  Daily resolution workflow: <strong style="color:var(--red)">{len(rq_overdue)} markets need resolution</strong> (expired, awaiting decision) ·
  <strong style="color:var(--yellow)">{len(rq_upcoming)} expiring soon</strong> (next 30 days, prep criteria) ·
  <span style="color:var(--muted)">{len(rq_contested)} contested · {len(rq_no_source)} missing source</span>
</p>
""")
        # Filter buttons
        f.write("""<div class="rq-filters">
  <button class="rq-btn on" onclick="rqFilter('all',this)">All</button>
  <button class="rq-btn" onclick="rqFilter('overdue',this)">🔴 Needs Resolution</button>
  <button class="rq-btn" onclick="rqFilter('upcoming',this)">📅 Expiring Soon</button>
  <button class="rq-btn" onclick="rqFilter('contested',this)">⚠️ Contested</button>
  <button class="rq-btn" onclick="rqFilter('nosource',this)">🔗 Missing Source</button>
</div>
<div id="rq-list">
""")

        def write_rq_card(f, item):
            ev = item["ev"]
            h  = item["hours_left"]
            bucket = item.get("bucket","upcoming")
            if bucket == "overdue":
                card_cls = "urgent"; timer_cls = "red"
                days_since = abs(h) / 24
                timer_str = f"{days_since:.0f}d ago" if days_since >= 1 else f"{abs(h):.0f}h ago"
                pri_badge = '<span class="b b-r">NEEDS RESOLUTION</span>'
            elif h < 72:
                card_cls = "today"; timer_cls = "yellow"; pri_badge = '<span class="b b-y">URGENT</span>'
                timer_str = f"{h:.0f}h"
            else:
                card_cls = "week"; timer_cls = "blue"; pri_badge = '<span class="b b-b">EXPIRING SOON</span>'
                timer_str = f"{h/24:.0f}d"

            conf_clr = item["conf_clr"]
            conf_html = f'<span class="rq-conf" style="background:{conf_clr}18;color:{conf_clr};border:1px solid {conf_clr}30">{esc(item["conf"])}</span>'

            prob_html = ""
            if item["implied_yes"] is not None:
                pct = int(item["implied_yes"] * 100)
                bar_clr = "#22c55e" if pct >= 80 else "#ef4444" if pct <= 20 else "#f59e0b"
                prob_html = f'<div style="margin-top:8px"><div style="font-size:10px;color:var(--muted);margin-bottom:3px">Market-implied outcome</div><div style="background:#060d1a;border-radius:4px;height:18px;overflow:hidden"><div style="height:100%;width:{pct}%;background:linear-gradient(90deg,{bar_clr},{bar_clr}aa);display:flex;align-items:center;padding:0 6px;font-size:10px;font-weight:700;color:#fff;min-width:30px">{pct}% YES</div></div></div>'
            elif item["top_outcome"] and item["top_prob"]:
                pct = int(item["top_prob"] * 100)
                prob_html = f'<div style="margin-top:8px"><div style="font-size:10px;color:var(--muted);margin-bottom:3px">Leading outcome</div><div style="background:#060d1a;border-radius:4px;height:18px;overflow:hidden"><div style="height:100%;width:{pct}%;background:linear-gradient(90deg,#3b82f6,#3b82f6aa);display:flex;align-items:center;padding:0 6px;font-size:10px;font-weight:700;color:#fff;min-width:30px">{esc(item["top_outcome"][:22])} {pct}%</div></div></div>'

            checks = []
            if item["has_source"]:  checks.append('<span class="rq-check chk-ok">✓ Source URL</span>')
            else:                   checks.append('<span class="rq-check chk-err">✗ No source</span>')
            if item["desc_ok"]:     checks.append('<span class="rq-check chk-ok">✓ Description</span>')
            else:                   checks.append('<span class="rq-check chk-warn">⚠ Thin desc</span>')
            if item["is_contested"]: checks.append('<span class="rq-check chk-warn">⚠ Contested</span>')
            if ev.get("qa_grade") == "FAIL": checks.append('<span class="rq-check chk-err">✗ QA fail</span>')
            if ev.get("ps_whale_count") and ev["ps_whale_count"] > 5:
                checks.append(f'<span class="rq-check chk-warn">🐋 {ev["ps_whale_count"]} whales</span>')
            checks_html = " ".join(checks)

            data_attrs = (f'data-bucket="{bucket}" data-contested="{"1" if item["is_contested"] else "0"}" '
                          f'data-nosource="{"1" if not item["has_source"] else "0"}"')
            cat_s   = esc(ev.get("category",""))
            title_s = esc(ev["title"][:90] + ("…" if len(ev["title"])>90 else ""))
            vol_s   = fmt_usd(ev["volume"])

            f.write(f'<div class="rq-card {card_cls}" {data_attrs}>\n')
            f.write(f'  <div><div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">{pri_badge} <span class="b b-m" style="font-size:9px">{cat_s}</span></div>')
            f.write(f'  <div class="rq-title">{title_s}</div>')
            f.write(f'  {prob_html}')
            f.write(f'  <div class="rq-checks">{checks_html}</div>')
            f.write(f'  </div>')
            f.write(f'  <div class="rq-right"><div class="rq-timer {timer_cls}">{timer_str}</div><div class="rq-vol">{vol_s} vol</div>{conf_html}</div>')
            f.write(f'</div>\n')

        if rq_overdue:
            f.write(f'<div style="font-size:11px;font-weight:600;color:var(--red);text-transform:uppercase;letter-spacing:.5px;padding:8px 0 6px">🔴 Needs Resolution — {len(rq_overdue)} markets</div>\n')
            for item in rq_overdue[:50]:
                write_rq_card(f, item)

        if rq_upcoming:
            f.write(f'<div style="font-size:11px;font-weight:600;color:var(--yellow);text-transform:uppercase;letter-spacing:.5px;padding:14px 0 6px">📅 Expiring Soon — {len(rq_upcoming)} markets</div>\n')
            for item in rq_upcoming:
                write_rq_card(f, item)

        if not rq:
            f.write('<div style="color:var(--muted);text-align:center;padding:40px">No markets require resolution action right now.</div>\n')
        f.write('</div>\n</div>\n')  # end rq-list, end t0

        # ═══════════════════════════════════════════════════════════
        # TAB 1 — OVERVIEW
        # ═══════════════════════════════════════════════════════════
        f.write('<div id="t1" class="pane">\n')
        f.write(f"""<div class="kpis">
  <div class="kpi"><div class="v">{n}</div><div class="l">Markets Monitored</div></div>
  <div class="kpi"><div class="v">{fmt_usd(total_vol)}</div><div class="l">Total Volume</div></div>
  <div class="kpi"><div class="v">{fmt_usd(total_oi)}</div><div class="l">Open Interest</div></div>
  <div class="kpi"><div class="v" style="color:var(--red)">{len(rq_overdue)}</div><div class="l">Needs Resolution</div><div class="s">{len(rq_upcoming)} expiring soon</div></div>
  <div class="kpi"><div class="v" style="color:var(--yellow)">{len(rq_contested)}</div><div class="l">Contested Outcomes</div><div class="s">Outcome not clear-cut</div></div>
  <div class="kpi"><div class="v" style="color:var(--red)">{qa_fail}</div><div class="l">QA Failures</div><div class="s">{qa_review} under review</div></div>
  <div class="kpi"><div class="v" style="color:var(--yellow)">{int_high}</div><div class="l">Integrity Alerts</div><div class="s">{int_med} medium</div></div>
  <div class="kpi"><div class="v" style="color:var(--purple)">{comp_high}</div><div class="l">Compliance Flags</div><div class="s">{comp_med} medium</div></div>
</div>
""")
        f.write('<div class="charts-row">\n')
        f.write(f'  <div class="cc"><h3>Volume by Category ($M)</h3><div class="cw"><canvas id="catChart"></canvas></div></div>\n')
        f.write(f'  <div class="cc"><h3>Risk Distribution</h3><div class="cw"><canvas id="riskChart"></canvas></div></div>\n')
        f.write('</div>\n')
        # Category table
        f.write('<div class="tbl-hdr"><h3>Category Breakdown</h3></div>\n')
        f.write('<div class="tbl-wrap"><table>\n')
        f.write('<thead><tr><th>Category</th><th>Markets</th><th>Volume</th><th>Avg/Market</th></tr></thead><tbody>\n')
        for cat,vol in top_cats:
            c = cat_cnt[cat]; avg = fmt_usd(vol/c) if c else "$0"
            pct = vol/total_vol*100 if total_vol else 0
            f.write(f'<tr><td class="mt">{esc(cat)}<div class="mini-bar-w"><div class="mini-bar" style="width:{min(pct,100):.0f}%"></div></div></td>'
                    f'<td>{c}</td><td>{fmt_usd(vol)}</td><td>{avg}</td></tr>\n')
        f.write('</tbody></table></div>\n</div>\n')

        # ═══════════════════════════════════════════════════════════
        # TAB 2 — WORLD MAP
        # ═══════════════════════════════════════════════════════════
        f.write('<div id="t2" class="pane">\n')
        f.write('<p style="color:var(--muted);font-size:12px;margin-bottom:14px">Click a country to see its political, economic &amp; geopolitical bets. Log scale — differences visible at all sizes.</p>\n')
        f.write('<div id="map-wrap"><div id="pm"></div>\n')
        f.write('<div id="mp"><div><span class="close-mp" onclick="closePanel()">✕</span>\n')
        f.write('<div class="mp-cn" id="mp-cn">—</div><div class="mp-st" id="mp-st"></div></div>\n')
        f.write('<div class="mp-mkts" id="mp-mkts"></div></div></div>\n')
        f.write('<div class="map-btns"><button class="mbtn on" id="btn-c" onclick="setLayer(\'count\')">Market Count</button>'
                '<button class="mbtn" id="btn-v" onclick="setLayer(\'volume\')">USD Volume</button></div>\n')

        popup_json = json.dumps(popup_data)
        f.write(f"""<script>
var ISO={json.dumps(isos)},CNT={json.dumps(counts)},VOL={json.dumps(volumes)};
var NMS={json.dumps(names)},LC={json.dumps(log_counts)},LV={json.dumps(log_volumes)};
var PD={popup_json},layer='count';
function renderMap(){{
  var z=layer==='count'?LC:LV;
  var txt=NMS.map(function(n,i){{return '<b>'+n+'</b><br>'+CNT[i]+' markets<br>$'+(VOL[i]/1e6).toFixed(1)+'M vol';}});
  Plotly.react('pm',[{{type:'choropleth',locations:ISO,z:z,text:txt,hoverinfo:'text',
    locationmode:'ISO-3',
    colorscale:[[0,'#090f1e'],[0.1,'#0d1f40'],[0.3,'#1a3a6b'],[0.5,'#1d4ed8'],[0.75,'#3b82f6'],[1,'#93c5fd']],
    showscale:true,zmin:0,zmax:Math.max.apply(null,z)*1.05,
    colorbar:{{title:layer==='count'?'Markets':'Vol',titlefont:{{color:'#64748b',size:10}},
      tickfont:{{color:'#64748b',size:9}},bgcolor:'#0d1827',bordercolor:'#1e3a5f',len:0.5,thickness:11}}
  }}],{{
    paper_bgcolor:'#060d1a',plot_bgcolor:'#060d1a',
    geo:{{showframe:false,showcoastlines:true,coastlinecolor:'#1e3a5f',showland:true,
      landcolor:'#0d1827',showocean:true,oceancolor:'#060d1a',
      showcountries:true,countrycolor:'#1e3a5f',showlakes:false,
      bgcolor:'#060d1a',projection:{{type:'natural earth'}}}},
    margin:{{t:0,b:0,l:0,r:0}},height:500
  }},{{responsive:true,displayModeBar:false}});
  document.getElementById('pm').on('plotly_click',function(d){{openPanel(d.points[0].location);}});
}}
function openPanel(iso){{
  var i=PD[iso];if(!i)return;
  document.getElementById('mp-cn').textContent=i.name;
  document.getElementById('mp-st').textContent=i.count+' total · '+i.volume;
  var h='';
  if(!i.markets||!i.markets.length){{h='<div class="emp">No political/economic<br>markets for this country.</div>';}}
  else{{i.markets.forEach(function(m){{
    var cc=m.cat==='Politics & Elections'?'#a855f7':m.cat==='Geopolitics & World Affairs'?'#ef4444':'#3b82f6';
    var pr=m.prob?'<span class="pmk-p">'+m.prob+'</span>':'';
    h+='<div class="pmk"><div class="pmk-t">'+m.title+'</div>'+
      '<div class="pmk-m"><span style="color:'+cc+'">'+m.cat+'</span>'+
      '<span>'+m.vol+'</span><span>exp '+m.end+'</span>'+pr+'</div></div>';
  }});}}
  document.getElementById('mp-mkts').innerHTML=h;
  document.getElementById('mp').classList.add('on');
}}
function closePanel(){{document.getElementById('mp').classList.remove('on');}}
function setLayer(l){{
  layer=l;
  document.getElementById('btn-c').classList.toggle('on',l==='count');
  document.getElementById('btn-v').classList.toggle('on',l==='volume');
  renderMap();
}}
document.querySelector('[data-t="t2"]').addEventListener('click',function(){{setTimeout(renderMap,80);}});
</script>
""")
        f.write('</div>\n')

        # ═══════════════════════════════════════════════════════════
        # TAB 3 — ELECTIONS
        # ═══════════════════════════════════════════════════════════
        f.write('<div id="t3" class="pane">\n')
        f.write(f'<p style="color:var(--muted);font-size:12px;margin-bottom:14px">{len(elec_markets)} political markets · bars show current betting probability (implied market odds).</p>\n')
        f.write('<div class="e-grid">\n')
        shown = 0
        for country, markets in sorted(by_country_e.items(), key=lambda x: sum(m["volume"] for m in x[1]), reverse=True):
            for em in markets[:3]:
                shown += 1
                if shown > 60: break
                cands_html = ""
                if em["candidates"]:
                    for c in sorted(em["candidates"], key=lambda x: x["prob"], reverse=True)[:5]:
                        pct = int(c["prob"]*100)
                        prof = c.get("profile") or {}
                        clr = prof.get("clr","#3b82f6")
                        ideo = prof.get("ideology",""); party = prof.get("party","")
                        tags = ""
                        if ideo:  tags += f'<span class="ctag" style="background:{clr}22;color:{clr}">{esc(ideo)}</span>'
                        if party: tags += f'<span class="ctag" style="background:#111e30;color:#64748b">{esc(party)}</span>'
                        cands_html += (f'<div class="crow"><div class="cn">{esc(c["name"][:15])}</div>'
                                       f'<div class="cbw"><div class="cb" style="width:{max(pct,8)}%;background:linear-gradient(90deg,{clr}cc,{clr}55)">{pct}%</div></div>'
                                       f'<div class="cpct">{pct}%</div></div><div class="ctags">{tags}</div>')
                else:
                    cands_html = '<div style="color:var(--muted);font-size:11px">No probability data</div>'
                f.write(f'<div class="e-card"><div class="ec">{esc(COUNTRY_NAMES.get(em["country"],em["country"]))}</div>'
                        f'<div class="et">{esc(em["title"][:72])}</div>{cands_html}'
                        f'<div class="ef"><span>Vol: {fmt_usd(em["volume"])}</span><span>Exp: {fmt_date(em["end_date"])}</span></div></div>\n')
        if shown == 0: f.write('<div style="color:var(--muted)">No election markets found.</div>\n')
        f.write('</div>\n</div>\n')

        # ═══════════════════════════════════════════════════════════
        # TAB 4 — ALL MARKETS (Daily Ops)
        # ═══════════════════════════════════════════════════════════
        f.write('<div id="t4" class="pane">\n')
        f.write('<div class="tbl-hdr"><h3>All Active Markets</h3>'
                '<input class="srch" placeholder="🔍 Search…" oninput="filterTbl(\'ops\',this.value)"></div>\n')
        f.write('<div class="tbl-wrap"><table id="tbl-ops">\n')
        f.write('<thead><tr><th onclick="srt(\'tbl-ops\',0)">Market</th>'
                '<th onclick="srt(\'tbl-ops\',1)">Volume ↕</th>'
                '<th onclick="srt(\'tbl-ops\',2)">24h ↕</th>'
                '<th onclick="srt(\'tbl-ops\',3)">Liquidity ↕</th>'
                '<th onclick="srt(\'tbl-ops\',4)">Expires ↕</th>'
                '<th onclick="srt(\'tbl-ops\',5)">Risk</th>'
                '</tr></thead><tbody>\n')
        for ev in daily_sorted[:200]:
            ti  = esc(ev["title"][:68] + ("…" if len(ev["title"])>68 else ""))
            cat = esc(ev.get("category",""))
            end = ev["end_date"]
            exp_s  = fmt_date(end)
            exp_ts = end.timestamp() if end else 1e12
            h_left = (end - TODAY).total_seconds()/3600 if end else 9999
            exp_cls = "style='color:var(--red);font-weight:600'" if h_left < 24 else "style='color:var(--yellow)'" if h_left < 72 else ""
            lvl = ev["ops_level"]
            bcl = {"LOW":"b-g","MEDIUM":"b-y","HIGH":"b-r","CRITICAL":"b-r"}.get(lvl,"b-m")
            f.write(f'<tr data-search="{ti.lower()}">'
                    f'<td class="mt">{ti}<small>{cat}</small></td>'
                    f'<td data-val="{ev["volume"]}">{fmt_usd(ev["volume"])}</td>'
                    f'<td data-val="{ev["volume_24h"]}">{fmt_usd(ev["volume_24h"])}</td>'
                    f'<td data-val="{ev["liquidity"]}">{fmt_usd(ev["liquidity"])}</td>'
                    f'<td data-val="{exp_ts}"><span {exp_cls}>{exp_s}</span></td>'
                    f'<td><span class="b {bcl}">{lvl}</span></td></tr>\n')
        f.write('</tbody></table></div>\n</div>\n')

        # ═══════════════════════════════════════════════════════════
        # TAB 5 — LISTING QA
        # ═══════════════════════════════════════════════════════════
        f.write('<div id="t5" class="pane">\n')
        f.write(f"""<div class="kpis" style="margin-bottom:16px">
  <div class="kpi"><div class="v" style="color:var(--green)">{qa_pass}</div><div class="l">PASS</div></div>
  <div class="kpi"><div class="v" style="color:var(--yellow)">{qa_review}</div><div class="l">REVIEW</div></div>
  <div class="kpi"><div class="v" style="color:var(--red)">{qa_fail}</div><div class="l">FAIL</div></div>
  <div class="kpi"><div class="v" style="color:var(--muted)">{qa_res}</div><div class="l">RESOLVED</div><div class="s">Correctly excluded</div></div>
</div>
""")
        f.write('<div class="tbl-hdr"><h3>Markets Needing QA Attention</h3>'
                '<input class="srch" placeholder="🔍 Search…" oninput="filterTbl(\'qa\',this.value)"></div>\n')
        f.write('<div class="tbl-wrap"><table id="tbl-qa">\n')
        f.write('<thead><tr><th onclick="srt(\'tbl-qa\',0)">Market</th>'
                '<th onclick="srt(\'tbl-qa\',1)">Score ↕</th>'
                '<th>Issues</th>'
                '<th onclick="srt(\'tbl-qa\',3)">PS Arb ↕</th>'
                '<th onclick="srt(\'tbl-qa\',4)">Volume ↕</th>'
                '</tr></thead><tbody>\n')
        for ev in qa_issues[:100]:
            ti  = esc(ev["title"][:62] + ("…" if len(ev["title"])>62 else ""))
            cat = esc(ev.get("category",""))
            bcl = "b-r" if ev["qa_grade"]=="FAIL" else "b-y"
            fh  = "".join(f'<span class="fc">{esc(fl)}</span>' for fl in ev["qa_flags"]) or '<span class="ok">✓ OK</span>'
            arb = ev.get("ps_rules_arb")
            arb_s = f'<span style="color:{"#ef4444" if arb and arb>50 else "#f59e0b" if arb and arb>25 else "#22c55e"}">{arb}</span>' if arb is not None else '<span style="color:var(--muted)">—</span>'
            f.write(f'<tr data-search="{ti.lower()}">'
                    f'<td class="mt">{ti}<small>{cat}</small></td>'
                    f'<td data-val="{ev["qa_score"]}"><span class="b {bcl}">{ev["qa_grade"]}</span> {ev["qa_score"]}</td>'
                    f'<td><div class="flags">{fh}</div></td>'
                    f'<td data-val="{arb or 0}">{arb_s}</td>'
                    f'<td data-val="{ev["volume"]}">{fmt_usd(ev["volume"])}</td></tr>\n')
        f.write('</tbody></table></div>\n</div>\n')

        # ═══════════════════════════════════════════════════════════
        # TAB 6 — COMPLIANCE
        # ═══════════════════════════════════════════════════════════
        f.write('<div id="t6" class="pane">\n')
        f.write(f"""<div class="kpis" style="margin-bottom:16px">
  <div class="kpi"><div class="v" style="color:var(--red)">{comp_high}</div><div class="l">HIGH Risk</div></div>
  <div class="kpi"><div class="v" style="color:var(--yellow)">{comp_med}</div><div class="l">MEDIUM</div></div>
  <div class="kpi"><div class="v" style="color:var(--green)">{comp_low}</div><div class="l">LOW / Clear</div></div>
</div>
""")
        f.write('<div class="tbl-hdr"><h3>Flagged Markets</h3>'
                '<input class="srch" placeholder="🔍 Search…" oninput="filterTbl(\'comp\',this.value)"></div>\n')
        f.write('<div class="tbl-wrap"><table id="tbl-comp">\n')
        f.write('<thead><tr><th onclick="srt(\'tbl-comp\',0)">Market</th>'
                '<th onclick="srt(\'tbl-comp\',1)">Risk ↕</th>'
                '<th>Flags</th>'
                '<th onclick="srt(\'tbl-comp\',3)">Volume ↕</th>'
                '</tr></thead><tbody>\n')
        for ev in comp_flagged[:80]:
            ti  = esc(ev["title"][:62] + ("…" if len(ev["title"])>62 else ""))
            bcl = "b-r" if ev["comp_level"]=="HIGH" else "b-y"
            fh  = "".join(f'<span class="fc">{esc(fl)}</span>' for fl in ev["comp_flags"])
            f.write(f'<tr data-search="{ti.lower()}">'
                    f'<td class="mt">{ti}</td>'
                    f'<td data-val="{ev["comp_score"]}"><span class="b {bcl}">{ev["comp_level"]}</span></td>'
                    f'<td><div class="flags">{fh}</div></td>'
                    f'<td data-val="{ev["volume"]}">{fmt_usd(ev["volume"])}</td></tr>\n')
        f.write('</tbody></table></div>\n</div>\n')

        # ═══════════════════════════════════════════════════════════
        # SCRIPTS
        # ═══════════════════════════════════════════════════════════
        f.write(f"""<script>
function showTab(id){{
  document.querySelectorAll('.tab').forEach(function(t){{t.classList.toggle('on',t.dataset.t===id);}});
  document.querySelectorAll('.pane').forEach(function(p){{p.classList.toggle('on',p.id===id);}});
}}
function srt(tid,col){{
  var tbl=document.getElementById(tid);
  var rows=Array.from(tbl.querySelectorAll('tbody tr'));
  var dir=tbl.dataset.sc==col&&tbl.dataset.sd=='1'?-1:1;
  tbl.dataset.sc=col;tbl.dataset.sd=dir;
  tbl.querySelectorAll('th').forEach(function(th,i){{th.classList.toggle('srt',i==col);}});
  rows.sort(function(a,b){{
    var ac=a.cells[col],bc=b.cells[col];
    if(!ac||!bc)return 0;
    var av=ac.dataset.val||ac.innerText,bv=bc.dataset.val||bc.innerText;
    var an=parseFloat(av),bn=parseFloat(bv);
    if(!isNaN(an)&&!isNaN(bn))return dir*(an-bn);
    return dir*av.localeCompare(bv);
  }});
  var tb=tbl.querySelector('tbody');rows.forEach(function(r){{tb.appendChild(r);}});
}}
function filterTbl(name,q){{
  var tbl=document.getElementById('tbl-'+name);
  var lq=q.toLowerCase();
  tbl.querySelectorAll('tbody tr').forEach(function(r){{
    r.style.display=(!lq||r.dataset.search&&r.dataset.search.includes(lq))?'':'none';
  }});
}}
function rqFilter(type,btn){{
  document.querySelectorAll('.rq-btn').forEach(function(b){{b.classList.remove('on');}});
  btn.classList.add('on');
  document.querySelectorAll('.rq-card').forEach(function(c){{
    if(type==='all'){{c.style.display='';return;}}
    if(type==='overdue')   {{c.style.display=c.dataset.bucket==='overdue'?'':'none';return;}}
    if(type==='upcoming')  {{c.style.display=c.dataset.bucket==='upcoming'?'':'none';return;}}
    if(type==='contested') {{c.style.display=c.dataset.contested==='1'?'':'none';return;}}
    if(type==='nosource')  {{c.style.display=c.dataset.nosource==='1'?'':'none';return;}}
  }});
}}
// Chart.js category bar
(function(){{
  var ctx=document.getElementById('catChart');
  if(!ctx)return;
  new Chart(ctx,{{type:'bar',data:{{
    labels:{chart_labels},
    datasets:[{{label:'Volume ($M)',data:{chart_vols},
      backgroundColor:'rgba(59,130,246,0.75)',borderColor:'rgba(59,130,246,1)',
      borderWidth:1,borderRadius:3}}]
  }},options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:function(c){{return'$'+c.parsed.x+'M';}}}}}}}},
    scales:{{x:{{grid:{{color:'rgba(255,255,255,0.04)'}},ticks:{{color:'#64748b',font:{{size:9}}}},border:{{color:'#1e3a5f'}}}},
             y:{{grid:{{display:false}},ticks:{{color:'#94a3b8',font:{{size:9}}}},border:{{color:'#1e3a5f'}}}}}}
  }}}});
}})();
// Chart.js risk donut
(function(){{
  var ctx=document.getElementById('riskChart');if(!ctx)return;
  new Chart(ctx,{{type:'doughnut',data:{{
    labels:['QA Pass','QA Review','QA Fail','Integrity High','Compliance High'],
    datasets:[{{data:[{qa_pass},{qa_review},{qa_fail},{int_high},{comp_high}],
      backgroundColor:['rgba(34,197,94,.8)','rgba(245,158,11,.8)','rgba(239,68,68,.8)','rgba(168,85,247,.8)','rgba(34,211,238,.8)'],
      borderColor:'#060d1a',borderWidth:2}}]
  }},options:{{responsive:true,maintainAspectRatio:false,cutout:'60%',
    plugins:{{legend:{{position:'right',labels:{{color:'#94a3b8',font:{{size:9}},boxWidth:9,padding:9}}}},
              tooltip:{{callbacks:{{label:function(c){{return c.label+': '+c.parsed;}}}}}}}}
  }}}});
}})();
</script></body></html>
""")  

    print(f"  HTML size: {len(open(out_path).read())//1024} KB")
