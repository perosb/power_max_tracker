import logging
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util
from homeassistant.helpers.storage import Store
from .const import (
    DOMAIN,
    CONF_NUM_MAX_VALUES,
    CONF_SOURCE_SENSOR,
    CONF_BINARY_SENSOR,
    CONF_MONTHLY_RESET,
    CONF_POWER_SCALING_FACTOR,
    KILOWATT_HOURS_PER_WATT_HOUR,
    SECONDS_PER_HOUR,
)
from .coordinator import PowerMaxCoordinator

_LOGGER = logging.getLogger(__name__)


class MockEntry:
    """Mock ConfigEntry for YAML configurations."""

    def __init__(
        self,
        entry_id,
        domain,
        data,
        options=None,
        source="user",
        title="",
        version=1,
        minor_version=1,
        state=ConfigEntryState.LOADED,
    ):
        self.entry_id = entry_id
        self.domain = domain
        self.data = data
        self.options = options or {}
        self.source = source
        self.title = title
        self.version = version
        self.minor_version = minor_version
        self.state = state
        self.update_listeners = []
        self.reason = None
        self.when_setup = None

    async def async_setup(self, hass, integration=None):
        """Mock async_setup method."""
        return True

    async def async_unload(self, hass, integration=None):
        """Mock async_unload method."""
        return True


class GatedSensorEntity(SensorEntity):
    """Base class for sensors gated by a binary sensor."""

    def __init__(self, entry):
        """Initialize."""
        super().__init__()
        self._binary_sensor = entry.data.get(CONF_BINARY_SENSOR)

    def _can_update(self):
        """Check if the sensor can update based on binary sensor state."""
        if not self._binary_sensor:
            return True
        state = self.hass.states.get(self._binary_sensor)
        return state is not None and state.state == "on"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up sensors for config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await _setup_sensors(hass, coordinator, entry, async_add_entities)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Set up sensors for YAML configuration."""
    _LOGGER.debug(f"async_setup_platform called with config: {config}")
    num_max_values = config.get(CONF_NUM_MAX_VALUES, 2)
    if not isinstance(num_max_values, int) or not (1 <= num_max_values <= 10):
        _LOGGER.error("num_max_values must be an integer between 1 and 10")
        return

    yaml_config = {
        CONF_SOURCE_SENSOR: config.get(CONF_SOURCE_SENSOR),
        CONF_NUM_MAX_VALUES: num_max_values,
        CONF_MONTHLY_RESET: config.get(CONF_MONTHLY_RESET, False),
        CONF_BINARY_SENSOR: config.get(CONF_BINARY_SENSOR),
        CONF_POWER_SCALING_FACTOR: float(config.get(CONF_POWER_SCALING_FACTOR, 1.0)),
    }

    # Create a unique ID
    unique_id = f"yaml_{yaml_config[CONF_SOURCE_SENSOR].replace('.', '_')}"

    # Create coordinator
    coordinator = PowerMaxCoordinator(hass, None, yaml_config, unique_id)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][unique_id] = coordinator
    await coordinator.async_setup()

    # Create mock entry
    mock_entry = MockEntry(
        entry_id=unique_id,
        domain=DOMAIN,
        data=yaml_config,
        options={},
        source="user",
        title=f"YAML {yaml_config[CONF_SOURCE_SENSOR]}",
        version=1,
        minor_version=1,
        state=ConfigEntryState.LOADED,
    )

    await _setup_sensors(hass, coordinator, mock_entry, async_add_entities)

    return True


async def _setup_sensors(
    hass: HomeAssistant,
    coordinator: PowerMaxCoordinator,
    entry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up sensors for a coordinator."""
    num_max_values = coordinator.num_max_values
    sensors = [
        MaxPowerSensor(coordinator, idx, f"Max Hourly Average Power {idx + 1}")
        for idx in range(num_max_values)
    ]
    # Add average max power sensor
    average_max_sensor = AverageMaxPowerSensor(coordinator, entry)
    sensors.append(average_max_sensor)
    # Add SourcePowerSensor
    source_sensor = SourcePowerSensor(coordinator, entry)
    sensors.append(source_sensor)
    # Add HourlyAveragePowerSensor
    hourly_average_power_sensor = HourlyAveragePowerSensor(coordinator, entry)
    sensors.append(hourly_average_power_sensor)
    async_add_entities(sensors, update_before_add=True)
    for sensor in sensors:
        coordinator.add_entity(sensor)


class MaxPowerSensor(SensorEntity):
    """Sensor for max hourly average power in kW."""

    def __init__(self, coordinator: PowerMaxCoordinator, index: int, name: str):
        """Initialize."""
        super().__init__()
        self._coordinator = coordinator
        self._index = index
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.unique_id}_max_values_{index + 1}"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:chart-line"
        self._attr_should_poll = False  # Updated via coordinator
        self._attr_force_update = True  # Force state updates

    @property
    def native_value(self):
        """Return the state."""
        max_values = self._coordinator.max_values
        current_value = (
            round(max_values[self._index], 2) if len(max_values) > self._index else 0.0
        )
        return current_value

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        timestamps = getattr(self._coordinator, "max_values_timestamps", [])
        last_update = None
        if len(timestamps) > self._index and timestamps[self._index] is not None:
            last_update = timestamps[self._index].isoformat()
        return {"last_update": last_update}


class AverageMaxPowerSensor(SensorEntity):
    """Sensor for the average of all max hourly average power values."""

    def __init__(self, coordinator: PowerMaxCoordinator, entry: ConfigEntry = None):
        """Initialize."""
        super().__init__()
        self._coordinator = coordinator
        self._entry = entry
        self._attr_name = "Average Max Hourly Average Power"
        self._attr_unique_id = f"{coordinator.unique_id}_average_max"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:chart-line"
        self._attr_should_poll = False  # Updated via coordinator
        self._attr_force_update = True  # Force state updates

    @property
    def native_value(self):
        """Return the state."""
        max_values = self._coordinator.max_values
        if max_values:
            return round(sum(max_values) / len(max_values), 2)
        return 0.0

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        prev_values = self._coordinator.previous_month_max_values
        prev_avg = round(sum(prev_values) / len(prev_values), 2) if prev_values else 0.0
        return {"previous_month_average": prev_avg}


class SourcePowerSensor(GatedSensorEntity):
    """Sensor that tracks the source sensor state, gated by binary sensor."""

    def __init__(self, coordinator: PowerMaxCoordinator, entry):
        """Initialize."""
        super().__init__(entry)
        self._coordinator = coordinator
        self._entry = entry
        self._source_sensor = entry.data[CONF_SOURCE_SENSOR]
        self._attr_name = f"Power Max Source {self._source_sensor.split('.')[-1]}"
        self._attr_unique_id = f"{coordinator.unique_id}_source"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:power"
        self._attr_should_poll = False  # Updated via state changes
        self._state = 0.0

    async def async_added_to_hass(self):
        """Handle entity added to hass."""

        async def _async_state_changed(event):
            """Handle state changes of source or binary sensor."""
            if self._can_update():
                source_state = self.hass.states.get(self._source_sensor)
                if source_state is not None and source_state.state not in (
                    "unavailable",
                    "unknown",
                ):
                    try:
                        value = float(source_state.state)
                        self._state = (
                            max(0.0, value) * self._coordinator.power_scaling_factor
                        )  # Apply scaling factor
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            f"Invalid state for {self._source_sensor}: {source_state.state}"
                        )
                        self._state = 0.0
                else:
                    _LOGGER.debug(
                        f"Source sensor {self._source_sensor} unavailable or unknown"
                    )
                    self._state = 0.0
            else:
                self._state = 0.0
            self.async_write_ha_state()

        # Track state changes of source and binary sensors
        sensors = [self._source_sensor]
        if self._binary_sensor:
            sensors.append(self._binary_sensor)
        self.async_on_remove(
            async_track_state_change_event(self.hass, sensors, _async_state_changed)
        )

    @property
    def native_value(self):
        """Return the state."""
        return self._state


class HourlyAveragePowerSensor(GatedSensorEntity):
    """Sensor for hourly average power in kW so far the current hour."""

    def __init__(self, coordinator: PowerMaxCoordinator, entry):
        """Initialize."""
        super().__init__(entry)
        self._coordinator = coordinator
        self._entry = entry
        self._source_sensor = entry.data[CONF_SOURCE_SENSOR]
        self._attr_name = f"Hourly Average Power {self._source_sensor.split('.')[-1]}"
        self._attr_unique_id = f"{coordinator.unique_id}_hourly_average_power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_should_poll = False
        # Initialize state (will be loaded in async_added_to_hass)
        self._accumulated_energy = 0.0
        self._last_power = 0.0
        self._last_time = None
        self._hour_start = None
        self._store = None

    async def _save_state(self):
        """Save the current state to storage."""
        if self._store:
            data = {
                "accumulated_energy": self._accumulated_energy,
                "last_power": self._last_power,
                "last_time": self._last_time.isoformat() if self._last_time else None,
                "hour_start": self._hour_start.isoformat()
                if self._hour_start
                else None,
            }
            await self._store.async_save(data)

    async def async_added_to_hass(self):
        """Handle entity added to hass."""
        # Get storage for this sensor
        self._store = Store(
            self.hass,
            1,
            f"power_max_tracker_{self._coordinator.unique_id}_hourly_sensor",
        )
        # Load persisted state
        stored_data = await self._store.async_load()
        now = dt_util.utcnow()
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        if stored_data:
            self._accumulated_energy = stored_data.get("accumulated_energy", 0.0)
            self._last_power = stored_data.get("last_power", 0.0)
            last_time_str = stored_data.get("last_time")
            if last_time_str:
                self._last_time = dt_util.parse_datetime(last_time_str)
            hour_start_str = stored_data.get("hour_start")
            if hour_start_str:
                self._hour_start = dt_util.parse_datetime(hour_start_str)
            # Check if stored hour_start is in the current hour
            if self._hour_start and (
                self._hour_start.date() != current_hour_start.date()
                or self._hour_start.hour != current_hour_start.hour
            ):
                # Different hour, reset accumulated energy
                self._accumulated_energy = 0.0
                self._last_power = 0.0
                self._last_time = now
                self._hour_start = current_hour_start
        else:
            # No stored data, initialize for current hour
            self._accumulated_energy = 0.0
            self._last_power = 0.0
            self._last_time = now
            self._hour_start = current_hour_start

        async def _async_hour_start(now):
            """Reset at the start of each hour."""
            self._accumulated_energy = 0.0
            self._last_power = 0.0
            self._last_time = now
            self._hour_start = now
            await self._save_state()
            self.async_write_ha_state()

        # Track hour changes
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                _async_hour_start,
                hour=None,
                minute=0,
                second=0,
            )
        )

        async def _async_state_changed(event):
            """Handle state changes of source or binary sensor."""
            now = dt_util.utcnow()
            if self._last_time is None:
                self._last_time = now
                return
            if self._can_update():
                source_state = self.hass.states.get(self._source_sensor)
                if source_state is not None and source_state.state not in (
                    "unavailable",
                    "unknown",
                ):
                    try:
                        current_power = float(source_state.state)
                        if current_power < 0:
                            current_power = 0.0
                        current_power *= (
                            self._coordinator.power_scaling_factor
                        )  # Apply scaling factor
                        delta_seconds = (now - self._last_time).total_seconds()
                        if delta_seconds > 0:
                            # Average power in W
                            avg_power = (self._last_power + current_power) / 2
                            # Energy in kWh
                            delta_energy = (
                                avg_power
                                * delta_seconds
                                * KILOWATT_HOURS_PER_WATT_HOUR
                                / SECONDS_PER_HOUR
                            )
                            self._accumulated_energy += delta_energy
                        self._last_power = current_power
                        self._last_time = now
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            f"Invalid state for {self._source_sensor}: {source_state.state}"
                        )
                        self._last_power = 0.0
                else:
                    _LOGGER.debug(
                        f"Source sensor {self._source_sensor} unavailable or unknown"
                    )
                    self._last_power = 0.0
            else:
                self._last_power = 0.0
            await self._save_state()
            self.async_write_ha_state()

        # Track state changes of source and binary sensors
        sensors = [self._source_sensor]
        if self._binary_sensor:
            sensors.append(self._binary_sensor)
        self.async_on_remove(
            async_track_state_change_event(self.hass, sensors, _async_state_changed)
        )

    @property
    def native_value(self):
        """Return the state."""
        if self._hour_start is None:
            return 0.0
        now = dt_util.utcnow()
        elapsed_hours = (now - self._hour_start).total_seconds() / SECONDS_PER_HOUR
        if elapsed_hours > 0:
            return round(self._accumulated_energy / elapsed_hours, 3)
        return 0.0
