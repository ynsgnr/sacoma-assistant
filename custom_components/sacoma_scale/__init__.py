"""The SACOMA smart scale integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr

from .const import CONF_DEVICE_NAME, CONF_DRIVE, DEFAULT_DRIVE, DOMAIN
from .coordinator import SacomaScaleCoordinator
from .users import users_from_config

PLATFORMS: list[Platform] = [Platform.SENSOR]

type SacomaConfigEntry = ConfigEntry[SacomaScaleCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SacomaConfigEntry) -> bool:
    """Set up SACOMA scale from a config entry."""
    address = entry.unique_id
    if address is None:
        raise ConfigEntryError("config entry is missing the device address")

    # Options override data once the user edits the device name / users / drive flag.
    config = {**entry.data, **entry.options}
    address = address.upper()
    device_name = config.get(CONF_DEVICE_NAME) or entry.title or "SACOMA Smart Scale"
    users = users_from_config(config)

    # Register the physical scale so each user's sensors can hang off it as sub-devices.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, address)},
        connections={(dr.CONNECTION_BLUETOOTH, address)},
        manufacturer="ICOMON",
        model="SACOMA Ultra",
        name=device_name,
    )

    coordinator = SacomaScaleCoordinator(
        hass, entry, address, device_name, users, drive=config.get(CONF_DRIVE, DEFAULT_DRIVE)
    )
    await coordinator.async_start()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SacomaConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop()
    return unload_ok


async def _async_reload_on_update(hass: HomeAssistant, entry: SacomaConfigEntry) -> None:
    """Reload the entry when the user edits the device name, users, or drive flag."""
    await hass.config_entries.async_reload(entry.entry_id)
