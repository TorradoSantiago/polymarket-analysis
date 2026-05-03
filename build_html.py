"""HTML generation for Polymarket Ops Intelligence Dashboard v4"""
import json, math
from collections import defaultdict
from datetime import datetime, timezone

TODAY = datetime.now(timezone.utc)

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

def expiry_class(dt):
    if not dt: return ""
    h = (dt - TODAY).total_seconds() / 3600
    if h < 0: return "exp-over"
    if h < 24: return "exp-urgent"
    if h < 168: return "exp-soon"
    return ""

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

MAP_CATEGORIES = {"Politics & Elections", "Economics & Finance", "Geopolitics & World Affairs"}

def _get_top_prob(ev):
    if ev.get("outcomes_data"):
        od = ev["outcomes_data"][0]
        if od.get("pairs"):
            top = max(od["pairs"], key=lambda x: x[1])
            return f"{top[0]}: {top[1]*100:.0f}%"
    return ""

def build_map_data(events):
    by_country = defaultdict(lambda: {"count": 0, "volume": 0.0, "markets": []})
    for ev in events:
        iso = ev.get("country")
        if not iso: continue
        cat = ev.get("category","Other")
        by_country[iso]["count"]  += 1
        by_country[iso]["volume"] += ev["volume"]
        if cat in MAP_CATEGORIES:
            by_country[iso]["markets"].append({
                "title": ev["title"][:88],
                "vol":   fmt_usd(ev["volume"]),
                "cat":   cat,
                "end":   fmt_date(ev["end_date"]),
                "prob":  _get_top_prob(ev),
            })
    for iso in by_country:
        by_country[iso]["markets"].sort(key=lambda x: -ev["volume"] if False else 0)
    return dict(by_country)

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

def detect_candidates(title):
    t = title.lower()
    return [n for n in CANDIDATE_PROFILES if n in t]

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
        res.append({
            "title": ev["title"], "country": country,
            "cname": COUNTRY_NAMES.get(country, country),
            "volume": ev["volume"], "end_date": ev["end_date"],
            "candidates": prob_data,
        })
    res.sort(key=lambda x: x["volume"], reverse=True)
    return res


def write_dashboard(events, out_path):
    now_str = TODAY.strftime("%b %d %Y, %H:%M UTC")

    # ── stats ──
    total_vol  = sum(e["volume"] for e in events)
    total_oi   = sum(e["open_interest"] for e in events)
    n          = len(events)
    qa_pass    = sum(1 for e in events if e["qa_grade"]=="PASS")
    qa_review  = sum(1 for e in events if e["qa_grade"]=="REVIEW")
    qa_fail    = sum(1 for e in events if e["qa_grade"]=="FAIL")
    qa_res     = sum(1 for e in events if e["qa_grade"]=="RESOLVED")
    int_high   = sum(1 for e in events if e["int_level"]=="HIGH")
    comp_high  = sum(1 for e in events if e["comp_level"]=="HIGH")
    comp_med   = sum(1 for e in events if e["comp_level"]=="MEDIUM")
    int_med    = sum(1 for e in events if e["int_level"]=="MEDIUM")
    ops_high   = sum(1 for e in events if e["ops_level"] in ("HIGH","CRITICAL"))

    # ── category chart data ──
    cat_vol = defaultdict(float)
    cat_cnt = defaultdict(int)
    for e in events:
        cat_vol[e["category"]] += e["volume"]
        cat_cnt[e["category"]] += 1
    top_cats = sorted(cat_vol.items(), key=lambda x: x[1], reverse=True)[:8]
    chart_labels  = json.dumps([c[0].replace(" & ", " & ").replace(", Health & Env.", "") for c,_ in top_cats])
    chart_vols    = json.dumps([round(cat_vol[c]/1e6, 1) for c,_ in top_cats])
    chart_cnts    = json.dumps([cat_cnt[c] for c,_ in top_cats])

    # ── map ──
    map_data = build_map_data(events)
    isos     = list(map_data.keys())
    counts   = [map_data[i]["count"] for i in isos]
    volumes  = [map_data[i]["volume"] for i in isos]
    names    = [COUNTRY_NAMES.get(i, i) for i in isos]
    log_counts  = [round(math.log10(v+1), 3) for v in counts]
    log_volumes = [round(math.log10(v/1e4+1), 3) for v in volumes]
    popup_data  = {}
    for iso, d in map_data.items():
        popup_data[iso] = {
            "name": COUNTRY_NAMES.get(iso, iso),
            "count": d["count"],
            "volume": fmt_usd(d["volume"]),
            "markets": d["markets"][-15:],
        }

    # ── elections ──
    elec_markets = build_elections(events)
    by_country = defaultdict(list)
    for em in elec_markets:
        by_country[em["country"]].append(em)

    # ── tables ──
    daily_sorted  = sorted(events, key=lambda x: x["volume"], reverse=True)
    qa_issues     = sorted([e for e in events if e["qa_grade"] in ("FAIL","REVIEW")], key=lambda x: x["qa_score"])
    comp_flagged  = sorted([e for e in events if e["comp_level"] in ("HIGH","MEDIUM")], key=lambda x: x["comp_score"])

    # ────────────────────────────────────────────────────────────────────
    with open(out_path, "w", encoding="utf-8") as f:

        f.write("""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Polymarket Ops Intelligence</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0a0f1e;--bg2:#111827;--bg3:#1e293b;--border:#1e3a5f;--text:#e2e8f0;--muted:#64748b;--blue:#3b82f6;--green:#22c55e;--yellow:#f59e0b;--red:#ef4444;--purple:#a855f7;--cyan:#22d3ee}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;min-height:100vh}
/* HEADER */
.hdr{background:linear-gradient(90deg,#0d1b2e,#0a0f1e);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;justify-content:space-between}
.hdr h1{font-size:17px;font-weight:700;color:#fff;letter-spacing:-.3px}.hdr h1 em{color:var(--blue);font-style:normal}
.hdr-right{display:flex;gap:16px;align-items:center}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.hdr-meta{font-size:11px;color:var(--muted)}
/* TABS */
.tabs{display:flex;gap:2px;padding:0 24px;background:#0d1827;border-bottom:1px solid var(--border);overflow-x:auto}
.tab{padding:11px 16px;cursor:pointer;font-size:12px;font-weight:500;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap;transition:all .15s}
.tab:hover{color:var(--text)}.tab.on{color:var(--blue);border-bottom-color:var(--blue)}
/* CONTENT */
.pane{display:none;padding:20px 24px}.pane.on{display:block}
/* KPI GRID */
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:12px;margin-bottom:22px}
.kpi{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px 16px}
.kpi .v{font-size:26px;font-weight:700;color:#fff;line-height:1}
.kpi .l{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;margin-top:5px}
.kpi .s{font-size:11px;color:#94a3b8;margin-top:5px;line-height:1.4}
/* CHARTS ROW */
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:22px}
.chart-card{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:16px}
.chart-card h3{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px}
.chart-wrap{position:relative;height:220px}
/* TABLES */
.tbl-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.tbl-hdr h3{font-size:13px;font-weight:600;color:var(--text)}
.srch{background:var(--bg3);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:6px 12px;font-size:12px;width:220px;outline:none}
.srch::placeholder{color:var(--muted)}.srch:focus{border-color:var(--blue)}
.tbl-wrap{border:1px solid var(--border);border-radius:8px;overflow:hidden;overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{background:#0d1b2e;color:var(--muted);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:9px 13px;text-align:left;white-space:nowrap;cursor:pointer;user-select:none}
th:hover{color:var(--text)}th.srt{color:var(--blue)}
td{padding:9px 13px;border-top:1px solid #111827;vertical-align:middle}
tr:hover td{background:#0d1b2e}
.mt{font-weight:500;max-width:320px;color:var(--text)}
.mt small{display:block;color:var(--muted);font-size:10px;margin-top:2px;font-weight:400}
/* BADGES */
.b{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;white-space:nowrap}
.b-g{background:#22c55e18;color:#22c55e;border:1px solid #22c55e30}
.b-y{background:#f59e0b18;color:#f59e0b;border:1px solid #f59e0b30}
.b-r{background:#ef444418;color:#ef4444;border:1px solid #ef444430}
.b-p{background:#a855f718;color:#a855f7;border:1px solid #a855f730}
.b-m{background:#94a3b818;color:#94a3b8;border:1px solid #94a3b830}
.b-b{background:#3b82f618;color:#3b82f6;border:1px solid #3b82f630}
/* EXPIRY */
.exp-over{color:#ef4444;font-weight:600}
.exp-urgent{color:#f59e0b;font-weight:600}
.exp-soon{color:#94a3b8}
/* FLAGS */
.flags{display:flex;flex-wrap:wrap;gap:3px}
.fc{font-size:9px;background:#ef444410;color:#f87171;border:1px solid #ef444428;padding:1px 5px;border-radius:3px}
.ok{font-size:9px;background:#22c55e10;color:#4ade80;border:1px solid #22c55e28;padding:1px 5px;border-radius:3px}
/* ELECTIONS */
.e-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.e-card{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px}
.e-card .ec{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.e-card .et{font-size:12px;font-weight:600;color:var(--text);margin-bottom:12px;line-height:1.4}
.crow{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.cn{font-size:12px;font-weight:600;min-width:85px;color:var(--text)}
.cbw{flex:1;background:#0f172a;border-radius:3px;height:20px;overflow:hidden;position:relative}
.cb{height:100%;display:flex;align-items:center;padding-left:7px;font-size:10px;font-weight:700;color:#fff;min-width:30px;border-radius:3px}
.cpct{font-size:11px;color:var(--muted);min-width:34px;text-align:right}
.ctags{display:flex;gap:3px;margin-bottom:4px}
.ctag{font-size:9px;padding:1px 4px;border-radius:2px;font-weight:600}
.ef{display:flex;justify-content:space-between;margin-top:8px;font-size:10px;color:#475569}
/* MAP */
#map-wrap{display:flex;gap:16px;min-height:520px}
#pm{flex:1}
#mp{width:320px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px;display:none;flex-direction:column;max-height:580px}
#mp.on{display:flex}
.mp-cn{font-size:15px;font-weight:700;color:#fff;margin-bottom:3px}
.mp-st{font-size:11px;color:var(--muted);margin-bottom:10px}
.mp-mkts{overflow-y:auto;flex:1}
.pmk{background:#0d1827;border-radius:6px;padding:9px;margin-bottom:7px;border:1px solid var(--border)}
.pmk-t{font-size:11px;font-weight:600;color:var(--text);margin-bottom:4px}
.pmk-m{display:flex;gap:8px;flex-wrap:wrap;font-size:10px;color:var(--muted)}
.pmk-p{color:var(--green);font-weight:600}
.emp{color:var(--muted);font-size:12px;text-align:center;padding:30px 0}
.close-mp{float:right;cursor:pointer;color:var(--muted);font-size:16px;line-height:1}
.close-mp:hover{color:#fff}
.map-btns{margin-top:10px;display:flex;gap:8px}
.mbtn{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:6px 14px;border-radius:6px;cursor:pointer;font-size:11px;transition:border-color .15s}
.mbtn.on{border-color:var(--blue);color:var(--blue)}
/* MINI BARS (overview category table) */
.mini-bar-w{height:4px;background:#1e293b;border-radius:2px;margin-top:4px}
.mini-bar{height:100%;border-radius:2px;background:var(--blue)}
</style></head><body>
""")

        # ── HEADER ──
        f.write(f"""<div class="hdr">
  <div style="display:flex;align-items:center;gap:12px">
    <div class="live-dot"></div>
    <h1>Polymarket <em>Ops Intelligence</em></h1>
  </div>
  <div class="hdr-right">
    <span class="hdr-meta">{n} markets · {fmt_usd(total_vol)} volume</span>
    <span class="hdr-meta">{now_str}</span>
  </div>
</div>
""")

        # ── TABS ──
        f.write("""<div class="tabs">
  <div class="tab on" data-t="t0" onclick="showTab('t0')">📊 Overview</div>
  <div class="tab" data-t="t1" onclick="showTab('t1')">🗺️ World Map</div>
  <div class="tab" data-t="t2" onclick="showTab('t2')">🗳️ Elections</div>
  <div class="tab" data-t="t3" onclick="showTab('t3')">📋 Daily Ops</div>
  <div class="tab" data-t="t4" onclick="showTab('t4')">🔍 QA Review</div>
  <div class="tab" data-t="t5" onclick="showTab('t5')">⚖️ Compliance</div>
</div>
""")

        # ════════════════════════════════════════════════════════════════
        # TAB 0 — OVERVIEW
        # ════════════════════════════════════════════════════════════════
        f.write('<div id="t0" class="pane on">\n')
        f.write(f"""<div class="kpis">
  <div class="kpi"><div class="v">{n}</div><div class="l">Active Markets</div><div class="s">Fetched from Gamma API</div></div>
  <div class="kpi"><div class="v">{fmt_usd(total_vol)}</div><div class="l">Total Volume</div><div class="s">All-time traded</div></div>
  <div class="kpi"><div class="v">{fmt_usd(total_oi)}</div><div class="l">Open Interest</div><div class="s">Money at stake now</div></div>
  <div class="kpi"><div class="v" style="color:var(--red)">{qa_fail}</div><div class="l">QA Issues</div><div class="s">{qa_review} review · {qa_res} resolved</div></div>
  <div class="kpi"><div class="v" style="color:var(--yellow)">{int_high}</div><div class="l">Integrity Flags</div><div class="s">{int_med} medium risk</div></div>
  <div class="kpi"><div class="v" style="color:var(--purple)">{comp_high}</div><div class="l">Compliance Risk</div><div class="s">{comp_med} medium · {comp_high} high</div></div>
</div>
""")
        # Charts row
        f.write('<div class="charts-row">\n')
        f.write(f"""  <div class="chart-card">
    <h3>Volume by Category ($M)</h3>
    <div class="chart-wrap"><canvas id="catChart"></canvas></div>
  </div>
  <div class="chart-card">
    <h3>Risk Distribution</h3>
    <div class="chart-wrap"><canvas id="riskChart"></canvas></div>
  </div>
</div>
""")
        # Category mini-table
        f.write('<div class="tbl-hdr"><h3>Market Categories</h3></div>\n')
        f.write('<div class="tbl-wrap"><table>\n')
        f.write('<thead><tr><th>Category</th><th>Markets</th><th>Volume</th><th>Avg Size</th></tr></thead><tbody>\n')
        for cat, vol in top_cats:
            cnt_v = cat_cnt[cat]
            avg   = fmt_usd(vol / cnt_v) if cnt_v else "$0"
            pct   = vol / total_vol * 100 if total_vol else 0
            f.write(f'<tr><td class="mt">{esc(cat)}<div class="mini-bar-w"><div class="mini-bar" style="width:{min(pct,100):.0f}%"></div></div></td>'
                    f'<td>{cnt_v}</td><td data-val="{vol}">{fmt_usd(vol)}</td><td>{avg}</td></tr>\n')
        f.write('</tbody></table></div>\n')
        f.write('</div>\n')  # end t0

        # ════════════════════════════════════════════════════════════════
        # TAB 1 — WORLD MAP
        # ════════════════════════════════════════════════════════════════
        f.write('<div id="t1" class="pane">\n')
        f.write("""<p style="color:var(--muted);font-size:12px;margin-bottom:14px">
  Click a country to see its political, economic &amp; geopolitical markets.
  Colors use a <strong>log scale</strong> — small differences are still visible.
</p>
<div id="map-wrap">
  <div id="pm"></div>
  <div id="mp">
    <div><span class="close-mp" onclick="closePanel()">✕</span>
    <div class="mp-cn" id="mp-cn">—</div>
    <div class="mp-st" id="mp-st"></div></div>
    <div class="mp-mkts" id="mp-mkts"></div>
  </div>
</div>
<div class="map-btns">
  <button class="mbtn on" id="btn-c" onclick="setLayer('count')">Market Count</button>
  <button class="mbtn" id="btn-v" onclick="setLayer('volume')">USD Volume</button>
</div>
""")
        popup_json = json.dumps(popup_data)
        f.write(f"""<script>
var ISO={json.dumps(isos)};
var CNT={json.dumps(counts)};
var VOL={json.dumps(volumes)};
var NMS={json.dumps(names)};
var LC={json.dumps(log_counts)};
var LV={json.dumps(log_volumes)};
var PD={popup_json};
var layer='count';
function renderMap(){{
  var z=layer==='count'?LC:LV;
  var txt=NMS.map(function(n,i){{
    return '<b>'+n+'</b><br>'+CNT[i]+' markets<br>$'+(VOL[i]/1e6).toFixed(1)+'M volume';
  }});
  Plotly.react('pm',[{{
    type:'choropleth',locations:ISO,z:z,text:txt,hoverinfo:'text',
    locationmode:'ISO-3',
    colorscale:[[0,'#0d1827'],[0.15,'#1a3a6b'],[0.35,'#1d4ed8'],
                [0.55,'#2563eb'],[0.75,'#3b82f6'],[1,'#93c5fd']],
    showscale:true,zmin:0,zmax:Math.max.apply(null,z),
    colorbar:{{title:layer==='count'?'Markets (log)':'Vol (log)',
      titlefont:{{color:'#64748b',size:10}},tickfont:{{color:'#64748b',size:9}},
      bgcolor:'#111827',bordercolor:'#1e3a5f',len:0.55,thickness:12}}
  }}],{{
    paper_bgcolor:'#0a0f1e',plot_bgcolor:'#0a0f1e',
    geo:{{showframe:false,showcoastlines:true,coastlinecolor:'#1e3a5f',
          showland:true,landcolor:'#111827',showocean:true,oceancolor:'#0a0f1e',
          showcountries:true,countrycolor:'#1e3a5f',showlakes:false,
          bgcolor:'#0a0f1e',projection:{{type:'natural earth'}}}},
    margin:{{t:0,b:0,l:0,r:0}},height:520
  }},{{responsive:true,displayModeBar:false}});
  document.getElementById('pm').on('plotly_click',function(d){{
    openPanel(d.points[0].location);
  }});
}}
function openPanel(iso){{
  var info=PD[iso];if(!info)return;
  document.getElementById('mp-cn').textContent=info.name;
  document.getElementById('mp-st').textContent=info.count+' total markets · '+info.volume+' traded';
  var html='';
  if(!info.markets||!info.markets.length){{
    html='<div class="emp">No political/economic markets<br>for this country.</div>';
  }}else{{
    info.markets.forEach(function(m){{
      var cc=m.cat==='Politics & Elections'?'#a855f7':m.cat==='Geopolitics & World Affairs'?'#ef4444':'#3b82f6';
      var prob=m.prob?'<span class="pmk-p">'+m.prob+'</span>':'';
      html+='<div class="pmk"><div class="pmk-t">'+m.title+'</div>'+
        '<div class="pmk-m"><span style="color:'+cc+'">'+m.cat+'</span>'+
        '<span>'+m.vol+'</span><span>exp '+m.end+'</span>'+prob+'</div></div>';
    }});
  }}
  document.getElementById('mp-mkts').innerHTML=html;
  document.getElementById('mp').classList.add('on');
}}
function closePanel(){{document.getElementById('mp').classList.remove('on');}}
function setLayer(l){{
  layer=l;
  document.getElementById('btn-c').classList.toggle('on',l==='count');
  document.getElementById('btn-v').classList.toggle('on',l==='volume');
  renderMap();
}}
document.querySelector('[data-t="t1"]').addEventListener('click',function(){{
  setTimeout(renderMap,80);
}});
</script>
""")
        f.write('</div>\n')  # end t1

        # ════════════════════════════════════════════════════════════════
        # TAB 2 — ELECTIONS
        # ════════════════════════════════════════════════════════════════
        f.write('<div id="t2" class="pane">\n')
        f.write(f'<p style="color:var(--muted);font-size:12px;margin-bottom:14px">{len(elec_markets)} active political markets · probability bars show current betting odds.</p>\n')
        f.write('<div class="e-grid">\n')
        shown = 0
        for country, markets in sorted(by_country.items(), key=lambda x: sum(m["volume"] for m in x[1]), reverse=True):
            for em in markets[:3]:
                shown += 1
                if shown > 60: break
                cands_html = ""
                if em["candidates"]:
                    for c in sorted(em["candidates"], key=lambda x: x["prob"], reverse=True)[:5]:
                        pct  = int(c["prob"] * 100)
                        prof = c.get("profile") or {}
                        clr  = prof.get("clr", "#3b82f6")
                        ideo = prof.get("ideology", "")
                        party= prof.get("party", "")
                        tags = ""
                        if ideo:  tags += f'<span class="ctag" style="background:{clr}22;color:{clr}">{esc(ideo)}</span>'
                        if party: tags += f'<span class="ctag" style="background:#1e293b;color:#64748b">{esc(party)}</span>'
                        cands_html += (
                            f'<div class="crow"><div class="cn">{esc(c["name"][:16])}</div>'
                            f'<div class="cbw"><div class="cb" style="width:{max(pct,8)}%;background:linear-gradient(90deg,{clr}cc,{clr}66)">{pct}%</div></div>'
                            f'<div class="cpct">{pct}%</div></div>'
                            f'<div class="ctags">{tags}</div>'
                        )
                else:
                    cands_html = '<div style="color:var(--muted);font-size:11px">Probability data unavailable</div>'
                vol_s = fmt_usd(em["volume"])
                exp_s = fmt_date(em["end_date"])
                f.write(
                    f'<div class="e-card">'
                    f'<div class="ec">{esc(COUNTRY_NAMES.get(em["country"], em["country"]))}</div>'
                    f'<div class="et">{esc(em["title"][:75])}</div>'
                    f'{cands_html}'
                    f'<div class="ef"><span>Vol: {vol_s}</span><span>Exp: {exp_s}</span></div>'
                    f'</div>\n'
                )
        if shown == 0:
            f.write('<div style="color:var(--muted)">No election markets found.</div>\n')
        f.write('</div>\n</div>\n')  # end t2

        # ════════════════════════════════════════════════════════════════
        # TAB 3 — DAILY OPS
        # ════════════════════════════════════════════════════════════════
        f.write('<div id="t3" class="pane">\n')
        f.write('<div class="tbl-hdr"><h3>All Active Markets</h3>'
                '<input class="srch" placeholder="🔍 Search markets…" oninput="filterTbl(\'ops\',this.value)"></div>\n')
        f.write('<div class="tbl-wrap"><table id="tbl-ops">\n')
        f.write('<thead><tr><th onclick="srt(\'tbl-ops\',0)">Market</th>'
                '<th onclick="srt(\'tbl-ops\',1)">Volume ↕</th>'
                '<th onclick="srt(\'tbl-ops\',2)">24h Vol ↕</th>'
                '<th onclick="srt(\'tbl-ops\',3)">Liquidity ↕</th>'
                '<th onclick="srt(\'tbl-ops\',4)">Expires ↕</th>'
                '<th onclick="srt(\'tbl-ops\',5)">Risk</th>'
                '</tr></thead><tbody>\n')
        for ev in daily_sorted[:200]:
            ti  = esc(ev["title"][:70] + ("…" if len(ev["title"])>70 else ""))
            cat = esc(ev.get("category",""))
            end = ev["end_date"]
            exp_s   = fmt_date(end)
            exp_cls = expiry_class(end)
            exp_ts  = end.timestamp() if end else 1e12
            lvl = ev["ops_level"]
            bcl = {"LOW":"b-g","MEDIUM":"b-y","HIGH":"b-r","CRITICAL":"b-r"}.get(lvl,"b-m")
            f.write(f'<tr data-search="{ti.lower()}">'
                    f'<td class="mt">{ti}<small>{cat}</small></td>'
                    f'<td data-val="{ev["volume"]}">{fmt_usd(ev["volume"])}</td>'
                    f'<td data-val="{ev["volume_24h"]}">{fmt_usd(ev["volume_24h"])}</td>'
                    f'<td data-val="{ev["liquidity"]}">{fmt_usd(ev["liquidity"])}</td>'
                    f'<td data-val="{exp_ts}"><span class="{exp_cls}">{exp_s}</span></td>'
                    f'<td><span class="b {bcl}">{lvl}</span></td>'
                    f'</tr>\n')
        f.write('</tbody></table></div>\n</div>\n')  # end t3

        # ════════════════════════════════════════════════════════════════
        # TAB 4 — QA REVIEW
        # ════════════════════════════════════════════════════════════════
        f.write('<div id="t4" class="pane">\n')
        f.write(f"""<div class="kpis" style="margin-bottom:16px">
  <div class="kpi"><div class="v" style="color:var(--green)">{qa_pass}</div><div class="l">PASS</div></div>
  <div class="kpi"><div class="v" style="color:var(--yellow)">{qa_review}</div><div class="l">REVIEW</div></div>
  <div class="kpi"><div class="v" style="color:var(--red)">{qa_fail}</div><div class="l">FAIL</div></div>
  <div class="kpi"><div class="v" style="color:var(--muted)">{qa_res}</div><div class="l">RESOLVED</div><div class="s">Correctly excluded</div></div>
</div>
""")
        f.write('<div class="tbl-hdr"><h3>Markets Needing Review</h3>'
                '<input class="srch" placeholder="🔍 Search…" oninput="filterTbl(\'qa\',this.value)"></div>\n')
        f.write('<div class="tbl-wrap"><table id="tbl-qa">\n')
        f.write('<thead><tr><th onclick="srt(\'tbl-qa\',0)">Market</th>'
                '<th onclick="srt(\'tbl-qa\',1)">Score ↕</th>'
                '<th>Issues Found</th>'
                '<th onclick="srt(\'tbl-qa\',3)">PS Arb ↕</th>'
                '<th onclick="srt(\'tbl-qa\',4)">Volume ↕</th>'
                '</tr></thead><tbody>\n')
        for ev in qa_issues[:100]:
            ti   = esc(ev["title"][:65] + ("…" if len(ev["title"])>65 else ""))
            cat  = esc(ev.get("category",""))
            bcl  = "b-r" if ev["qa_grade"]=="FAIL" else "b-y"
            flags_html = "".join(f'<span class="fc">{esc(fg)}</span>' for fg in ev["qa_flags"]) or '<span class="ok">✓ OK</span>'
            arb  = ev.get("ps_rules_arb")
            arb_s = f'<span style="color:{"#ef4444" if arb and arb>50 else "#f59e0b" if arb and arb>25 else "#22c55e"}">{arb}</span>' if arb is not None else '<span style="color:var(--muted)">—</span>'
            f.write(f'<tr data-search="{ti.lower()}">'
                    f'<td class="mt">{ti}<small>{cat}</small></td>'
                    f'<td data-val="{ev["qa_score"]}"><span class="b {bcl}">{ev["qa_grade"]}</span> {ev["qa_score"]}</td>'
                    f'<td><div class="flags">{flags_html}</div></td>'
                    f'<td data-val="{arb or 0}">{arb_s}</td>'
                    f'<td data-val="{ev["volume"]}">{fmt_usd(ev["volume"])}</td>'
                    f'</tr>\n')
        f.write('</tbody></table></div>\n</div>\n')  # end t4

        # ════════════════════════════════════════════════════════════════
        # TAB 5 — COMPLIANCE
        # ════════════════════════════════════════════════════════════════
        low_comp = sum(1 for e in events if e["comp_level"]=="LOW")
        f.write('<div id="t5" class="pane">\n')
        f.write(f"""<div class="kpis" style="margin-bottom:16px">
  <div class="kpi"><div class="v" style="color:var(--red)">{comp_high}</div><div class="l">HIGH Risk</div></div>
  <div class="kpi"><div class="v" style="color:var(--yellow)">{comp_med}</div><div class="l">MEDIUM Risk</div></div>
  <div class="kpi"><div class="v" style="color:var(--green)">{low_comp}</div><div class="l">LOW Risk</div></div>
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
            ti  = esc(ev["title"][:65] + ("…" if len(ev["title"])>65 else ""))
            bcl = "b-r" if ev["comp_level"]=="HIGH" else "b-y"
            fh  = "".join(f'<span class="fc">{esc(fg)}</span>' for fg in ev["comp_flags"])
            f.write(f'<tr data-search="{ti.lower()}">'
                    f'<td class="mt">{ti}</td>'
                    f'<td data-val="{ev["comp_score"]}"><span class="b {bcl}">{ev["comp_level"]}</span></td>'
                    f'<td><div class="flags">{fh}</div></td>'
                    f'<td data-val="{ev["volume"]}">{fmt_usd(ev["volume"])}</td>'
                    f'</tr>\n')
        f.write('</tbody></table></div>\n</div>\n')  # end t5

        # ════════════════════════════════════════════════════════════════
        # SCRIPTS
        # ════════════════════════════════════════════════════════════════
        f.write(f"""<script>
// Tab switching
function showTab(id){{
  document.querySelectorAll('.tab').forEach(function(t){{t.classList.toggle('on',t.dataset.t===id);}});
  document.querySelectorAll('.pane').forEach(function(p){{p.classList.toggle('on',p.id===id);}});
}}
// Sort
function srt(tid,col){{
  var tbl=document.getElementById(tid);
  var rows=Array.from(tbl.querySelectorAll('tbody tr'));
  var dir=tbl.dataset.sc==col&&tbl.dataset.sd=='1'?-1:1;
  tbl.dataset.sc=col; tbl.dataset.sd=dir;
  tbl.querySelectorAll('th').forEach(function(th,i){{th.classList.toggle('srt',i==col);}});
  rows.sort(function(a,b){{
    var ac=a.cells[col],bc=b.cells[col];
    if(!ac||!bc)return 0;
    var av=ac.dataset.val||ac.innerText.replace(/[^\\d.]/g,'');
    var bv=bc.dataset.val||bc.innerText.replace(/[^\\d.]/g,'');
    var an=parseFloat(av),bn=parseFloat(bv);
    if(!isNaN(an)&&!isNaN(bn))return dir*(an-bn);
    return dir*av.localeCompare(bv);
  }});
  var tb=tbl.querySelector('tbody');
  rows.forEach(function(r){{tb.appendChild(r);}});
}}
// Search / filter
function filterTbl(name,q){{
  var tbl=document.getElementById('tbl-'+name);
  var lq=q.toLowerCase();
  tbl.querySelectorAll('tbody tr').forEach(function(r){{
    r.style.display=(r.dataset.search&&r.dataset.search.includes(lq))||!lq?'':'none';
  }});
}}
// Chart.js — category bar
(function(){{
  var ctx=document.getElementById('catChart');
  if(!ctx)return;
  new Chart(ctx,{{
    type:'bar',
    data:{{
      labels:{chart_labels},
      datasets:[{{
        label:'Volume ($M)',
        data:{chart_vols},
        backgroundColor:'rgba(59,130,246,0.7)',
        borderColor:'rgba(59,130,246,1)',
        borderWidth:1,borderRadius:3,
      }}]
    }},
    options:{{
      indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:function(c){{return '$'+c.parsed.x+'M';}}}}}}}},
      scales:{{
        x:{{grid:{{color:'rgba(255,255,255,0.05)'}},ticks:{{color:'#64748b',font:{{size:10}}}},border:{{color:'#1e3a5f'}}}},
        y:{{grid:{{display:false}},ticks:{{color:'#94a3b8',font:{{size:10}}}},border:{{color:'#1e3a5f'}}}}
      }}
    }}
  }});
}})();
// Chart.js — risk donut
(function(){{
  var ctx=document.getElementById('riskChart');
  if(!ctx)return;
  new Chart(ctx,{{
    type:'doughnut',
    data:{{
      labels:['QA Pass','QA Review','QA Fail','Integrity High','Compliance High'],
      datasets:[{{
        data:[{qa_pass},{qa_review},{qa_fail},{int_high},{comp_high}],
        backgroundColor:['rgba(34,197,94,0.8)','rgba(245,158,11,0.8)','rgba(239,68,68,0.8)','rgba(168,85,247,0.8)','rgba(34,211,238,0.8)'],
        borderColor:'#0a0f1e',borderWidth:2,
      }}]
    }},
    options:{{
      responsive:true,maintainAspectRatio:false,cutout:'62%',
      plugins:{{
        legend:{{position:'right',labels:{{color:'#94a3b8',font:{{size:10}},boxWidth:10,padding:10}}}},
        tooltip:{{callbacks:{{label:function(c){{return c.label+': '+c.parsed;}}}}}}
      }}
    }}
  }});
}})();
</script>
</body></html>
""")

    size_kb = sum(1 for _ in open(out_path, 'rb', buffering=8192).read()) // 1024
    print(f"  HTML size: ~{len(open(out_path).read())//1024} KB")

