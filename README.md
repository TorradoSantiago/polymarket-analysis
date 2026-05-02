# 📊 Polymarket Market Analysis

> **Which sectors dominate prediction markets?**
> An exploratory data analysis of Polymarket's trading activity — by volume, liquidity, and engagement.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Data Source](https://img.shields.io/badge/Data-Polymarket%20API-purple)](https://gamma-api.polymarket.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🔍 Research Questions

1. **Which categories dominate by total volume traded** (USD)?
2. Which sectors attract the most **liquidity** and **open interest**?
3. How does activity distribute across **timeframes** (24h, 7d, 30d)?
4. What are the **top individual markets** by volume?
5. How are **implied probabilities** distributed across active markets?
6. What is the **capital efficiency** of each category (volume/liquidity ratio)?

---

## 📈 Key Findings (live as of last run)

From a sample of 200 most-traded active events (~$6.7B total volume):

| Category | Markets | Volume (USD) | Share |
|---|---|---|---|
| 🔴 Politics & Elections | 60 | $3.18B | **47.3%** |
| 🔵 Sports | 52 | $2.51B | **37.3%** |
| 🟠 Geopolitics & World Affairs | 44 | $535M | 7.9% |
| 🩷 Culture & Entertainment | 9 | $247M | 3.7% |
| 🟡 Crypto & Blockchain | 16 | $117M | 1.7% |
| 🟢 Economics & Finance | 10 | $95M | 1.4% |
| 🌿 Science, Health & Env. | 3 | $24M | 0.4% |
| 🟣 Technology & AI | 6 | $23M | 0.3% |

> **Top insight:** Politics & Elections + Sports together account for ~85% of all traded volume, despite representing only ~56% of market count — suggesting much higher average market size in these categories.

---

## 🗂️ Project Structure

```
polymarket-analysis/
├── notebooks/
│   └── polymarket_eda.ipynb    ← Main analysis notebook (10 sections, 10 charts)
├── src/
│   ├── fetcher.py              ← Polymarket Gamma API client (paginated)
│   └── classifier.py           ← Rule-based market category classifier
├── data/
│   └── .gitkeep                ← Cached CSVs go here (gitignored)
├── build_notebook.py           ← Regenerates the notebook from source
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/polymarket-analysis.git
cd polymarket-analysis
pip install -r requirements.txt
```

### 2. Run the notebook

```bash
jupyter lab
# Open notebooks/polymarket_eda.ipynb and Run All
```

> No API key required. All data is fetched live from the [Polymarket Gamma API](https://gamma-api.polymarket.com) (public endpoint).

---

## 📓 Notebook Sections

| # | Section | Description |
|---|---|---|
| 0 | Setup & Data Collection | Fetches up to 2,000 events via paginated API calls |
| 1 | Categorisation | Rule-based classifier using event tags + title keywords |
| 2 | High-level Overview | Total volume, liquidity, open interest summary |
| 3 | Volume by Category | Treemap + horizontal bar comparison |
| 4 | Market Count & Engagement | Bubble chart: count vs avg volume vs comments |
| 5 | Temporal Volume Analysis | 24h / 7d / 30d activity breakdown + Pareto curve |
| 6 | Top Individual Markets | Top 20 markets by all-time volume |
| 7 | Market Efficiency | YES price distribution across active markets |
| 8 | Active vs Resolved | Status breakdown by category |
| 9 | Liquidity Depth | Volume/Liquidity ratio (capital efficiency) |

---

## 🔧 Modules

### `src/fetcher.py`

```python
from src.fetcher import fetch_all_events

# Fetch up to 1,000 active events sorted by volume
df = fetch_all_events(max_records=1000, active=True, closed=False)
```

Key parameters:
- `max_records` — total events to fetch (paginates automatically)
- `active` / `closed` — filter by market status
- `order` — sort field: `"volume"`, `"liquidity"`, `"creationDate"`
- `sleep_between` — seconds between requests (default 0.4s)

### `src/classifier.py`

```python
from src.classifier import classify_df, CATEGORY_COLORS

df = classify_df(df)   # adds a 'category' column
# 8 categories + "Other / Miscellaneous"
```

Categories: `Politics & Elections`, `Crypto & Blockchain`, `Economics & Finance`,
`Sports`, `Technology & AI`, `Culture & Entertainment`, `Geopolitics & World Affairs`,
`Science, Health & Environment`, `Other / Miscellaneous`

---

## 📊 Charts Preview

The notebook produces 10 interactive Plotly charts:

- **Fig 1** — Treemap: volume share by category
- **Fig 2** — Volume vs Liquidity comparison
- **Fig 3** — Bubble chart: market count × avg volume × total volume
- **Fig 4** — Engagement (comments) by category
- **Fig 5** — Temporal activity: 24h / 7d / 30d grouped bar
- **Fig 6** — Volume Pareto chart
- **Fig 7** — Top 20 markets by volume (horizontal bar)
- **Fig 8** — YES price distribution (implied probability histogram)
- **Fig 9** — Active vs Resolved market count by category
- **Fig 10** — Capital efficiency: Volume/Liquidity ratio

---

## 🛠️ Extending the Analysis

Some ideas for further work:

- **Time series**: use the `/trades` endpoint to reconstruct volume over time
- **Calibration**: compare implied probabilities vs actual resolution outcomes
- **Liquidity dynamics**: track how spreads evolve as events approach resolution
- **Geographic clustering**: map political markets by country/region
- **NLP classification**: replace the rule-based classifier with a fine-tuned text model

---

## 📚 References

- [Polymarket Gamma API](https://gamma-api.polymarket.com)
- [Polymarket Documentation](https://docs.polymarket.com)
- [Jon Becker — prediction-market-analysis](https://github.com/jon-becker/prediction-market-analysis)
- [Dune Analytics — Polymarket Dashboards](https://dune.com/browse/dashboards?q=polymarket)
- [a16z — Getting prediction market regulation right](https://a16zcrypto.com/posts/article/getting-prediction-market-regulation-right-cftc)

---

## 📄 License

MIT — feel free to fork, extend, and cite.
