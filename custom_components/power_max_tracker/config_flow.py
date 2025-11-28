import uuid
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import (
    DOMAIN,
    CONF_SOURCE_SENSOR,
    CONF_MONTHLY_RESET,
    CONF_NUM_MAX_VALUES,
    CONF_BINARY_SENSOR,
    CONF_PRICE_PER_KW,
    CONF_POWER_SCALING_FACTOR,
    CONF_START_TIME,
    CONF_STOP_TIME,
    CONF_TIME_SCALING_FACTOR,
)


class PowerMaxTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self, *args, **kwargs):
        """Initialize the config flow."""
        super().__init__(*args, **kwargs)
        self._basic_config = None
        self._reconfigure_entry = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            if not self._validate_num_max_values(user_input):
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._get_schema(),
                    errors={"base": "invalid_max_values"},
                )
            # Store the first step data and move to time configuration
            self._basic_config = user_input
            return await self.async_step_time_config()

        return self.async_show_form(
            step_id="user",
            data_schema=self._get_schema(),
        )

    async def async_step_time_config(self, user_input=None):
        """Handle the time configuration step."""
        if user_input is not None:
            # Validate that binary sensor and time fields are mutually exclusive
            binary_sensor = user_input.get(CONF_BINARY_SENSOR)
            time_scaling = user_input.get(CONF_TIME_SCALING_FACTOR)
            start_time = user_input.get(CONF_START_TIME)
            stop_time = user_input.get(CONF_STOP_TIME)

            errors = {}
            if binary_sensor and (start_time or stop_time or time_scaling):
                errors["base"] = "binary_sensor_exclusive"

            if errors:
                return self.async_show_form(
                    step_id="time_config",
                    data_schema=self._get_time_config_schema(),
                    errors=errors,
                )

            # Combine basic config with time config
            basic_config = self._basic_config
            combined_config = {**basic_config, **user_input}
            return await self._create_entry(combined_config)

        return self.async_show_form(
            step_id="time_config",
            data_schema=self._get_time_config_schema(),
        )

    async def async_step_import(self, import_config):
        """Handle YAML configuration import."""
        if not self._validate_num_max_values(import_config):
            return self.async_abort(reason="invalid_max_values")

        # Duplicate checking is handled in async_setup(), so we always create here
        return await self._create_entry(import_config)

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration of an existing entry."""
        entry = self._get_reconfigure_entry()
        self._reconfigure_entry = entry

        if user_input is not None:
            if not self._validate_num_max_values(user_input):
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=self._get_reconfigure_schema(entry),
                    errors={"base": "invalid_max_values"},
                )
            # Store the basic config and move to time configuration
            self._basic_config = user_input
            return await self.async_step_reconfigure_time()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._get_reconfigure_schema(entry),
        )

    async def async_step_reconfigure_time(self, user_input=None):
        """Handle the time configuration step for reconfiguration."""
        entry = self._reconfigure_entry

        if user_input is not None:
            # Validate that binary sensor and time fields are mutually exclusive
            binary_sensor = user_input.get(CONF_BINARY_SENSOR)
            time_scaling = user_input.get(CONF_TIME_SCALING_FACTOR)
            start_time = user_input.get(CONF_START_TIME)
            stop_time = user_input.get(CONF_STOP_TIME)

            errors = {}
            if binary_sensor and (start_time or stop_time or time_scaling):
                errors["base"] = "binary_sensor_exclusive"

            if errors:
                return self.async_show_form(
                    step_id="reconfigure_time",
                    data_schema=self._get_reconfigure_time_schema(entry),
                    errors=errors,
                )

            # Combine basic config with time config
            combined_config = {**self._basic_config, **user_input}
            return await self._update_entry(entry, combined_config)

        return self.async_show_form(
            step_id="reconfigure_time",
            data_schema=self._get_reconfigure_time_schema(entry),
        )

    def _validate_num_max_values(self, data):
        """Validate the number of max values is within acceptable range."""
        num_max = int(data.get(CONF_NUM_MAX_VALUES, 2))
        return 1 <= num_max <= 10

    def _get_base_schema_fields(self):
        """Return the base schema field definitions."""
        return {
            CONF_SOURCE_SENSOR: selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            CONF_MONTHLY_RESET: selector.BooleanSelector(),
            CONF_NUM_MAX_VALUES: selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=10, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            CONF_BINARY_SENSOR: selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            CONF_PRICE_PER_KW: selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=100.0,
                    step=0.001,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            CONF_POWER_SCALING_FACTOR: selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.001,
                    max=10000.0,
                    step=0.001,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }

    def _get_reconfigure_schema(self, entry):
        """Return the data schema for basic reconfiguration."""
        fields = self._get_base_schema_fields()
        schema_dict = {
            vol.Required(
                CONF_SOURCE_SENSOR, default=entry.data.get(CONF_SOURCE_SENSOR)
            ): fields[CONF_SOURCE_SENSOR],
            vol.Optional(
                CONF_MONTHLY_RESET, default=entry.data.get(CONF_MONTHLY_RESET, False)
            ): fields[CONF_MONTHLY_RESET],
            vol.Required(
                CONF_NUM_MAX_VALUES, default=entry.data.get(CONF_NUM_MAX_VALUES, 2)
            ): fields[CONF_NUM_MAX_VALUES],
            vol.Optional(
                CONF_PRICE_PER_KW,
                default=entry.data.get(CONF_PRICE_PER_KW, 0.0),
            ): fields[CONF_PRICE_PER_KW],
            vol.Optional(
                CONF_POWER_SCALING_FACTOR,
                default=entry.data.get(CONF_POWER_SCALING_FACTOR, 1.0),
            ): fields[CONF_POWER_SCALING_FACTOR],
        }

        return vol.Schema(schema_dict)

    def _get_time_config_schema(self):
        """Return the data schema for the time configuration step."""
        fields = self._get_base_schema_fields()
        return vol.Schema(
            {
                vol.Optional(CONF_START_TIME, default="00:00"): selector.TimeSelector(),
                vol.Optional(CONF_STOP_TIME, default="23:59"): selector.TimeSelector(),
                vol.Optional(CONF_TIME_SCALING_FACTOR): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=10000.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(CONF_BINARY_SENSOR): fields[CONF_BINARY_SENSOR],
            }
        )

    def _get_reconfigure_time_schema(self, entry):
        """Return the data schema for reconfiguration time configuration."""
        fields = self._get_base_schema_fields()
        schema_dict = {}

        # Add time-based scaling options first (same order as initial time config)
        schema_dict[
            vol.Optional(
                CONF_START_TIME, default=entry.data.get(CONF_START_TIME, "00:00")
            )
        ] = selector.TimeSelector()
        schema_dict[
            vol.Optional(
                CONF_STOP_TIME, default=entry.data.get(CONF_STOP_TIME, "23:59")
            )
        ] = selector.TimeSelector()
        schema_dict[
            vol.Optional(
                CONF_TIME_SCALING_FACTOR,
                default=entry.data.get(CONF_TIME_SCALING_FACTOR, 1.0),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=10000.0,
                step=0.1,
                mode=selector.NumberSelectorMode.BOX,
            )
        )

        # Add binary sensor field last (same as initial time config)
        binary_sensor = entry.data.get(CONF_BINARY_SENSOR)
        if binary_sensor:
            schema_dict[vol.Optional(CONF_BINARY_SENSOR, default=binary_sensor)] = (
                fields[CONF_BINARY_SENSOR]
            )
        else:
            schema_dict[vol.Optional(CONF_BINARY_SENSOR)] = fields[CONF_BINARY_SENSOR]

        return vol.Schema(schema_dict)

    async def _update_entry(self, entry, data):
        """Normalize data and update the config entry."""
        normalized = self._normalize_config_data(data)
        return self.async_update_reload_and_abort(
            entry,
            data=normalized,
        )

    def _get_schema(self):
        """Return the data schema for the form."""
        fields = self._get_base_schema_fields()
        return vol.Schema(
            {
                vol.Required(CONF_SOURCE_SENSOR): fields[CONF_SOURCE_SENSOR],
                vol.Optional(CONF_MONTHLY_RESET, default=False): fields[
                    CONF_MONTHLY_RESET
                ],
                vol.Required(CONF_NUM_MAX_VALUES, default=2): fields[
                    CONF_NUM_MAX_VALUES
                ],
                vol.Optional(CONF_PRICE_PER_KW, default=0.0): fields[CONF_PRICE_PER_KW],
            }
        )

    def _normalize_config_data(self, data):
        """Normalize configuration data."""
        return {
            CONF_SOURCE_SENSOR: data[CONF_SOURCE_SENSOR],
            CONF_MONTHLY_RESET: data.get(CONF_MONTHLY_RESET, False),
            CONF_NUM_MAX_VALUES: int(data.get(CONF_NUM_MAX_VALUES, 2)),
            CONF_PRICE_PER_KW: float(data.get(CONF_PRICE_PER_KW, 0.0)),
            CONF_BINARY_SENSOR: data.get(CONF_BINARY_SENSOR),
            CONF_POWER_SCALING_FACTOR: float(data.get(CONF_POWER_SCALING_FACTOR, 1.0)),
            CONF_START_TIME: data.get(CONF_START_TIME, "00:00"),
            CONF_STOP_TIME: data.get(CONF_STOP_TIME, "23:59"),
            CONF_TIME_SCALING_FACTOR: data.get(CONF_TIME_SCALING_FACTOR),
        }

    async def _create_entry(self, data):
        """Normalize data and create the config entry."""
        normalized = self._normalize_config_data(data)

        source_sensor = normalized[CONF_SOURCE_SENSOR]
        # Generate a truly unique ID to prevent conflicts when multiple entries use the same source sensor
        unique_id = str(uuid.uuid4())
        await self.async_set_unique_id(unique_id)
        title = f"Power Max Tracker ({source_sensor.split('.')[-1]})"
        return self.async_create_entry(title=title, data=normalized)
