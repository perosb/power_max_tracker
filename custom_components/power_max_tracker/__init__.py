"""Power Max Tracker integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
from .const import DOMAIN
from .coordinator import PowerMaxCoordinator
from . import sensor  # noqa: F401

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Power Max Tracker integration from YAML."""

    async def update_max_values_service(call: ServiceCall) -> None:
        """Service to update max values from midnight."""
        _LOGGER.debug("Running update_max_values_service")
        for coord in hass.data.get(DOMAIN, {}).values():
            if isinstance(coord, PowerMaxCoordinator):
                await coord.async_update_max_values_from_midnight()

    async def reset_max_values_service(call: ServiceCall) -> None:
        """Service to reset max values to 0."""
        _LOGGER.debug("Running reset_max_values_service")
        for coord in hass.data.get(DOMAIN, {}).values():
            if isinstance(coord, PowerMaxCoordinator):
                await coord.async_update_max_values_to_current_month()

    if not hass.services.has_service(DOMAIN, "update_max_values"):
        hass.services.async_register(
            DOMAIN, "update_max_values", update_max_values_service
        )
    if not hass.services.has_service(DOMAIN, "reset_max_values"):
        hass.services.async_register(
            DOMAIN, "reset_max_values", reset_max_values_service
        )

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the integration from a config entry."""
    try:
        coordinator = PowerMaxCoordinator(hass, entry)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator
        await coordinator.async_setup()

        # Forward setup to sensor platform asynchronously
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True
    except Exception as err:
        raise ConfigEntryNotReady(f"Error setting up Power Max Tracker: {err}")

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_unload()
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False
