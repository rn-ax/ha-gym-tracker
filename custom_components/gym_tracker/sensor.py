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

    async_add_entities([
        GymSessionsTotalSensor(coordinator, entry.entry_id),
        GymSessionStreakSensor(coordinator, entry.entry_id),
        GymCostPerSessionSensor(coordinator, entry.entry_id),
    ])


class _GymSensorBase(CoordinatorEntity[GymTrackerCoordinator], SensorEntity):
    """Shared device grouping for every entity this integration creates."""

    def __init__(self, coordinator: GymTrackerCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Gym Tracker",
        }


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
