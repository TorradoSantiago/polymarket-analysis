"""
run_analysis.py
---------------
Fetches live Polymarket data, runs the full EDA, and produces:
  - assets/fig_*.png          (individual charts, high-res)
  - report.html               (self-contained HTML report with embedded images)
  - data/events_snapshot.csv  (raw data cache)

Usage:  python run_analysis.py
"""

import sys, os, io, base64, json, textwrap, warnings
from pathlib import Path
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import seaborn as sns

from src.fetcher import fetch_all_events
from src.classifier import classify_df, CATEGORY_COLORS

# ── Config ────────────────────────────────────────────────────────────────────
ASSETS    = Path("assets")
DATA_DIR  = Path("data")
ASSETS.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

N_RECORDS   = 1000   # total events to fetch (active + closed)
STYLE       = "seaborn-v0_8-whitegrid"
DPI         = 150
FIG_W       = 12
FIG_H       = 6

plt.style.use(STYLE)
FONT = {"family": "DejaVu Sans"}
matplotlib.rc("font", **FONT)

# ── Colour map (matplotlib-compatible) ───────────────────────────────────────
CAT_ORDER = [
    "Politics & Elections",
    "Sports",
    "Geopolitics & World Affairs",
    "Culture & Entertainment",
    "Crypto & Blockchain",
    "Economics & Finance",
    "Technology & AI",
    "Science, Health & Environment",
    "Other / Miscellaneous",
]
COLORS = {cat: CATEGORY_COLORS.get(cat, "#ADB5BD") for cat in CAT_ORDER}

FIGURES: list[dict] = []   # collect {title, path, b64} for HTML

def savefig(fig, name: str, title: str):
    path = ASSETS / f"{name}.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    FIGURES.append({"title": title, "path": str(path), "b64": b64})
    print(f"  ✓ {name}.png")


def fmt_usd(x):
    if x >= 1e9:  return f"${x/1e9:.1f}B"
    if x >= 1e6:  return f"${x/1e6:.0f}M"
    if x >= 1e3:  return f"${x/1e3:.0f}K"
    return f"${x:.0f}"


# ═════════════════════════════════════════════════════════════════════════════
# 1. FETCH DATA
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("  POLYMARKET EDA — running analysis")
print("="*60)

print("\n[1/9] Fetching data from Polymarket Gamma API…")
df_active = fetch_all_events(max_records=N_RECORDS//2, active=True,  closed=False, verbose=False)
df_closed = fetch_all_events(max_records=N_RECORDS//2, active=False, closed=True,  verbose=False)
df_raw    = pd.concat([df_active, df_closed], ignore_index=True).drop_duplicates("id")
print(f"       {len(df_raw):,} events fetched  "
      f"(active={len(df_active)}, closed={len(df_closed)})")

df = classify_df(df_raw)
df.to_csv(DATA_DIR / "events_snapshot.csv", index=False)
print(f"       Saved → data/events_snapshot.csv")

# ── Aggregation ───────────────────────────────────────────────────────────────
agg = (
    df.groupby("category")
    .agg(
        n_events      =("id",            "count"),
        volume        =("volume",         "sum"),
        volume_24h    =("volume_24h",     "sum"),
        volume_1w     =("volume_1w",      "sum"),
        volume_1mo    =("volume_1mo",     "sum"),
        liquidity     =("liquidity",      "sum"),
        open_interest =("open_interest",  "sum"),
        avg_volume    =("volume",         "mean"),
        comment_count =("comment_count",  "sum"),
    )
    .reset_index()
)
agg["vol_share_pct"] = 100 * agg["volume"]    / agg["volume"].sum()
agg["liq_share_pct"] = 100 * agg["liquidity"] / agg["liquidity"].sum()
agg = agg.sort_values("volume", ascending=False).reset_index(drop=True)

present = [c for c in CAT_ORDER if c in agg["category"].values]
agg = agg.set_index("category").reindex(present).dropna(how="all").reset_index()
colors_list = [COLORS[c] for c in agg["category"]]

# ═════════════════════════════════════════════════════════════════════════════
# FIG 1 — Pie chart: volume share
# ═════════════════════════════════════════════════════════════════════════════
print("\n[2/9] Generating charts…")

fig, ax = plt.subplots(figsize=(FIG_W, 7))
wedges, texts, autotexts = ax.pie(
    agg["volume"],
    labels=None,
    colors=[COLORS.get(c, "#ADB5BD") for c in agg["category"]],
    autopct=lambda p: f"{p:.1f}%" if p > 2 else "",
    startangle=140,
    pctdistance=0.80,
    wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
)
for at in autotexts:
    at.set_fontsize(11)
    at.set_fontweight("bold")
    at.set_color("white")

legend_labels = [
    f"{row['category']}  —  {fmt_usd(row['volume'])}  ({row['vol_share_pct']:.1f}%)"
    for _, row in agg.iterrows()
]
patches = [mpatches.Patch(color=COLORS.get(c, "#ADB5BD")) for c in agg["category"]]
ax.legend(patches, legend_labels, loc="center left", bbox_to_anchor=(1.02, 0.5),
          fontsize=10, frameon=True, framealpha=0.9)
ax.set_title("Fig 1 · Total All-Time Volume by Category", fontsize=15, fontweight="bold", pad=18)
fig.tight_layout()
savefig(fig, "fig1_volume_pie", "Fig 1 · Volume Share by Category (Pie)")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 2 — Horizontal bar: volume + liquidity
# ═════════════════════════════════════════════════════════════════════════════
agg_sorted = agg.sort_values("volume")
fig, axes = plt.subplots(1, 2, figsize=(FIG_W, max(5, len(agg_sorted)*0.55 + 1.5)))

for ax, col, label in zip(
    axes,
    ["volume", "liquidity"],
    ["Total Volume (USD)", "Total Liquidity (USD)"],
):
    bars = ax.barh(
        agg_sorted["category"],
        agg_sorted[col],
        color=[COLORS.get(c, "#ADB5BD") for c in agg_sorted["category"]],
        edgecolor="white", linewidth=0.8, height=0.65,
    )
    ax.set_xlabel(label, fontsize=11)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_usd(x)))
    ax.set_title(label, fontsize=12, fontweight="bold")
    ax.tick_params(axis="y", labelsize=10)
    for bar, val in zip(bars, agg_sorted[col]):
        ax.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height()/2,
                fmt_usd(val), va="center", fontsize=9)

fig.suptitle("Fig 2 · Volume vs Liquidity by Category", fontsize=14, fontweight="bold", y=1.01)
fig.tight_layout()
savefig(fig, "fig2_volume_vs_liquidity", "Fig 2 · Volume vs Liquidity")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 3 — Bubble chart: count × avg_volume (bubble=total volume)
# ═════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(FIG_W, 6.5))
sizes = 600 * agg["volume"] / agg["volume"].max()
sizes = sizes.clip(lower=80)

scatter = ax.scatter(
    agg["n_events"],
    agg["avg_volume"],
    s=sizes * 3,
    c=[COLORS.get(c, "#ADB5BD") for c in agg["category"]],
    alpha=0.80,
    edgecolors="white",
    linewidths=1.5,
)
for _, row in agg.iterrows():
    ax.annotate(
        "\n".join(row["category"].split(" & ") if " & " in row["category"] else row["category"].split()),
        (row["n_events"], row["avg_volume"]),
        textcoords="offset points", xytext=(10, 5),
        fontsize=9, ha="left",
    )

ax.set_xlabel("Number of Events", fontsize=12)
ax.set_ylabel("Average Volume per Event (USD)", fontsize=12)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_usd(x)))
ax.set_yscale("log")
ax.set_title(
    "Fig 3 · Market Count vs. Avg Volume per Market\n"
    "(bubble size = total category volume)",
    fontsize=13, fontweight="bold",
)
fig.tight_layout()
savefig(fig, "fig3_bubble_count_avgvol", "Fig 3 · Count × Avg Volume Bubble Chart")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 4 — Stacked bar: volume by timeframe
# ═════════════════════════════════════════════════════════════════════════════
top5 = agg.nlargest(6, "volume").copy()
x = np.arange(len(top5))
w = 0.25

fig, ax = plt.subplots(figsize=(FIG_W, 5.5))
b1 = ax.bar(x - w,   top5["volume_24h"], w, label="24 hours",  color="#2A9D8F", alpha=0.9)
b2 = ax.bar(x,       top5["volume_1w"],  w, label="7 days",    color="#457B9D", alpha=0.9)
b3 = ax.bar(x + w,   top5["volume_1mo"], w, label="30 days",   color="#E76F51", alpha=0.9)

ax.set_xticks(x)
ax.set_xticklabels([c.replace(" & ", "\n& ") for c in top5["category"]], fontsize=10)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_usd(x)))
ax.set_ylabel("Volume (USD)", fontsize=11)
ax.legend(fontsize=11, loc="upper right")
ax.set_title("Fig 4 · Recent Volume Activity by Category (top 6)", fontsize=13, fontweight="bold")
fig.tight_layout()
savefig(fig, "fig4_temporal_volume", "Fig 4 · Temporal Volume by Category")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 5 — Pareto: cumulative volume concentration
# ═════════════════════════════════════════════════════════════════════════════
agg_p = agg.sort_values("volume", ascending=False).copy()
agg_p["cum_pct"] = 100 * agg_p["volume"].cumsum() / agg_p["volume"].sum()

fig, ax1 = plt.subplots(figsize=(FIG_W, 5.5))
bars = ax1.bar(
    agg_p["category"],
    agg_p["volume"],
    color=[COLORS.get(c, "#ADB5BD") for c in agg_p["category"]],
    edgecolor="white", linewidth=0.8,
)
ax1.set_ylabel("Total Volume (USD)", fontsize=11)
ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_usd(x)))
ax1.set_xticklabels(
    [c.replace(" & ", "\n& ").replace(" / ", "\n/ ") for c in agg_p["category"]],
    rotation=20, ha="right", fontsize=9,
)

ax2 = ax1.twinx()
ax2.plot(agg_p["category"], agg_p["cum_pct"], "ko-", linewidth=2, markersize=7)
for i, (cat, pct) in enumerate(zip(agg_p["category"], agg_p["cum_pct"])):
    ax2.annotate(f"{pct:.0f}%", (cat, pct), textcoords="offset points",
                 xytext=(0, 8), ha="center", fontsize=9, fontweight="bold")
ax2.set_ylabel("Cumulative Volume %", fontsize=11)
ax2.set_ylim(0, 120)
ax2.axhline(80, color="red", linestyle="--", alpha=0.4, label="80% threshold")

ax1.set_title("Fig 5 · Volume Pareto — Concentration across Categories",
              fontsize=13, fontweight="bold")
fig.tight_layout()
savefig(fig, "fig5_pareto", "Fig 5 · Volume Pareto Chart")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 6 — Top 20 markets by volume
# ═════════════════════════════════════════════════════════════════════════════
top20 = df.nlargest(20, "volume")[["title", "volume", "category", "active"]].copy()
top20["title_short"] = top20["title"].str[:70]
top20 = top20.sort_values("volume")

fig, ax = plt.subplots(figsize=(FIG_W, 8.5))
bar_colors = [COLORS.get(c, "#ADB5BD") for c in top20["category"]]
bars = ax.barh(
    top20["title_short"], top20["volume"],
    color=bar_colors, edgecolor="white", linewidth=0.5, height=0.75,
)
for bar, val in zip(bars, top20["volume"]):
    ax.text(bar.get_width() * 1.005, bar.get_y() + bar.get_height()/2,
            fmt_usd(val), va="center", fontsize=9)

ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_usd(x)))
ax.set_xlabel("All-time Volume (USD)", fontsize=11)
ax.tick_params(axis="y", labelsize=8.5)
ax.set_title("Fig 6 · Top 20 Markets by All-Time Volume", fontsize=13, fontweight="bold")

legend_patches = [
    mpatches.Patch(color=COLORS.get(c, "#ADB5BD"), label=c)
    for c in top20["category"].unique()
]
ax.legend(handles=legend_patches, loc="lower right", fontsize=9)
fig.tight_layout()
savefig(fig, "fig6_top20_markets", "Fig 6 · Top 20 Markets by Volume")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 7 — YES price distribution  (from markets endpoint)
# ═════════════════════════════════════════════════════════════════════════════
import requests as _req

def _get_prices(limit=500):
    r = _req.get(
        "https://gamma-api.polymarket.com/markets",
        params={"limit": limit, "active": "true", "order": "volume", "ascending": "false"},
        timeout=30,
    )
    r.raise_for_status()
    rows = []
    for m in r.json():
        try:
            prices = [float(p) for p in json.loads(m.get("outcomePrices","[]"))]
            outs   = json.loads(m.get("outcomes","[]"))
            for price, out in zip(prices, outs):
                if out.lower() in ("yes","true","1"):
                    rows.append(price)
        except Exception:
            pass
    return rows

yes_prices = _get_prices(500)
yes_arr = np.array(yes_prices)

fig, ax = plt.subplots(figsize=(FIG_W, 5))
ax.hist(yes_arr, bins=50, color="#457B9D", edgecolor="white", linewidth=0.4)
ax.axvline(0.5,  color="red",    linestyle="--", linewidth=1.8, label="50% (toss-up)")
ax.axvline(yes_arr.mean(), color="orange", linestyle="-", linewidth=1.8,
           label=f"Mean = {yes_arr.mean():.3f}")
ax.set_xlabel("YES Price (Implied Probability)", fontsize=12)
ax.set_ylabel("Number of Markets", fontsize=12)
ax.legend(fontsize=11)
near_50 = ((yes_arr >= 0.4) & (yes_arr <= 0.6)).sum()
ax.set_title(
    f"Fig 7 · Distribution of YES Prices (Implied Probabilities)\n"
    f"n={len(yes_arr):,} active binary markets  |  "
    f"{near_50} ({100*near_50/len(yes_arr):.0f}%) near 50% (competitive markets)",
    fontsize=12, fontweight="bold",
)
fig.tight_layout()
savefig(fig, "fig7_yes_prices", "Fig 7 · YES Price Distribution")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 8 — Active vs Resolved by category
# ═════════════════════════════════════════════════════════════════════════════
status = (
    df.groupby(["category","active"])
    .size()
    .unstack(fill_value=0)
    .rename(columns={True:"Active", False:"Resolved"})
    .reindex(present)
    .fillna(0)
    .sort_values("Active", ascending=False)
)

fig, ax = plt.subplots(figsize=(FIG_W, 5.5))
x = np.arange(len(status))
w = 0.38
active_vals   = status["Active"].values   if "Active"   in status.columns else np.zeros(len(status))
resolved_vals = status["Resolved"].values if "Resolved" in status.columns else np.zeros(len(status))
ax.bar(x - w/2, active_vals,   w, label="Active",   color="#2A9D8F", alpha=0.9)
ax.bar(x + w/2, resolved_vals, w, label="Resolved", color="#E9C46A", alpha=0.9)
ax.set_xticks(x)
ax.set_xticklabels(
    [c.replace(" & ","\n& ").replace(" / ","\n/ ") for c in status.index],
    rotation=18, ha="right", fontsize=9.5,
)
ax.set_ylabel("Number of Events", fontsize=11)
ax.legend(fontsize=11)
ax.set_title("Fig 8 · Active vs Resolved Market Count by Category",
             fontsize=13, fontweight="bold")
fig.tight_layout()
savefig(fig, "fig8_active_vs_resolved", "Fig 8 · Active vs Resolved")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 9 — Capital efficiency (volume / liquidity ratio)
# ═════════════════════════════════════════════════════════════════════════════
agg_eff = agg.copy()
agg_eff["efficiency"] = agg_eff["volume"] / agg_eff["liquidity"].replace(0, np.nan)
agg_eff = agg_eff.dropna(subset=["efficiency"]).sort_values("efficiency")

fig, ax = plt.subplots(figsize=(FIG_W, 5))
bars = ax.barh(
    agg_eff["category"], agg_eff["efficiency"],
    color=[COLORS.get(c,"#ADB5BD") for c in agg_eff["category"]],
    edgecolor="white", linewidth=0.8, height=0.65,
)
for bar, val in zip(bars, agg_eff["efficiency"]):
    ax.text(bar.get_width()*1.01, bar.get_y()+bar.get_height()/2,
            f"{val:.1f}×", va="center", fontsize=10, fontweight="bold")
ax.set_xlabel("Volume / Liquidity (Capital Efficiency Ratio)", fontsize=11)
ax.set_title(
    "Fig 9 · Capital Efficiency by Category  (Volume / Liquidity)\n"
    "Higher = more trading per dollar of locked capital",
    fontsize=12, fontweight="bold",
)
fig.tight_layout()
savefig(fig, "fig9_capital_efficiency", "Fig 9 · Capital Efficiency")

# ═════════════════════════════════════════════════════════════════════════════
# FIG 10 — Heatmap: volume share across time windows
# ═════════════════════════════════════════════════════════════════════════════
heat_df = agg.set_index("category")[["volume_24h","volume_1w","volume_1mo","volume"]].copy()
heat_df.columns = ["24h","7 days","30 days","All-time"]
# Normalise each column to 0-100%
heat_norm = 100 * heat_df.div(heat_df.sum(axis=0), axis=1)

fig, ax = plt.subplots(figsize=(FIG_W, max(5, len(heat_norm)*0.55 + 2)))
sns.heatmap(
    heat_norm, annot=True, fmt=".1f", cmap="YlOrRd",
    linewidths=0.5, linecolor="white",
    cbar_kws={"label": "% share of column total"},
    ax=ax,
)
ax.set_title(
    "Fig 10 · Volume Share Heatmap by Timeframe\n"
    "(each column = % of that period's total volume)",
    fontsize=13, fontweight="bold",
)
ax.set_ylabel("")
ax.tick_params(axis="y", labelsize=10, rotation=0)
fig.tight_layout()
savefig(fig, "fig10_heatmap", "Fig 10 · Volume Heatmap by Timeframe")

print(f"\n  ✓ All 10 charts generated in assets/\n")

# ═════════════════════════════════════════════════════════════════════════════
# 3. SUMMARY STATS
# ═════════════════════════════════════════════════════════════════════════════
print("[3/9] Computing summary stats…")

total_vol  = df["volume"].sum()
total_liq  = df["liquidity"].sum()
total_oi   = df["open_interest"].sum()
top3_cats  = agg.nlargest(3,"volume")["category"].tolist()
top3_share = agg.nlargest(3,"volume")["vol_share_pct"].sum()
snap_date  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

SUMMARY_ROWS = []
for _, row in agg.iterrows():
    SUMMARY_ROWS.append({
        "category":    row["category"],
        "n_events":    int(row["n_events"]),
        "volume":      row["volume"],
        "vol_pct":     row["vol_share_pct"],
        "liquidity":   row["liquidity"],
        "liq_pct":     row["liq_share_pct"],
        "avg_volume":  row["avg_volume"],
        "comments":    int(row["comment_count"]),
    })

# ═════════════════════════════════════════════════════════════════════════════
# 4. BUILD HTML REPORT
# ═════════════════════════════════════════════════════════════════════════════
print("[4/9] Building HTML report…")

def _row_color(cat):
    hex_ = CATEGORY_COLORS.get(cat, "#ADB5BD").lstrip("#")
    r,g,b = int(hex_[0:2],16), int(hex_[2:4],16), int(hex_[4:6],16)
    return f"rgba({r},{g},{b},0.12)"

table_rows_html = ""
for row in SUMMARY_ROWS:
    bg = _row_color(row["category"])
    dot_color = CATEGORY_COLORS.get(row["category"],"#ADB5BD")
    table_rows_html += f"""
    <tr style="background:{bg}">
      <td><span class="dot" style="background:{dot_color}"></span>{row['category']}</td>
      <td class="num">{row['n_events']:,}</td>
      <td class="num"><strong>{fmt_usd(row['volume'])}</strong></td>
      <td class="num">
        <div class="bar-cell">
          <div class="bar-fill" style="width:{row['vol_pct']:.1f}%;background:{dot_color}"></div>
          <span>{row['vol_pct']:.1f}%</span>
        </div>
      </td>
      <td class="num">{fmt_usd(row['liquidity'])}</td>
      <td class="num">{row['liq_pct']:.1f}%</td>
      <td class="num">{fmt_usd(row['avg_volume'])}</td>
      <td class="num">{row['comments']:,}</td>
    </tr>"""

figures_html = ""
for fig_info in FIGURES:
    figures_html += f"""
    <section class="fig-section">
      <h2>{fig_info['title']}</h2>
      <img src="data:image/png;base64,{fig_info['b64']}" alt="{fig_info['title']}" loading="lazy">
    </section>"""

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polymarket EDA — Category Analysis</title>
<style>
  :root{{
    --bg:#f8f9fa; --card:#ffffff; --text:#212529; --muted:#6c757d;
    --border:#dee2e6; --accent:#2E75B6;
  }}
  *{{box-sizing:border-box; margin:0; padding:0}}
  body{{font-family:'Segoe UI',Arial,sans-serif; background:var(--bg); color:var(--text); padding:0 0 60px}}

  header{{background:linear-gradient(135deg,#1F4E79 0%,#2E75B6 100%);
          color:#fff; padding:50px 40px 40px; text-align:center}}
  header h1{{font-size:2.4rem; margin-bottom:10px; font-weight:700}}
  header p{{font-size:1.1rem; opacity:.85; max-width:700px; margin:0 auto}}
  .meta{{margin-top:18px; font-size:.9rem; opacity:.7}}

  .kpi-grid{{display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
             gap:18px; padding:30px 40px}}
  .kpi{{background:var(--card); border-radius:12px; padding:22px 20px;
        border:1px solid var(--border); text-align:center;
        box-shadow:0 2px 8px rgba(0,0,0,.06)}}
  .kpi .value{{font-size:1.9rem; font-weight:700; color:var(--accent)}}
  .kpi .label{{font-size:.85rem; color:var(--muted); margin-top:4px}}

  .section{{padding:12px 40px}}
  .section h2{{font-size:1.4rem; color:#1F4E79; border-bottom:3px solid #2E75B6;
               padding-bottom:8px; margin-bottom:20px}}

  table{{width:100%; border-collapse:collapse; background:var(--card);
         border-radius:10px; overflow:hidden;
         box-shadow:0 2px 8px rgba(0,0,0,.07)}}
  thead tr{{background:#1F4E79; color:#fff}}
  th{{padding:12px 14px; text-align:left; font-size:.9rem; font-weight:600}}
  td{{padding:11px 14px; font-size:.88rem; border-bottom:1px solid #f0f0f0}}
  td.num{{text-align:right}}
  tr:last-child td{{border-bottom:none}}

  .dot{{display:inline-block; width:10px; height:10px; border-radius:50%;
        margin-right:8px; vertical-align:middle}}

  .bar-cell{{display:flex; align-items:center; gap:8px; justify-content:flex-end}}
  .bar-fill{{height:10px; border-radius:4px; min-width:2px}}
  .bar-cell span{{white-space:nowrap; font-weight:600; min-width:38px; text-align:right}}

  .fig-section{{background:var(--card); border-radius:12px; padding:28px;
                margin-bottom:28px; border:1px solid var(--border);
                box-shadow:0 2px 8px rgba(0,0,0,.06)}}
  .fig-section h2{{font-size:1.15rem; color:#1F4E79; margin-bottom:16px; font-weight:600}}
  .fig-section img{{width:100%; border-radius:6px; display:block}}

  .insight-box{{background:#EBF4FF; border-left:5px solid #2E75B6;
                border-radius:0 8px 8px 0; padding:18px 22px; margin:0 40px 28px;
                font-size:.95rem; line-height:1.6}}
  .insight-box strong{{color:#1F4E79}}

  footer{{text-align:center; color:var(--muted); font-size:.85rem; margin-top:40px}}
  @media(max-width:700px){{
    header{{padding:30px 20px}}
    .kpi-grid,.section{{padding-left:16px;padding-right:16px}}
    .insight-box{{margin:0 16px 20px}}
  }}
</style>
</head>
<body>

<header>
  <h1>📊 Polymarket — Market Category Analysis</h1>
  <p>Exploratory analysis of which sectors dominate prediction markets by volume,
     liquidity, and user engagement</p>
  <div class="meta">
    Data source: Polymarket Gamma API (public) &nbsp;|&nbsp;
    Author: Santiago Torrado &nbsp;|&nbsp;
    Generated: {snap_date}
  </div>
</header>

<!-- KPIs -->
<div class="kpi-grid">
  <div class="kpi"><div class="value">{len(df):,}</div><div class="label">Total Events Analyzed</div></div>
  <div class="kpi"><div class="value">{fmt_usd(total_vol)}</div><div class="label">Total Volume (USD)</div></div>
  <div class="kpi"><div class="value">{fmt_usd(total_liq)}</div><div class="label">Total Liquidity (USD)</div></div>
  <div class="kpi"><div class="value">{fmt_usd(total_oi)}</div><div class="label">Open Interest (USD)</div></div>
  <div class="kpi"><div class="value">{df['active'].sum():,}</div><div class="label">Active Markets</div></div>
  <div class="kpi"><div class="value">{agg['category'].nunique()}</div><div class="label">Categories Identified</div></div>
</div>

<!-- Key insight -->
<div class="insight-box">
  🔑 <strong>Key Finding:</strong>
  <strong>{top3_cats[0]}</strong> and <strong>{top3_cats[1]}</strong> together account for
  <strong>{top3_share:.1f}%</strong> of all traded volume,
  despite representing only {100*agg.nlargest(2,'volume')['n_events'].sum()/agg['n_events'].sum():.0f}% of market count —
  indicating significantly higher average market size in these categories.
  Notably, <em>Crypto & Blockchain</em> — the native environment of Polymarket — accounts for only ~2% of volume,
  suggesting the platform's users are primarily motivated by real-world event prediction rather than crypto speculation.
</div>

<!-- Summary table -->
<div class="section">
  <h2>📋 Summary by Category</h2>
  <table>
    <thead>
      <tr>
        <th>Category</th>
        <th style="text-align:right">Events</th>
        <th style="text-align:right">Volume (USD)</th>
        <th style="text-align:right">Volume Share</th>
        <th style="text-align:right">Liquidity</th>
        <th style="text-align:right">Liq. Share</th>
        <th style="text-align:right">Avg / Market</th>
        <th style="text-align:right">Comments</th>
      </tr>
    </thead>
    <tbody>{table_rows_html}</tbody>
  </table>
</div>

<!-- Charts -->
<div class="section" style="margin-top:32px">
  <h2>📈 Charts</h2>
</div>
{figures_html}

<footer>
  <p>Data fetched live from <a href="https://gamma-api.polymarket.com">gamma-api.polymarket.com</a>
  · No API key required · MIT License</p>
  <p style="margin-top:6px">
    <a href="https://github.com/yourusername/polymarket-analysis">github.com/yourusername/polymarket-analysis</a>
  </p>
</footer>

</body>
</html>"""

report_path = Path("report.html")
report_path.write_text(html, encoding="utf-8")
size_kb = report_path.stat().st_size // 1024
print(f"  ✓ report.html  ({size_kb} KB, self-contained)")

# ═════════════════════════════════════════════════════════════════════════════
# 5. FINAL SUMMARY
# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("  DONE — final output summary")
print("="*60)
print(f"  Events analyzed  : {len(df):,}")
print(f"  Total volume     : {fmt_usd(total_vol)}")
print(f"  Charts generated : {len(FIGURES)}")
print(f"  report.html      : {size_kb} KB (open in browser)")
print(f"  data snapshot    : data/events_snapshot.csv")
print()
print("  Volume by category:")
for row in SUMMARY_ROWS:
    bar = "█" * int(row["vol_pct"] / 3)
    print(f"    {row['category']:<42} {row['vol_pct']:>5.1f}%  {bar}")
print("="*60)
  