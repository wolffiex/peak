"""
Common constants used throughout the application.
"""
import pytz
from skyfield.api import load, Topos

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
LOCATION = Topos(latitude_degrees=LATITUDE, longitude_degrees=LONGITUDE, elevation_m=ELEVATION)
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