[![power_max_tracker](https://img.shields.io/github/release/perosb/power_max_tracker/all.svg?label=current%20release)](https://github.com/perosb/power_max_tracker) [![downloads](https://img.shields.io/github/downloads/perosb/power_max_tracker/total?label=downloads)](https://github.com/perosb/power_max_tracker)

# Power Max Tracker Integration for Home Assistant

The **Power Max Tracker** integration for Home Assistant tracks the maximum hourly average power values from a specified power sensor, with optional gating by a binary sensor. It creates sensors to display the top power values in kilowatts (kW), their average, a source sensor that mirrors the input sensor in watts (W), and an hourly average power sensor, all ignoring negative values and setting to `0` when the binary sensor is off.

## Features
- **Max Power Sensors**: Creates `num_max_values` sensors (e.g., `sensor.max_hourly_average_power_1_<entry_id>`, `sensor.max_hourly_average_power_2_<entry_id>`) showing the top hourly average power values in kW, rounded to 2 decimal places, with a `last_update` attribute for the timestamp of the last value change.
- **Average Max Power Sensor**: Creates a sensor (e.g., `sensor.average_max_hourly_average_power_<entry_id>`) showing the average of all max hourly average power values in kW, with an attribute `previous_month_average` for the previous month's average.
- **Average Max Cost Sensor**: Creates a sensor (e.g., `sensor.average_max_hourly_average_power_cost_<entry_id>`) showing the monetary cost of the average max hourly average power in the configured currency, with attributes for previous month cost and price per kW. Only created when price per kW is greater than 0.
- **Source Power Sensor**: Creates a sensor (e.g., `sensor.power_max_source_<entry_id>`) that tracks the source sensor's state in watts, setting to `0` for negative values or when the binary sensor is off/unavailable.
- **Hourly Average Power Sensor**: Creates a sensor (e.g., `sensor.hourly_average_power_<entry_id>`) that calculates the average power in kW so far in the current hour based on the source sensor's power, gated by the binary sensor, with periodic updates to account for 0W periods.
- **Hourly Updates**: Updates `max_values` at 1 minute past each hour using hourly average statistics from the source sensor.
- **Negative Value Filtering**: Ignores negative power values in all sensors.
- **Binary Sensor Gating**: Only updates when the binary sensor (if configured) is `"on"`.
- **Monthly Reset**: Optionally resets `max_values` to `0` on the 1st of each month.
- **Multiple Config Entries**: Supports multiple source sensors with separate max value tracking.
- **Power Scaling Factor**: Automatically detected based on the source sensor's unit_of_measurement (W/kW). No manual configuration required.
- **Electricity Price Configuration**: Configure electricity price per kW to calculate power costs.
- **Services**: Provides `power_max_tracker.update_max_values` to recalculate max values from midnight, and `power_max_tracker.reset_max_values` to update max values to the current month's maximum so far.

## Installation
1. **Via HACS**:
   - Add `https://github.com/perosb/power_max_tracker` as a custom repository in HACS.
   - Install the `Power Max Tracker` integration.
   - Restart Home Assistant.

2. **Manual Installation**:
   - Download the latest release from `https://github.com/perosb/power_max_tracker`.
   - Extract the `power_max_tracker` folder to `/config/custom_components/`.
   - Restart Home Assistant.

## Configuration
Add the integration via the Home Assistant UI or `configuration.yaml`.

### UI Configuration
1. Go to **Settings > Devices & Services > Add Integration**.
2. Search for "Power Max Tracker" and select it.
3. Configure the options:
   - **Source Sensor**: The power sensor to track (must provide watts).
   - **Number of Max Values**: Number of max power sensors (1-10, default 2).
   - **Monthly Reset**: Reset max values on the 1st of each month.
   - **Binary Sensor**: Optional binary sensor to gate updates.
   - **Price per kW**: Electricity price per kilowatt (0.01-100.0, default 0.0). When set to 0, no cost sensor is created.
   - **Power Scaling Factor**: **Automatically detected** based on source sensor's unit_of_measurement. No manual configuration needed.

### YAML Configuration
Add to your `configuration.yaml` under the `sensor` section:

```yaml
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.power_sensor
    num_max_values: 2
    monthly_reset: false
    binary_sensor: binary_sensor.power_enabled
    price_per_kw: 0.25
    power_scaling_factor: 1000  # If source sensor is in kW, convert to W
```

**Note:** YAML configurations create config entries automatically. To modify, edit `configuration.yaml` and restart Home Assistant.

### Configuration Options
- `source_sensor` (required): The power sensor to track (e.g., `sensor.power_sensor`), must provide watts (W).
- `num_max_values` (optional, default: 2): Number of max power sensors (1–10).
- `monthly_reset` (optional, default: `false`): Reset max values to `0` on the 1st of each month.
- `binary_sensor` (optional): A binary sensor (e.g., `binary_sensor.power_enabled`) to gate updates; only updates when `"on"`.
- `price_per_kw` (optional, default: 0.0): Electricity price per kilowatt for cost calculations (0.01-100.0). When set to 0, no cost sensor is created.
- `power_scaling_factor` (optional, default: 1.0): **Deprecated**. Scaling factor is now automatically detected based on source sensor's unit_of_measurement.

### Example Binary Sensor Template
If you want to gate the power tracking based on time (e.g., only during high peak hours in certain months), create a template binary sensor in your `configuration.yaml` and reference it in the `binary_sensor` option. Here's an example that activates during weekdays (Mon-Fri) from 7 AM to 8 PM in the months of November through March:

```yaml
template:
  - binary_sensor:
      - name: "Power Tracking Gate"
        state: >
          {% set current_month = now().month %}
          {% set current_day = now().weekday() %}
          {% set current_hour = now().hour %}
          {% if current_month in [11, 12, 1, 2, 3] and current_day in [0, 1, 2, 3, 4] and current_hour >= 7 and current_hour < 20 %}
            True
          {% else %}
            False
          {% endif %}
```

Then, configure the integration to use this sensor:
```yaml
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.power_sensor
    binary_sensor: binary_sensor.power_tracking_gate
```

## Usage
- **Entities Created**:
  - `sensor.max_hourly_average_power_<index>_<unique_id>`: Top `num_max_values` hourly average power values in kW (e.g., `sensor.max_hourly_average_power_1_yaml_sensor_tibber_power`).
  - `sensor.average_max_hourly_average_power_<unique_id>`: Average of all max hourly average power values in kW (includes `previous_month_average` attribute).
  - `sensor.average_max_hourly_average_power_cost_<unique_id>`: Cost of the average max hourly average power in the configured currency (includes `previous_month_cost` and `price_per_kw` attributes). Only created when price per kW > 0.
  - `sensor.power_max_source_<unique_id>`: Tracks the source sensor in watts, `0` if negative or binary sensor is off/unavailable.
  - `sensor.hourly_average_power_<unique_id>`: Average power in kW so far in the current hour, with periodic updates for 0W periods.
- **Services**:
  - `power_max_tracker.update_max_values`: Recalculates max values from midnight to the current hour.
  - `power_max_tracker.reset_max_values`: Updates max values to the current month's maximum so far (resets to 0 and recalculates from month start).
- **Updates**: Max sensors update at 1 minute past each hour or after calling services. The source and hourly average sensors update in real-time when the binary sensor is `"on"`, with additional periodic updates for the hourly average sensor.

## Important Notes
- **Source Sensor Units**: The integration automatically detects whether the source sensor provides power in watts (W) or kilowatts (kW) based on the sensor's unit_of_measurement attribute. No manual configuration is required.
- **Renaming Source Sensor**: If the `source_sensor` is renamed (e.g., from `sensor.power_sensor` to `sensor.new_power_sensor`), the integration will stop tracking it. Update the configuration with the new entity ID and restart Home Assistant to restore functionality.

## License
MIT License. See `LICENSE` file for details.
