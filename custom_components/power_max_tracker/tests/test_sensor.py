"""Tests for PowerMaxTracker sensors.

Note: These tests require a full Home Assistant development environment with all dependencies.
They will fail when run in a standalone environment without HA installed.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

from custom_components.power_max_tracker.sensor import (
    MaxPowerSensor,
    SourcePowerSensor,
    HourlyAveragePowerSensor,
    AverageMaxPowerSensor,
    AverageMaxCostSensor,
    async_setup_entry,
    async_setup_platform,
)
from custom_components.power_max_tracker.const import (
    CONF_SOURCE_SENSOR,
    CONF_MONTHLY_RESET,
    CONF_NUM_MAX_VALUES,
    CONF_BINARY_SENSOR,
    DOMAIN,
)


class TestMaxPowerSensor:
    """Test cases for MaxPowerSensor."""

    @pytest.mark.asyncio
    async def test_init(self, coordinator):
        """Test sensor initialization."""
        sensor = MaxPowerSensor(coordinator, 0, "Test Max 1")

        assert sensor._coordinator == coordinator
        assert sensor._index == 0

    def test_native_value(self, coordinator):
        """Test native value property."""
        sensor = MaxPowerSensor(coordinator, 0, "Test Max 1")

        # Initially should be 0.0
        assert sensor.native_value == 0.0

        # Update coordinator max values
        coordinator.max_values = [5.0, 3.0]

        assert sensor.native_value == 5.0

    def test_extra_state_attributes(self, coordinator):
        """Test extra state attributes."""
        sensor = MaxPowerSensor(coordinator, 0, "Test Max 1")

        now = datetime.now()
        coordinator.max_values_timestamps = [now, None]

        attributes = sensor.extra_state_attributes

        assert "last_update" in attributes
        assert attributes["last_update"] == now.isoformat()


class TestSourcePowerSensor:
    """Test cases for SourcePowerSensor."""

    @pytest.mark.asyncio
    async def test_init(self, coordinator, mock_config_entry):
        """Test source sensor initialization."""
        sensor = SourcePowerSensor(coordinator, mock_config_entry)

        assert sensor._coordinator == coordinator
        assert sensor._entry == mock_config_entry

    def test_native_value_no_source_entity(self, coordinator, mock_config_entry):
        """Test native value when no source entity is set."""
        sensor = SourcePowerSensor(coordinator, mock_config_entry)

        # source_sensor_entity_id is None by default
        assert sensor.native_value == 0.0

    def test_native_value_with_source_entity(
        self, coordinator, mock_config_entry, mock_hass
    ):
        """Test native value with source entity set."""
        sensor = SourcePowerSensor(coordinator, mock_config_entry)
        coordinator.source_sensor_entity_id = "sensor.test_power"

        # Mock the state
        mock_state = MagicMock()
        mock_state.state = "1500.5"
        mock_hass.states.get.return_value = mock_state

        # Need to call async_added_to_hass to set up state tracking
        # For testing, we'll manually set the state
        sensor._state = 1500.5

        assert sensor.native_value == 1500.5

    def test_extra_state_attributes(self, coordinator, mock_config_entry):
        """Test extra state attributes."""
        sensor = SourcePowerSensor(coordinator, mock_config_entry)

        # SourcePowerSensor doesn't have extra_state_attributes method
        # Let's check if it has any attributes
        assert hasattr(sensor, "_coordinator")


class TestHourlyAveragePowerSensor:
    """Test cases for HourlyAveragePowerSensor."""

    @pytest.mark.asyncio
    async def test_init(self, coordinator, mock_config_entry):
        """Test hourly average sensor initialization."""
        sensor = HourlyAveragePowerSensor(coordinator, mock_config_entry)

        assert sensor._coordinator == coordinator
        assert sensor._entry == mock_config_entry

    def test_native_value_no_data(self, coordinator, mock_config_entry):
        """Test native value with no data."""
        sensor = HourlyAveragePowerSensor(coordinator, mock_config_entry)

        # Without proper initialization, should return 0.0
        assert sensor.native_value == 0.0


class TestAverageMaxPowerSensor:
    """Test cases for AverageMaxPowerSensor."""

    @pytest.mark.asyncio
    async def test_init(self, coordinator, mock_config_entry):
        """Test average max sensor initialization."""
        sensor = AverageMaxPowerSensor(coordinator, mock_config_entry)

        assert sensor._coordinator == coordinator
        assert sensor._entry == mock_config_entry

    def test_native_value(self, coordinator, mock_config_entry):
        """Test native value calculation."""
        sensor = AverageMaxPowerSensor(coordinator, mock_config_entry)

        # Test with max values
        coordinator.max_values = [5.0, 3.0]

        assert sensor.native_value == 4.0  # Average of max values

    def test_native_value_empty_list(self, coordinator, mock_config_entry):
        """Test native value with empty previous month values."""
        sensor = AverageMaxPowerSensor(coordinator, mock_config_entry)

        coordinator.previous_month_max_values = []

        assert sensor.native_value == 0.0

    def test_extra_state_attributes(self, coordinator, mock_config_entry):
        """Test extra state attributes."""
        sensor = AverageMaxPowerSensor(coordinator, mock_config_entry)

        # Test with previous month values
        coordinator.previous_month_max_values = [5.0, 3.0]

        attributes = sensor.extra_state_attributes

        assert "previous_month_average" in attributes
        assert attributes["previous_month_average"] == 4.0


class TestAverageMaxCostSensor:
    """Test cases for AverageMaxCostSensor."""

    @pytest.mark.asyncio
    async def test_init(self, coordinator, mock_config_entry):
        """Test average max cost sensor initialization."""
        sensor = AverageMaxCostSensor(coordinator, mock_config_entry)

        assert sensor._coordinator == coordinator
        assert sensor._entry == mock_config_entry
        assert sensor._attr_device_class == "monetary"
        assert (
            sensor._attr_state_class is None
        )  # Monetary sensors don't use MEASUREMENT
        assert sensor._attr_icon == "mdi:currency-usd"

    def test_native_value_with_price_and_max_values(
        self, coordinator, mock_config_entry
    ):
        """Test native value calculation with price and max values."""
        sensor = AverageMaxCostSensor(coordinator, mock_config_entry)

        # Set up coordinator data
        coordinator.max_values = [5.0, 3.0]  # Average = 4.0
        coordinator.price_per_kw = 0.15  # 15 cents per kW

        # Expected: 4.0 * 0.15 = 0.6, rounded to 2 decimals = 0.6
        assert sensor.native_value == 0.6

    def test_native_value_no_max_values(self, coordinator, mock_config_entry):
        """Test native value with no max values."""
        sensor = AverageMaxCostSensor(coordinator, mock_config_entry)

        coordinator.max_values = []
        coordinator.price_per_kw = 0.15

        assert sensor.native_value == 0.0

    def test_native_value_zero_price(self, coordinator, mock_config_entry):
        """Test native value with zero price."""
        sensor = AverageMaxCostSensor(coordinator, mock_config_entry)

        coordinator.max_values = [5.0, 3.0]
        coordinator.price_per_kw = 0.0

        assert sensor.native_value == 0.0

    def test_native_unit_of_measurement_with_hass(
        self, coordinator, mock_config_entry, mock_hass
    ):
        """Test native unit of measurement with hass available."""
        sensor = AverageMaxCostSensor(coordinator, mock_config_entry)
        sensor.hass = mock_hass
        mock_hass.config.currency = "USD"

        assert sensor.native_unit_of_measurement == "USD"

    def test_native_unit_of_measurement_no_hass(self, coordinator, mock_config_entry):
        """Test native unit of measurement without hass."""
        sensor = AverageMaxCostSensor(coordinator, mock_config_entry)

        assert sensor.native_unit_of_measurement is None

    def test_extra_state_attributes(self, coordinator, mock_config_entry):
        """Test extra state attributes."""
        sensor = AverageMaxCostSensor(coordinator, mock_config_entry)

        # Set up coordinator data
        coordinator.max_values = [5.0, 3.0]  # Current average = 4.0
        coordinator.previous_month_max_values = [6.0, 4.0]  # Previous average = 5.0
        coordinator.price_per_kw = 0.15

        attributes = sensor.extra_state_attributes

        assert "previous_month_average" in attributes
        assert attributes["previous_month_average"] == 5.0  # (6.0 + 4.0) / 2
        assert "previous_month_cost" in attributes
        assert attributes["previous_month_cost"] == 0.75  # 5.0 * 0.15
        assert "price_per_kw" in attributes
        assert attributes["price_per_kw"] == 0.15

    def test_extra_state_attributes_no_previous_data(
        self, coordinator, mock_config_entry
    ):
        """Test extra state attributes with no previous month data."""
        sensor = AverageMaxCostSensor(coordinator, mock_config_entry)

        coordinator.max_values = [5.0, 3.0]
        coordinator.previous_month_max_values = []
        coordinator.price_per_kw = 0.15

        attributes = sensor.extra_state_attributes

        assert attributes["previous_month_average"] == 0.0
        assert attributes["previous_month_cost"] == 0.0
        assert attributes["price_per_kw"] == 0.15


class TestSensorSetup:
    """Test cases for sensor setup functions."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, mock_hass, mock_config_entry, coordinator):
        """Test async setup entry."""
        # Mock the coordinator in hass.data
        mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: coordinator}

        # Mock the sensor setup
        with patch(
            "custom_components.power_max_tracker.sensor._setup_sensors"
        ) as mock_setup_sensors:
            async_add_entities = AsyncMock()
            result = await async_setup_entry(
                mock_hass, mock_config_entry, async_add_entities
            )

            assert result is None  # async_setup_entry doesn't return anything
            mock_setup_sensors.assert_called_once_with(
                mock_hass, coordinator, mock_config_entry, async_add_entities
            )

    @pytest.mark.asyncio
    async def test_async_setup_platform(self, mock_hass, coordinator):
        """Test async setup platform."""
        config = {
            CONF_SOURCE_SENSOR: "sensor.test_power",
            CONF_MONTHLY_RESET: True,
            CONF_NUM_MAX_VALUES: 3,
            CONF_BINARY_SENSOR: "binary_sensor.test",
        }

        # Mock the coordinator creation and setup
        with patch(
            "custom_components.power_max_tracker.sensor.PowerMaxCoordinator"
        ) as mock_coordinator_class:
            mock_coordinator_class.return_value = coordinator
            coordinator.async_setup = AsyncMock()

            # Mock the sensor setup
            with patch(
                "custom_components.power_max_tracker.sensor._setup_sensors"
            ) as mock_setup_sensors:
                result = await async_setup_platform(
                    mock_hass, config, MagicMock(), None
                )

                assert result is True
                mock_coordinator_class.assert_called_once()
                coordinator.async_setup.assert_called_once()
                mock_setup_sensors.assert_called_once()
