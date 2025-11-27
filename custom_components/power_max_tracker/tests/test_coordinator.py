"""Tests for PowerMaxCoordinator.

Note: These tests require a full Home Assistant development environment with all dependencies.
They will fail when run in a standalone environment without HA installed.
For basic unit testing of helper methods, use test_coordinator_helpers.py instead.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from homeassistant.helpers.storage import Store

from custom_components.power_max_tracker.const import (
    MAX_VALUES_STORAGE_KEY,
    TIMESTAMPS_STORAGE_KEY,
    PREVIOUS_MONTH_STORAGE_KEY,
)


class TestPowerMaxCoordinator:
    """Test cases for PowerMaxCoordinator."""

    def test_init(self, coordinator, mock_hass, mock_config_entry):
        """Test coordinator initialization."""
        assert coordinator.hass == mock_hass
        assert coordinator.entry == mock_config_entry
        assert coordinator.source_sensor == "sensor.test_power"
        assert coordinator.monthly_reset is False
        assert coordinator.num_max_values == 2
        assert coordinator.binary_sensor is None
        assert coordinator.max_values == [0.0, 0.0]
        assert coordinator.max_values_timestamps == [None, None]
        assert coordinator.previous_month_max_values == []
        assert isinstance(coordinator._max_values_store, Store)
        assert coordinator.entities == []
        assert coordinator._listeners == []

    def test_watts_to_kilowatts_conversion(self, coordinator):
        """Test watts to kilowatts conversion."""
        assert coordinator._watts_to_kilowatts(1000) == 1.0
        assert coordinator._watts_to_kilowatts(500) == 0.5
        assert coordinator._watts_to_kilowatts(0) == 0.0
        assert coordinator._watts_to_kilowatts(2500) == 2.5

    def test_average_max_value_empty_list(self, coordinator):
        """Test average_max_value property with empty max_values list."""
        # Default coordinator has empty max_values [0.0, 0.0], but let's test with truly empty
        coordinator.max_values = []
        assert coordinator.average_max_value == 0.0

    def test_average_max_value_single_value(self, coordinator):
        """Test average_max_value property with single value."""
        coordinator.max_values = [5.0]
        assert coordinator.average_max_value == 5.0

    def test_average_max_value_multiple_values(self, coordinator):
        """Test average_max_value property with multiple values."""
        coordinator.max_values = [10.0, 6.0, 8.0]
        assert coordinator.average_max_value == 8.0  # (10 + 6 + 8) / 3 = 8.0

    def test_average_max_value_with_zeros(self, coordinator):
        """Test average_max_value property with some zero values."""
        coordinator.max_values = [10.0, 0.0, 5.0]
        assert coordinator.average_max_value == 5.0  # (10 + 0 + 5) / 3 = 5.0

    def test_previous_month_average_max_value_empty_list(self, coordinator):
        """Test previous_month_average_max_value property with empty list."""
        # Default is already empty
        assert coordinator.previous_month_average_max_value == 0.0

    def test_previous_month_average_max_value_single_value(self, coordinator):
        """Test previous_month_average_max_value property with single value."""
        coordinator.previous_month_max_values = [7.5]
        assert coordinator.previous_month_average_max_value == 7.5

    def test_previous_month_average_max_value_multiple_values(self, coordinator):
        """Test previous_month_average_max_value property with multiple values."""
        coordinator.previous_month_max_values = [12.0, 8.0, 10.0]
        assert (
            coordinator.previous_month_average_max_value == 10.0
        )  # (12 + 8 + 10) / 3 = 10.0

    def test_previous_month_average_max_value_with_zeros(self, coordinator):
        """Test previous_month_average_max_value property with some zero values."""
        coordinator.previous_month_max_values = [15.0, 0.0, 5.0]
        assert (
            coordinator.previous_month_average_max_value == 6.666666666666667
        )  # (15 + 0 + 5) / 3

    def test_update_max_values_with_timestamp_new_value(self, coordinator):
        """Test updating max values with a new value."""
        now = datetime.now()

        # Test adding first value
        result = coordinator._update_max_values_with_timestamp(5.0, now)
        assert result is True
        assert coordinator.max_values == [5.0, 0.0]
        assert coordinator.max_values_timestamps == [now, None]

        # Test adding second value
        result = coordinator._update_max_values_with_timestamp(3.0, now)
        assert result is True
        assert coordinator.max_values == [5.0, 3.0]
        assert coordinator.max_values_timestamps == [now, now]

        # Test adding higher value that replaces existing
        result = coordinator._update_max_values_with_timestamp(7.0, now)
        assert result is True
        assert coordinator.max_values == [7.0, 5.0]
        assert coordinator.max_values_timestamps == [now, now]

    def test_update_max_values_with_timestamp_duplicate_value(self, coordinator):
        """Test updating max values with duplicate values."""
        now = datetime.now()

        # Add initial values
        coordinator._update_max_values_with_timestamp(5.0, now)
        coordinator._update_max_values_with_timestamp(3.0, now)

        # Try to add the same value again - should not update
        result = coordinator._update_max_values_with_timestamp(5.0, now)
        assert result is False  # No change because value already exists
        assert coordinator.max_values == [5.0, 3.0]

    def test_update_max_values_with_timestamp_no_change(self, coordinator):
        """Test updating max values with a value that doesn't make the top N."""
        now = datetime.now()

        # Fill with high values
        coordinator._update_max_values_with_timestamp(10.0, now)
        coordinator._update_max_values_with_timestamp(8.0, now)

        # Try to add a low value that doesn't make the cut
        result = coordinator._update_max_values_with_timestamp(1.0, now)
        assert result is False
        assert coordinator.max_values == [10.0, 8.0]

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_query_hourly_statistics_success(
        self, mock_get_instance, coordinator
    ):
        """Test successful hourly statistics query."""
        # Set the source sensor entity ID for the test
        coordinator.source_sensor_entity_id = "sensor.test_power"
        
        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder

        # Mock the async_add_executor_job call
        mock_recorder.async_add_executor_job = AsyncMock()

        # Mock statistics response
        stats_data = {"sensor.test_power": [{"mean": 1500.0}]}
        mock_recorder.async_add_executor_job.return_value = stats_data

        start_time = datetime.now()
        end_time = start_time + timedelta(hours=1)

        result = await coordinator._query_hourly_statistics(start_time, end_time)

        assert result == 1500.0
        mock_recorder.async_add_executor_job.assert_called_once()

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_query_hourly_statistics_no_data(
        self, mock_get_instance, coordinator
    ):
        """Test hourly statistics query with no data."""
        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder

        # Mock the async_add_executor_job call
        mock_recorder.async_add_executor_job = AsyncMock()

        # Mock empty statistics response
        stats_data = {}
        mock_recorder.async_add_executor_job.return_value = stats_data

        start_time = datetime.now()
        end_time = start_time + timedelta(hours=1)

        result = await coordinator._query_hourly_statistics(start_time, end_time)

        assert result is None

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_query_hourly_statistics_none_mean(
        self, mock_get_instance, coordinator
    ):
        """Test hourly statistics query with None mean value."""
        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder

        # Mock the async_add_executor_job call
        mock_recorder.async_add_executor_job = AsyncMock()

        # Mock statistics response with None mean
        stats_data = {"sensor.test_power": [{"mean": None}]}
        mock_recorder.async_add_executor_job.return_value = stats_data

        start_time = datetime.now()
        end_time = start_time + timedelta(hours=1)

        result = await coordinator._query_hourly_statistics(start_time, end_time)

        assert result is None

    def test_is_valid_entity_valid(self, coordinator):
        """Test entity validation with valid entity."""
        mock_entity = MagicMock()
        mock_entity._attr_unique_id = "test_max_values_1"
        mock_entity.entity_id = "sensor.test"
        mock_entity.async_write_ha_state = MagicMock()

        assert coordinator._is_valid_entity(mock_entity) is True

    def test_is_valid_entity_invalid(self, coordinator):
        """Test entity validation with invalid entity."""
        # Test None entity
        assert coordinator._is_valid_entity(None) is False

        # Test entity without required attributes
        mock_entity = MagicMock()
        # Configure the mock to not have the required attributes
        mock_entity._attr_unique_id = None
        mock_entity.entity_id = None
        mock_entity.async_write_ha_state = None
        assert coordinator._is_valid_entity(mock_entity) is False

    def test_can_update_max_values_no_binary_sensor(self, coordinator):
        """Test max values update check without binary sensor."""
        assert coordinator._can_update_max_values() is True

    def test_can_update_max_values_with_binary_sensor_on(self, coordinator, mock_hass):
        """Test max values update check with binary sensor in 'on' state."""
        coordinator.binary_sensor = "binary_sensor.test"

        mock_state = MagicMock()
        mock_state.state = "on"
        mock_hass.states.get.return_value = mock_state

        assert coordinator._can_update_max_values() is True

    def test_can_update_max_values_with_binary_sensor_off(self, coordinator, mock_hass):
        """Test max values update check with binary sensor in 'off' state."""
        coordinator.binary_sensor = "binary_sensor.test"

        mock_state = MagicMock()
        mock_state.state = "off"
        mock_hass.states.get.return_value = mock_state

        assert coordinator._can_update_max_values() is False

    def test_can_update_max_values_with_binary_sensor_unavailable(
        self, coordinator, mock_hass
    ):
        """Test max values update check with unavailable binary sensor."""
        coordinator.binary_sensor = "binary_sensor.test"

        mock_hass.states.get.return_value = None

        assert coordinator._can_update_max_values() is False

    @pytest.mark.asyncio
    async def test_async_setup_with_stored_data(self, coordinator, mock_hass):
        """Test async setup with stored data including timestamp strings."""
        # Mock stored data with timestamp strings
        stored_data = {
            MAX_VALUES_STORAGE_KEY: [5.0, 3.0],
            TIMESTAMPS_STORAGE_KEY: ["2023-01-01T12:00:00", "2023-01-01T13:00:00"],
            PREVIOUS_MONTH_STORAGE_KEY: [4.0, 2.0],
        }

        mock_store = MagicMock()
        mock_store.async_load = AsyncMock(return_value=stored_data)
        coordinator._max_values_store = mock_store

        await coordinator.async_setup()

        # Check that timestamps were converted to datetime objects
        assert len(coordinator.max_values_timestamps) == 2
        assert isinstance(coordinator.max_values_timestamps[0], datetime)
        assert isinstance(coordinator.max_values_timestamps[1], datetime)
        assert coordinator.previous_month_max_values == [4.0, 2.0]

    @pytest.mark.asyncio
    async def test_save_max_values_data(self, coordinator):
        """Test saving max values data to storage."""
        mock_store = MagicMock()
        mock_store.async_save = AsyncMock()
        coordinator._max_values_store = mock_store

        # Set some test data
        coordinator.max_values = [10.0, 8.0]
        coordinator.max_values_timestamps = [datetime.now(), datetime.now()]
        coordinator.previous_month_max_values = [5.0, 3.0]

        await coordinator._save_max_values_data()

        expected_data = {
            MAX_VALUES_STORAGE_KEY: [10.0, 8.0],
            TIMESTAMPS_STORAGE_KEY: coordinator.max_values_timestamps,
            PREVIOUS_MONTH_STORAGE_KEY: [5.0, 3.0],
        }

        mock_store.async_save.assert_called_once_with(expected_data)

    def test_add_entity_valid_source(self, coordinator):
        """Test adding a valid source entity."""
        mock_entity = MagicMock()
        mock_entity._attr_unique_id = "test_source"
        mock_entity.entity_id = "sensor.test_power"
        mock_entity.async_write_ha_state = MagicMock()

        coordinator.add_entity(mock_entity)

        assert mock_entity in coordinator.entities
        assert coordinator.source_sensor_entity_id == "sensor.test_power"

    def test_add_entity_valid_max_values(self, coordinator):
        """Test adding a valid max values entity."""
        mock_entity = MagicMock()
        mock_entity._attr_unique_id = "test_max_values_1"
        mock_entity.entity_id = "sensor.test_max_1"
        mock_entity.async_write_ha_state = MagicMock()

        coordinator.add_entity(mock_entity)

        assert mock_entity in coordinator.entities
        assert coordinator.source_sensor_entity_id is None  # Not a source entity

    def test_add_entity_invalid(self, coordinator):
        """Test adding an invalid entity."""
        mock_entity = MagicMock()
        # Invalid unique_id - doesn't match expected patterns
        mock_entity._attr_unique_id = "invalid_unique_id"
        mock_entity.entity_id = "sensor.test"
        mock_entity.async_write_ha_state = MagicMock()

        # Should not raise an exception, just not add the entity
        coordinator.add_entity(mock_entity)

        # Entity should not be added
        assert mock_entity not in coordinator.entities

    def test_auto_detect_scaling_factor_kw_unit(self, coordinator):
        """Test auto-detecting scaling factor for kW unit."""
        coordinator.source_sensor_entity_id = "sensor.test_power"

        # Mock the state with kW unit
        mock_state = MagicMock()
        mock_state.attributes = {"unit_of_measurement": "kW"}
        coordinator.hass.states.get.return_value = mock_state

        coordinator._auto_detect_scaling_factor()

        assert coordinator.power_scaling_factor == 1000.0

    def test_auto_detect_scaling_factor_watt_unit(self, coordinator):
        """Test auto-detecting scaling factor for W unit."""
        coordinator.source_sensor_entity_id = "sensor.test_power"

        # Mock the state with W unit
        mock_state = MagicMock()
        mock_state.attributes = {"unit_of_measurement": "W"}
        coordinator.hass.states.get.return_value = mock_state

        coordinator._auto_detect_scaling_factor()

        assert coordinator.power_scaling_factor == 1.0

    def test_auto_detect_scaling_factor_unknown_unit(self, coordinator):
        """Test auto-detecting scaling factor for unknown unit."""
        coordinator.source_sensor_entity_id = "sensor.test_power"

        # Mock the state with unknown unit
        mock_state = MagicMock()
        mock_state.attributes = {"unit_of_measurement": "unknown"}
        coordinator.hass.states.get.return_value = mock_state

        coordinator._auto_detect_scaling_factor()

        assert coordinator.power_scaling_factor == 1.0

    def test_auto_detect_scaling_factor_no_unit(self, coordinator):
        """Test auto-detecting scaling factor when no unit is available."""
        coordinator.source_sensor_entity_id = "sensor.test_power"

        # Mock the state with no unit
        mock_state = MagicMock()
        mock_state.attributes = {}
        coordinator.hass.states.get.return_value = mock_state

        coordinator._auto_detect_scaling_factor()

        assert coordinator.power_scaling_factor == 1.0

    def test_auto_detect_scaling_factor_no_source_entity(self, coordinator):
        """Test auto-detecting scaling factor when no source entity is set."""
        coordinator.source_sensor_entity_id = None
        coordinator.power_scaling_factor = 1.0

        coordinator._auto_detect_scaling_factor()

        # Should remain unchanged
        assert coordinator.power_scaling_factor == 1.0

    @pytest.mark.asyncio
    async def test_async_setup_no_stored_data(self, coordinator):
        """Test async setup with no stored data."""
        mock_store = MagicMock()
        mock_store.async_load = AsyncMock(return_value=None)
        coordinator._max_values_store = mock_store

        await coordinator.async_setup()

        # Should have listeners added
        assert len(coordinator._listeners) == 1  # Only hourly listener since monthly_reset is False

    @pytest.mark.asyncio
    async def test_async_setup_with_monthly_reset(self, coordinator):
        """Test async setup with monthly reset enabled."""
        coordinator.monthly_reset = True
        
        mock_store = MagicMock()
        mock_store.async_load = AsyncMock(return_value=None)
        coordinator._max_values_store = mock_store

        await coordinator.async_setup()

        # Should have both listeners
        assert len(coordinator._listeners) == 2

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_update_max_values_from_range_success(
        self, mock_get_instance, coordinator
    ):
        """Test updating max values from a range with successful statistics."""
        coordinator.source_sensor_entity_id = "sensor.test_power"
        
        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder
        mock_recorder.async_add_executor_job = AsyncMock()
        
        # Mock statistics response for 2 hours
        stats_data = {"sensor.test_power": [{"mean": 2000.0}]}  # 2 kW
        mock_recorder.async_add_executor_job.return_value = stats_data

        mock_store = MagicMock()
        mock_store.async_save = AsyncMock()
        coordinator._max_values_store = mock_store

        start_time = datetime.now()
        end_time = start_time + timedelta(hours=2)

        await coordinator._update_max_values_from_range(start_time, end_time)

        # Should have updated max values (2.0 kW added once, since duplicate values aren't added)
        assert coordinator.max_values == [2.0, 0.0]
        mock_store.async_save.assert_called_once()

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_async_update_hourly_success(
        self, mock_get_instance, coordinator
    ):
        """Test successful hourly update."""
        coordinator.source_sensor_entity_id = "sensor.test_power"
        
        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder
        mock_recorder.async_add_executor_job = AsyncMock()
        
        stats_data = {"sensor.test_power": [{"mean": 3000.0}]}  # 3 kW
        mock_recorder.async_add_executor_job.return_value = stats_data

        mock_store = MagicMock()
        mock_store.async_save = AsyncMock()
        coordinator._max_values_store = mock_store

        now = datetime.now()

        await coordinator._async_update_hourly(now)

        # Should have updated max values
        assert coordinator.max_values == [3.0, 0.0]
        mock_store.async_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_hourly_no_source_entity(self, coordinator):
        """Test hourly update when source entity is not set."""
        # source_sensor_entity_id is None by default
        now = datetime.now()

        # Should not raise an exception and should return early
        await coordinator._async_update_hourly(now)

        # Max values should remain unchanged
        assert coordinator.max_values == [0.0, 0.0]

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_async_update_max_values_from_midnight(
        self, mock_get_instance, coordinator
    ):
        """Test updating max values from midnight."""
        coordinator.source_sensor_entity_id = "sensor.test_power"
        
        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder
        mock_recorder.async_add_executor_job = AsyncMock()
        
        stats_data = {"sensor.test_power": [{"mean": 1000.0}]}  # 1 kW
        mock_recorder.async_add_executor_job.return_value = stats_data

        mock_store = MagicMock()
        mock_store.async_save = AsyncMock()
        coordinator._max_values_store = mock_store

        await coordinator.async_update_max_values_from_midnight()

        # Should have updated max values
        assert 1.0 in coordinator.max_values

    @pytest.mark.asyncio
    async def test_async_update_max_values_from_midnight_no_source(self, coordinator):
        """Test updating max values from midnight when no source entity."""
        # Should not raise an exception
        await coordinator.async_update_max_values_from_midnight()

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_async_update_max_values_to_current_month(
        self, mock_get_instance, coordinator
    ):
        """Test updating max values to current month."""
        coordinator.source_sensor_entity_id = "sensor.test_power"
        
        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder
        mock_recorder.async_add_executor_job = AsyncMock()
        
        stats_data = {"sensor.test_power": [{"mean": 4000.0}]}  # 4 kW
        mock_recorder.async_add_executor_job.return_value = stats_data

        mock_store = MagicMock()
        mock_store.async_save = AsyncMock()
        coordinator._max_values_store = mock_store

        await coordinator.async_update_max_values_to_current_month()

        # Should have reset and updated max values
        assert coordinator.max_values == [4.0, 0.0]

    @pytest.mark.asyncio
    async def test_update_entities_with_valid_entities(self, coordinator):
        """Test updating entities with valid entities."""
        mock_entity = MagicMock()
        mock_entity._attr_unique_id = "test_max_values_1"
        mock_entity.entity_id = "sensor.test"
        mock_entity.async_write_ha_state = MagicMock()
        mock_entity.async_schedule_update_ha_state = MagicMock()

        coordinator.entities = [mock_entity]

        await coordinator._update_entities("test update")

        mock_entity.async_schedule_update_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_entities_with_invalid_entities(self, coordinator):
        """Test updating entities with some invalid entities."""
        valid_entity = MagicMock()
        valid_entity._attr_unique_id = "test_max_values_1"
        valid_entity.entity_id = "sensor.test"
        valid_entity.async_write_ha_state = MagicMock()
        valid_entity.async_schedule_update_ha_state = MagicMock()

        invalid_entity = MagicMock()
        invalid_entity._attr_unique_id = "invalid_unique_id"  # Invalid
        invalid_entity.entity_id = "sensor.invalid"
        invalid_entity.async_write_ha_state = MagicMock()
        invalid_entity.async_schedule_update_ha_state = MagicMock()

        coordinator.entities = [valid_entity, invalid_entity]

        await coordinator._update_entities("test update")

        # Should have removed invalid entity
        assert len(coordinator.entities) == 1
        assert valid_entity in coordinator.entities
        assert invalid_entity not in coordinator.entities

    @pytest.mark.asyncio
    async def test_async_reset_monthly_first_of_month(self, coordinator):
        """Test monthly reset on the 1st of the month."""
        coordinator.monthly_reset = True
        coordinator.max_values = [5.0, 3.0]
        coordinator.previous_month_max_values = []

        mock_store = MagicMock()
        mock_store.async_save = AsyncMock()
        coordinator._max_values_store = mock_store

        # Create a datetime for the 1st of the month
        first_of_month = datetime(2023, 1, 1, 0, 0, 0)

        await coordinator._async_reset_monthly(first_of_month)

        # Should have stored previous values and reset
        assert coordinator.previous_month_max_values == [5.0, 3.0]
        assert coordinator.max_values == [0.0, 0.0]
        mock_store.async_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_reset_monthly_not_first_of_month(self, coordinator):
        """Test monthly reset not on the 1st of the month."""
        coordinator.monthly_reset = True
        coordinator.max_values = [5.0, 3.0]

        # Create a datetime for the 2nd of the month
        second_of_month = datetime(2023, 1, 2, 0, 0, 0)

        await coordinator._async_reset_monthly(second_of_month)

        # Should not have reset
        assert coordinator.max_values == [5.0, 3.0]

    def test_async_unload(self, coordinator):
        """Test unloading the coordinator."""
        mock_listener1 = MagicMock()
        mock_listener2 = MagicMock()
        coordinator._listeners = [mock_listener1, mock_listener2]

        coordinator.async_unload()

        mock_listener1.assert_called_once()
        mock_listener2.assert_called_once()
        assert coordinator._listeners == []
