"""Constants for the Breville+ Cooking integration."""

from datetime import timedelta

DOMAIN = "breville_cooking"

# The appliance list is refreshed this often; live state arrives over the
# websocket.
APPLIANCE_REFRESH_INTERVAL = timedelta(minutes=30)

# Websocket reconnect backoff, as the app: 5 s growing x1.8, capped here.
WS_RECONNECT_MIN = 5.0
WS_RECONNECT_FACTOR = 1.8
WS_RECONNECT_MAX = 300.0

SERVICE_START_COOK = "start_cook"
ATTR_TEMPERATURE = "temperature"
ATTR_DURATION = "duration"
ATTR_MODE = "mode"
ATTR_CONVECTION = "convection"
ATTR_LEVEL = "level"
ATTR_AUTO_START_TIMER = "auto_start_timer"
ATTR_KEEP_WARM = "keep_warm"
