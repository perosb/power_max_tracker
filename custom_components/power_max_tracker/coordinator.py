from datetime import datetime, timedelta
import logging
from homeassistant.helpers.event import async_track_time_change
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from .const import (
    CONF_SOURCE_SENSOR,
    CONF_MONTHLY_RESET,
    CONF_NUM_MAX_VALUES,
    CONF_BINARY_SENSOR,
    CONF_PRICE_PER_KW,
    CONF_POWER_SCALING_FACTOR,
    CONF_START_TIME,
    CONF_STOP_TIME,
    CONF_TIME_SCALING_FACTOR,
    SECONDS_PER_HOUR,
    WATTS_TO_KILOWATTS,
    STORAGE_VERSION,
    MAX_VALUES_STORAGE_KEY,
    TIMESTAMPS_STORAGE_KEY,
    PREVIOUS_MONTH_STORAGE_KEY,
)

_LOGGER = logging.getLogger(__name__)


class PowerMaxCoordinator:
    """Coordinator for updating max hourly average power values in kW."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry | None,
        yaml_config: dict | None = None,
        yaml_unique_id: str | None = None,
    ):
        self.hass = hass
        self.entry = entry
        self.yaml_config = yaml_config
        self.yaml_unique_id = yaml_unique_id

        # Get configuration from either entry or yaml_config
        if entry:
            # Config entry mode
            self.source_sensor = entry.data[CONF_SOURCE_SENSOR]
            self.monthly_reset = entry.data.get(CONF_MONTHLY_RESET, False)
            self.num_max_values = int(entry.data.get(CONF_NUM_MAX_VALUES, 2))
            self.binary_sensor = entry.data.get(CONF_BINARY_SENSOR, None)
            self.price_per_kw = float(entry.data.get(CONF_PRICE_PER_KW, 0.0))
            self.power_scaling_factor = float(
                entry.data.get(CONF_POWER_SCALING_FACTOR, 1.0)
            )
            self.start_time = entry.data.get(CONF_START_TIME, None)
            self.stop_time = entry.data.get(CONF_STOP_TIME, None)
            self.time_scaling_factor = float(
                entry.data.get(CONF_TIME_SCALING_FACTOR, 1.0) or 1.0
            )
            self.unique_id = entry.entry_id
        else:
            # YAML mode
            self.source_sensor = yaml_config[CONF_SOURCE_SENSOR]
            self.monthly_reset = yaml_config.get(CONF_MONTHLY_RESET, False)
            self.num_max_values = int(yaml_config.get(CONF_NUM_MAX_VALUES, 2))
            self.binary_sensor = yaml_config.get(CONF_BINARY_SENSOR, None)
            self.price_per_kw = float(yaml_config.get(CONF_PRICE_PER_KW, 0.0))
            self.power_scaling_factor = float(
                yaml_config.get(CONF_POWER_SCALING_FACTOR, 1.0)
            )
            self.start_time = yaml_config.get(CONF_START_TIME, None)
            self.stop_time = yaml_config.get(CONF_STOP_TIME, None)
            self.time_scaling_factor = float(
                yaml_config.get(CONF_TIME_SCALING_FACTOR, 1.0) or 1.0
            )
            self.unique_id = yaml_unique_id

        self.source_sensor_entity_id = None  # Set dynamically after entity registration
        self.max_values = [0.0] * self.num_max_values
        self.max_values_timestamps = [None] * self.num_max_values
        self.previous_month_max_values = []

        # Initialize storage for max values data
        storage_key = f"power_max_tracker_{self.unique_id}_max_values"
        self._max_values_store = Store(self.hass, STORAGE_VERSION, storage_key)
        self.entities = []  # Store sensor entities
        self._listeners = []

    def add_entity(self, entity):
        """Add a sensor entity to the coordinator."""
        if (
            entity is not None
            and hasattr(entity, "_attr_unique_id")
            and hasattr(entity, "entity_id")
            and hasattr(entity, "async_write_ha_state")
            and callable(getattr(entity, "async_write_ha_state", None))
            and (
                entity._attr_unique_id.endswith("_source")
                or entity._attr_unique_id.endswith("_hourly_average_power")
                or entity._attr_unique_id.endswith("_average_max")
                or entity._attr_unique_id.endswith("_average_max_cost")
                or any(
                    entity._attr_unique_id.endswith(f"_max_values_{i + 1}")
                    for i in range(self.num_max_values)
                )
            )
        ):
            self.entities.append(entity)
            if entity._attr_unique_id.endswith("_source"):
                self.source_sensor_entity_id = entity.entity_id
                # Auto-detect scaling factor based on source sensor unit only if not explicitly configured
                if self.power_scaling_factor == 1.0:  # Default value means auto-detect
                    self._auto_detect_scaling_factor()
        else:
            _LOGGER.error(
                f"Failed to add entity: {entity}, has_unique_id={hasattr(entity, '_attr_unique_id')}, "
                f"has_entity_id={hasattr(entity, 'entity_id')}, "
                f"has_async_write={hasattr(entity, 'async_write_ha_state')}, "
                f"is_callable={callable(getattr(entity, 'async_write_ha_state', None)) if entity else False}"
            )

    def _auto_detect_scaling_factor(self):
        """Auto-detect scaling factor based on source sensor's unit of measurement."""
        if not self.source_sensor_entity_id:
            return

        # Try to get the unit from the entity registry first
        unit = None
        try:
            from homeassistant.helpers.entity_registry import (
                async_get as async_get_entity_registry,
            )

            entity_registry = async_get_entity_registry(self.hass)
            entity_entry = entity_registry.async_get(self.source_sensor_entity_id)
            if entity_entry and hasattr(entity_entry, "unit_of_measurement"):
                unit = entity_entry.unit_of_measurement
        except Exception as e:
            _LOGGER.debug(f"Could not access entity registry: {e}")

        # Fallback to state attributes if not in registry
        if not unit:
            try:
                state = self.hass.states.get(self.source_sensor_entity_id)
                if state and "unit_of_measurement" in state.attributes:
                    unit = state.attributes["unit_of_measurement"]
            except Exception as e:
                _LOGGER.debug(f"Could not access state: {e}")

        if unit:
            unit_lower = unit.lower()
            if unit_lower in ["kw", "kilowatt", "kilowatts"]:
                self.power_scaling_factor = 1000.0  # Convert kW to W
                _LOGGER.debug(
                    f"Auto-detected kW unit for {self.source_sensor_entity_id}, setting scaling factor to 1000"
                )
            elif unit_lower in ["w", "watt", "watts"]:
                self.power_scaling_factor = 1.0  # No scaling needed
                _LOGGER.debug(
                    f"Auto-detected W unit for {self.source_sensor_entity_id}, setting scaling factor to 1"
                )
            else:
                _LOGGER.warning(
                    f"Unknown unit '{unit}' for {self.source_sensor_entity_id}, using default scaling factor of 1.0"
                )
                self.power_scaling_factor = 1.0
        else:
            _LOGGER.debug(
                f"Could not determine unit for {self.source_sensor_entity_id}, using default scaling factor of 1.0"
            )
            self.power_scaling_factor = 1.0

    async def async_setup(self):
        """Set up hourly update and monthly reset."""
        # Load stored max values data
        stored_data = await self._max_values_store.async_load()
        if stored_data:
            self.max_values = stored_data.get(MAX_VALUES_STORAGE_KEY, self.max_values)
            # Convert timestamp strings back to datetime objects
            stored_timestamps = stored_data.get(
                TIMESTAMPS_STORAGE_KEY, self.max_values_timestamps
            )
            self.max_values_timestamps = [
                dt_util.parse_datetime(ts) if isinstance(ts, str) and ts else ts
                for ts in stored_timestamps
            ]
            self.previous_month_max_values = stored_data.get(
                PREVIOUS_MONTH_STORAGE_KEY, self.previous_month_max_values
            )

        # Clean invalid entities
        self.entities = [e for e in self.entities if self._is_valid_entity(e)]

        # Auto-detect scaling factor if not already done and still at default
        if self.source_sensor_entity_id and self.power_scaling_factor == 1.0:
            self._auto_detect_scaling_factor()

        # Hourly update listener (for max values)
        self._listeners.append(
            async_track_time_change(
                self.hass,
                self._async_update_hourly,
                hour=None,
                minute=1,
                second=0,
            )
        )

        # Monthly reset listener (daily at 00:00 to check for 1st of the month)
        if self.monthly_reset:
            self._listeners.append(
                async_track_time_change(
                    self.hass,
                    self._async_reset_monthly,
                    hour=0,
                    minute=2,
                    second=0,
                )
            )

    async def _save_max_values_data(self):
        """Save max values data to storage."""
        data = {
            MAX_VALUES_STORAGE_KEY: self.max_values,
            TIMESTAMPS_STORAGE_KEY: self.max_values_timestamps,
            PREVIOUS_MONTH_STORAGE_KEY: self.previous_month_max_values,
        }
        await self._max_values_store.async_save(data)

    def _is_valid_entity(self, entity):
        """Check if an entity is valid for state updates."""
        return (
            entity is not None
            and hasattr(entity, "_attr_unique_id")
            and hasattr(entity, "entity_id")
            and hasattr(entity, "async_write_ha_state")
            and callable(getattr(entity, "async_write_ha_state", None))
            and (
                entity._attr_unique_id.endswith("_source")
                or entity._attr_unique_id.endswith("_hourly_average_power")
                or entity._attr_unique_id.endswith("_average_max")
                or entity._attr_unique_id.endswith("_average_max_cost")
                or any(
                    entity._attr_unique_id.endswith(f"_max_values_{i + 1}")
                    for i in range(self.num_max_values)
                )
            )
        )

    @property
    def average_max_value(self):
        """Return the average of all max values."""
        if self.max_values:
            return sum(self.max_values) / len(self.max_values)
        return 0.0

    @property
    def previous_month_average_max_value(self):
        """Return the average of previous month max values."""
        if self.previous_month_max_values:
            return sum(self.previous_month_max_values) / len(
                self.previous_month_max_values
            )
        return 0.0

    def _watts_to_kilowatts(self, watts: float) -> float:
        """Convert watts to kilowatts.

        Args:
            watts: Power value in watts

        Returns:
            Power value in kilowatts
        """
        return watts / WATTS_TO_KILOWATTS

    def _update_max_values_with_timestamp(
        self, new_value: float, timestamp: datetime
    ) -> bool:
        """Update max values list with a new value and its timestamp.

        Args:
            new_value: New power value in kW to potentially add to max values
            timestamp: Timestamp when this value was recorded

        Returns:
            True if max values were updated, False otherwise
        """
        # Check if the new value is already in the list - if so, don't add it again
        if new_value in self.max_values:
            return False

        old_max_values = self.max_values
        new_max_values = sorted(self.max_values + [new_value], reverse=True)[
            : self.num_max_values
        ]

        # If the new list is the same as the old list, no change occurred
        if new_max_values == old_max_values:
            return False

        new_timestamps = self.max_values_timestamps.copy()

        # The new value was added since it wasn't already in the list
        # Find where the new value was inserted
        insert_index = 0
        for i, val in enumerate(new_max_values):
            if val == new_value and (
                i >= len(old_max_values) or old_max_values[i] != new_value
            ):
                insert_index = i
                break

        # Shift timestamps and add new timestamp
        new_timestamps.insert(insert_index, timestamp)
        new_timestamps = new_timestamps[: self.num_max_values]

        self.max_values = new_max_values
        self.max_values_timestamps = new_timestamps
        return True

    async def _query_hourly_statistics(
        self, start_time: datetime, end_time: datetime
    ) -> float | None:
        """Query hourly average power statistics for the source sensor.

        Args:
            start_time: Start time for the statistics query
            end_time: End time for the statistics query

        Returns:
            Hourly average power in watts, or None if no data available
        """
        _LOGGER.debug(
            f"Querying hourly stats for {self.source_sensor_entity_id} from {start_time} to {end_time}"
        )
        stats = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time,
            end_time,
            [self.source_sensor_entity_id],
            "hour",
            None,
            {"mean"},
        )

        if (
            self.source_sensor_entity_id in stats
            and stats[self.source_sensor_entity_id]
            and stats[self.source_sensor_entity_id][0]["mean"] is not None
        ):
            # SourcePowerSensor already emits scaled values in watts
            return stats[self.source_sensor_entity_id][0]["mean"]
        else:
            _LOGGER.warning(
                f"No mean statistics found for {self.source_sensor_entity_id} from {start_time} to {end_time}. Stats: {stats}"
            )
            return None

    async def _update_max_values_from_range(
        self, start_time: datetime, end_time: datetime, reset_max: bool = False
    ):
        """Update max values from a range of hours."""
        if reset_max:
            self.max_values = [0.0] * self.num_max_values
            self.max_values_timestamps = [None] * self.num_max_values

        hours = int((end_time - start_time).total_seconds() // SECONDS_PER_HOUR)
        if hours == 0:
            return

        for hour in range(hours):
            hour_start = start_time + timedelta(hours=hour)
            hour_end = hour_start + timedelta(hours=1)

            hourly_avg_watts = await self._query_hourly_statistics(hour_start, hour_end)

            if hourly_avg_watts is not None and hourly_avg_watts >= 0:
                hourly_avg_kw = self._watts_to_kilowatts(hourly_avg_watts)
                if self._can_update_max_values():
                    self._update_max_values_with_timestamp(hourly_avg_kw, hour_end)

        await self._save_max_values_data()
        await self._update_entities("range update")

    async def _async_update_hourly(self, now):
        """Calculate hourly average power in kW and update max values if binary sensor allows."""
        if not self.source_sensor_entity_id:
            _LOGGER.debug(
                f"Cannot update hourly stats: source_sensor_entity_id not set for {self.source_sensor}"
            )
            return

        end_time = now.replace(minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(hours=1)

        hourly_avg_watts = await self._query_hourly_statistics(start_time, end_time)

        if hourly_avg_watts is not None:
            # Only use non-negative values
            if hourly_avg_watts >= 0:
                hourly_avg_kw = self._watts_to_kilowatts(hourly_avg_watts)
                _LOGGER.debug(
                    f"Hourly average power for {start_time} to {end_time}: {hourly_avg_kw} kW (from {hourly_avg_watts} W)"
                )
                # Check binary sensor state
                if self._can_update_max_values():
                    if self._update_max_values_with_timestamp(hourly_avg_kw, now):
                        await self._save_max_values_data()
                        # Force sensor update
                        await self._update_entities("hourly update")
                else:
                    _LOGGER.debug(
                        "Skipping max values update due to binary sensor state"
                    )
            else:
                _LOGGER.debug(
                    f"Skipping negative hourly average power: {hourly_avg_watts} W"
                )

    async def async_update_max_values_from_midnight(self):
        """Update max values from midnight to the current hour."""
        if not self.source_sensor_entity_id:
            _LOGGER.debug(
                f"Cannot update max values: source_sensor_entity_id not set for {self.source_sensor}"
            )
            return

        now = datetime.now()
        end_time = now.replace(minute=0, second=0, microsecond=0)
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)  # Midnight
        await self._update_max_values_from_range(start_time, end_time, reset_max=False)

    async def async_update_max_values_to_current_month(self):
        """Update max values to the current month's max so far."""
        _LOGGER.info("Performing manual update of max values to current month's max")
        now = datetime.now()
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_time = now
        await self._update_max_values_from_range(start_time, end_time, reset_max=True)

    async def _update_entities(self, update_type: str):
        """Update all valid entities and log the process."""
        # Filter and clean invalid entities
        valid_entities = [e for e in self.entities if self._is_valid_entity(e)]
        # Remove invalid entities from self.entities
        if len(valid_entities) < len(self.entities):
            _LOGGER.warning(
                f"Removed {len(self.entities) - len(valid_entities)} invalid entities from coordinator for {self.source_sensor}"
            )
            self.entities = valid_entities

        _LOGGER.debug(
            f"Processing {update_type} for {len(valid_entities)} valid entities"
        )
        for entity in valid_entities:
            try:
                write_method = entity.async_schedule_update_ha_state
                if write_method is not None:
                    write_method()
                else:
                    _LOGGER.error(
                        f"async_schedule_update_ha_state is None for entity {entity.entity_id} with unique_id {entity._attr_unique_id}"
                    )
            except Exception as e:
                _LOGGER.error(
                    f"Failed to schedule state update for entity {entity.entity_id} with unique_id {entity._attr_unique_id}: {e}"
                )
        if not valid_entities:
            _LOGGER.error(
                f"No valid entities found for {update_type} for {self.source_sensor}"
            )

    def _can_update_max_values(self):
        """Check if max values can be updated based on binary sensor state."""
        if not self.binary_sensor:
            return True  # No binary sensor configured, allow updates
        state = self.hass.states.get(self.binary_sensor)
        if state is None or state.state == "unavailable":
            _LOGGER.debug(f"Binary sensor {self.binary_sensor} is unavailable")
            return False
        return state.state == "on"  # Only update if sensor is True (on)

    async def _async_reset_monthly(self, now):
        """Reset max values if it's the 1st of the month."""
        if self.monthly_reset and now.day == 1:
            _LOGGER.info(
                f"Performing monthly reset of {self.num_max_values} max values"
            )
            # Store current max values as previous month
            self.previous_month_max_values = self.max_values.copy()
            self.max_values = [0.0] * self.num_max_values
            self.max_values_timestamps = [None] * self.num_max_values
            await self._save_max_values_data()
            # Force sensor update
            await self._update_entities("monthly reset")

    def async_unload(self):
        """Unload listeners."""
        for listener in self._listeners:
            listener()
        self._listeners.clear()
