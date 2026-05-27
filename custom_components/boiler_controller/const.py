DOMAIN = "boiler_controller"
VERSION = "1.0.0"

PLATFORMS = ["sensor", "select", "number", "button"]

# Configuration flow step IDs
STEP_POWER_SENSOR = "power_sensor"
STEP_DEVICE_CONFIG = "device_config"

# Configuration keys
CONF_P1_TOTAL_ENTITY = "power_sensor"
CONF_DEVICE_URL = "device_url"
CONF_POLL_INTERVAL = "poll_interval"
CONF_DEVICE_ID = "device_id"

# Boiler Controller mDNS hostname prefix (pb-bc-*)
BC_HOST_PREFIX = ("pb-bc-",)

# Control modes
BOILER_MODE_AUTO = "auto"
BOILER_MODE_MANUAL = "manual"
BOILER_MODE_ON = "on"
BOILER_MODE_OFF = "off"
BOILER_MODE_CALIBRATING = "calibrating"
BOILER_MODES = [BOILER_MODE_AUTO, BOILER_MODE_MANUAL, BOILER_MODE_ON, BOILER_MODE_OFF]

# Manual mode defaults
DEFAULT_MANUAL_WATTS = 0

# Seconds between device status polls (updates all sensor values)
DEFAULT_POLL_INTERVAL = 10

# Calibration service names
SERVICE_RUN_CALIBRATION = "run_calibration"
SERVICE_CANCEL_CALIBRATION = "cancel_calibration"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

# Poll interval while waiting for device calibration to complete
CALIBRATION_POLL_SECONDS = 5

# Safety limits
MAX_EXPORT_WATTS = 3500