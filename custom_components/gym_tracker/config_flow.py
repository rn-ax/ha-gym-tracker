"""Config flow for the Gym Tracker integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_GYM_ZONES,
    CONF_MONTH,
    CONF_MONTHLY_COST,
    CONF_TRACKED_PERSON,
    CONF_YEAR,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CALENDAR_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="calendar")
        ),
        vol.Required(CONF_TRACKED_PERSON): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="person")
        ),
        vol.Required(CONF_GYM_ZONES): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="zone", multiple=True)
        ),
    }
)


def monthly_cost_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Schema for the "add/update one month's cost" form.

    Shared between the options flow and the missing-cost repair fix flow so
    the two paths can't drift apart.
    """
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_YEAR, default=defaults.get(CONF_YEAR, vol.UNDEFINED)
            ): int,
            vol.Required(
                CONF_MONTH, default=defaults.get(CONF_MONTH, vol.UNDEFINED)
            ): vol.All(int, vol.Range(min=1, max=12)),
            vol.Required(CONF_MONTHLY_COST): vol.Coerce(float),
        }
    )


class GymTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Gym Tracker integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_CALENDAR_ENTITY])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Gym Tracker", data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> GymTrackerOptionsFlow:
        return GymTrackerOptionsFlow()


class GymTrackerOptionsFlow(config_entries.OptionsFlow):
    """Add or update a single month's cost.

    Append-only in practice (per user, once a month's cost is set it isn't
    expected to change), so there's no separate edit/delete UI -- resubmit
    the same year/month to overwrite it.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            key = f"{user_input[CONF_YEAR]:04d}-{user_input[CONF_MONTH]:02d}"
            monthly_costs = dict(self.config_entry.options.get("monthly_costs", {}))
            monthly_costs[key] = user_input[CONF_MONTHLY_COST]
            return self.async_create_entry(
                title="", data={"monthly_costs": monthly_costs}
            )

        return self.async_show_form(step_id="init", data_schema=monthly_cost_schema())
