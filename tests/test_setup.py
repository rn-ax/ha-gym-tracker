"""End-to-end smoke test: real async_setup_entry, real platforms.

Verifies the one thing no other test checks -- that the sensors actually
land on their entity_ids (the legacy ones dashboards depend on, plus the
newer ones) and reflect real (faked) calendar data.
"""

from datetime import date, timedelta

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gym_tracker.const import DOMAIN

ENTRY_DATA = {
    "calendar_entity": "calendar.gym",
    "tracked_person": "person.samuel",
    "gym_zones": ["zone.gymmet"],
}


async def test_setup_creates_legacy_entity_ids_with_real_values(
    hass: HomeAssistant, enable_custom_integrations
):
    today = dt_util.now().date()

    all_events = [
        {"start": today.isoformat() + "T18:00:00", "summary": "Gym"},
        {
            "start": (today - timedelta(days=1)).isoformat() + "T18:00:00",
            "summary": "Gym",
        },
        {
            "start": (today - timedelta(days=2)).isoformat() + "T09:00:00",
            "summary": "Walk",
        },
    ]

    async def fake_get_events(call: ServiceCall) -> ServiceResponse:
        # A real `calendar.get_events` only returns events inside the
        # requested window -- filtering here too so the coordinator's
        # cache-fold fetch and its "recent window" fetch don't both see
        # (and double-count) the same events.
        start = call.data["start_date_time"][:10]
        end = call.data["end_date_time"][:10]
        events = [e for e in all_events if start <= e["start"][:10] <= end]
        return {"calendar.gym": {"events": events}}

    hass.services.async_register(
        "calendar",
        "get_events",
        fake_get_events,
        supports_response=SupportsResponse.ONLY,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        options={"monthly_costs": {f"{today.year:04d}-{today.month:02d}": 59.90}},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    total = hass.states.get("sensor.gym_sessions_total")
    this_year = hass.states.get("sensor.gym_sessions_this_year")
    streak = hass.states.get("sensor.gym_session_streak")
    cost = hass.states.get("sensor.gym_cost_per_session")
    ongoing = hass.states.get("binary_sensor.gym_session_ongoing")
    yearly = hass.states.get("sensor.gym_yearly_stats")
    weekly = hass.states.get("sensor.gym_weekly_sessions")

    assert total is not None and total.state == "2"  # two "Gym"-summary days
    assert this_year is not None and this_year.state == "2"  # both are this year
    # 3: today + yesterday (Gym) + the day before (Walk) -- a walk still
    # counts toward the streak, just not toward the gym-specific total/cost.
    assert streak is not None and streak.state == "3"
    assert cost is not None and float(cost.state) == round(59.90 * 12 / 2, 2)
    assert ongoing is not None and ongoing.state == "off"
    weeks_elapsed_this_year = ((today - date(today.year, 1, 1)).days + 1) / 7
    assert yearly is not None and yearly.state == "1"  # one tracked year so far
    assert yearly.attributes["years"] == [
        {
            "year": today.year,
            "sessions": 2,
            "avg_per_week": round(2 / weeks_elapsed_this_year, 1),
            "total_cost": 59.90,
            "cost_per_session": round(59.90 / 2, 2),
        }
    ]
    assert yearly.attributes["payments"] == [
        {"year": today.year, "month": today.month, "cost": 59.90}
    ]
    # Both Gym days fall inside the 12-week window regardless of which
    # calendar week each one lands in, so the total is always 2 -- but
    # which week bucket gets which count depends on today's weekday (the
    # two dates can straddle a Mon/Sun boundary), so that split is computed
    # rather than hardcoded.
    assert weekly is not None and weekly.state == "2"
    current_week_start = today - timedelta(days=today.weekday())
    yesterday = today - timedelta(days=1)
    current_week_sessions = sum(
        1 for d in (today, yesterday) if d >= current_week_start
    )
    assert weekly.attributes["weeks"][-1] == {
        "week_start": current_week_start.isoformat(),
        "sessions": current_week_sessions,
    }

    # `_attr_has_entity_name = False` means each entity's own `_attr_name`
    # is used as the friendly_name verbatim -- HA does not prepend the
    # device name in that case, so grouping under a device (below) doesn't
    # change these legacy-matching names.
    assert total.attributes["friendly_name"] == "Gym sessions total"
    assert this_year.attributes["friendly_name"] == "Gym sessions this year"
    assert streak.attributes["friendly_name"] == "Gym session streak"
    assert cost.attributes["friendly_name"] == "Gym cost per session"
    assert ongoing.attributes["friendly_name"] == "Gym session ongoing"

    # Every entity groups onto one "Gym Tracker" device, so it gets a real
    # device page (entity list, logbook) in Settings -> Devices & Services.
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None and device.name == "Gym Tracker"

    entity_registry = er.async_get(hass)
    for entity_id in [
        "sensor.gym_sessions_total",
        "sensor.gym_sessions_this_year",
        "sensor.gym_session_streak",
        "sensor.gym_cost_per_session",
        "sensor.gym_yearly_stats",
        "sensor.gym_weekly_sessions",
        "binary_sensor.gym_session_ongoing",
    ]:
        registry_entry = entity_registry.async_get(entity_id)
        assert registry_entry is not None and registry_entry.device_id == device.id

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
