"""End-to-end smoke test: real async_setup_entry, real platforms.

Verifies the one thing no other test checks -- that the three sensors
actually land on the legacy entity_ids (sensor.gym_sessions_total etc.)
dashboards depend on, and that they reflect real (faked) calendar data.
"""

from datetime import date, timedelta

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
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
    streak = hass.states.get("sensor.gym_session_streak")
    cost = hass.states.get("sensor.gym_cost_per_session")
    ongoing = hass.states.get("binary_sensor.gym_session_ongoing")

    assert total is not None and total.state == "2"  # two "Gym"-summary days
    # 3: today + yesterday (Gym) + the day before (Walk) -- a walk still
    # counts toward the streak, just not toward the gym-specific total/cost.
    assert streak is not None and streak.state == "3"
    assert cost is not None and float(cost.state) == round(59.90 * 12 / 2, 2)
    assert ongoing is not None and ongoing.state == "off"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
