"""Tests for the Gym Tracker config flow.

async_setup_entry is patched out for all of these -- they exercise the flow
itself (forms, validation, entry creation), not the coordinator's real
setup, which needs a live calendar/zone/person entity graph that belongs in
a coordinator-focused test instead (see test_coordinator.py).
"""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.gym_tracker.const import DOMAIN

VALID_USER_INPUT = {
    "calendar_entity": "calendar.gym",
    "tracked_person": "person.samuel",
    "gym_zones": ["zone.gymmet", "zone.gym_neptunigatan"],
}


async def test_user_flow_creates_entry(hass: HomeAssistant, enable_custom_integrations):
    with patch(
        "custom_components.gym_tracker.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], VALID_USER_INPUT
        )

    assert result["type"] == "create_entry"
    assert result["data"] == VALID_USER_INPUT


async def test_duplicate_calendar_aborts(hass: HomeAssistant, enable_custom_integrations):
    with patch(
        "custom_components.gym_tracker.async_setup_entry", return_value=True
    ):
        first = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        await hass.config_entries.flow.async_configure(first["flow_id"], VALID_USER_INPUT)

        second = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            second["flow_id"], VALID_USER_INPUT
        )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_options_flow_upserts_monthly_cost(
    hass: HomeAssistant, enable_custom_integrations
):
    with patch(
        "custom_components.gym_tracker.async_setup_entry", return_value=True
    ):
        flow_result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        entry_result = await hass.config_entries.flow.async_configure(
            flow_result["flow_id"], VALID_USER_INPUT
        )
        entry = entry_result["result"]

        options_result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            options_result["flow_id"],
            {"year": 2026, "month": 9, "monthly_cost": 59.90},
        )
        assert result["type"] == "create_entry"
        assert entry.options["monthly_costs"] == {"2026-09": 59.90}

        # A second submission for a different month upserts alongside the
        # first rather than replacing it.
        options_result = await hass.config_entries.options.async_init(entry.entry_id)
        await hass.config_entries.options.async_configure(
            options_result["flow_id"],
            {"year": 2026, "month": 10, "monthly_cost": 59.90},
        )
        assert entry.options["monthly_costs"] == {"2026-09": 59.90, "2026-10": 59.90}
