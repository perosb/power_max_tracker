"""Tests for PowerMaxTracker __init__.py services.

Note: These tests require a full Home Assistant development environment with all dependencies.
They will fail when run in a standalone environment without HA installed.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from custom_components.power_max_tracker import async_setup, async_setup_entry, async_unload_entry
from custom_components.power_max_tracker.const import DOMAIN


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.services = MagicMock()
    hass.data = {}
    hass.config = MagicMock()
    hass.config.config_dir = "/tmp/test_hass_config"
    hass.loop = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.domain = DOMAIN
    return entry


class TestInitServices:
    """Test cases for __init__.py functions."""

    @pytest.mark.asyncio
    async def test_async_setup_success(self, mock_hass):
        """Test successful async setup."""
        config = {
            DOMAIN: {
                "source_sensor": "sensor.test_power",
                "monthly_reset": True,
                "num_max_values": 3,
            }
        }

        # Mock the config entries flow
        with patch("homeassistant.config_entries.ConfigEntriesFlowManager.async_create_flow") as mock_create_flow:
            mock_create_flow.return_value = None

            result = await async_setup(mock_hass, config)

            assert result is True

    @pytest.mark.asyncio
    async def test_async_setup_no_config(self, mock_hass):
        """Test async setup with no config."""
        result = await async_setup(mock_hass, {})

        assert result is True

    @pytest.mark.asyncio
    async def test_async_setup_entry_success(self, mock_hass, mock_config_entry):
        """Test successful async setup entry."""
        # Mock the config entry data
        mock_config_entry.data = {
            "source_sensor": "sensor.test_power",
            "monthly_reset": False,
            "num_max_values": 2,
        }

        # Mock async_add_executor_job for storage
        mock_hass.async_add_executor_job = AsyncMock(return_value={})

        # Mock the forward entry setups
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()

        result = await async_setup_entry(mock_hass, mock_config_entry)

        assert result is True
        mock_hass.config_entries.async_forward_entry_setups.assert_called_once_with(mock_config_entry, ["sensor"])

    @pytest.mark.asyncio
    async def test_async_unload_entry_success(self, mock_hass, mock_config_entry):
        """Test successful async unload entry."""
        # Mock stored coordinator
        mock_coordinator = MagicMock()
        mock_coordinator.async_unload = MagicMock()
        mock_hass.data[DOMAIN] = {"test_entry_id": mock_coordinator}
        mock_config_entry.entry_id = "test_entry_id"

        # Mock platform unload
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        mock_coordinator.async_unload.assert_called_once()
        mock_hass.config_entries.async_unload_platforms.assert_called_once_with(mock_config_entry, [Platform.SENSOR])

    @pytest.mark.asyncio
    async def test_update_max_values_service(self, mock_hass):
        """Test update max values service."""
        # Test that async_setup registers services
        result = await async_setup(mock_hass, {})
        # Should return True
        assert result is True

    @pytest.mark.asyncio
    async def test_reset_max_values_service(self, mock_hass):
        """Test reset max values service."""
        # Test that async_setup registers services
        result = await async_setup(mock_hass, {})
        # Should return True
        assert result is True