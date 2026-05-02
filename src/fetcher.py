"""
fetcher.py
----------
Fetches market and event data from the Polymarket Gamma API.
No API key required — all endpoints are public.
"""

import requests
import pandas as pd
import time
from typing import Optional

GAMMA_BASE = "https://gamma-api.polymarket.com"

# ── Endpoints ────────────────────────────────────────────────────────────────
EVENTS_URL  = f"{GAMMA_BASE}/events"
MARKETS_URL = f"{GAMMA_BASE}/markets"


def fetch_events(
    limit: int = 100,
    offset: int = 0,
    active: Optional[bool] = None,
    closed: Optional[bool] = None,
    order: str = "volume",
    ascending: bool = False,
) -> list[dict]:
    """Fetch a single page of events from the Gamma API."""
    params: dict = {
        "limit": limit,
        "offset": offset,
        "order": order,
        "ascending": str(ascending).lower(),
    }
    if active is not None:
        params["active"] = str(active).lower()
    if closed is not None:
        params["closed"] = str(closed).lower()

    resp = requests.get(EVENTS_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_all_events(
    max_records: int = 2000,
    page_size: int = 100,
    active: Optional[bool] = None,
    closed: Optional[bool] = None,
    order: str = "volume",
    sleep_between: float = 0.4,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Paginate through the Gamma API and return a DataFrame of events.

    Parameters
    ----------
    max_records : max total events to fetch
    page_size   : events per API call (max 100)
    active      : filter by active status (None = all)
    closed      : filter by closed status (None = all)
    order       : sort field ('volume', 'liquidity', 'creationDate', …)
    sleep_between : seconds between requests (be polite to the API)
    verbose     : print progress
    """
    all_events: list[dict] = []
    offset = 0

    while len(all_events) < max_records:
        batch_size = min(page_size, max_records - len(all_events))
        if verbose:
            print(f"  Fetching events {offset} – {offset + batch_size} …")

        try:
            batch = fetch_events(
                limit=batch_size,
                offset=offset,
                active=active,
                closed=closed,
                order=order,
            )
        except requests.RequestException as exc:
            print(f"  ⚠ API error at offset {offset}: {exc}. Stopping.")
            break

        if not batch:
            if verbose:
                print("  No more records.")
            break

        all_events.extend(batch)
        offset += len(batch)

        if len(batch) < batch_size:
            break  # last page

        time.sleep(sleep_between)

    if verbose:
        print(f"  ✓ Fetched {len(all_events)} events total.\n")

    return _events_to_df(all_events)


def _events_to_df(events: list[dict]) -> pd.DataFrame:
    """
    Flatten the events list into a tidy DataFrame.
    Extracts tag labels, numeric fields, and date fields.
    """
    rows = []
    for e in events:
        tags = [t.get("label", "") for t in e.get("tags", [])]
        rows.append(
            {
                "id":              e.get("id"),
                "title":           e.get("title", ""),
                "slug":            e.get("slug", ""),
                "active":          e.get("active", False),
                "closed":          e.get("closed", False),
                "featured":        e.get("featured", False),
                "new":             e.get("new", False),
                "start_date":      e.get("startDate"),
                "end_date":        e.get("endDate"),
                "created_at":      e.get("createdAt"),
                # Volume fields
                "volume":          _to_float(e.get("volume")),
                "volume_24h":      _to_float(e.get("volume24hr")),
                "volume_1w":       _to_float(e.get("volume1wk")),
                "volume_1mo":      _to_float(e.get("volume1mo")),
                "volume_1yr":      _to_float(e.get("volume1yr")),
                # Liquidity / OI
                "liquidity":       _to_float(e.get("liquidityClob") or e.get("liquidity")),
                "open_interest":   _to_float(e.get("openInterest")),
                # Engagement
                "comment_count":   e.get("commentCount", 0),
                "competitive":     _to_float(e.get("competitive")),
                # Markets count
                "num_markets":     len(e.get("markets", [])),
                # Tags (raw list & joined string)
                "tags":            tags,
                "tags_str":        ", ".join(tags),
            }
        )

    df = pd.DataFrame(rows)

    # Parse dates
    for col in ["start_date", "end_date", "created_at"]:
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    return df


def _to_float(val) -> float:
    """Safely cast a value to float."""
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0
