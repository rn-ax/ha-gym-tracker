"""Sensor entities for the Gym Tracker integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GymTrackerCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: GymTrackerCoordinator = hass.data[DOMAIN][entry.entry_id].coordinator

    async_add_entities(
        [
            GymSessionsTotalSensor(coordinator, entry.entry_id),
            GymSessionsThisYearSensor(coordinator, entry.entry_id),
            GymSessionStreakSensor(coordinator, entry.entry_id),
            GymCostPerSessionSensor(coordinator, entry.entry_id),
            GymYearlyStatsSensor(coordinator, entry.entry_id),
        ]
    )


class _GymSensorBase(CoordinatorEntity[GymTrackerCoordinator], SensorEntity):
    """Shared base for every sensor this integration creates.

    Deliberately no `device_info`: HA's entity-naming logic prefixes the
    device name onto the displayed friendly_name for an auto-named entity
    (one with no user-set registry `name` override) regardless of
    `has_entity_name`, so grouping under a device produced e.g. "Gym
    Tracker Gym session streak" instead of "Gym session streak". Without a
    device there's nothing to prefix with.
    """

    def __init__(self, coordinator: GymTrackerCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id


class GymSessionsTotalSensor(_GymSensorBase):
    # Matches the legacy AppDaemon entity_id (sensor.gym_sessions_total) so
    # existing dashboards keep working across the migration. Setting
    # entity_id directly (rather than relying on name-slug derivation) is
    # what actually pins this -- HA's suggested_object_id derivation
    # prefixes the device name onto a has_entity_name=False entity's name
    # for new entities, so relying on the name alone produced
    # sensor.gym_tracker_gym_sessions_total instead (caught by
    # tests/test_setup.py).
    entity_id = "sensor.gym_sessions_total"
    _attr_has_entity_name = False
    _attr_name = "Gym sessions total"
    _attr_icon = "mdi:dumbbell"
    _attr_native_unit_of_measurement = "sessions"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_sessions_total"

    @property
    def native_value(self):
        return self.coordinator.data["total_sessions"]


class GymSessionsThisYearSensor(_GymSensorBase):
    # New (not a legacy AppDaemon entity_id) -- the old system never
    # exposed a year-scoped count, only the all-time total, which is what
    # led to dashboards mislabeling that all-time total as "this year".
    entity_id = "sensor.gym_sessions_this_year"
    _attr_has_entity_name = False
    _attr_name = "Gym sessions this year"
    _attr_icon = "mdi:dumbbell"
    _attr_native_unit_of_measurement = "sessions"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_sessions_this_year"

    @property
    def native_value(self):
        return self.coordinator.data["sessions_this_year"]


class GymSessionStreakSensor(_GymSensorBase):
    entity_id = "sensor.gym_session_streak"
    _attr_has_entity_name = False
    _attr_name = "Gym session streak"
    _attr_icon = "mdi:fire"
    _attr_native_unit_of_measurement = "days"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_session_streak"

    @property
    def native_value(self):
        return self.coordinator.data["streak"]


class GymYearlyStatsSensor(_GymSensorBase):
    """One row per tracked calendar year, for a dashboard table card.

    The state is just the row count -- the actual data (year, sessions,
    avg_per_week, total_cost, cost_per_session per row) lives in the
    `years` attribute, which a card like flex-table-card's `attr_as_list`
    can expand into a table with no other Home Assistant plumbing needed.
    """

    entity_id = "sensor.gym_yearly_stats"
    _attr_has_entity_name = False
    _attr_name = "Gym yearly stats"
    _attr_icon = "mdi:table"
    _attr_native_unit_of_measurement = "years"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_yearly_stats"

    @property
    def native_value(self):
        return len(self.coordinator.data["yearly_stats"])

    @property
    def extra_state_attributes(self):
        return {"years": self.coordinator.data["yearly_stats"]}


class GymCostPerSessionSensor(_GymSensorBase):
    entity_id = "sensor.gym_cost_per_session"
    _attr_has_entity_name = False
    _attr_name = "Gym cost per session"
    _attr_icon = "mdi:currency-eur"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    # No state_class: MONETARY only permits None or TOTAL, and this value
    # isn't a running total -- it's a point-in-time ratio that can go up or
    # down as sessions/cost change.

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_cost_per_session"

    @property
    def native_value(self):
        # None (unavailable) when the current month's cost isn't configured
        # yet -- the Repairs issue the coordinator raises is what actually
        # prompts fixing that, not an error here.
        return self.coordinator.data["cost_per_session"]
