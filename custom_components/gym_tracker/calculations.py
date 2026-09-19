"""Pure calculation logic for the Gym Tracker integration.

No Home Assistant imports here on purpose: everything in this module is a
plain function over dates/dicts so it can be unit-tested directly, without
spinning up any part of HA.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional


def dedupe_event_dates(
    events: list[dict[str, Any]], summary_filter: Optional[str] = None
) -> set[date]:
    """Return the set of unique calendar days covered by `events`.

    `summary_filter`, when given, keeps only events whose `summary` matches
    exactly (e.g. "Gym") -- events with any other summary (a walk, etc.) are
    dropped. Two events landing on the same calendar day collapse into one
    entry either way: these functions count *days*, not raw event rows.
    """
    dates: set[date] = set()
    for event in events:
        if summary_filter is not None and event.get("summary") != summary_filter:
            continue
        start = event.get("start")
        if not start:
            continue
        try:
            dates.add(datetime.fromisoformat(start.split("T")[0]).date())
        except ValueError:
            continue
    return dates


def compute_streak(all_dates: set[date], today: date) -> int:
    """Count consecutive days of activity ending today (or yesterday).

    If nothing happened today, the streak still counts as alive through
    yesterday -- it only breaks once a full day is missed with no activity
    logged at all.
    """
    d = today
    if d not in all_dates:
        d -= timedelta(days=1)
    if d not in all_dates:
        return 0

    streak = 0
    while d in all_dates:
        streak += 1
        d -= timedelta(days=1)
    return streak


def compute_cost_per_session(
    monthly_cost: Optional[float], sessions_this_year: int
) -> Optional[float]:
    """Annualize `monthly_cost` and split it across this year's sessions.

    Returns None (the sensor goes unavailable, not an error) when there's
    no cost configured yet for the current month, or no sessions yet this
    year to divide it across -- both are normal, expected states, not bugs.
    """
    if monthly_cost is None or sessions_this_year <= 0:
        return None
    return round((monthly_cost * 12) / sessions_this_year, 2)
