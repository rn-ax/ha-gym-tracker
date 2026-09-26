"""Unit tests for the pure calculation logic in calculations.py.

No Home Assistant test harness needed here -- these are plain functions.
"""

from datetime import date, timedelta

from custom_components.gym_tracker.calculations import (
    compute_cost_per_session,
    compute_streak,
    compute_weekly_sessions,
    compute_yearly_stats,
    dedupe_event_dates,
    format_monthly_payments,
    months_missing_cost,
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
        assert (
            compute_streak(dates("2025-11-09", "2025-11-07", "2025-11-06"), TODAY) == 1
        )

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


class TestComputeYearlyStats:
    def test_rows_are_newest_year_first(self):
        rows = compute_yearly_stats(
            {"2023": 10, "2024": 20}, dates("2025-01-05"), {}, TODAY
        )
        assert [r["year"] for r in rows] == [2025, 2024, 2023]

    def test_sessions_combine_cache_and_after_cutoff_dates(self):
        rows = compute_yearly_stats(
            {"2025": 50},
            dates("2025-11-01", "2025-11-05", "2024-12-31"),
            {},
            TODAY,
        )
        by_year = {r["year"]: r["sessions"] for r in rows}
        assert by_year[2025] == 52  # 50 cached + 2 after cutoff
        assert by_year[2024] == 1  # only the after-cutoff date

    def test_no_cost_data_leaves_cost_fields_none(self):
        row = compute_yearly_stats({"2024": 100}, set(), {}, TODAY)[0]
        assert row["total_cost"] is None
        assert row["cost_per_session"] is None

    def test_cost_summed_across_the_years_own_months(self):
        rows = compute_yearly_stats(
            {"2024": 100},
            set(),
            {"2024-01": 50.0, "2024-02": 50.0, "2025-01": 999.0},
            TODAY,
        )
        row = next(r for r in rows if r["year"] == 2024)
        assert row["total_cost"] == 100.0
        assert row["cost_per_session"] == 1.0

    def test_avg_per_week_for_a_past_full_year(self):
        row = compute_yearly_stats({"2024": 104}, set(), {}, TODAY)[0]
        assert row["avg_per_week"] == round(104 / (365.25 / 7), 1)

    def test_avg_per_week_for_current_year_uses_elapsed_days(self):
        row = compute_yearly_stats({}, dates("2025-01-05"), {}, TODAY)[0]
        elapsed_weeks = ((TODAY - date(2025, 1, 1)).days + 1) / 7
        assert row["avg_per_week"] == round(1 / elapsed_weeks, 1)


class TestMonthsMissingCost:
    def test_no_tracked_years_returns_empty(self):
        assert months_missing_cost(set(), {}, TODAY) == []

    def test_no_costs_at_all_flags_every_month_from_january(self):
        # TODAY is 2025-11-09, so January through November are owed.
        assert months_missing_cost({2025}, {}, TODAY) == [
            (2025, m) for m in range(1, 12)
        ]

    def test_filled_months_are_excluded(self):
        costs = {f"2025-{m:02d}": 59.90 for m in range(1, 6)}
        assert months_missing_cost({2025}, costs, TODAY) == [
            (2025, m) for m in range(6, 12)
        ]

    def test_starts_from_the_earliest_tracked_year(self):
        missing = months_missing_cost({2024, 2025}, {}, TODAY)
        assert missing[0] == (2024, 1)
        assert missing[-1] == (2025, 11)
        assert len(missing) == 12 + 11

    def test_fully_covered_range_returns_empty(self):
        costs = {f"2025-{m:02d}": 59.90 for m in range(1, 12)}
        assert months_missing_cost({2025}, costs, TODAY) == []


class TestFormatMonthlyPayments:
    def test_empty_costs_returns_empty_list(self):
        assert format_monthly_payments({}) == []

    def test_rows_are_newest_month_first(self):
        rows = format_monthly_payments(
            {"2025-01": 59.90, "2025-03": 59.90, "2025-02": 59.90}
        )
        assert [(r["year"], r["month"]) for r in rows] == [
            (2025, 3),
            (2025, 2),
            (2025, 1),
        ]

    def test_row_shape_and_cost_value(self):
        rows = format_monthly_payments({"2025-06": 67.90})
        assert rows == [{"year": 2025, "month": 6, "cost": 67.90}]


class TestComputeWeeklySessions:
    def test_returns_num_weeks_consecutive_rows_oldest_first(self):
        weeks = compute_weekly_sessions(set(), TODAY, num_weeks=12)
        assert len(weeks) == 12
        starts = [date.fromisoformat(w["week_start"]) for w in weeks]
        assert starts == sorted(starts)
        assert all((starts[i + 1] - starts[i]).days == 7 for i in range(11))

    def test_last_row_is_the_current_in_progress_week(self):
        weeks = compute_weekly_sessions(set(), TODAY, num_weeks=12)
        last_start = date.fromisoformat(weeks[-1]["week_start"])
        assert last_start.weekday() == 0  # Monday
        assert last_start <= TODAY <= last_start + timedelta(days=6)

    def test_counts_sessions_within_each_week(self):
        current_week_start = TODAY - timedelta(days=TODAY.weekday())
        gym_dates = {
            current_week_start,  # this week
            current_week_start - timedelta(days=1),  # last week's Sunday
            current_week_start - timedelta(weeks=1),  # last week's Monday
        }
        weeks = compute_weekly_sessions(gym_dates, TODAY, num_weeks=2)
        assert weeks[0]["sessions"] == 2  # last week
        assert weeks[1]["sessions"] == 1  # this week

    def test_dates_outside_the_window_are_ignored(self):
        current_week_start = TODAY - timedelta(days=TODAY.weekday())
        old_date = current_week_start - timedelta(weeks=5)
        weeks = compute_weekly_sessions({old_date}, TODAY, num_weeks=2)
        assert sum(w["sessions"] for w in weeks) == 0

    def test_zero_weeks_requested_returns_empty(self):
        assert compute_weekly_sessions(set(), TODAY, num_weeks=0) == []
