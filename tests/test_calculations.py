"""Unit tests for the pure calculation logic in calculations.py.

No Home Assistant test harness needed here -- these are plain functions.
"""

from datetime import date

from custom_components.gym_tracker.calculations import (
    compute_cost_per_session,
    compute_streak,
    dedupe_event_dates,
)

TODAY = date(2025, 11, 9)


def dates(*isoformats: str) -> set[date]:
    return {date.fromisoformat(d) for d in isoformats}


class TestComputeStreak:
    def test_zero_streak_after_gap(self):
        assert compute_streak(dates("2025-11-01", "2025-10-31"), TODAY) == 0

    def test_one_day_streak_for_today_only(self):
        assert compute_streak(dates("2025-11-09"), TODAY) == 1

    def test_streak_breaks_after_one_day_gap(self):
        assert compute_streak(dates("2025-11-09", "2025-11-07", "2025-11-06"), TODAY) == 1

    def test_continuous_streak(self):
        assert (
            compute_streak(
                dates("2025-11-09", "2025-11-08", "2025-11-07", "2025-11-06"), TODAY
            )
            == 4
        )

    def test_streak_counts_yesterday_when_nothing_logged_today_yet(self):
        assert (
            compute_streak(dates("2025-11-08", "2025-11-07", "2025-11-06"), TODAY) == 3
        )

    def test_empty_dates_is_zero_streak(self):
        assert compute_streak(set(), TODAY) == 0


class TestDedupeEventDates:
    def test_no_filter_counts_every_summary(self):
        events = [
            {"start": "2025-11-09T18:00:00", "summary": "Gym"},
            {"start": "2025-11-08T09:00:00", "summary": "Walk"},
        ]
        assert dedupe_event_dates(events) == dates("2025-11-09", "2025-11-08")

    def test_filter_drops_non_matching_summaries(self):
        events = [
            {"start": "2025-11-09T18:00:00", "summary": "Gym"},
            {"start": "2025-11-08T09:00:00", "summary": "Walk"},
        ]
        assert dedupe_event_dates(events, summary_filter="Gym") == dates("2025-11-09")

    def test_two_events_same_day_dedupe_to_one_date(self):
        events = [
            {"start": "2025-11-09T07:00:00", "summary": "Gym"},
            {"start": "2025-11-09T18:00:00", "summary": "Gym"},
        ]
        assert dedupe_event_dates(events, summary_filter="Gym") == dates("2025-11-09")

    def test_missing_start_is_skipped(self):
        events = [{"summary": "Gym"}]
        assert dedupe_event_dates(events, summary_filter="Gym") == set()

    def test_empty_events_returns_empty_set(self):
        assert dedupe_event_dates([]) == set()


class TestComputeCostPerSession:
    def test_no_cost_configured_returns_none(self):
        assert compute_cost_per_session(None, sessions_this_year=5) is None

    def test_zero_sessions_this_year_returns_none(self):
        assert compute_cost_per_session(59.90, sessions_this_year=0) is None

    def test_splits_annualized_cost_across_sessions(self):
        # 59.90/month * 12 = 718.80/year, split over 10 sessions
        assert compute_cost_per_session(59.90, sessions_this_year=10) == 71.88

    def test_result_is_rounded_to_cents(self):
        assert compute_cost_per_session(59.90, sessions_this_year=7) == 102.69
