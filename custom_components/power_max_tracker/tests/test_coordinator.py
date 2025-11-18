"""Tests for PowerMaxCoordinator.

Note: These tests require a full Home Assistant development environment with all dependencies.
They will fail when run in a standalone environment without HA installed.
For basic unit testing of helper methods, use test_coordinator_helpers.py instead.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from custom_components.power_max_tracker.coordinator import PowerMaxCoordinator
from custom_components.power_max_tracker.const import (
    CONF_SOURCE_SENSOR,
    CONF_MONTHLY_RESET,
    CONF_NUM_MAX_VALUES,
    CONF_BINARY_SENSOR,
    MAX_VALUES_STORAGE_KEY,
    TIMESTAMPS_STORAGE_KEY,
    PREVIOUS_MONTH_STORAGE_KEY,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
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
        assert coordinator.entities == []
        assert coordinator._listeners == []

    def test_watts_to_kilowatts_conversion(self, coordinator):
        """Test watts to kilowatts conversion."""
        assert coordinator._watts_to_kilowatts(1000) == 1.0
        assert coordinator._watts_to_kilowatts(500) == 0.5
        assert coordinator._watts_to_kilowatts(0) == 0.0
        assert coordinator._watts_to_kilowatts(2500) == 2.5

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


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
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
