"""
classifier.py
-------------
Rule-based category classification for Polymarket events.

Strategy:
  1. Check the event's tag labels against keyword maps.
  2. Fall back to keyword scan of the title.
  3. Label as "Other / Miscellaneous" if nothing matches.

Categories (macro-level):
  - Politics & Elections
  - Crypto & Blockchain
  - Economics & Finance
  - Sports
  - Technology & AI
  - Culture & Entertainment
  - Geopolitics & World Affairs
  - Science, Health & Environment
  - Other / Miscellaneous
"""

import re
from typing import Optional
import pandas as pd

# ── Category definitions ──────────────────────────────────────────────────────
# Map: category_name → list of keywords (lowercased) to match against tags or title

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Politics & Elections": [
        "politics", "election", "elections", "congress", "senate", "house races",
        "republican", "democrat", "trump", "biden", "harris", "president",
        "governor", "mayor", "parliament", "vote", "ballot", "primary",
        "us government", "government", "law", "supreme court", "courts",
        "speaker", "cabinet", "policy", "legislation",
    ],
    "Crypto & Blockchain": [
        "crypto", "bitcoin", "ethereum", "btc", "eth", "defi", "nft",
        "blockchain", "token", "altcoin", "solana", "dogecoin", "xrp",
        "stablecoin", "binance", "coinbase", "exchange", "web3", "layer 2",
        "memecoin", "on-chain", "onchain", "polymarket",
    ],
    "Economics & Finance": [
        "economy", "economics", "finance", "business", "markets",
        "inflation", "interest rate", "fed", "federal reserve", "gdp",
        "recession", "stocks", "s&p", "nasdaq", "bonds", "treasury",
        "monetary", "fiscal", "trade", "tariff", "wall street", "ipo",
    ],
    "Sports": [
        "sports", "nba", "nfl", "nhl", "mlb", "soccer", "football",
        "basketball", "baseball", "tennis", "golf", "mma", "ufc",
        "boxing", "olympics", "world cup", "champions league", "premier league",
        "ncaa", "ncaab", "ncaaf", "formula 1", "f1", "esports", "gaming",
        "cycling", "athletics", "swimming",
    ],
    "Technology & AI": [
        "tech", "technology", "ai", "artificial intelligence", "openai",
        "big tech", "chatgpt", "gpt", "llm", "machine learning",
        "google", "apple", "microsoft", "meta", "amazon", "startup",
        "software", "hardware", "robotics", "autonomous", "self-driving",
        "spacex", "space", "nasa", "satellite",
    ],
    "Culture & Entertainment": [
        "culture", "music", "movies", "film", "tv", "television",
        "celebrities", "entertainment", "awards", "oscars", "grammys",
        "taylor swift", "celebrity", "pop culture", "streaming",
        "netflix", "disney", "youtube", "social media", "viral",
        "fashion", "art",
    ],
    "Geopolitics & World Affairs": [
        "geopolitics", "world", "ukraine", "russia", "nato", "china",
        "middle east", "israel", "iran", "north korea", "taiwan",
        "war", "conflict", "military", "sanctions", "diplomacy",
        "united nations", "international", "foreign policy",
        "immigration", "border",
    ],
    "Science, Health & Environment": [
        "science", "health", "medical", "covid", "pandemic", "vaccine",
        "climate", "environment", "energy", "oil", "nuclear",
        "weather", "hurricane", "earthquake", "wildfire",
        "biology", "physics", "astronomy", "research", "fda", "who",
    ],
}

# Priority order when multiple categories match (first wins)
PRIORITY_ORDER = [
    "Sports",
    "Crypto & Blockchain",
    "Politics & Elections",
    "Geopolitics & World Affairs",
    "Economics & Finance",
    "Technology & AI",
    "Science, Health & Environment",
    "Culture & Entertainment",
    "Other / Miscellaneous",
]


def classify_event(tags: list[str], title: str = "") -> str:
    """
    Return the macro-category for a single event.

    Parameters
    ----------
    tags  : list of tag label strings from the API
    title : event title (used as fallback)
    """
    combined = " ".join(tags + [title]).lower()

    scores: dict[str, int] = {cat: 0 for cat in CATEGORY_KEYWORDS}

    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", combined):
                scores[cat] += 1

    # Pick the category with the most keyword hits, respecting priority order
    best_cat: Optional[str] = None
    best_score = 0

    for cat in PRIORITY_ORDER[:-1]:  # exclude "Other"
        if scores[cat] > best_score:
            best_score = scores[cat]
            best_cat = cat

    return best_cat if best_cat else "Other / Miscellaneous"


def classify_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a 'category' column to a DataFrame that has 'tags' (list) and 'title' columns.
    Returns a copy of the DataFrame with the new column.
    """
    df = df.copy()
    df["category"] = df.apply(
        lambda row: classify_event(
            row.get("tags", []) if isinstance(row.get("tags"), list) else [],
            row.get("title", ""),
        ),
        axis=1,
    )
    return df


# ── Colour palette for plots ──────────────────────────────────────────────────
CATEGORY_COLORS: dict[str, str] = {
    "Politics & Elections":           "#E63946",
    "Crypto & Blockchain":            "#F4A261",
    "Economics & Finance":            "#2A9D8F",
    "Sports":                         "#457B9D",
    "Technology & AI":                "#9B5DE5",
    "Culture & Entertainment":        "#F15BB5",
    "Geopolitics & World Affairs":    "#FF6B35",
    "Science, Health & Environment":  "#06D6A0",
    "Other / Miscellaneous":          "#ADB5BD",
}
