"""Binary sensor entities for the Gym Tracker integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
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
    async_add_entities([GymSessionOngoingBinarySensor(coordinator, entry.entry_id)])


class GymSessionOngoingBinarySensor(
    CoordinatorEntity[GymTrackerCoordinator], BinarySensorEntity
):
    """Replaces input_boolean.gym_session_ongoing.

    Exposes `session_start` as an attribute (not just on/off) so a future
    automation -- e.g. an iOS Live Activity showing elapsed session time --
    has what it needs without a breaking change later.
    """

    entity_id = "binary_sensor.gym_session_ongoing"
    _attr_has_entity_name = False
    _attr_name = "Gym session ongoing"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: GymTrackerCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_session_ongoing"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Gym Tracker",
        }

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data["session_ongoing"])

    @property
    def extra_state_attributes(self):
        session_start = self.coordinator.data.get("session_start")
        return {"session_start": session_start.isoformat() if session_start else None}
