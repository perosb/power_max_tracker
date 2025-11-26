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
    CONF_POWER_SCALING_FACTOR,
)


class PowerMaxTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            num_max = int(user_input.get(CONF_NUM_MAX_VALUES, 2))
            if num_max < 1 or num_max > 10:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._get_schema(),
                    errors={"base": "invalid_max_values"},
                )
            return self._create_entry(user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self._get_schema(),
        )

    async def async_step_import(self, import_config):
        """Handle YAML configuration import."""
        num_max = int(import_config.get(CONF_NUM_MAX_VALUES, 2))
        if num_max < 1 or num_max > 10:
            return self.async_abort(reason="invalid_max_values")

        # Duplicate checking is handled in async_setup(), so we always create here
        return self._create_entry(import_config)

    def _get_schema(self):
        """Return the data schema for the form."""
        return vol.Schema(
            {
                vol.Required(CONF_SOURCE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="power")
                ),
                vol.Optional(
                    CONF_MONTHLY_RESET, default=False
                ): selector.BooleanSelector(),
                vol.Required(CONF_NUM_MAX_VALUES, default=2): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=10, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(CONF_BINARY_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor")
                ),
                vol.Optional(
                    CONF_POWER_SCALING_FACTOR, default=1.0
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.01,
                        max=10000.0,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

    def _create_entry(self, data):
        """Normalize data and create the config entry."""
        normalized = {
            CONF_SOURCE_SENSOR: data[CONF_SOURCE_SENSOR],
            CONF_MONTHLY_RESET: data.get(CONF_MONTHLY_RESET, False),
            CONF_NUM_MAX_VALUES: int(data.get(CONF_NUM_MAX_VALUES, 2)),
            CONF_POWER_SCALING_FACTOR: float(data.get(CONF_POWER_SCALING_FACTOR, 1.0)),
        }
        if data.get(CONF_BINARY_SENSOR):
            normalized[CONF_BINARY_SENSOR] = data[CONF_BINARY_SENSOR]

        source_sensor = normalized[CONF_SOURCE_SENSOR]
        title = f"Power Max Tracker ({source_sensor.split('.')[-1]}-{str(uuid.uuid4())[:8]})"
        return self.async_create_entry(title=title, data=normalized)
