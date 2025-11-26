import pytest
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.power_max_tracker.coordinator import PowerMaxCoordinator
from custom_components.power_max_tracker.const import (
    CONF_SOURCE_SENSOR,
    CONF_MONTHLY_RESET,
    CONF_NUM_MAX_VALUES,
    CONF_BINARY_SENSOR,
    DOMAIN,
)


@pytest.fixture(autouse=True, scope="session")
def verify_cleanup():
    """Override HA plugin's verify_cleanup fixture to prevent event loop issues."""
    pass


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.data = {}
    hass.config = MagicMock()
    hass.config.config_dir = "/tmp/test_hass_config"
    hass.config_entries = MagicMock()
    hass.loop = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.domain = DOMAIN
    entry.data = {
        CONF_SOURCE_SENSOR: "sensor.test_power",
        CONF_MONTHLY_RESET: False,
        CONF_NUM_MAX_VALUES: 2,
        CONF_BINARY_SENSOR: None,
    }
    return entry


@pytest.fixture
def coordinator(mock_hass, mock_config_entry):
    """Create a PowerMaxCoordinator instance."""
    return PowerMaxCoordinator(mock_hass, mock_config_entry)