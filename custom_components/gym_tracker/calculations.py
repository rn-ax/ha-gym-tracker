"""Pure calculation logic for the Gym Tracker integration.

No Home Assistant imports here on purpose: everything in this module is a
plain function over dates/dicts so it can be unit-tested directly, without
spinning up any part of HA.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def dedupe_event_dates(
    events: list[dict[str, Any]], summary_filter: str | None = None
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
    monthly_cost: float | None, sessions_this_year: int
) -> float | None:
    """Annualize `monthly_cost` and split it across this year's sessions.

    Returns None (the sensor goes unavailable, not an error) when there's
    no cost configured yet for the current month, or no sessions yet this
    year to divide it across -- both are normal, expected states, not bugs.
    """
    if monthly_cost is None or sessions_this_year <= 0:
        return None
    return round((monthly_cost * 12) / sessions_this_year, 2)


def months_missing_cost(
    tracked_years: set[int], monthly_costs: dict[str, float], today: date
) -> list[tuple[int, int]]:
    """Every (year, month) from the start of tracking through today with no cost entry.

    A membership is billed monthly regardless of whether that particular
    month had any gym visits, so this checks calendar months, not gym
    dates -- "start of tracking" is January of the earliest tracked year,
    since that's the earliest month a cost could plausibly be owed for.
    """
    if not tracked_years:
        return []

    year, month = min(tracked_years), 1
    missing = []
    while (year, month) <= (today.year, today.month):
        if f"{year:04d}-{month:02d}" not in monthly_costs:
            missing.append((year, month))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return missing


def format_monthly_payments(monthly_costs: dict[str, float]) -> list[dict[str, Any]]:
    """Turn `monthly_costs` into a dashboard-ready row list, newest first.

    A separate function (rather than just exposing the raw dict) because a
    dashboard table card needs a list of same-shaped rows, not a
    "YYYY-MM" -> float mapping.
    """
    rows = []
    for month_key in sorted(monthly_costs, reverse=True):
        year, month = month_key.split("-")
        rows.append(
            {"year": int(year), "month": int(month), "cost": monthly_costs[month_key]}
        )
    return rows


def compute_yearly_stats(
    sessions_by_year_before_cutoff: dict[str, int],
    gym_dates_after_cutoff: set[date],
    monthly_costs: dict[str, float],
    today: date,
) -> list[dict[str, Any]]:
    """One summary row per calendar year with any tracked gym session.

    Folded years are cached as plain counts, not raw dates (see
    coordinator.py), so a row can only report what that shape of data
    supports: a session count, a weekly-pace average, and cost/session --
    not a per-year longest streak, which would need the individual dates.
    Rows are newest year first, matching how the dashboard table reads.
    """
    years = set(sessions_by_year_before_cutoff) | {
        str(d.year) for d in gym_dates_after_cutoff
    }

    rows = []
    for year_key in sorted(years, reverse=True):
        year = int(year_key)
        sessions = sessions_by_year_before_cutoff.get(year_key, 0) + sum(
            1 for d in gym_dates_after_cutoff if d.year == year
        )

        year_costs = [
            cost
            for month_key, cost in monthly_costs.items()
            if month_key.startswith(f"{year_key}-")
        ]
        total_cost = round(sum(year_costs), 2) if year_costs else None

        if year == today.year:
            weeks_elapsed = ((today - date(year, 1, 1)).days + 1) / 7
        else:
            weeks_elapsed = 365.25 / 7

        rows.append(
            {
                "year": year,
                "sessions": sessions,
                "avg_per_week": round(sessions / weeks_elapsed, 1),
                "total_cost": total_cost,
                "cost_per_session": (
                    round(total_cost / sessions, 2) if total_cost and sessions else None
                ),
            }
        )
    return rows
