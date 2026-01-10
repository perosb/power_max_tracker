[![power_max_tracker](https://img.shields.io/github/release/perosb/power_max_tracker/all.svg?label=current%20release)](https://github.com/perosb/power_max_tracker) [![downloads](https://img.shields.io/github/downloads/perosb/power_max_tracker/total?label=downloads)](https://github.com/perosb/power_max_tracker)

# Power Max Tracker Integration for Home Assistant

Tracks maximum hourly average power values from a power sensor, with optional gating by binary sensor or time windows. Creates sensors for max values, averages, costs, and real-time tracking.

*Swedish: Spårar effektvärden från en effektsensor för att enkelt kunna påverka din effekttariff. Valfri styrning via binär sensor eller tidsfönster. Skapar sensorer för maxvärden, medelvärden, kostnader och realtidsspårning.*

## Features
- **Max Power Sensors**: Top hourly average power values in kW with timestamps
- **Average & Cost Sensors**: Average of max values and monetary cost calculation
- **Real-time Source Sensor**: Mirrors input sensor with gating applied
- **Hourly Average Sensor**: Current hour's average power calculation
- **Flexible Gating**: Binary sensor or time-window based power scaling
- **Single Peak per Day**: Option to track only one peak value per day instead of multiple hourly peaks
- **Automatic Scaling**: Detects W/kW units from source sensor
- **Services**: Manual max value updates and resets

## Installation
1. **Via HACS**: Add `https://github.com/perosb/power_max_tracker` as custom repository
2. **Manual**: Copy `power_max_tracker` folder to `/config/custom_components/`
3. Restart Home Assistant

## Configuration

### UI Setup
1. **Settings > Devices & Services > Add Integration**
2. Search "Power Max Tracker"
3. Configure:
   - **Source Sensor**: Power sensor to track (must provide W or kW)
   - **Number of Max Values**: How many top values to track (1-10)
   - **Monthly Reset**: Clear max values on 1st of each month
   - **Single Peak per Day**: Track only one peak per day instead of multiple hourly peaks
   - **Price per kW**: Electricity cost (creates cost sensor when > 0)
   - **Cycle Type**: Choose between hourly or quarterly (15-minute) tracking intervals

4. Choose gating method:
   - **Binary Sensor**: Only track when sensor is "on"
   - **Time Window**: Scale power during specific hours (e.g., peak pricing)

### YAML Configuration
```yaml
sensor:
  - platform: power_max_tracker
    source_sensor: sensor.your_power_sensor
    num_max_values: 3
    monthly_reset: true
    single_peak_per_day: false
    price_per_kw: 0.25
    cycle_type: hourly  # or "quarterly" for 15-minute intervals
    # Choose one gating method:
    binary_sensor: binary_sensor.power_active  # OR
    start_time: "14:00"
    stop_time: "20:00"
    time_scaling_factor: 2.0
```

## Usage

### Entities Created
- `sensor.max_hourly_average_power_1_<id>`: Highest cycle average (kW)
- `sensor.max_hourly_average_power_2_<id>`: Second highest (kW)
- `sensor.average_max_hourly_average_power_<id>`: Average of all max values
- `sensor.average_max_hourly_average_power_cost_<id>`: Cost of average max (when price configured)
- `sensor.power_max_source_<id>`: Real-time source tracking (W, hidden by default)
- `sensor.<cycle>_average_power_<id>`: Current cycle average (kW, e.g., "hourly_average_power" or "quarterly_average_power")

### Services
- `power_max_tracker.update_max_values`: Recalculate from midnight
- `power_max_tracker.reset_max_values`: Reset to current month max

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
- **Units**: Automatically detects W/kW from source sensor's unit_of_measurement
- **Gating**: Binary sensor and time scaling are mutually exclusive
- **Time Windows**: Support crossing midnight (e.g., 22:00 to 06:00)
- **Cycle Types**: Choose between hourly (60-minute) or quarterly (15-minute) tracking intervals
- **Single Peak per Day**: When enabled, tracks only the highest peak per day instead of multiple cycle peaks, changing how max values are stored and averaged
- **Negative Values**: Ignored in all calculations
- **Storage**: Max values persist across restarts

## License
MIT License
