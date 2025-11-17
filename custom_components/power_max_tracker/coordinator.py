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

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        self.source_sensor = entry.data[CONF_SOURCE_SENSOR]
        self.source_sensor_entity_id = None  # Set dynamically after entity registration
        self.monthly_reset = entry.data.get(CONF_MONTHLY_RESET, False)
        self.num_max_values = int(entry.data.get(CONF_NUM_MAX_VALUES, 2))  # Cast to int
        self.binary_sensor = entry.data.get(CONF_BINARY_SENSOR, None)
        self.max_values = entry.data.get("max_values", [0.0] * self.num_max_values)
        if len(self.max_values) != self.num_max_values:
            self.max_values = [0.0] * self.num_max_values
        self.max_values_timestamps = entry.data.get(
            "max_values_timestamps", [None] * self.num_max_values
        )
        if len(self.max_values_timestamps) != self.num_max_values:
            self.max_values_timestamps = [None] * self.num_max_values
        self.previous_month_max_values = entry.data.get("previous_month_max_values", [])
        # Initialize storage for max values data
        self._max_values_store = Store(
            self.hass, STORAGE_VERSION, f"power_max_tracker_{entry.entry_id}_max_values"
        )
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
                or any(
                    entity._attr_unique_id.endswith(f"_max_values_{i + 1}")
                    for i in range(self.num_max_values)
                )
            )
        ):
            self.entities.append(entity)
            _LOGGER.debug(
                f"Added entity {entity.entity_id} with unique_id {entity._attr_unique_id}"
            )
            if entity._attr_unique_id.endswith("_source"):
                self.source_sensor_entity_id = entity.entity_id
                _LOGGER.debug(
                    f"Set source_sensor_entity_id to {self.source_sensor_entity_id}"
                )
        else:
            _LOGGER.error(
                f"Failed to add entity: {entity}, has_unique_id={hasattr(entity, '_attr_unique_id')}, "
                f"has_entity_id={hasattr(entity, 'entity_id')}, "
                f"has_async_write={hasattr(entity, 'async_write_ha_state')}, "
                f"is_callable={callable(getattr(entity, 'async_write_ha_state', None)) if entity else False}"
            )

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
        _LOGGER.debug(
            f"After setup cleanup, {len(self.entities)} valid entities for {self.source_sensor}"
        )

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
                or any(
                    entity._attr_unique_id.endswith(f"_max_values_{i + 1}")
                    for i in range(self.num_max_values)
                )
            )
        )

    async def _async_update_hourly(self, now):
        """Calculate hourly average power in kW and update max values if binary sensor allows."""
        if not self.source_sensor_entity_id:
            _LOGGER.debug(
                f"Cannot update hourly stats: source_sensor_entity_id not set for {self.source_sensor}"
            )
            return

        end_time = now.replace(minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(hours=1)

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
            hourly_avg_watts = stats[self.source_sensor_entity_id][0]["mean"]
            # Only use non-negative values
            if hourly_avg_watts >= 0:
                hourly_avg_kw = (
                    hourly_avg_watts / WATTS_TO_KILOWATTS
                )  # Convert watts to kW
                _LOGGER.debug(
                    f"Hourly average power for {start_time} to {end_time}: {hourly_avg_kw} kW (from {hourly_avg_watts} W)"
                )
                # Check binary sensor state
                if self._can_update_max_values():
                    # Insert new value into sorted max_values list
                    new_max_values = sorted(
                        self.max_values + [hourly_avg_kw], reverse=True
                    )[: self.num_max_values]
                    new_timestamps = self.max_values_timestamps.copy()

                    # Find where the new value was inserted
                    old_max_values = self.max_values
                    if hourly_avg_kw not in old_max_values or old_max_values.count(
                        hourly_avg_kw
                    ) < new_max_values.count(hourly_avg_kw):
                        # New value was added, update timestamps accordingly
                        insert_index = 0
                        for i, val in enumerate(new_max_values):
                            if val == hourly_avg_kw and (
                                i >= len(old_max_values)
                                or old_max_values[i] != hourly_avg_kw
                            ):
                                insert_index = i
                                break

                        # Shift timestamps and add new timestamp
                        new_timestamps.insert(insert_index, now)
                        new_timestamps = new_timestamps[: self.num_max_values]

                    if new_max_values != self.max_values:
                        self.max_values = new_max_values
                        self.max_values_timestamps = new_timestamps
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
        else:
            _LOGGER.warning(
                f"No mean statistics found for {self.source_sensor_entity_id} from {start_time} to {end_time}. Stats: {stats}"
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
        _LOGGER.debug(
            f"Updating max values for {self.source_sensor_entity_id} from {start_time} to {end_time}"
        )

        # Calculate number of hours from midnight to current hour
        hours = (end_time - start_time).seconds // SECONDS_PER_HOUR
        if hours == 0:
            _LOGGER.debug("No hours to process since midnight")
            return

        new_max_values = self.max_values.copy()
        new_timestamps = self.max_values_timestamps.copy()
        for hour in range(hours):
            hour_start = start_time + timedelta(hours=hour)
            hour_end = hour_start + timedelta(hours=1)
            _LOGGER.debug(
                f"Querying stats for {self.source_sensor_entity_id} from {hour_start} to {hour_end}"
            )
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                hour_start,
                hour_end,
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
                hourly_avg_watts = stats[self.source_sensor_entity_id][0]["mean"]
                if hourly_avg_watts >= 0:
                    hourly_avg_kw = (
                        hourly_avg_watts / WATTS_TO_KILOWATTS
                    )  # Convert watts to kW
                    _LOGGER.debug(
                        f"Hourly average power for {hour_start} to {hour_end}: {hourly_avg_kw} kW (from {hourly_avg_watts} W)"
                    )
                    if self._can_update_max_values():
                        old_max_values = new_max_values
                        new_max_values = sorted(
                            new_max_values + [hourly_avg_kw], reverse=True
                        )[: self.num_max_values]

                        # Update timestamps if value was added
                        if hourly_avg_kw not in old_max_values or old_max_values.count(
                            hourly_avg_kw
                        ) < new_max_values.count(hourly_avg_kw):
                            insert_index = 0
                            for i, val in enumerate(new_max_values):
                                if val == hourly_avg_kw and (
                                    i >= len(old_max_values)
                                    or old_max_values[i] != hourly_avg_kw
                                ):
                                    insert_index = i
                                    break

                            new_timestamps.insert(insert_index, hour_end)
                            new_timestamps = new_timestamps[: self.num_max_values]
                    else:
                        _LOGGER.debug(
                            "Skipping max values update due to binary sensor state"
                        )
                else:
                    _LOGGER.debug(
                        f"Skipping negative hourly average power: {hourly_avg_watts} W"
                    )
            else:
                _LOGGER.warning(
                    f"No mean statistics found for {self.source_sensor_entity_id} from {hour_start} to {hour_end}. Stats: {stats}"
                )

        # Update max values if changed
        if new_max_values != self.max_values:
            self.max_values = new_max_values
            self.max_values_timestamps = new_timestamps
            await self._save_max_values_data()
            # Force sensor update
            await self._update_entities("midnight update")

    async def async_reset_max_values_manually(self):
        """Manually update max values to the current month's max so far."""
        _LOGGER.info("Performing manual update of max values to current month's max")
        now = datetime.now()
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_time = now
        _LOGGER.debug(
            f"Calculating monthly max for {self.source_sensor_entity_id} from {start_time} to {end_time}"
        )

        # Calculate number of hours from start_time to end_time
        hours = int((end_time - start_time).total_seconds() // SECONDS_PER_HOUR)
        if hours == 0:
            _LOGGER.debug("No hours to process for monthly update")
            new_max_values = [0.0] * self.num_max_values
            new_timestamps = [None] * self.num_max_values
        else:
            new_max_values = [0.0] * self.num_max_values  # Start fresh for the month
            new_timestamps = [None] * self.num_max_values
            for hour in range(hours):
                hour_start = start_time + timedelta(hours=hour)
                hour_end = hour_start + timedelta(hours=1)
                _LOGGER.debug(
                    f"Querying stats for {self.source_sensor_entity_id} from {hour_start} to {hour_end}"
                )
                stats = await get_instance(self.hass).async_add_executor_job(
                    statistics_during_period,
                    self.hass,
                    hour_start,
                    hour_end,
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
                    hourly_avg_watts = stats[self.source_sensor_entity_id][0]["mean"]
                    if hourly_avg_watts >= 0:
                        hourly_avg_kw = (
                            hourly_avg_watts / WATTS_TO_KILOWATTS
                        )  # Convert watts to kW
                        _LOGGER.debug(
                            f"Hourly average power for {hour_start} to {hour_end}: {hourly_avg_kw} kW (from {hourly_avg_watts} W)"
                        )
                        if self._can_update_max_values():
                            old_max_values = new_max_values
                            new_max_values = sorted(
                                new_max_values + [hourly_avg_kw], reverse=True
                            )[: self.num_max_values]

                            # Update timestamps if value was added
                            if (
                                hourly_avg_kw not in old_max_values
                                or old_max_values.count(hourly_avg_kw)
                                < new_max_values.count(hourly_avg_kw)
                            ):
                                insert_index = 0
                                for i, val in enumerate(new_max_values):
                                    if val == hourly_avg_kw and (
                                        i >= len(old_max_values)
                                        or old_max_values[i] != hourly_avg_kw
                                    ):
                                        insert_index = i
                                        break

                                new_timestamps.insert(insert_index, hour_end)
                                new_timestamps = new_timestamps[: self.num_max_values]
                        else:
                            _LOGGER.debug(
                                "Skipping max values update due to binary sensor state"
                            )
                    else:
                        _LOGGER.debug(
                            f"Skipping negative hourly average power: {hourly_avg_watts} W"
                        )
                else:
                    _LOGGER.warning(
                        f"No mean statistics found for {self.source_sensor_entity_id} from {hour_start} to {hour_end}. Stats: {stats}"
                    )

        # Update max values
        self.max_values = new_max_values
        self.max_values_timestamps = new_timestamps
        await self._save_max_values_data()
        # Force sensor update
        await self._update_entities("manual monthly update")

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
            _LOGGER.debug(
                f"Updating entity {entity.entity_id} with unique_id {entity._attr_unique_id}"
            )
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
