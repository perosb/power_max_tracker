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
)


class PowerMaxTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            if not self._validate_num_max_values(user_input):
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._get_schema(),
                    errors={"base": "invalid_max_values"},
                )
            return await self._create_entry(user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self._get_schema(),
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

        if user_input is not None:
            if not self._validate_num_max_values(user_input):
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=self._get_reconfigure_schema(entry),
                    errors={"base": "invalid_max_values"},
                )
            return await self._update_entry(entry, user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._get_reconfigure_schema(entry),
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
        }

    def _get_reconfigure_schema(self, entry):
        """Return the data schema for reconfiguration with current values."""
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
        }

        # Only add binary sensor field with default if it has a value
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
                vol.Optional(CONF_BINARY_SENSOR): fields[CONF_BINARY_SENSOR],
            }
        )

    def _normalize_config_data(self, data):
        """Normalize configuration data."""
        return {
            CONF_SOURCE_SENSOR: data[CONF_SOURCE_SENSOR],
            CONF_MONTHLY_RESET: data.get(CONF_MONTHLY_RESET, False),
            CONF_NUM_MAX_VALUES: int(data.get(CONF_NUM_MAX_VALUES, 2)),
            CONF_BINARY_SENSOR: data.get(CONF_BINARY_SENSOR),
        }

    async def _create_entry(self, data):
        """Normalize data and create the config entry."""
        normalized = self._normalize_config_data(data)

        source_sensor = normalized[CONF_SOURCE_SENSOR]
        unique_id = f"power_max_tracker_{source_sensor.replace('.', '_')}"
        await self.async_set_unique_id(unique_id)
        title = f"Power Max Tracker ({source_sensor.split('.')[-1]}-{str(uuid.uuid4())[:8]})"
        return self.async_create_entry(title=title, data=normalized)
