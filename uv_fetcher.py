"""
biotracking uv_fetcher.py
-------------------------
Fetches UV index data from the Open-Meteo API.

Open-Meteo is free, requires no API key, and receives only
coordinates and a date - no personal health data ever leaves
this machine.

API docs: https://open-meteo.com/en/docs

Usage:
    from uv_fetcher import fetch_uv_for_date, fetch_uv_range

    uv = fetch_uv_for_date("2025-01-03")
    # returns: {"date": "2025-01-03", "uv_morning": 1.2,
    #           "uv_noon": 4.8, "uv_evening": 0.3, "source": "api"}
"""

import json
import os
from datetime import date, datetime, timedelta
from typing import Optional

import requests


# ============================================================
# Config loading
# ============================================================

def load_config() -> dict:
    """Load location config from config.json."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            "config.json not found. Run setup.py first."
        )
    with open(config_path) as f:
        return json.load(f)


# ============================================================
# Open-Meteo API
# ============================================================

BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Hours to sample for morning / noon / evening UV
# Using local solar time approximations:
#   Morning:  9am  (index 9)
#   Noon:     12pm (index 12)
#   Evening:  5pm  (index 17)
HOUR_MORNING = 9
HOUR_NOON = 12
HOUR_EVENING = 17

# Open-Meteo forecast API notes:
# - Querying a single date for "today" returns unresolved forecast hours (all zeros)
# - Querying a range that includes yesterday forces resolved model data
# - Maximum historical range on the forecast endpoint is ~16 days back
# - For dates older than 16 days, use fetch_uv_range() with explicit start/end
#   that anchor to a known-good window, or use a separate historical source
# - The archive endpoint does NOT support uv_index (returns null for all hours)


def _build_params(lat: float, lon: float,
                  start_date: str, end_date: str,
                  timezone: str) -> dict:
    """Build the Open-Meteo request parameters.
    
    Always requests at least a two-day window ending on end_date,
    because single-day requests for today return unresolved zeros.
    The caller should filter results to the date they actually want.
    """
    # Ensure we always request at least two days
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if start == end:
        start = start - timedelta(days=1)

    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": "uv_index",
        "timezone": timezone,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }


def _extract_uv_for_date(data: dict, target_date: str) -> Optional[dict]:
    """Extract morning/noon/evening UV values for a single date
    from the Open-Meteo hourly response.

    Args:
        data: parsed JSON response from Open-Meteo
        target_date: YYYY-MM-DD string

    Returns:
        dict with uv_morning, uv_noon, uv_evening or None if date not found
    """
    times = data.get("hourly", {}).get("time", [])
    uv_values = data.get("hourly", {}).get("uv_index", [])

    if not times or not uv_values:
        return None

    # Build a lookup: "YYYY-MM-DDTHH:00" -> uv_value
    uv_by_time = dict(zip(times, uv_values))

    def get_hour(hour: int) -> Optional[float]:
        key = f"{target_date}T{hour:02d}:00"
        val = uv_by_time.get(key)
        # Round to 2 decimal places, treat None as 0.0
        return round(float(val), 2) if val is not None else 0.0

    return {
        "date": target_date,
        "uv_morning": get_hour(HOUR_MORNING),
        "uv_noon": get_hour(HOUR_NOON),
        "uv_evening": get_hour(HOUR_EVENING),
        "source": "api",
    }


def fetch_uv_for_date(target_date: str) -> Optional[dict]:
    """Fetch UV index for a single date.

    Args:
        target_date: YYYY-MM-DD string

    Returns:
        dict with date, uv_morning, uv_noon, uv_evening, source
        or None if the request fails
    """
    try:
        config = load_config()
        params = _build_params(
            lat=config["location_lat"],
            lon=config["location_lon"],
            start_date=target_date,
            end_date=target_date,
            timezone=config.get("timezone", "America/Chicago"),
        )

        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        return _extract_uv_for_date(data, target_date)

    except requests.exceptions.ConnectionError:
        # No internet - return None, caller decides whether to use manual entry
        return None
    except requests.exceptions.Timeout:
        return None
    except requests.exceptions.HTTPError as e:
        print(f"UV API HTTP error for {target_date}: {e}")
        return None
    except Exception as e:
        print(f"UV fetch error for {target_date}: {e}")
        return None


def fetch_uv_range(start_date: str, end_date: str) -> list[dict]:
    """Fetch UV index for a range of dates in a single API call.
    More efficient than calling fetch_uv_for_date in a loop.

    Args:
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD

    Returns:
        List of dicts, one per date in the range.
        Dates with no data are skipped rather than returned as None.
    """
    try:
        config = load_config()
        params = _build_params(
            lat=config["location_lat"],
            lon=config["location_lon"],
            start_date=start_date,
            end_date=end_date,
            timezone=config.get("timezone", "America/Chicago"),
        )

        response = requests.get(BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Walk through each date in the range
        results = []
        current = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

        while current <= end:
            date_str = current.isoformat()
            uv = _extract_uv_for_date(data, date_str)
            if uv:
                results.append(uv)
            current += timedelta(days=1)

        return results

    except requests.exceptions.ConnectionError:
        return []
    except Exception as e:
        print(f"UV range fetch error ({start_date} to {end_date}): {e}")
        return []


def fetch_and_store_uv_for_date(target_date: str) -> Optional[dict]:
    """Fetch UV for a date and store it in the database immediately.
    Returns the UV dict on success, None on failure.

    This is the function Flask routes should call - it handles
    both the API call and the database write in one step.
    """
    # Import here to avoid circular imports
    import db

    # Check if we already have it stored
    existing = db.get_uv_data(target_date)
    if existing and existing.get("source") == "api":
        return existing

    # Fetch from API
    uv = fetch_uv_for_date(target_date)
    if uv:
        db.upsert_uv_data(
            date_str=uv["date"],
            uv_morning=uv["uv_morning"],
            uv_noon=uv["uv_noon"],
            uv_evening=uv["uv_evening"],
            source="api",
        )
        return uv

    return None


def fetch_and_store_uv_range(start_date: str, end_date: str) -> int:
    """Fetch and store UV data for a date range.
    Skips dates already stored from the API.
    Returns count of dates successfully stored.
    """
    import db

    results = fetch_uv_range(start_date, end_date)
    stored = 0

    for uv in results:
        existing = db.get_uv_data(uv["date"])
        if existing and existing.get("source") == "api":
            continue  # already have it, skip
        db.upsert_uv_data(
            date_str=uv["date"],
            uv_morning=uv["uv_morning"],
            uv_noon=uv["uv_noon"],
            uv_evening=uv["uv_evening"],
            source="api",
        )
        stored += 1

    return stored


def backfill_uv_from_tracker_start() -> int:
    """Backfill UV data for all dates in daily_observations
    that don't yet have UV data stored.

    Call this once after importing your historical symptom data
    to populate UV for the entire tracking period.

    Returns count of dates successfully backfilled.
    """
    import db

    observations = db.get_all_daily_observations()
    if not observations:
        print("No daily observations found to backfill.")
        return 0

    dates_needing_uv = []
    for obs in observations:
        existing = db.get_uv_data(obs["date"])
        if not existing:
            dates_needing_uv.append(obs["date"])

    if not dates_needing_uv:
        print("UV data already present for all observation dates.")
        return 0

    # Fetch in one range call if dates are contiguous,
    # otherwise batch by month to keep API requests reasonable
    start = min(dates_needing_uv)
    end = max(dates_needing_uv)

    print(f"Backfilling UV data for {len(dates_needing_uv)} dates "
          f"({start} to {end})...")

    stored = fetch_and_store_uv_range(start, end)
    print(f"Backfill complete. Stored UV data for {stored} dates.")
    return stored


# ============================================================
# Manual UV entry fallback
# ============================================================

def store_manual_uv(date_str: str, uv_morning: float,
                    uv_noon: float, uv_evening: float) -> bool:
    """Store manually entered UV values when API is unavailable.
    Marks source as 'manual' so it's distinguishable in analysis.
    """
    import db
    db.upsert_uv_data(
        date_str=date_str,
        uv_morning=uv_morning,
        uv_noon=uv_noon,
        uv_evening=uv_evening,
        source="manual",
    )
    return True


# ============================================================
# Quick test - run this file directly to verify API connectivity
# ============================================================

if __name__ == "__main__":
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    today_str = today.isoformat()

    results = fetch_uv_range(yesterday, today_str)
    for r in results:
        print(f"{r['date']}  "
              f"morning: {r['uv_morning']}  "
              f"noon: {r['uv_noon']}  "
              f"evening: {r['uv_evening']}")