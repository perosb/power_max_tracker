[![power_max_tracker](https://img.shields.io/github/release/perosb/power_max_tracker/all.svg?label=current%20release)](https://github.com/perosb/power_max_tracker) [![downloads](https://img.shields.io/github/downloads/perosb/power_max_tracker/total?label=downloads)](https://github.com/perosb/power_max_tracker)

# Power Max Tracker Integration for Home Assistant

Tracks maximum cycle-average power values from a power sensor, with optional gating by a binary sensor or time window. It creates sensors for maximum values, averages, costs, and real-time tracking.

*Swedish: Spårar maxvärden för effektuttag från en effektsensor, med valfri styrning via binär sensor eller tidsfönster. Skapar sensorer för maxvärden, medelvärden, kostnader och realtidsspårning.*

## Features
- **Cycle-based max tracking**: Tracks maximum values for hourly, half-hourly, or quarterly averages
- **Average & cost sensors**: Calculates averages of the stored max values and optional cost estimates
- **Real-time source sensor**: Mirrors the input sensor with any configured gating applied
- **Current-cycle average sensor**: Shows the current ongoing cycle average in kW
- **Flexible gating**: Supports either binary-sensor gating or time-window scaling
- **Single peak per day**: Option to keep only one peak per day instead of multiple cycle peaks
- **Automatic unit handling**: Detects W or kW from the source sensor automatically, with an optional explicit scaling override
- **Services**: Includes manual recalculation and reset services

## Installation
1. **Via HACS**: Add `https://github.com/perosb/power_max_tracker` as a custom repository
2. **Manual**: Copy the `power_max_tracker` folder to `/config/custom_components/`
3. Restart Home Assistant

## Configuration

### UI Setup
1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **Power Max Tracker**
3. Configure:
   - **Source Sensor**: Power sensor to track (must provide W or kW)
   - **Number of Max Values**: How many top values to track (1-10)
   - **Monthly Reset**: Clear stored maxima on the 1st of each month
   - **Single Peak per Day**: Track only one peak per day instead of multiple cycle peaks
   - **Price per kW**: Optional electricity cost input (creates a cost sensor when greater than 0)
   - **Cycle Type**: Choose between hourly, half-hourly, or quarterly tracking intervals
   - **Power Scaling Factor**: Optional manual override for converting the source unit to watts
4. Choose one gating method:
   - **Binary Sensor**: Only track when the selected sensor is "on"
   - **Time Window**: Apply scaling during a specific time window (for example, peak pricing)

### YAML Configuration
```yaml
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.your_power_sensor
    num_max_values: 3
    monthly_reset: true
    single_peak_per_day: false
    price_per_kw: 0.25
    cycle_type: hourly  # hourly, half_hourly, or quarterly
    power_scaling_factor: 1.0  # optional; auto-detected when omitted
    # Choose one gating method:
    binary_sensor: binary_sensor.power_active  # OR
    start_time: "14:00"
    stop_time: "20:00"
    time_scaling_factor: 2.0
```

## Usage

### Entities Created
Entity names follow the selected cycle type. For example, with an hourly setup you will get sensors such as:
- `sensor.max_hourly_average_power_1_<id>`: Highest cycle average (kW)
- `sensor.max_hourly_average_power_2_<id>`: Second highest (kW)
- `sensor.max_hourly_average_power_last_update_1_<id>`: Timestamp for the highest recorded value
- `sensor.max_hourly_average_power_last_update_2_<id>`: Timestamp for the second highest recorded value
- `sensor.average_max_hourly_average_power_<id>`: Average of all stored max values
- `sensor.average_max_hourly_average_power_cost_<id>`: Cost of the average max (when pricing is configured)
- `sensor.power_max_source_<id>`: Real-time source tracking (hidden by default)
- `sensor.hourly_average_power_<id>`: Current cycle average (kW)

The same pattern is used for half-hourly and quarterly cycles, with the cycle name included in the entity names.

### Services
- `power_max_tracker.update_max_values`: Recalculate stored maxima from midnight
- `power_max_tracker.reset_max_values`: Reset the stored maxima for the current month

### Examples

**Basic Tracking:**
```yaml
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.main_power
    num_max_values: 2
    price_per_kw: 0.30
```

**Peak Hour Scaling (2x during 2-8 PM):**
```yaml
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.power_usage
    start_time: "14:00"
    stop_time: "20:00"
    time_scaling_factor: 2.0
    price_per_kw: 0.45
```

**Binary Sensor Gating:**
```yaml
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.heat_pump
    binary_sensor: binary_sensor.heat_pump_active
```

## Important Notes
- **Units**: The integration automatically detects W or kW from the source sensor's unit, but you can override the conversion with `power_scaling_factor`
- **Gating**: Binary sensor gating and time-window scaling are mutually exclusive
- **Time Windows**: Time windows can cross midnight (for example, 22:00 to 06:00)
- **Cycle Types**: Choose between hourly, half-hourly, or quarterly tracking intervals
- **Single Peak per Day**: When enabled, only the highest peak for each day is stored and averaged
- **Negative Values**: Negative values are ignored in all calculations
- **Storage**: Stored max values persist across restarts

## License
MIT License
