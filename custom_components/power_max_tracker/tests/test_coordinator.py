"""Tests for PowerMaxCoordinator.

Note: These tests require a full Home Assistant development environment with all dependencies.
They will fail when run in a standalone environment without HA installed.
For basic unit testing of helper methods, use test_coordinator_helpers.py instead.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock

from homeassistant.helpers.storage import Store

from custom_components.power_max_tracker.const import (
    MAX_VALUES_STORAGE_KEY,
    TIMESTAMPS_STORAGE_KEY,
    PREVIOUS_MONTH_STORAGE_KEY,
    QUARTERLY_UPDATE_MINUTES,
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

    def test_get_current_cycle_start_hourly(self, coordinator):
        """Test _get_current_cycle_start for hourly cycles."""
        # Test various times for hourly cycles
        test_cases = [
            # (input_time, expected_start_time)
            (
                datetime(2023, 1, 1, 10, 30, 0),
                datetime(2023, 1, 1, 9, 0, 0),
            ),  # 10:30 -> previous hour start
            (
                datetime(2023, 1, 1, 11, 1, 0),
                datetime(2023, 1, 1, 10, 0, 0),
            ),  # 11:01 -> previous hour start
            (
                datetime(2023, 1, 1, 0, 15, 0),
                datetime(2022, 12, 31, 23, 0, 0),
            ),  # Midnight -> previous day
        ]

        for input_time, expected_start in test_cases:
            result = coordinator._get_current_cycle_start(input_time)
            assert result == expected_start, (
                f"Failed for {input_time}: expected {expected_start}, got {result}"
            )

    def test_get_current_cycle_start_quarterly(self, coordinator):
        """Test _get_current_cycle_start for quarterly cycles."""
        # Change coordinator to quarterly cycle
        coordinator.cycle_type = "quarterly"

        test_cases = [
            # (input_time, expected_start_time)
            (
                datetime(2023, 1, 1, 10, 15, 0),
                datetime(2023, 1, 1, 10, 0, 0),
            ),  # 10:15 -> 10:00
            (
                datetime(2023, 1, 1, 10, 30, 0),
                datetime(2023, 1, 1, 10, 15, 0),
            ),  # 10:30 -> 10:15
            (
                datetime(2023, 1, 1, 10, 45, 0),
                datetime(2023, 1, 1, 10, 30, 0),
            ),  # 10:45 -> 10:30
            (
                datetime(2023, 1, 1, 11, 0, 0),
                datetime(2023, 1, 1, 10, 45, 0),
            ),  # 11:00 -> 10:45
            (
                datetime(2023, 1, 1, 10, 7, 0),
                datetime(2023, 1, 1, 9, 45, 0),
            ),  # 10:07 -> 9:45
        ]

        for input_time, expected_start in test_cases:
            result = coordinator._get_current_cycle_start(input_time)
            assert result == expected_start, (
                f"Failed for {input_time}: expected {expected_start}, got {result}"
            )

    def test_period_property(self, coordinator):
        """Test period property for different cycle types."""
        # Default is hourly
        assert coordinator.period == "hour"

        # Change to quarterly
        coordinator.cycle_type = "quarterly"
        assert coordinator.period == "5minute"

    def test_seconds_per_cycle_property(self, coordinator):
        """Test seconds_per_cycle property for different cycle types."""
        # Default is hourly
        assert coordinator.seconds_per_cycle == 3600

        # Change to quarterly
        coordinator.cycle_type = "quarterly"
        assert coordinator.seconds_per_cycle == 900

    def test_update_minute_property(self, coordinator):
        """Test update_minute property for different cycle types."""
        # Default is hourly
        assert coordinator.update_minute == 1

        # Change to quarterly
        coordinator.cycle_type = "quarterly"
        assert coordinator.update_minute == QUARTERLY_UPDATE_MINUTES

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
        assert (
            coordinator.average_max_value == 7.5
        )  # (10 + 5) / 2 = 7.5 (zeros excluded)

    def test_average_max_value_with_negatives(self, coordinator):
        """Test average_max_value property with negative values."""
        coordinator.max_values = [10.0, -5.0, 5.0]
        assert (
            coordinator.average_max_value == 7.5
        )  # (10 + 5) / 2 = 7.5 (negatives excluded)

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
            coordinator.previous_month_average_max_value == 10.0
        )  # (15 + 5) / 2 = 10.0 (zeros excluded)

    def test_previous_month_average_max_value_with_negatives(self, coordinator):
        """Test previous_month_average_max_value property with negative values."""
        coordinator.previous_month_max_values = [15.0, -5.0, 5.0]
        assert (
            coordinator.previous_month_average_max_value == 10.0
        )  # (15 + 5) / 2 = 10.0 (negatives excluded)

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
    async def test_query_period_statistics_success(
        self, mock_get_instance, coordinator
    ):
        """Test successful period statistics query."""
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

        result = await coordinator._query_period_statistics(start_time, end_time)

        assert result == 1500.0
        mock_recorder.async_add_executor_job.assert_called_once()

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_query_period_statistics_no_data(
        self, mock_get_instance, coordinator
    ):
        """Test period statistics query with no data."""
        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder

        # Mock the async_add_executor_job call
        mock_recorder.async_add_executor_job = AsyncMock()

        # Mock empty statistics response
        stats_data = {}
        mock_recorder.async_add_executor_job.return_value = stats_data

        start_time = datetime.now()
        end_time = start_time + timedelta(hours=1)

        result = await coordinator._query_period_statistics(start_time, end_time)

        assert result is None

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_query_period_statistics_none_mean(
        self, mock_get_instance, coordinator
    ):
        """Test period statistics query with None mean value."""
        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder

        # Mock the async_add_executor_job call
        mock_recorder.async_add_executor_job = AsyncMock()

        # Mock statistics response with None mean
        stats_data = {"sensor.test_power": [{"mean": None}]}
        mock_recorder.async_add_executor_job.return_value = stats_data

        start_time = datetime.now()
        end_time = start_time + timedelta(hours=1)

        result = await coordinator._query_period_statistics(start_time, end_time)

        assert result is None

    def test_is_valid_entity_valid(self, coordinator):
        """Test entity validation with valid entity."""
        mock_entity = MagicMock()
        mock_entity._attr_unique_id = "test_max_values_1"
        mock_entity.entity_id = "sensor.test"
        mock_entity.async_write_ha_state = MagicMock()

        assert coordinator._is_valid_entity(mock_entity) is True

    def test_is_valid_entity_quarterly_cycle(self, coordinator_quarterly):
        """Test entity validation for quarterly cycles."""
        # Test quarterly average power entity
        mock_entity = MagicMock()
        mock_entity._attr_unique_id = "test_quarterly_average_power"
        mock_entity.entity_id = "sensor.test"
        mock_entity.async_write_ha_state = MagicMock()

        assert coordinator_quarterly._is_valid_entity(mock_entity) is True

        # Test that hourly entity is not valid for quarterly coordinator
        mock_entity_hourly = MagicMock()
        mock_entity_hourly._attr_unique_id = "test_hourly_average_power"
        mock_entity_hourly.entity_id = "sensor.test"
        mock_entity_hourly.async_write_ha_state = MagicMock()

        assert coordinator_quarterly._is_valid_entity(mock_entity_hourly) is False


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
    async def test_async_update_period_success(self, mock_get_instance, coordinator):
        """Test successful period update."""
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

        await coordinator._async_update_period(now)

        # Should have updated max values
        assert coordinator.max_values == [3.0, 0.0]
        mock_store.async_save.assert_called_once()

    @patch("custom_components.power_max_tracker.coordinator.get_instance")
    @pytest.mark.asyncio
    async def test_async_update_period_quarterly_success(
        self, mock_get_instance, coordinator
    ):
        """Test successful period update for quarterly cycles."""
        coordinator.cycle_type = "quarterly"
        coordinator.source_sensor_entity_id = "sensor.test_power"

        mock_recorder = MagicMock()
        mock_get_instance.return_value = mock_recorder
        mock_recorder.async_add_executor_job = AsyncMock()

        # For quarterly, it will make 3 calls for 5-minute periods
        # Each returning the same stats data
        stats_data = {"sensor.test_power": [{"mean": 1500.0}]}  # 1.5 kW
        mock_recorder.async_add_executor_job.return_value = stats_data

        mock_store = MagicMock()
        mock_store.async_save = AsyncMock()
        coordinator._max_values_store = mock_store

        # Test at 10:15 - should measure 10:00 to 10:15
        now = datetime(2023, 1, 1, 10, 15, 0)

        await coordinator._async_update_period(now)

        # Should have updated max values
        assert coordinator.max_values == [1.5, 0.0]  # Same average
        mock_store.async_save.assert_called_once()

        # Verify the statistics queries were called for 5-minute periods
        # Should have made 3 calls for 10:00-10:05, 10:05-10:10, 10:10-10:15
        assert mock_recorder.async_add_executor_job.call_count == 3

        # Check the first call
        first_call = mock_recorder.async_add_executor_job.call_args_list[0]
        start_time, end_time = first_call[0][2], first_call[0][3]
        expected_start = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        expected_end = datetime(2023, 1, 1, 10, 5, 0, tzinfo=timezone.utc)
        assert start_time == expected_start
        assert end_time == expected_end

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

    def test_single_peak_per_day_false_uses_hourly_logic(self, coordinator):
        """Test that single_peak_per_day=False uses hourly peak logic."""
        now = datetime(2025, 12, 9, 10, 0, 0)

        # Ensure single_peak_per_day is False (default)
        assert coordinator.single_peak_per_day is False

        # Add multiple values - should work like hourly peaks
        result1 = coordinator._update_max_values_with_timestamp(5.0, now)
        assert result1 is True
        assert coordinator.max_values == [5.0, 0.0]

        result2 = coordinator._update_max_values_with_timestamp(3.0, now)
        assert result2 is True
        assert coordinator.max_values == [5.0, 3.0]

    def test_single_peak_per_day_true_uses_daily_logic(self, coordinator):
        """Test that single_peak_per_day=True uses daily peak logic."""
        # Set single_peak_per_day to True
        coordinator.single_peak_per_day = True

        now = datetime(2025, 12, 9, 10, 0, 0)  # Dec 9, 2025, 10:00 AM

        # Add first value for today
        result1 = coordinator._update_max_values_with_timestamp(5.0, now)
        assert result1 is True
        assert coordinator.max_values == [5.0, 0.0]
        assert coordinator.max_values_timestamps[0].date() == now.date()

        # Add lower value for same day - should not update
        result2 = coordinator._update_max_values_with_timestamp(3.0, now)
        assert result2 is False  # No change because 3.0 < 5.0
        assert coordinator.max_values == [5.0, 0.0]

        # Add higher value for same day - should update
        result3 = coordinator._update_max_values_with_timestamp(7.0, now)
        assert result3 is True
        assert coordinator.max_values == [7.0, 0.0]

        # Add value for different day
        tomorrow = now + timedelta(days=1)
        result4 = coordinator._update_max_values_with_timestamp(4.0, tomorrow)
        assert result4 is True
        assert coordinator.max_values == [7.0, 4.0]
        assert coordinator.max_values_timestamps[0].date() == now.date()
        assert coordinator.max_values_timestamps[1].date() == tomorrow.date()

    def test_single_peak_per_day_multiple_days(self, coordinator):
        """Test single peak per day with multiple days and peak replacement."""
        coordinator.single_peak_per_day = True

        # Day 1: Add multiple values, should keep only the highest
        day1_time1 = datetime(2025, 12, 9, 10, 0, 0)
        day1_time2 = datetime(2025, 12, 9, 14, 0, 0)
        day1_time3 = datetime(2025, 12, 9, 18, 0, 0)

        coordinator._update_max_values_with_timestamp(5.0, day1_time1)
        coordinator._update_max_values_with_timestamp(
            8.0, day1_time2
        )  # Higher, should replace
        coordinator._update_max_values_with_timestamp(
            6.0, day1_time3
        )  # Lower, should not replace

        assert coordinator.max_values == [8.0, 0.0]
        assert coordinator.max_values_timestamps[0].date() == day1_time2.date()

        # Day 2: Add value
        day2_time = datetime(2025, 12, 10, 12, 0, 0)
        coordinator._update_max_values_with_timestamp(9.0, day2_time)

        assert coordinator.max_values == [9.0, 8.0]
        # After sorting, 9.0 (Day 2) should be first, 8.0 (Day 1) should be second
        assert coordinator.max_values_timestamps[0].date() == day2_time.date()
        assert coordinator.max_values_timestamps[1].date() == day1_time2.date()

        # Day 3: Add value that should become the highest
        day3_time = datetime(2025, 12, 11, 16, 0, 0)
        coordinator._update_max_values_with_timestamp(10.0, day3_time)

        assert coordinator.max_values == [10.0, 9.0]
        # After sorting, 10.0 (Day 3) should be first, 9.0 (Day 2) should be second
        assert coordinator.max_values_timestamps[0].date() == day3_time.date()
        assert coordinator.max_values_timestamps[1].date() == day2_time.date()

    def test_single_peak_per_day_max_values_limit(self, coordinator):
        """Test single peak per day respects num_max_values limit."""
        coordinator.single_peak_per_day = True
        coordinator.num_max_values = 2  # Limit to 2 values

        # Add values for 3 different days
        day1 = datetime(2025, 12, 9, 10, 0, 0)
        day2 = datetime(2025, 12, 10, 10, 0, 0)
        day3 = datetime(2025, 12, 11, 10, 0, 0)

        coordinator._update_max_values_with_timestamp(5.0, day1)
        coordinator._update_max_values_with_timestamp(6.0, day2)
        coordinator._update_max_values_with_timestamp(
            4.0, day3
        )  # Should not make top 2

        assert coordinator.max_values == [6.0, 5.0]  # Top 2 values
        assert coordinator.max_values_timestamps[0].date() == day2.date()
        assert coordinator.max_values_timestamps[1].date() == day1.date()
        assert len([x for x in coordinator.max_values if x > 0]) == 2

    def test_single_peak_per_day_midnight_wrap_around(self, coordinator):
        """Test single peak per day handles midnight transitions correctly."""
        coordinator.single_peak_per_day = True

        # Simulate values around midnight transition
        # Use explicit names for clarity
        BEFORE_MIDNIGHT = datetime(2025, 12, 9, 23, 30, 0)  # Dec 9, 11:30 PM
        AFTER_MIDNIGHT = datetime(2025, 12, 10, 0, 30, 0)  # Dec 10, 12:30 AM
        SAME_DAY_LATER = datetime(2025, 12, 10, 2, 0, 0)  # Dec 10, 2:00 AM

        coordinator._update_max_values_with_timestamp(5.0, BEFORE_MIDNIGHT)
        coordinator._update_max_values_with_timestamp(6.0, AFTER_MIDNIGHT)

        # Both should be treated as separate days
        assert coordinator.max_values == [6.0, 5.0]
        assert (
            coordinator.max_values_timestamps[0].date() == AFTER_MIDNIGHT.date()
        )  # Dec 10
        assert (
            coordinator.max_values_timestamps[1].date() == BEFORE_MIDNIGHT.date()
        )  # Dec 9

        # Test updating same day after midnight
        coordinator._update_max_values_with_timestamp(
            7.0, SAME_DAY_LATER
        )  # Higher value for same day

        # Should update the Dec 10 entry
        assert coordinator.max_values == [7.0, 5.0]
        assert (
            coordinator.max_values_timestamps[0].date() == SAME_DAY_LATER.date()
        )  # Dec 10
        assert (
            coordinator.max_values_timestamps[1].date() == BEFORE_MIDNIGHT.date()
        )  # Dec 9
