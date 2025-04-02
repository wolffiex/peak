"""
Common utilities and constants used throughout the application.
"""

import pytz
from skyfield.api import load, Topos
from skyfield.almanac import find_discrete
from datetime import datetime, timedelta, timezone

# Location constants (South Lake Tahoe)
LATITUDE = 38.8864
LONGITUDE = -119.9972
ELEVATION = 1900  # meters, approximate for South Lake Tahoe

# Timezone constants
LOCAL_TIMEZONE = pytz.timezone("America/Los_Angeles")

# Database constants
DATABASE_NAME = "monitoring"
DATABASE_USER = "adam"

# Skyfield constants
EPHEMERIS_FILE = "/home/adam/code/peak/de421.bsp"
EPH = load(EPHEMERIS_FILE)
TS = load.timescale()

# Create skyfield objects
# Create location object for skyfield
LOCATION = Topos(
    latitude_degrees=LATITUDE, longitude_degrees=LONGITUDE, elevation_m=ELEVATION
)
OBSERVER = EPH["earth"] + LOCATION
SUN = EPH["sun"]
MOON = EPH["moon"]

# Planet objects
PLANETS = {
    "Mars": EPH["mars"],
    "Venus": EPH["venus"],
    "Saturn": EPH["saturn barycenter"],
    "Jupiter": EPH["jupiter barycenter"],
}


def format_local_time(utc_time_str, tz, visible=True):
    """
    Format a UTC time string to a human-readable local time.

    Args:
        utc_time_str: UTC time string in the format "%Y-%m-%d %H:%M UTC"
        tz: The timezone to convert to
        visible: Whether the object is visible (determines return value if no time)

    Returns:
        A human-readable string like "Today at 2:30 PM" or "Tomorrow at 3:45 AM"
    """
    if not utc_time_str or "No" in utc_time_str or not visible:
        return "Not visible today"

    # Parse UTC time string
    utc_time = datetime.strptime(utc_time_str, "%Y-%m-%d %H:%M UTC")
    utc_time = utc_time.replace(tzinfo=timezone.utc)

    # Convert to local time
    local_time = utc_time.astimezone(tz)

    # Get today and tomorrow dates in the local timezone
    today_local = datetime.now(tz).date()
    tomorrow_local = today_local + timedelta(days=1)

    # Format time with "today" or "tomorrow" prefix
    time_str = local_time.strftime("%I:%M %p").lstrip("0")
    if local_time.date() == today_local:
        return f"Today at {time_str}"
    elif local_time.date() == tomorrow_local:
        return f"Tomorrow at {time_str}"
    else:
        return f"{local_time.strftime('%A')} at {time_str}"


def localize_time(time_obj):
    """
    Convert a datetime object to local Pacific Time.

    Args:
        time_obj: A datetime object, which may or may not have timezone information

    Returns:
        A datetime object localized to Pacific Time
    """
    if time_obj is None:
        return None

    if time_obj.tzinfo is not None:
        # If datetime already has timezone info, convert to local timezone
        return time_obj.astimezone(LOCAL_TIMEZONE)
    else:
        # If datetime is naive (no timezone), assume it's UTC and convert
        return pytz.utc.localize(time_obj).astimezone(LOCAL_TIMEZONE)


def get_sunrise_sunset(date_local):
    """
    Calculate sunrise and sunset times for a given date.

    Args:
        date_local: A datetime object with the date to calculate for (in local timezone)

    Returns:
        A tuple (sunrise_time, sunset_time) with datetime objects in UTC timezone
    """
    # Create time range for the given date (midnight to midnight local time)
    date_start = LOCAL_TIMEZONE.localize(
        datetime(date_local.year, date_local.month, date_local.day, 0, 0, 0)
    )
    date_end = LOCAL_TIMEZONE.localize(
        datetime(date_local.year, date_local.month, date_local.day, 23, 59, 59)
    )

    # Convert to skyfield time objects
    t0 = TS.from_datetime(date_start)
    t1 = TS.from_datetime(date_end)

    def sunrise_sunset(t):
        """Return 1 for sunrise, 0 for sunset"""
        position = OBSERVER.at(t).observe(SUN).apparent()
        alt, _, _ = position.altaz()
        return alt.degrees > 0.0

    # Add the step_days attribute required by find_discrete
    sunrise_sunset.step_days = 0.01  # Check roughly every 15 minutes

    # Find sunrise and sunset times
    times, events = find_discrete(t0, t1, sunrise_sunset)

    sunrise_time = None
    sunset_time = None

    for time, event in zip(times, events):
        if event == 1:  # Sunrise
            sunrise_time = time.utc_datetime()
        elif event == 0:  # Sunset
            sunset_time = time.utc_datetime()

    return sunrise_time, sunset_time
