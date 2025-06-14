"""
Common utilities and constants used throughout the application.
"""

import pytz
import time
import json
import psycopg2
from psycopg2 import sql
import functools
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


class PostgresCache:
    """
    Postgres-based cache that works across multiple processes/workers.
    """

    def __init__(self, db_params=None):
        self.db_params = db_params or {"dbname": DATABASE_NAME, "user": DATABASE_USER}
        self._ensure_cache_table()

    def _get_connection(self):
        """Get a connection to the database"""
        return psycopg2.connect(**self.db_params)

    def _ensure_cache_table(self):
        """Ensure the cache table exists"""
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            # Create the cache table if it doesn't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
            """)

            # Create index on expires_at for efficient cleanup
            cur.execute("""
                CREATE INDEX IF NOT EXISTS app_cache_expires_idx ON app_cache (expires_at)
            """)

            conn.commit()
        except (Exception, psycopg2.Error) as error:
            print(f"Error creating cache table: {error}")
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def get(self, key):
        """Get a value from cache if it exists and is not expired"""
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            # Get the cache entry if it exists and is not expired
            cur.execute(
                """
                SELECT value FROM app_cache 
                WHERE key = %s AND expires_at > NOW()
            """,
                (key,),
            )

            result = cur.fetchone()

            if result:
                # Deserialize the JSON value
                return json.loads(result[0])

            return None
        except (Exception, psycopg2.Error) as error:
            print(f"Error getting from cache: {error}")
            return None
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def set(self, key, value, ttl_seconds):
        """Set a value in the cache with expiration"""
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            # Serialize the value as JSON
            serialized_value = json.dumps(value)

            # Calculate expiration time
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

            # Insert or update the cache entry
            cur.execute(
                """
                INSERT INTO app_cache (key, value, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (key) 
                DO UPDATE SET value = %s, expires_at = %s
            """,
                (key, serialized_value, expires_at, serialized_value, expires_at),
            )

            conn.commit()
            return True
        except (Exception, psycopg2.Error) as error:
            print(f"Error setting cache: {error}")
            if conn:
                conn.rollback()
            return False
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def cleanup_expired(self):
        """Clean up expired cache entries"""
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            # Delete expired entries
            cur.execute("DELETE FROM app_cache WHERE expires_at <= NOW()")
            deleted_count = cur.rowcount
            conn.commit()

            return deleted_count
        except (Exception, psycopg2.Error) as error:
            print(f"Error cleaning up cache: {error}")
            if conn:
                conn.rollback()
            return 0
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()


# Create a global cache instance
postgres_cache = PostgresCache()


def cached(ttl_seconds):
    """
    Decorator that caches function results for specified seconds.
    Works across multiple processes by using Postgres-based caching.

    Usage:
        @cached(300)  # Cache for 5 minutes
        def my_function(arg1, arg2):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from the function name
            cache_key = f"{func.__module__}.{func.__name__}"

            # Check cache first
            cached_result = postgres_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Cache miss, call the original function
            result = func(*args, **kwargs)

            # Cache the result
            postgres_cache.set(cache_key, result, ttl_seconds)

            return result

        return wrapper

    return decorator
