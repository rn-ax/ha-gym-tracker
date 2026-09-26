"""Event-driven coordinator for the Gym Tracker integration.

There is no polling interval: every refresh is triggered either by the
tracked person entering/leaving a gym zone, a change to the underlying
calendar, or a daily housekeeping tick (see async_setup below).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .calculations import compute_cost_per_session, compute_streak, dedupe_event_dates
from .const import (
    CACHE_FOLD_AFTER_DAYS,
    CONF_CALENDAR_ENTITY,
    CONF_GYM_ZONES,
    CONF_TRACKED_PERSON,
    DAILY_REFRESH_HOUR,
    DAILY_REFRESH_MINUTE,
    DOMAIN,
    GYM_EVENT_SUMMARY,
    SESSION_START_DEBOUNCE_MINUTES,
    STREAK_LOOKBACK_DAYS,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
EPOCH = date(2000, 1, 1)


class GymTrackerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Tracks gym sessions from a calendar plus zone-based auto-detection."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.entry = entry
        self._calendar_entity: str = entry.data[CONF_CALENDAR_ENTITY]
        self._tracked_person: str = entry.data[CONF_TRACKED_PERSON]
        self._gym_zones: list[str] = entry.data[CONF_GYM_ZONES]

        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
        self._cutoff: date = EPOCH
        self._gym_sessions_before_cutoff = 0
        self._gym_sessions_by_year_before_cutoff: dict[str, int] = {}

        self._session_ongoing = False
        self._session_start = None
        self._pending_start_cancel = None

        self._unsub: list = []

    async def async_setup(self) -> None:
        """Load the persisted cache and wire up all listeners."""
        stored = await self._store.async_load()
        if stored:
            self._cutoff = date.fromisoformat(stored["cutoff"])
            self._gym_sessions_before_cutoff = stored["gym_sessions_before_cutoff"]
            self._gym_sessions_by_year_before_cutoff = dict(
                stored["gym_sessions_by_year_before_cutoff"]
            )

        self._unsub.append(
            async_track_state_change_event(
                self.hass, [self._tracked_person], self._handle_person_state_change
            )
        )
        self._unsub.append(
            self.hass.bus.async_listen(
                "calendar.add_event", self._handle_calendar_event
            )
        )
        self._unsub.append(
            self.hass.bus.async_listen(
                "calendar.remove_event", self._handle_calendar_event
            )
        )
        self._unsub.append(
            async_track_time_change(
                self.hass,
                self._handle_daily_tick,
                hour=DAILY_REFRESH_HOUR,
                minute=DAILY_REFRESH_MINUTE,
                second=0,
            )
        )

    @callback
    def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        if self._pending_start_cancel:
            self._pending_start_cancel()
            self._pending_start_cancel = None

    def _zone_friendly_names(self) -> set[str]:
        names = set()
        for zone_id in self._gym_zones:
            state = self.hass.states.get(zone_id)
            if state:
                names.add(state.attributes.get("friendly_name", zone_id))
        return names

    @callback
    def _handle_person_state_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return

        zone_names = self._zone_friendly_names()
        was_in_zone = old_state is not None and old_state.state in zone_names
        now_in_zone = new_state.state in zone_names

        if now_in_zone and not was_in_zone:
            # Debounced like the automation it replaces (`for: minutes: 5`):
            # a brief pass through the zone doesn't count, only staying.
            if self._pending_start_cancel:
                self._pending_start_cancel()
            self._pending_start_cancel = async_call_later(
                self.hass,
                SESSION_START_DEBOUNCE_MINUTES * 60,
                self._confirm_session_start,
            )
        elif was_in_zone and not now_in_zone:
            # Leaving has no debounce, matching the existing automations'
            # asymmetry -- a real visit ending should be recorded promptly.
            if self._pending_start_cancel:
                self._pending_start_cancel()
                self._pending_start_cancel = None
            if self._session_ongoing:
                self.hass.async_create_task(self._end_session())

    @callback
    def _confirm_session_start(self, _now) -> None:
        self._pending_start_cancel = None
        self._session_ongoing = True
        self._session_start = dt_util.utcnow() - timedelta(
            minutes=SESSION_START_DEBOUNCE_MINUTES
        )
        if self.data is not None:
            self.async_set_updated_data(
                {
                    **self.data,
                    "session_ongoing": self._session_ongoing,
                    "session_start": self._session_start,
                }
            )

    async def _end_session(self) -> None:
        start = self._session_start or dt_util.utcnow()
        end = dt_util.utcnow()
        self._session_ongoing = False
        self._session_start = None

        await self.hass.services.async_call(
            "calendar",
            "create_event",
            {
                "entity_id": self._calendar_entity,
                "summary": GYM_EVENT_SUMMARY,
                "start_date_time": start.isoformat(sep=" ", timespec="seconds"),
                "end_date_time": end.isoformat(sep=" ", timespec="seconds"),
            },
            blocking=True,
        )
        # calendar.create_event fires calendar.add_event itself, which
        # _handle_calendar_event turns into a refresh -- nothing more to do
        # here beyond making sure `session_ongoing` flips off immediately
        # rather than waiting for that refresh to complete.
        if self.data is not None:
            self.async_set_updated_data(
                {**self.data, "session_ongoing": False, "session_start": None}
            )

    @callback
    def _handle_calendar_event(self, event: Event) -> None:
        if event.data.get("entity_id") != self._calendar_entity:
            return
        self.hass.async_create_task(self.async_refresh())

    @callback
    def _handle_daily_tick(self, _now) -> None:
        async def _run() -> None:
            await self._fold_cache_if_due()
            await self.async_refresh()

        self.hass.async_create_task(_run())

    async def _fold_cache_if_due(self) -> None:
        today = dt_util.now().date()
        fold_before = today - timedelta(days=CACHE_FOLD_AFTER_DAYS)
        if fold_before <= self._cutoff:
            return

        events = await self._get_events(self._cutoff, fold_before)
        gym_dates = dedupe_event_dates(events, summary_filter=GYM_EVENT_SUMMARY)
        self._gym_sessions_before_cutoff += len(gym_dates)
        for gym_date in gym_dates:
            year_key = str(gym_date.year)
            self._gym_sessions_by_year_before_cutoff[year_key] = (
                self._gym_sessions_by_year_before_cutoff.get(year_key, 0) + 1
            )
        self._cutoff = fold_before
        await self._save_cache()

    async def _save_cache(self) -> None:
        await self._store.async_save(
            {
                "cutoff": self._cutoff.isoformat(),
                "gym_sessions_before_cutoff": self._gym_sessions_before_cutoff,
                "gym_sessions_by_year_before_cutoff": self._gym_sessions_by_year_before_cutoff,
            }
        )

    async def async_rebuild_cache(self) -> None:
        """Reset the cache and force a full recompute from scratch.

        Escape hatch for the one real risk in this caching design: editing
        or deleting a calendar event older than the fold cutoff would
        otherwise never be picked up again.
        """
        self._cutoff = EPOCH
        self._gym_sessions_before_cutoff = 0
        self._gym_sessions_by_year_before_cutoff = {}
        await self._fold_cache_if_due()
        await self.async_refresh()

    async def _get_events(self, start: date, end: date) -> list[dict[str, Any]]:
        response = await self.hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": self._calendar_entity,
                "start_date_time": f"{start.isoformat()} 00:00:00",
                "end_date_time": f"{end.isoformat()} 23:59:59",
            },
            blocking=True,
            return_response=True,
        )
        return response[self._calendar_entity]["events"]

    async def _async_update_data(self) -> dict[str, Any]:
        await self._fold_cache_if_due()

        today = dt_util.now().date()
        streak_window_start = today - timedelta(days=STREAK_LOOKBACK_DAYS)
        fetch_start = min(self._cutoff, streak_window_start)
        events = await self._get_events(fetch_start, today)

        all_dates = dedupe_event_dates(events)
        streak_dates = {d for d in all_dates if d >= streak_window_start}

        gym_dates_after_cutoff = {
            d
            for d in dedupe_event_dates(events, summary_filter=GYM_EVENT_SUMMARY)
            if d >= self._cutoff
        }
        total_sessions = self._gym_sessions_before_cutoff + len(gym_dates_after_cutoff)

        current_year = today.year
        sessions_this_year = self._gym_sessions_by_year_before_cutoff.get(
            str(current_year), 0
        ) + len({d for d in gym_dates_after_cutoff if d.year == current_year})

        current_month_key = f"{today.year:04d}-{today.month:02d}"
        monthly_costs = self.entry.options.get("monthly_costs", {})
        monthly_cost = monthly_costs.get(current_month_key)
        self._sync_missing_cost_issue(monthly_cost, today)

        return {
            "total_sessions": total_sessions,
            "streak": compute_streak(streak_dates, today),
            "cost_per_session": compute_cost_per_session(
                monthly_cost, sessions_this_year
            ),
            "session_ongoing": self._session_ongoing,
            "session_start": self._session_start,
        }

    def _sync_missing_cost_issue(self, monthly_cost: float | None, today: date) -> None:
        issue_id = f"missing_monthly_cost_{self.entry.entry_id}"
        if monthly_cost is None:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="missing_monthly_cost",
                translation_placeholders={
                    "year": str(today.year),
                    "month": f"{today.month:02d}",
                },
                data={
                    "entry_id": self.entry.entry_id,
                    "year": today.year,
                    "month": today.month,
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
