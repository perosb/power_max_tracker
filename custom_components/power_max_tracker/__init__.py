"""Power Max Tracker integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import ConfigEntryNotReady
from .const import DOMAIN, CONF_SOURCE_SENSOR, CONF_MONTHLY_RESET, CONF_NUM_MAX_VALUES, CONF_BINARY_SENSOR
from .coordinator import PowerMaxCoordinator
from . import sensor  # noqa: F401

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_SOURCE_SENSOR): cv.entity_id,
                        vol.Optional(CONF_NUM_MAX_VALUES, default=2): vol.All(
                            vol.Coerce(int), vol.Range(min=1, max=10)
                        ),
                        vol.Optional(CONF_MONTHLY_RESET, default=False): cv.boolean,
                        vol.Optional(CONF_BINARY_SENSOR): cv.entity_id,
                    }
                )
            ],
        )
    },
    extra=vol.ALLOW_EXTRA,
)

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
                await coord.async_reset_max_values_manually()

    if not hass.services.has_service(DOMAIN, "update_max_values"):
        hass.services.async_register(DOMAIN, "update_max_values", update_max_values_service)
    if not hass.services.has_service(DOMAIN, "reset_max_values"):
        hass.services.async_register(DOMAIN, "reset_max_values", reset_max_values_service)

    if DOMAIN not in config:
        return True

    # Process YAML configuration with proper entry management
    yaml_configs = []
    for conf in config[DOMAIN]:
        num_max_values = conf.get(CONF_NUM_MAX_VALUES, 2)
        if not isinstance(num_max_values, int) or not (1 <= num_max_values <= 10):
            _LOGGER.error("num_max_values must be an integer between 1 and 10")
            continue

        yaml_config = {
            CONF_SOURCE_SENSOR: conf.get(CONF_SOURCE_SENSOR),
            CONF_NUM_MAX_VALUES: num_max_values,
            CONF_MONTHLY_RESET: conf.get(CONF_MONTHLY_RESET, False),
            CONF_BINARY_SENSOR: conf.get(CONF_BINARY_SENSOR),
        }
        yaml_configs.append(yaml_config)

    # Update existing entries and create new ones as needed
    existing_entries = {
        entry.entry_id: entry for entry in hass.config_entries.async_entries(DOMAIN)
    }
    processed_entry_ids = set()

    for yaml_config in yaml_configs:
        # Find existing entry with matching config
        matching_entry = None
        for entry in existing_entries.values():
            if (
                entry.source == config_entries.SOURCE_IMPORT
                and entry.data.get(CONF_SOURCE_SENSOR)
                == yaml_config[CONF_SOURCE_SENSOR]
                and entry.data.get(CONF_NUM_MAX_VALUES)
                == yaml_config[CONF_NUM_MAX_VALUES]
                and entry.data.get(CONF_MONTHLY_RESET)
                == yaml_config[CONF_MONTHLY_RESET]
                and entry.data.get(CONF_BINARY_SENSOR)
                == yaml_config[CONF_BINARY_SENSOR]
            ):
                matching_entry = entry
                break

        if matching_entry:
            # Entry already exists with correct config, mark as processed
            processed_entry_ids.add(matching_entry.entry_id)
            _LOGGER.debug(
                f"YAML entry already exists for {yaml_config[CONF_SOURCE_SENSOR]}"
            )
        else:
            # Create new entry for this YAML config
            _LOGGER.debug(
                f"Creating new YAML entry for {yaml_config[CONF_SOURCE_SENSOR]}"
            )
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_IMPORT},
                    data=yaml_config,
                )
            )

    # Remove YAML entries that are no longer in configuration
    for entry_id, entry in existing_entries.items():
        if (
            entry.source == config_entries.SOURCE_IMPORT
            and entry_id not in processed_entry_ids
        ):
            _LOGGER.debug(f"Removing obsolete YAML entry: {entry_id}")
            await hass.config_entries.async_remove(entry_id)

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
