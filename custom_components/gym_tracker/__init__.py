"""The Gym Tracker integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, SERVICE_REBUILD_CACHE
from .coordinator import GymTrackerCoordinator

PLATFORMS = ["sensor", "binary_sensor"]


@dataclass
class RuntimeData:
    coordinator: GymTrackerCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = GymTrackerCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = RuntimeData(coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    async def _handle_rebuild_cache(call: ServiceCall) -> None:
        await coordinator.async_rebuild_cache()

    hass.services.async_register(DOMAIN, SERVICE_REBUILD_CACHE, _handle_rebuild_cache)

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        runtime: RuntimeData = hass.data[DOMAIN].pop(entry.entry_id)
        runtime.coordinator.async_unload()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_REBUILD_CACHE)
    return unloaded
