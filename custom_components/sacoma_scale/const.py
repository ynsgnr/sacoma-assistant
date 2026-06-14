"""Constants for the SACOMA smart scale integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "sacoma_scale"

# --- BLE wire identifiers (ICOMON / Chipsea FFB0 service) ------------------------------
# The scale exposes a single proprietary service holding one write characteristic
# (commands, app -> scale) and two notify characteristics (scale -> app):
#   * FFB2 streams the live weight (A2 frames)
#   * FFB3 carries the final BIA result (A3 frame: weight + 10 segmental impedances)
SERVICE_UUID: Final = "0000ffb0-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID: Final = "0000ffb1-0000-1000-8000-00805f9b34fb"
WEIGHT_NOTIFY_UUID: Final = "0000ffb2-0000-1000-8000-00805f9b34fb"
RESULT_NOTIFY_UUID: Final = "0000ffb3-0000-1000-8000-00805f9b34fb"

# Advertised Complete Local Name seen in the device captures. Note this is the BLE
# advertising name (which the Fitdays app lets you customise), not the GATT model
# number ("FG2015B-A"). Used as a discovery hint when the FFB0 service UUID is not
# present in the advertisement; the service UUID is the universal match.
LOCAL_NAME: Final = "MY_SCALE"

# --- Config entry keys ----------------------------------------------------------------
CONF_ADDRESS: Final = "address"
CONF_DEVICE_NAME: Final = "device_name"
CONF_DRIVE: Final = "drive"          # bool -> run the FFB1 sync that drives the scale's screen
CONF_USERS: Final = "users"          # list of user dicts (keys below)

# Per-user keys. Weight range drives auto-selection; the profile feeds the WLA25 algorithm.
CONF_USER_NAME: Final = "name"
CONF_WEIGHT_MIN: Final = "weight_min"
CONF_WEIGHT_MAX: Final = "weight_max"
CONF_HEIGHT_CM: Final = "height_cm"
CONF_AGE: Final = "age"
CONF_SEX: Final = "sex"              # "male" / "female"
CONF_ATHLETE: Final = "athlete"      # bool -> PeopleType.SPORTMAN
CONF_USER_ID: Final = "user_id"      # scale account id (0 = none/test); only used when driving
CONF_ADD_ANOTHER: Final = "add_another"

SEX_MALE: Final = "male"
SEX_FEMALE: Final = "female"

DEFAULT_HEIGHT_CM: Final = 170
DEFAULT_AGE: Final = 30
DEFAULT_USER_ID: Final = 0
# Reading is passive; driving only adds the on-device body-comp screen, so it stays opt-in.
DEFAULT_DRIVE: Final = False

# --- Timing (seconds) -----------------------------------------------------------------
# Overall budget for one connection: read the settled weight, then (when driving) publish.
MEASUREMENT_TIMEOUT_S: Final = 45.0
# Sub-budget for the live weight to settle at its peak before we select a user.
READ_WEIGHT_TIMEOUT_S: Final = 25.0
# How long to keep driving the scale (sustained sync) after selecting a user.
PUBLISH_SECONDS: Final = 20.0
DRIVE_INTERVAL_S: Final = 0.4
# Stabilized weight must hold within this band for SETTLE_READS samples to be trusted.
WEIGHT_EPSILON_KG: Final = 0.05
SETTLE_READS: Final = 8
MIN_WEIGHT_KG: Final = 20.0
