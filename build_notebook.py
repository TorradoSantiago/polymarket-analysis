"""
build_notebook.py
-----------------
Generates notebooks/polymarket_eda.ipynb using matplotlib/seaborn.
Run: python build_notebook.py
"""
import json, textwrap

def code(source):
    return {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":textwrap.dedent(source).strip()}

def md(source):
    return {"cell_type":"markdown","metadata":{},"source":textwrap.dedent(source).strip()}

cells = []

# ── Title ─────────────────────────────────────────────────────────────────────
cells.append(md("""
# 📊 Polymarket — Exploratory Data Analysis
### Market Category Distribution by Volume, Liquidity & Activity

**Author:** Santiago Torrado &nbsp;|&nbsp; **Source:** [Polymarket Gamma API](https://gamma-api.polymarket.com) (public, no key needed)

---
**Research questions:**
1. Which sectors dominate Polymarket by **total volume** (USD)?
2. Which categories attract the most **liquidity** and **open interest**?
3. How does volume distribute across **timeframes** (24 h, 7 d, 30 d)?
4. What do the **top individual markets** look like?
5. How **efficient** is capital allocation across categories?
"""))

# ── 0. Setup ──────────────────────────────────────────────────────────────────
cells.append(md("## 0 · Setup & Data Collection"))

cells.append(code("""
import sys, os, warnings
sys.path.insert(0, os.path.abspath('..'))
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import seaborn as sns

from src.fetcher import fetch_all_events
from src.classifier import classify_df, CATEGORY_COLORS

plt.style.use('seaborn-v0_8-whitegrid')
pd.set_option('display.float_format', '{:,.2f}'.format)
FIG_W = 12

def fmt_usd(x):
    if x >= 1e9: return f'${x/1e9:.1f}B'
    if x >= 1e6: return f'${x/1e6:.0f}M'
    if x >= 1e3: return f'${x/1e3:.0f}K'
    return f'${x:.0f}'

print('✓ Libraries loaded')
"""))

cells.append(code("""
print('Fetching active markets …')
df_active = fetch_all_events(max_records=500, active=True, closed=False)
print('Fetching resolved markets …')
df_closed = fetch_all_events(max_records=500, active=False, closed=True)
df_raw = pd.concat([df_active, df_closed], ignore_index=True).drop_duplicates('id')
print(f'\\n✓ {len(df_raw):,} events | ${df_raw[\"volume\"].sum():,.0f} total volume')
"""))

# ── 1. Classify ───────────────────────────────────────────────────────────────
cells.append(md("## 1 · Categorisation"))

cells.append(code("""
df = classify_df(df_raw)

# Aggregate
agg = (
    df.groupby('category')
    .agg(
        n_events=('id','count'), volume=('volume','sum'),
        volume_24h=('volume_24h','sum'), volume_1w=('volume_1w','sum'),
        volume_1mo=('volume_1mo','sum'), liquidity=('liquidity','sum'),
        open_interest=('open_interest','sum'), avg_volume=('volume','mean'),
        comment_count=('comment_count','sum'),
    ).reset_index()
)
agg['vol_pct'] = 100 * agg['volume'] / agg['volume'].sum()
agg['liq_pct'] = 100 * agg['liquidity'] / agg['liquidity'].sum()
agg = agg.sort_values('volume', ascending=False).reset_index(drop=True)

COLORS = {c: CATEGORY_COLORS.get(c,'#ADB5BD') for c in agg['category']}
print(agg[['category','n_events','volume','vol_pct']].to_string(index=False))
"""))

# ── 2. KPIs ───────────────────────────────────────────────────────────────────
cells.append(md("## 2 · High-level Overview"))

cells.append(code("""
print(f'Events analyzed : {len(df):,}')
print(f'Total volume    : ${df[\"volume\"].sum():,.0f}')
print(f'Total liquidity : ${df[\"liquidity\"].sum():,.0f}')
print(f'Open interest   : ${df[\"open_interest\"].sum():,.0f}')
print(f'Active markets  : {df[\"active\"].sum():,}')
"""))

# ── 3. Pie ────────────────────────────────────────────────────────────────────
cells.append(md("## 3 · Volume by Category — Pie"))

cells.append(code("""
fig, ax = plt.subplots(figsize=(FIG_W, 7))
colors_pie = [COLORS.get(c,'#ADB5BD') for c in agg['category']]
wedges, _, autotexts = ax.pie(
    agg['volume'], colors=colors_pie,
    autopct=lambda p: f'{p:.1f}%' if p > 2 else '',
    startangle=140, pctdistance=0.80,
    wedgeprops={'linewidth':1.5,'edgecolor':'white'},
)
for at in autotexts:
    at.set_fontsize(11); at.set_fontweight('bold'); at.set_color('white')

legend_labels = [f\"{r['category']}  —  {fmt_usd(r['volume'])}  ({r['vol_pct']:.1f}%)\"
                 for _, r in agg.iterrows()]
patches = [mpatches.Patch(color=COLORS.get(c,'#ADB5BD')) for c in agg['category']]
ax.legend(patches, legend_labels, loc='center left', bbox_to_anchor=(1.02,0.5), fontsize=10)
ax.set_title('Fig 1 · Total All-Time Volume by Category', fontsize=14, fontweight='bold')
plt.tight_layout(); plt.show()
"""))

# ── 4. Bar ────────────────────────────────────────────────────────────────────
cells.append(md("## 4 · Volume vs Liquidity"))

cells.append(code("""
agg_s = agg.sort_values('volume')
fig, axes = plt.subplots(1, 2, figsize=(FIG_W, max(5, len(agg_s)*0.55+1.5)))
for ax, col, lbl in zip(axes, ['volume','liquidity'], ['Total Volume (USD)','Total Liquidity (USD)']):
    bars = ax.barh(agg_s['category'], agg_s[col],
                   color=[COLORS.get(c,'#ADB5BD') for c in agg_s['category']],
                   edgecolor='white', height=0.65)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: fmt_usd(x)))
    ax.set_title(lbl, fontsize=11, fontweight='bold')
    for bar, val in zip(bars, agg_s[col]):
        ax.text(bar.get_width()*1.01, bar.get_y()+bar.get_height()/2,
                fmt_usd(val), va='center', fontsize=8)
fig.suptitle('Fig 2 · Volume vs Liquidity by Category', fontsize=13, fontweight='bold')
plt.tight_layout(); plt.show()
"""))

# ── 5. Bubble ─────────────────────────────────────────────────────────────────
cells.append(md("## 5 · Count × Avg Volume Bubble Chart"))

cells.append(code("""
fig, ax = plt.subplots(figsize=(FIG_W, 6))
sizes = (600 * agg['volume'] / agg['volume'].max()).clip(lower=80)
ax.scatter(agg['n_events'], agg['avg_volume'], s=sizes*3,
           c=[COLORS.get(c,'#ADB5BD') for c in agg['category']],
           alpha=0.8, edgecolors='white', linewidths=1.5)
for _, r in agg.iterrows():
    ax.annotate(r['category'], (r['n_events'], r['avg_volume']),
                xytext=(8,4), textcoords='offset points', fontsize=8)
ax.set_yscale('log')
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: fmt_usd(x)))
ax.set_xlabel('Number of Events'); ax.set_ylabel('Avg Volume / Event (USD)')
ax.set_title('Fig 3 · Market Count vs Avg Volume (bubble = total volume)', fontsize=12, fontweight='bold')
plt.tight_layout(); plt.show()
"""))

# ── 6. Temporal ───────────────────────────────────────────────────────────────
cells.append(md("## 6 · Temporal Volume Analysis"))

cells.append(code("""
top6 = agg.nlargest(6,'volume').copy()
x = np.arange(len(top6)); w = 0.25
fig, ax = plt.subplots(figsize=(FIG_W, 5))
ax.bar(x-w, top6['volume_24h'], w, label='24 hours',  color='#2A9D8F', alpha=0.9)
ax.bar(x,   top6['volume_1w'],  w, label='7 days',    color='#457B9D', alpha=0.9)
ax.bar(x+w, top6['volume_1mo'], w, label='30 days',   color='#E76F51', alpha=0.9)
ax.set_xticks(x)
ax.set_xticklabels([c.replace(' & ',chr(10)+'& ') for c in top6['category']], fontsize=9)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: fmt_usd(x)))
ax.legend(); ax.set_ylabel('Volume (USD)')
ax.set_title('Fig 4 · Recent Volume Activity by Category', fontsize=12, fontweight='bold')
plt.tight_layout(); plt.show()
"""))

# ── 7. Pareto ─────────────────────────────────────────────────────────────────
cells.append(md("## 7 · Volume Pareto Chart"))

cells.append(code("""
agg_p = agg.copy()
agg_p['cum_pct'] = 100 * agg_p['volume'].cumsum() / agg_p['volume'].sum()
fig, ax1 = plt.subplots(figsize=(FIG_W, 5))
ax1.bar(agg_p['category'], agg_p['volume'],
        color=[COLORS.get(c,'#ADB5BD') for c in agg_p['category']], edgecolor='white')
ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: fmt_usd(x)))
ax1.set_xticklabels([c.replace(' & ',chr(10)+'& ').replace(' / ',chr(10)+'/ ')
                     for c in agg_p['category']], rotation=15, ha='right', fontsize=8)
ax2 = ax1.twinx()
ax2.plot(agg_p['category'], agg_p['cum_pct'], 'ko-', linewidth=2, markersize=7)
for i,(cat,pct) in enumerate(zip(agg_p['category'],agg_p['cum_pct'])):
    ax2.annotate(f'{pct:.0f}%',(cat,pct),xytext=(0,8),textcoords='offset points',
                 ha='center',fontsize=8,fontweight='bold')
ax2.set_ylim(0,120); ax2.axhline(80,color='red',linestyle='--',alpha=0.4)
ax2.set_ylabel('Cumulative %')
ax1.set_title('Fig 5 · Volume Pareto — Concentration across Categories', fontsize=12, fontweight='bold')
plt.tight_layout(); plt.show()
"""))

# ── 8. Top 20 ─────────────────────────────────────────────────────────────────
cells.append(md("## 8 · Top 20 Markets by Volume"))

cells.append(code("""
top20 = df.nlargest(20,'volume')[['title','volume','category']].copy()
top20['title_short'] = top20['title'].str[:72]
top20 = top20.sort_values('volume')
fig, ax = plt.subplots(figsize=(FIG_W, 8))
bars = ax.barh(top20['title_short'], top20['volume'],
               color=[COLORS.get(c,'#ADB5BD') for c in top20['category']],
               edgecolor='white', height=0.75)
for bar, val in zip(bars, top20['volume']):
    ax.text(bar.get_width()*1.005, bar.get_y()+bar.get_height()/2,
            fmt_usd(val), va='center', fontsize=8)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: fmt_usd(x)))
ax.tick_params(axis='y',labelsize=8)
legend_patches = [mpatches.Patch(color=COLORS.get(c,'#ADB5BD'),label=c)
                  for c in top20['category'].unique()]
ax.legend(handles=legend_patches,fontsize=8,loc='lower right')
ax.set_title('Fig 6 · Top 20 Markets by All-Time Volume', fontsize=12, fontweight='bold')
plt.tight_layout(); plt.show()
"""))

# ── 9. Price dist ─────────────────────────────────────────────────────────────
cells.append(md("## 9 · YES Price Distribution (Implied Probabilities)"))

cells.append(code("""
import requests, json as _json

resp = requests.get('https://gamma-api.polymarket.com/markets',
    params={'limit':500,'active':'true','order':'volume','ascending':'false'}, timeout=30)
yes_prices = []
for m in resp.json():
    try:
        prices = [float(p) for p in _json.loads(m.get('outcomePrices','[]'))]
        outs   = _json.loads(m.get('outcomes','[]'))
        for price, out in zip(prices, outs):
            if out.lower() in ('yes','true','1'):
                yes_prices.append(price)
    except: pass
yes_arr = np.array(yes_prices)

fig, ax = plt.subplots(figsize=(FIG_W, 5))
ax.hist(yes_arr, bins=50, color='#457B9D', edgecolor='white', linewidth=0.4)
ax.axvline(0.5, color='red', linestyle='--', linewidth=2, label='50% (toss-up)')
ax.axvline(yes_arr.mean(), color='orange', linestyle='-', linewidth=2,
           label=f'Mean = {yes_arr.mean():.3f}')
ax.set_xlabel('YES Price (Implied Probability)', fontsize=11)
ax.set_ylabel('Number of Markets', fontsize=11)
ax.legend(fontsize=10)
near_50 = ((yes_arr>=0.4)&(yes_arr<=0.6)).sum()
ax.set_title(
    f'Fig 7 · YES Price Distribution  |  n={len(yes_arr):,} markets  |  '
    f'{near_50} ({100*near_50/len(yes_arr):.0f}%) near 50%',
    fontsize=11, fontweight='bold')
plt.tight_layout(); plt.show()
"""))

# ── 10. Heatmap ───────────────────────────────────────────────────────────────
cells.append(md("## 10 · Volume Share Heatmap by Timeframe"))

cells.append(code("""
heat = agg.set_index('category')[['volume_24h','volume_1w','volume_1mo','volume']].copy()
heat.columns = ['24h','7 days','30 days','All-time']
heat_norm = 100 * heat.div(heat.sum(axis=0), axis=1)

fig, ax = plt.subplots(figsize=(FIG_W, max(5, len(heat_norm)*0.55+2)))
sns.heatmap(heat_norm, annot=True, fmt='.1f', cmap='YlOrRd',
            linewidths=0.5, linecolor='white',
            cbar_kws={'label':'% of column total'}, ax=ax)
ax.set_ylabel(''); ax.tick_params(axis='y', rotation=0, labelsize=9)
ax.set_title('Fig 8 · Volume Share Heatmap  (each column = % of that period\'s total)',
             fontsize=12, fontweight='bold')
plt.tight_layout(); plt.show()
"""))

# ── 11. Capital efficiency ────────────────────────────────────────────────────
cells.append(md("## 11 · Capital Efficiency (Volume / Liquidity Ratio)"))

cells.append(code("""
agg_eff = agg.copy()
agg_eff['efficiency'] = agg_eff['volume'] / agg_eff['liquidity'].replace(0, np.nan)
agg_eff = agg_eff.dropna(subset=['efficiency']).sort_values('efficiency')

fig, ax = plt.subplots(figsize=(FIG_W, 4.5))
bars = ax.barh(agg_eff['category'], agg_eff['efficiency'],
               color=[COLORS.get(c,'#ADB5BD') for c in agg_eff['category']],
               edgecolor='white', height=0.65)
for bar, val in zip(bars, agg_eff['efficiency']):
    ax.text(bar.get_width()*1.01, bar.get_y()+bar.get_height()/2,
            f'{val:.1f}×', va='center', fontsize=10, fontweight='bold')
ax.set_xlabel('Volume / Liquidity (higher = more trading per $ locked)')
ax.set_title('Fig 9 · Capital Efficiency by Category', fontsize=12, fontweight='bold')
plt.tight_layout(); plt.show()
"""))

# ── 12. Summary ───────────────────────────────────────────────────────────────
cells.append(md("## 12 · Key Findings"))

cells.append(code("""
top3 = agg.nlargest(3,'volume')
top3_share = top3['vol_pct'].sum()

print('='*60)
print('  POLYMARKET — KEY FINDINGS')
print('='*60)
print(f'  Total events  : {len(df):,}')
print(f'  Total volume  : ${df[\"volume\"].sum():,.0f}')
print()
print(f'  Top category by volume    : {agg.iloc[0][\"category\"]}')
print(f'  Top category by liquidity : {agg.sort_values(\"liquidity\",ascending=False).iloc[0][\"category\"]}')
print(f'  Top category by count     : {agg.sort_values(\"n_events\",ascending=False).iloc[0][\"category\"]}')
print()
print(f'  Top 3 categories = {top3_share:.1f}% of all volume:')
for _, r in top3.iterrows():
    print(f'    {r[\"category\"]:<40} {r[\"vol_pct\"]:.1f}%')
print()
print('  Full distribution:')
for _, r in agg.iterrows():
    bar = chr(9608) * int(r['vol_pct']/3)
    print(f'    {r[\"category\"]:<42} {r[\"vol_pct\"]:>5.1f}%  {bar}')
print('='*60)
"""))

cells.append(md("""
---
## References
- [Polymarket Gamma API](https://gamma-api.polymarket.com)
- [Polymarket Documentation](https://docs.polymarket.com)
- [Jon Becker — prediction-market-analysis](https://github.com/jon-becker/prediction-market-analysis)
- [Dune Analytics — Polymarket dashboards](https://dune.com/browse/dashboards?q=polymarket)
"""))

# ── Write notebook ─────────────────────────────────────────────────────────────
nb = {
    "nbformat": 4, "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name":"Python 3","language":"python","name":"python3"},
        "language_info": {"name":"python","version":"3.10.0"},
    },
    "cells": cells,
}

import os
os.makedirs("notebooks", exist_ok=True)
out = "notebooks/polymarket_eda.ipynb"
with open(out, "w", encoding="utf-8") as f:
    import json
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"✓ Notebook written → {out}  ({len(cells)} cells)")
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     