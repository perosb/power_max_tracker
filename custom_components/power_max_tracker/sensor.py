import logging
from datetime import timedelta
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
    KILOWATT_HOURS_PER_WATT_HOUR,
    SECONDS_PER_HOUR,
    CYCLE_HALF_HOURLY,
    CYCLE_QUARTERLY,
    CYCLE_HOURLY,
)
from .coordinator import PowerMaxCoordinator

_LOGGER = logging.getLogger(__name__)

# Mapping for cycle type display names (entity names are typically in English)
CYCLE_NAME_MAPPING = {
    CYCLE_HALF_HOURLY: "Half-hourly",
    CYCLE_QUARTERLY: "Quarterly",
    CYCLE_HOURLY: "Hourly",
}


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

    def _is_time_in_window(self, now):
        """Check if current time is within the configured time window."""
        if not self._coordinator.start_time or not self._coordinator.stop_time:
            return False

        start_time = dt_util.parse_time(self._coordinator.start_time)
        stop_time = dt_util.parse_time(self._coordinator.stop_time)

        # Convert to today's datetime for comparison
        start_dt = dt_util.start_of_local_day(now).replace(
            hour=start_time.hour, minute=start_time.minute, second=start_time.second
        )
        stop_dt = dt_util.start_of_local_day(now).replace(
            hour=stop_time.hour, minute=stop_time.minute, second=stop_time.second
        )

        # Handle midnight wrap-around
        if stop_dt <= start_dt:
            # Time window crosses midnight
            stop_dt = stop_dt + timedelta(days=1)
            if now < start_dt:
                # Before start time, check if we're in the early morning window (midnight to stop_time)
                return now <= stop_dt - timedelta(days=1)
            else:
                # After start time, check current window
                return now <= stop_dt
        else:
            # Normal time window within same day
            return start_dt <= now <= stop_dt

    def _setup_state_change_tracking(self, source_sensor, callback):
        """Set up state change tracking for source and binary sensors."""
        sensors = [source_sensor]
        if self._binary_sensor:
            sensors.append(self._binary_sensor)
        self.async_on_remove(
            async_track_state_change_event(self.hass, sensors, callback)
        )

    def _log_scaling_applied(
        self, sensor_name, original_value, final_value, time_scaling_applied
    ):
        """Log scaling operation details."""
        _LOGGER.debug(
            f"{sensor_name} scaling applied - Original: {original_value}W, "
            f"Power scaling: {self._coordinator.power_scaling_factor}, "
            f"Time scaling: {self._coordinator.time_scaling_factor if time_scaling_applied else 'N/A'} "
            f"(applied: {time_scaling_applied}), Final: {final_value}W"
        )


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
    cycle_name = CYCLE_NAME_MAPPING.get(coordinator.cycle_type, "Hourly")
    sensors = [
        MaxPowerSensor(coordinator, idx, f"Max {cycle_name} Average Power {idx + 1}")
        for idx in range(num_max_values)
    ]
    # Add a timestamp sensor for each max value
    timestamp_sensors = [
        MaxPowerTimestampSensor(
            coordinator, idx, f"Max {cycle_name} Average Power Last Update {idx + 1}"
        )
        for idx in range(num_max_values)
    ]
    sensors.extend(timestamp_sensors)
    # Add average max power sensor
    average_max_sensor = AverageMaxPowerSensor(coordinator, entry)
    sensors.append(average_max_sensor)
    # Add cost sensor only if price is configured
    if coordinator.price_per_kw > 0:
        cost_sensor = AverageMaxCostSensor(coordinator, entry)
        sensors.append(cost_sensor)
    # Add SourcePowerSensor
    source_sensor = SourcePowerSensor(coordinator, entry)
    sensors.append(source_sensor)
    # Add HourlyAveragePowerSensor
    hourly_average_power_sensor = HourlyAveragePowerSensor(coordinator, entry)
    sensors.append(hourly_average_power_sensor)

    # Add main sensors with update_before_add
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
            round(max_values[self._index], 2) if len(max_values) > self._index and max_values[self._index] is not None else 0.0
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


class MaxPowerTimestampSensor(SensorEntity):
    """Sensor for the timestamp when a max power value was last updated."""

    def __init__(self, coordinator: PowerMaxCoordinator, index: int, name: str):
        """Initialize."""
        super().__init__()
        self._coordinator = coordinator
        self._index = index
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.unique_id}_max_timestamps_{index + 1}"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        # Do not set a state_class for timestamp sensors
        self._attr_should_poll = False

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        await super().async_added_to_hass()
        # Timestamp sensors are updated through the coordinator's _update_entities mechanism
        # which is triggered during period updates and monthly resets

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        timestamps = getattr(self._coordinator, "max_values_timestamps", [])
        return len(timestamps) > self._index and timestamps[self._index] is not None

    @property
    def native_value(self):
        """Return the state."""
        timestamps = getattr(self._coordinator, "max_values_timestamps", [])
        if len(timestamps) > self._index and timestamps[self._index] is not None:
            ts = timestamps[self._index]
            # Ensure timezone-aware
            if ts.tzinfo is None:
                return ts.replace(tzinfo=dt_util.UTC)
            return ts
        return None

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        max_values = getattr(self._coordinator, "max_values", [])
        current_value = (
            round(max_values[self._index], 2) if len(max_values) > self._index and max_values[self._index] is not None else 0.0
        )
        return {"power_value": current_value}


class AverageMaxPowerSensor(SensorEntity):
    """Sensor for the average of all max hourly average power values."""

    def __init__(self, coordinator: PowerMaxCoordinator, entry: ConfigEntry = None):
        """Initialize."""
        super().__init__()
        self._coordinator = coordinator
        self._entry = entry
        cycle_name = CYCLE_NAME_MAPPING.get(coordinator.cycle_type, "Hourly")
        self._attr_name = f"Average Max {cycle_name} Average Power"
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
        return round(self._coordinator.average_max_value, 2)

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        prev_avg = round(self._coordinator.previous_month_average_max_value, 2)
        return {"previous_month_average": prev_avg}


class AverageMaxCostSensor(SensorEntity):
    """Sensor for the cost of the average max hourly average power."""

    def __init__(self, coordinator: PowerMaxCoordinator, entry: ConfigEntry = None):
        """Initialize."""
        super().__init__()
        self._coordinator = coordinator
        self._entry = entry
        cycle_name = CYCLE_NAME_MAPPING.get(coordinator.cycle_type, "Hourly")
        self._attr_name = f"Average Max {cycle_name} Average Power Cost"
        self._attr_unique_id = f"{coordinator.unique_id}_average_max_cost"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = (
            None  # Monetary sensors should not use MEASUREMENT state class
        )
        self._attr_icon = "mdi:currency-usd"
        self._attr_should_poll = False  # Updated via coordinator
        self._attr_force_update = True  # Force state updates

    @property
    def native_value(self):
        """Return the state."""
        if self._coordinator.price_per_kw > 0:
            avg_power = self._coordinator.average_max_value
            return round(avg_power * self._coordinator.price_per_kw, 2)
        return 0.0

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        if hasattr(self, "hass") and self.hass:
            return self.hass.config.currency
        return None

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        prev_avg = self._coordinator.previous_month_average_max_value
        prev_cost = (
            round(prev_avg * self._coordinator.price_per_kw, 2)
            if self._coordinator.price_per_kw > 0
            else 0.0
        )
        return {
            "previous_month_average": round(prev_avg, 2),
            "previous_month_cost": prev_cost,
            "price_per_kw": self._coordinator.price_per_kw,
        }


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
        self._attr_entity_registry_visible_default = False  # Hidden by default
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
                        original_value = max(0.0, value)
                        scaled_value = (
                            original_value * self._coordinator.power_scaling_factor
                        )

                        # Apply time-based scaling if configured and within time window
                        time_scaling_applied = False
                        if (
                            self._coordinator.start_time
                            and self._coordinator.stop_time
                            and self._coordinator.time_scaling_factor is not None
                            and self._coordinator.time_scaling_factor != 1.0
                            and self._is_time_in_window(dt_util.utcnow())
                        ):
                            scaled_value *= self._coordinator.time_scaling_factor
                            time_scaling_applied = True

                        self._log_scaling_applied(
                            "SourcePowerSensor",
                            original_value,
                            scaled_value,
                            time_scaling_applied,
                        )

                        self._state = scaled_value
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
        self._setup_state_change_tracking(self._source_sensor, _async_state_changed)

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
        cycle_name = CYCLE_NAME_MAPPING.get(coordinator.cycle_type, "Hourly")
        self._attr_name = (
            f"{cycle_name} Average Power {self._source_sensor.split('.')[-1]}"
        )
        self._attr_unique_id = (
            f"{coordinator.unique_id}_{coordinator.cycle_type}_average_power"
        )
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_should_poll = False
        # Initialize state (will be loaded in async_added_to_hass)
        self._accumulated_energy = 0.0
        self._last_power = 0.0
        self._last_time = None
        self._cycle_start = None
        self._previous_cycle = None
        self._store = None

    def _now(self):
        """Return the current UTC time."""
        return dt_util.utcnow()

    def _get_current_cycle_start(self, now):
        """Floor the cycle start in local time and return the UTC instant."""
        local = dt_util.as_local(now)
        if self._coordinator.cycle_type == CYCLE_QUARTERLY:
            minute = (local.minute // 15) * 15
            local = local.replace(minute=minute, second=0, microsecond=0)
        elif self._coordinator.cycle_type == CYCLE_HALF_HOURLY:
            minute = (local.minute // 30) * 30
            local = local.replace(minute=minute, second=0, microsecond=0)
        else:
            local = local.replace(minute=0, second=0, microsecond=0)
        return dt_util.as_utc(local)

    def _energy_delta(self, power_watts, delta_seconds):
        """Convert a constant power interval to kWh."""
        return (
            power_watts
            * delta_seconds
            * KILOWATT_HOURS_PER_WATT_HOUR
            / SECONDS_PER_HOUR
        )

    def _close_energy_interval(self, end_time):
        """Hold the last observed power through end_time."""
        if self._last_time is None or end_time is None:
            return
        delta_seconds = (end_time - self._last_time).total_seconds()
        if delta_seconds <= 0:
            return
        self._accumulated_energy += self._energy_delta(
            self._last_power, delta_seconds
        )
        self._last_time = end_time

    def _compute_average(self, cycle_start, accumulated_energy, end_time):
        """Compute average power in kW for a cycle interval."""
        if cycle_start is None or end_time is None:
            return 0.0
        elapsed_seconds = (end_time - cycle_start).total_seconds()
        if elapsed_seconds > 0:
            return round(
                accumulated_energy * SECONDS_PER_HOUR / elapsed_seconds,
                3,
            )
        return 0.0

    def _snapshot_previous_cycle(self, end_time):
        """Close the cycle interval and store its average as previous_cycle."""
        if self._cycle_start is None or end_time is None:
            return
        if (end_time - self._cycle_start).total_seconds() <= 0:
            return
        self._close_energy_interval(end_time)
        self._previous_cycle = self._compute_average(
            self._cycle_start, self._accumulated_energy, end_time
        )

    async def _save_state(self):
        """Save the current state to storage."""
        if self._store:
            data = {
                "accumulated_energy": self._accumulated_energy,
                "last_power": self._last_power,
                "last_time": self._last_time.isoformat() if self._last_time else None,
                "cycle_start": self._cycle_start.isoformat()
                if self._cycle_start
                else None,
                "previous_cycle": self._previous_cycle,
            }
            await self._store.async_save(data)

    async def async_added_to_hass(self):
        """Handle entity added to hass."""
        # Get storage for this sensor
        self._store = Store(
            self.hass,
            1,
            f"power_max_tracker_{self._coordinator.unique_id}_{self._coordinator.cycle_type}_sensor",
        )
        # Load persisted state
        stored_data = await self._store.async_load()
        now = self._now()
        current_cycle_start = self._get_current_cycle_start(now)
        if stored_data:
            self._accumulated_energy = stored_data.get("accumulated_energy", 0.0)
            self._last_power = stored_data.get("last_power", 0.0)
            self._previous_cycle = stored_data.get("previous_cycle")
            last_time_str = stored_data.get("last_time")
            if last_time_str:
                self._last_time = dt_util.parse_datetime(last_time_str)
            cycle_start_str = stored_data.get("cycle_start")
            if cycle_start_str:
                stored_cycle_start = dt_util.parse_datetime(cycle_start_str)
                self._cycle_start = (
                    self._get_current_cycle_start(stored_cycle_start)
                    if stored_cycle_start
                    else None
                )
            # Check if stored cycle_start is in the current cycle
            if self._cycle_start and self._cycle_start != current_cycle_start:
                cycle_end = self._cycle_start + timedelta(
                    seconds=self._coordinator.seconds_per_cycle
                )
                if self._accumulated_energy > 0 or self._last_power:
                    self._snapshot_previous_cycle(cycle_end)
                self._accumulated_energy = 0.0
                self._last_time = now
                self._cycle_start = current_cycle_start
        else:
            # No stored data, initialize for current cycle
            self._accumulated_energy = 0.0
            self._last_power = 0.0
            self._last_time = now
            self._cycle_start = current_cycle_start
            self._previous_cycle = None

        async def _async_cycle_start(now):
            """Reset at the start of each cycle."""
            now = dt_util.as_utc(now)
            self._snapshot_previous_cycle(now)
            self._accumulated_energy = 0.0
            self._last_time = now
            self._cycle_start = self._get_current_cycle_start(now)
            await self._save_state()
            self.async_write_ha_state()

        # Track cycle changes
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                _async_cycle_start,
                hour=None,
                minute=self._coordinator.cycle_boundary_minutes,
                second=0,
            )
        )

        async def _async_state_changed(event):
            """Handle state changes of scaled source sensor."""
            now = self._now()
            if self._last_time is None:
                self._last_time = now
                return
            # Always process updates from the scaled SourcePowerSensor
            # Use the scaled SourcePowerSensor instead of raw source sensor
            source_entity_id = (
                self._coordinator.source_sensor_entity_id or self._source_sensor
            )
            source_state = self.hass.states.get(source_entity_id)
            if source_state is not None and source_state.state not in (
                "unavailable",
                "unknown",
            ):
                try:
                    current_power = float(source_state.state)
                    # SourcePowerSensor already emits scaled values in watts
                    # No additional scaling needed since SourcePowerSensor handles it

                    delta_seconds = (now - self._last_time).total_seconds()
                    if delta_seconds > 0:
                        # Average power in W
                        avg_power = (self._last_power + current_power) / 2
                        self._accumulated_energy += self._energy_delta(
                            avg_power, delta_seconds
                        )
                    self._last_power = current_power
                    self._last_time = now
                except (ValueError, TypeError):
                    _LOGGER.warning(
                        f"Invalid state for {source_entity_id}: {source_state.state}"
                    )
                    self._last_power = 0.0
            else:
                _LOGGER.debug(
                    f"Source sensor {source_entity_id} unavailable or unknown"
                )
                self._last_power = 0.0
            await self._save_state()
            self.async_write_ha_state()

        # Track state changes of scaled source sensor
        scaled_source_sensor = (
            self._coordinator.source_sensor_entity_id or self._source_sensor
        )
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [scaled_source_sensor], _async_state_changed
            )
        )

    @property
    def native_value(self):
        """Return the state."""
        now = self._now()
        energy = self._accumulated_energy
        if self._last_time is not None:
            delta_seconds = (now - self._last_time).total_seconds()
            if delta_seconds > 0:
                energy += self._energy_delta(self._last_power, delta_seconds)
        return self._compute_average(self._cycle_start, energy, now)

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        previous_cycle = self._previous_cycle
        if previous_cycle is not None:
            previous_cycle = round(previous_cycle, 3)
        return {"previous_cycle": previous_cycle}
