"""Constants for the Gym Tracker integration."""

DOMAIN = "gym_tracker"

CONF_CALENDAR_ENTITY = "calendar_entity"
CONF_TRACKED_PERSON = "tracked_person"
CONF_GYM_ZONES = "gym_zones"

CONF_YEAR = "year"
CONF_MONTH = "month"
CONF_MONTHLY_COST = "monthly_cost"

GYM_EVENT_SUMMARY = "Gym"

# How long the tracked person must stay in a configured zone before it
# counts as the start of a session, matching the "for: minutes: 5" debounce
# on the automations this integration replaces -- avoids a GPS blip near a
# zone boundary registering as a visit. Leaving has no such debounce,
# matching that same asymmetry.
SESSION_START_DEBOUNCE_MINUTES = 5

# A short, fixed lookback is enough for the streak: no realistic streak
# runs longer than this, so there's no need to widen it (or cache it) just
# because total-session history keeps growing.
STREAK_LOOKBACK_DAYS = 90

# Data older than this is treated as immutable and folded into the
# persisted cache rather than re-fetched every refresh -- see coordinator.py.
CACHE_FOLD_AFTER_DAYS = 90

DAILY_REFRESH_HOUR = 0
DAILY_REFRESH_MINUTE = 5

SERVICE_REBUILD_CACHE = "rebuild_cache"
