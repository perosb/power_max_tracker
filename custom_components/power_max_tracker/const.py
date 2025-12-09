DOMAIN = "power_max_tracker"
CONF_SOURCE_SENSOR = "source_sensor"
CONF_MONTHLY_RESET = "monthly_reset"
CONF_NUM_MAX_VALUES = "num_max_values"
CONF_BINARY_SENSOR = "binary_sensor"
CONF_PRICE_PER_KW = "price_per_kw"
CONF_POWER_SCALING_FACTOR = "power_scaling_factor"
CONF_START_TIME = "start_time"
CONF_STOP_TIME = "stop_time"
CONF_TIME_SCALING_FACTOR = "time_scaling_factor"
CONF_SINGLE_PEAK_PER_DAY = "single_peak_per_day"

# Constants for calculations
SECONDS_PER_HOUR = 3600
WATTS_TO_KILOWATTS = 1000.0
KILOWATT_HOURS_PER_WATT_HOUR = 1 / WATTS_TO_KILOWATTS

# Storage keys
STORAGE_VERSION = 1
MAX_VALUES_STORAGE_KEY = "max_values"
TIMESTAMPS_STORAGE_KEY = "max_values_timestamps"
PREVIOUS_MONTH_STORAGE_KEY = "previous_month_max_values"
