"""Tests for PowerMaxTracker config flow.

Note: These tests require a full Home Assistant development environment with all dependencies.
They will fail when run in a standalone environment without HA installed.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.power_max_tracker.config_flow import PowerMaxTrackerConfigFlow
from custom_components.power_max_tracker.const import (
    CONF_SOURCE_SENSOR,
    CONF_MONTHLY_RESET,
    CONF_NUM_MAX_VALUES,
    CONF_BINARY_SENSOR,
    CONF_POWER_SCALING_FACTOR,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    return hass


class TestPowerMaxTrackerConfigFlow:
    """Test cases for PowerMaxTrackerConfigFlow."""

    def test_get_schema(self, mock_hass):
        """Test schema generation."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass

        schema = flow._get_schema()

        # Check that schema is a vol.Schema object
        assert schema is not None
        # We can't easily check individual fields in a vol.Schema, but we can verify it's callable
        assert callable(schema)

    @pytest.mark.asyncio
    async def test_async_step_user_success(self, mock_hass):
        """Test successful user step."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass

        user_input = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: True,
            CONF_NUM_MAX_VALUES: 3,
            CONF_BINARY_SENSOR: "binary_sensor.test",
            CONF_POWER_SCALING_FACTOR: 0.5,
        }

        # Mock async_set_unique_id and async_create_entry
        flow.async_set_unique_id = AsyncMock()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        with patch("uuid.uuid4", return_value="12345678-1234-1234-1234-123456789012"):
            result = await flow.async_step_user(user_input)

        assert result["type"] == "create_entry"
        flow.async_set_unique_id.assert_called_once_with("power_max_tracker_sensor_test_power")
        expected_data = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: True,
            CONF_NUM_MAX_VALUES: 3,
            CONF_BINARY_SENSOR: "binary_sensor.test",
            CONF_POWER_SCALING_FACTOR: 0.5,
        }
        flow.async_create_entry.assert_called_once_with(
            title="Power Max Tracker (test_power-12345678)",
            data=expected_data
        )

    @pytest.mark.asyncio
    async def test_async_step_user_no_input(self, mock_hass):
        """Test user step with no input."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass

        result = await flow.async_step_user(None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_async_step_import_success(self, mock_hass):
        """Test successful import step."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass

        import_config = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: False,
            CONF_NUM_MAX_VALUES: 2,
            CONF_BINARY_SENSOR: None,
        }

        # Mock async_set_unique_id and async_create_entry
        flow.async_set_unique_id = AsyncMock()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        with patch("uuid.uuid4", return_value="12345678-1234-1234-1234-123456789012"):
            result = await flow.async_step_import(import_config)

        assert result["type"] == "create_entry"
        flow.async_set_unique_id.assert_called_once_with("power_max_tracker_sensor_test_power")
        expected_data = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: False,
            CONF_NUM_MAX_VALUES: 2,
            CONF_POWER_SCALING_FACTOR: 1.0,
            CONF_BINARY_SENSOR: None,
        }
        flow.async_create_entry.assert_called_once_with(
            title="Power Max Tracker (test_power-12345678)",
            data=expected_data
        )

    @pytest.mark.asyncio
    async def test_create_entry(self, mock_hass):
        """Test entry creation."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass
        flow.context = {}

        data = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: True,
            CONF_NUM_MAX_VALUES: 3,
            CONF_BINARY_SENSOR: "binary_sensor.test",
            CONF_POWER_SCALING_FACTOR: 1.0,
        }

        # Mock the async methods
        flow.async_set_unique_id = AsyncMock()
        flow.async_create_entry = MagicMock(return_value={
            "title": "Power Max Tracker (test_power-12345678)", 
            "data": data
        })

        with patch("uuid.uuid4", return_value="12345678-1234-1234-1234-123456789012"):
            entry = await flow._create_entry(data)

        assert entry["title"] == "Power Max Tracker (test_power-12345678)"
        assert entry["data"] == data

    @pytest.mark.asyncio
    async def test_async_step_reconfigure_success(self, mock_hass):
        """Test successful reconfiguration."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass

        # Mock the reconfigure entry
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_SOURCE_SENSOR: "sensor.old_power",
            CONF_MONTHLY_RESET: False,
            CONF_NUM_MAX_VALUES: 2,
            CONF_BINARY_SENSOR: None,
            CONF_POWER_SCALING_FACTOR: 1.0,
        }
        flow._get_reconfigure_entry = MagicMock(return_value=mock_entry)

        user_input = {
            CONF_SOURCE_SENSOR: "sensor.new_power",
            CONF_MONTHLY_RESET: True,
            CONF_NUM_MAX_VALUES: 5,
            CONF_BINARY_SENSOR: "binary_sensor.new",
            CONF_POWER_SCALING_FACTOR: 2.0,
        }

        # Mock async_update_reload_and_abort
        flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})

        result = await flow.async_step_reconfigure(user_input)

        assert result["type"] == "abort"
        expected_data = {
            CONF_SOURCE_SENSOR: "sensor.new_power",
            CONF_MONTHLY_RESET: True,
            CONF_NUM_MAX_VALUES: 5,
            CONF_BINARY_SENSOR: "binary_sensor.new",
            CONF_POWER_SCALING_FACTOR: 2.0,
        }
        flow.async_update_reload_and_abort.assert_called_once_with(
            mock_entry, data=expected_data
        )

    @pytest.mark.asyncio
    async def test_async_step_reconfigure_no_input(self, mock_hass):
        """Test reconfiguration step with no input."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass

        # Mock the reconfigure entry
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: True,
            CONF_NUM_MAX_VALUES: 3,
        }
        flow._get_reconfigure_entry = MagicMock(return_value=mock_entry)

        result = await flow.async_step_reconfigure(None)

        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure"

    @pytest.mark.asyncio
    async def test_async_step_reconfigure_invalid_max_values(self, mock_hass):
        """Test reconfiguration with invalid max values."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass

        # Mock the reconfigure entry
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: False,
            CONF_NUM_MAX_VALUES: 2,
        }
        flow._get_reconfigure_entry = MagicMock(return_value=mock_entry)

        user_input = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_NUM_MAX_VALUES: 15,  # Invalid: > 10
        }

        result = await flow.async_step_reconfigure(user_input)

        assert result["type"] == "form"
        assert result["errors"] == {"base": "invalid_max_values"}

    def test_get_reconfigure_schema(self, mock_hass):
        """Test reconfigure schema generation."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass

        # Mock the reconfigure entry
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: True,
            CONF_NUM_MAX_VALUES: 3,
            CONF_BINARY_SENSOR: "binary_sensor.test",
            CONF_POWER_SCALING_FACTOR: 2.5,
        }

        schema = flow._get_reconfigure_schema(mock_entry)

        # Check that schema is a vol.Schema object
        assert schema is not None
        assert callable(schema)

    def test_get_reconfigure_schema_no_binary_sensor(self, mock_hass):
        """Test reconfigure schema generation when binary sensor is not configured."""
        flow = PowerMaxTrackerConfigFlow()
        flow.hass = mock_hass

        # Mock the reconfigure entry with no binary sensor
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: True,
            CONF_NUM_MAX_VALUES: 3,
            CONF_BINARY_SENSOR: None,  # Not configured
            CONF_POWER_SCALING_FACTOR: 2.5,
        }

        schema = flow._get_reconfigure_schema(mock_entry)

        # Check that schema is a vol.Schema object and doesn't fail
        assert schema is not None
        assert callable(schema)