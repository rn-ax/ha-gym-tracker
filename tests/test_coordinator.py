"""Tests for GymTrackerCoordinator's zone-detection state machine.

These construct the coordinator directly against a MockConfigEntry rather
than going through the full config flow / async_setup_entry -- the
coordinator's `hass.services.async_call` is patched out so no real
`calendar` platform needs to be loaded.
"""

from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.gym_tracker.const import DOMAIN
from custom_components.gym_tracker.coordinator import GymTrackerCoordinator

ENTRY_DATA = {
    "calendar_entity": "calendar.gym",
    "tracked_person": "person.samuel",
    "gym_zones": ["zone.gymmet"],
}


async def _make_coordinator(hass: HomeAssistant) -> GymTrackerCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    hass.states.async_set("zone.gymmet", "zoning", {"friendly_name": "Gym Blomstringe"})
    hass.states.async_set("person.samuel", "home")
    coordinator = GymTrackerCoordinator(hass, entry)
    await coordinator.async_setup()
    return coordinator


async def test_entering_zone_and_staying_starts_session_after_debounce(
    hass: HomeAssistant,
):
    coordinator = await _make_coordinator(hass)
    try:
        hass.states.async_set("person.samuel", "Gym Blomstringe")
        await hass.async_block_till_done()
        assert coordinator._session_ongoing is False  # debounce hasn't elapsed yet

        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1)
        )
        await hass.async_block_till_done()
        assert coordinator._session_ongoing is True
    finally:
        coordinator.async_unload()


async def test_brief_zone_visit_does_not_start_session(hass: HomeAssistant):
    coordinator = await _make_coordinator(hass)
    try:
        hass.states.async_set("person.samuel", "Gym Blomstringe")
        await hass.async_block_till_done()
        hass.states.async_set("person.samuel", "home")
        await hass.async_block_till_done()

        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1)
        )
        await hass.async_block_till_done()
        assert coordinator._session_ongoing is False
    finally:
        coordinator.async_unload()


async def test_leaving_zone_ends_session_and_creates_calendar_event(
    hass: HomeAssistant,
):
    coordinator = await _make_coordinator(hass)
    mock_create_event = AsyncMock(return_value=None)
    hass.services.async_register("calendar", "create_event", mock_create_event)

    try:
        hass.states.async_set("person.samuel", "Gym Blomstringe")
        await hass.async_block_till_done()
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1)
        )
        await hass.async_block_till_done()
        assert coordinator._session_ongoing is True

        hass.states.async_set("person.samuel", "home")
        await hass.async_block_till_done()

        assert coordinator._session_ongoing is False
        mock_create_event.assert_awaited_once()
        call_data = mock_create_event.call_args.args[0].data
        assert call_data["entity_id"] == "calendar.gym"
        assert call_data["summary"] == "Gym"
    finally:
        coordinator.async_unload()
