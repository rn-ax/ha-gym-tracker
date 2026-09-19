"""Repair fix flow for a missing current-month cost.

Reuses the options flow's own form so the two entry points (Settings ->
Repairs, and the integration's own options) can never drift apart. The fix
flow itself only writes the config entry option and reloads it -- the
coordinator's own _sync_missing_cost_issue is what actually clears the
issue, on the refresh that reload triggers, so a fix applied through
regular options (bypassing this flow entirely) still clears it correctly.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant

from .config_flow import monthly_cost_schema
from .const import CONF_MONTH, CONF_MONTHLY_COST, CONF_YEAR


class MissingMonthlyCostFixFlow(RepairsFlow):
    """Fix flow for the "missing current month's cost" repair issue."""

    def __init__(self, entry_id: str, year: int, month: int) -> None:
        self._entry_id = entry_id
        self._year = year
        self._month = month

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            key = f"{user_input[CONF_YEAR]:04d}-{user_input[CONF_MONTH]:02d}"
            monthly_costs = dict(entry.options.get("monthly_costs", {}))
            monthly_costs[key] = user_input[CONF_MONTHLY_COST]
            self.hass.config_entries.async_update_entry(
                entry, options={**entry.options, "monthly_costs": monthly_costs}
            )
            await self.hass.config_entries.async_reload(self._entry_id)
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="confirm",
            data_schema=monthly_cost_schema(
                {CONF_YEAR: self._year, CONF_MONTH: self._month}
            ),
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> MissingMonthlyCostFixFlow:
    return MissingMonthlyCostFixFlow(data["entry_id"], data["year"], data["month"])
