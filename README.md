[![power_max_tracker](https://img.shields.io/github/release/perosb/power_max_tracker/all.svg?label=current%20release)](https://github.com/perosb/power_max_tracker) [![downloads](https://img.shields.io/github/downloads/perosb/power_max_tracker/total?label=downloads)](https://github.com/perosb/power_max_tracker)

# Power Max Tracker Integration for Home Assistant

The **Power Max Tracker** integration for Home Assistant tracks the maximum hourly average power values from a specified power sensor, with optional gating by a binary sensor. It creates sensors to display the top power values in kilowatts (kW), their average, a source sensor that mirrors the input sensor in watts (W), and an hourly average power sensor, all ignoring negative values and setting to `0` when the binary sensor is off.

## Features
- **Max Power Sensors**: Creates `num_max_values` sensors (e.g., `sensor.max_hourly_average_power_1_<entry_id>`, `sensor.max_hourly_average_power_2_<entry_id>`) showing the top hourly average power values in kW, rounded to 2 decimal places, with a `last_update` attribute for the timestamp of the last value change.
- **Average Max Power Sensor**: Creates a sensor (e.g., `sensor.average_max_hourly_average_power_<entry_id>`) showing the average of all max hourly average power values in kW, with an attribute `previous_month_average` for the previous month's average.
- **Average Max Cost Sensor**: Creates a sensor (e.g., `sensor.average_max_hourly_average_power_cost_<entry_id>`) showing the monetary cost of the average max hourly average power in the configured currency, with attributes for previous month cost and price per kW. Only created when price per kW is greater than 0.
- **Source Power Sensor**: Creates a sensor (e.g., `sensor.power_max_source_<entry_id>`) that tracks the source sensor in watts, setting to `0` for negative values or when the binary sensor is off/unavailable. **Hidden by default** - enable in entity settings if needed.
- **Hourly Average Power Sensor**: Creates a sensor (e.g., `sensor.hourly_average_power_<entry_id>`) that calculates the average power in kW so far in the current hour based on the source sensor's power, gated by the binary sensor, with periodic updates to account for 0W periods.
- **Time-Based Scaling**: Apply a scaling factor to power readings only during specified time windows (alternative to binary sensor gating). Supports time windows that cross midnight.
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
3. Configure the basic options:
   - **Source Sensor**: The power sensor to track (must provide watts).
   - **Number of Max Values**: Number of max power sensors (1-10, default 2).
   - **Monthly Reset**: Reset max values on the 1st of each month.
   - **Price per kW**: Electricity price per kilowatt (0.01-200.0, default 0.0). When set to 0, no cost sensor is created.
   - **Power Scaling Factor**: **Automatically detected** based on source sensor's unit_of_measurement. No manual configuration needed.
4. Configure the gating options (choose one):
   - **Binary Sensor**: Optional binary sensor to gate updates (only updates when "on").
   - **Time Window**: Configure time-based scaling instead of binary sensor gating:
     - **Start Time**: Time when scaling begins (default 00:00).
     - **Stop Time**: Time when scaling ends (default 23:59).
     - **Time Scaling Factor**: Scaling factor to apply during the time window (e.g., 2.0 to double power readings during peak hours).

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
- `binary_sensor` (optional): A binary sensor (e.g., `binary_sensor.power_enabled`) to gate updates; only updates when `"on"`. Mutually exclusive with time-based scaling options.
- `price_per_kw` (optional, default: 0.0): Electricity price per kilowatt for cost calculations (0.01-200). When set to 0, no cost sensor is created.
- `power_scaling_factor` (optional, default: 1.0): **Deprecated**. Scaling factor is now automatically detected based on source sensor's unit_of_measurement.
- `start_time` (optional, default: "00:00"): Start time for time-based scaling in HH:MM format. Mutually exclusive with binary_sensor.
- `stop_time` (optional, default: "23:59"): Stop time for time-based scaling in HH:MM format. Mutually exclusive with binary_sensor.
- `time_scaling_factor` (optional): Scaling factor to apply to power readings during the specified time window. Mutually exclusive with binary_sensor.

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

### Time-Based Scaling Example
Time-based scaling allows you to apply a scaling factor to power readings only during specific time windows, which is useful for peak/off-peak pricing or time-of-use rates. Here's an example that applies a 2x scaling factor during peak hours (2 PM to 8 PM):

```yaml
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.power_sensor
    start_time: "14:00"
    stop_time: "20:00"
    time_scaling_factor: 2.0
    price_per_kw: 0.35
```

This configuration will:
- Track power normally outside peak hours
- Multiply power readings by 2.0 during peak hours (2 PM to 8 PM)
- Calculate costs using the higher effective rate during peak hours
- Support time windows that cross midnight (e.g., start_time: "22:00", stop_time: "06:00")

**Note:** Binary sensor and time-based scaling options are mutually exclusive. Choose one gating method per configuration.

## Usage
- **Entities Created**:
  - `sensor.max_hourly_average_power_<index>_<unique_id>`: Top `num_max_values` hourly average power values in kW (e.g., `sensor.max_hourly_average_power_1_yaml_sensor_tibber_power`).
  - `sensor.average_max_hourly_average_power_<unique_id>`: Average of all max hourly average power values in kW (includes `previous_month_average` attribute).
  - `sensor.average_max_hourly_average_power_cost_<unique_id>`: Cost of the average max hourly average power in the configured currency (includes `previous_month_cost` and `price_per_kw` attributes). Only created when price per kW > 0.
  - `sensor.power_max_source_<unique_id>`: Tracks the source sensor in watts, `0` if negative or binary sensor is off/unavailable.
  - `sensor.hourly_average_power_<unique_id>`: Average power in kW so far in the current hour, with periodic updates for 0W periods.
- **Services**:
  - `power_max_tracker.update_max_values`: Recalculates max values from midnight to the current hour for instances not gated by binary sensors.
  - `power_max_tracker.reset_max_values`: Updates max values to the current month's maximum so far for instances not gated by binary sensors (resets to 0 and recalculates from month start).
- **Updates**: Max sensors update at 1 minute past each hour or after calling services. The source and hourly average sensors update in real-time when the binary sensor is `"on"`, with additional periodic updates for the hourly average sensor.

## Examples

### Basic Configuration
Track power from a smart meter with monthly resets and cost calculation:

```yaml
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.smart_meter_power
    num_max_values: 3
    monthly_reset: true
    price_per_kw: 0.28
```

### Peak/Off-Peak Pricing with Time-Based Scaling
Apply different scaling factors for peak and off-peak hours:

```yaml
# Peak hours (2x scaling)
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.power_consumption
    start_time: "14:00"
    stop_time: "20:00"
    time_scaling_factor: 2.0
    price_per_kw: 0.45
    num_max_values: 2

# Off-peak hours (0.5x scaling for credit/discount)
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.power_consumption
    start_time: "22:00"
    stop_time: "06:00"
    time_scaling_factor: 0.5
    price_per_kw: 0.15
    num_max_values: 2
```

### Seasonal Gating with Binary Sensor
Use a template binary sensor for seasonal time-of-use tracking:

```yaml
template:
  - binary_sensor:
      - name: "Winter Peak Hours"
        state: >
          {% set current_month = now().month %}
          {% set current_hour = now().hour %}
          {% if current_month in [12, 1, 2] and current_hour >= 17 and current_hour < 21 %}
            True
          {% else %}
            False
          {% endif %}

sensor:
  - platform: power_max_tracker
    source_sensor: sensor.heat_pump_power
    binary_sensor: binary_sensor.winter_peak_hours
    price_per_kw: 0.50
    monthly_reset: true
```

## Important Notes
- **Source Sensor Units**: The integration automatically detects whether the source sensor provides power in watts (W) or kilowatts (kW) based on the sensor's unit_of_measurement attribute. No manual configuration is required.
- **Time-Based Scaling**: When using time-based scaling, power readings are multiplied by the time_scaling_factor only during the specified time window. Outside the window, normal scaling applies. Time windows support crossing midnight.
- **Gating Methods**: Binary sensor gating and time-based scaling are mutually exclusive. Configure only one method per integration instance.
- **Renaming Source Sensor**: If the `source_sensor` is renamed (e.g., from `sensor.power_sensor` to `sensor.new_power_sensor`), the integration will stop tracking it. Update the configuration with the new entity ID and restart Home Assistant to restore functionality.

## License
MIT License. See `LICENSE` file for details.
