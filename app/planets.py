from skyfield.api import load, Topos
from skyfield.almanac import find_discrete, risings_and_settings, meridian_transits
from datetime import datetime, timedelta, timezone
import pytz

# Load ephemeris and time scale
eph = load("de421.bsp")  # You can use 'de440s.bsp' if you want more precision
ts = load.timescale()

# Define observer location
latitude = 38.8864
longitude = -119.9972
location = Topos(latitude_degrees=latitude, longitude_degrees=longitude)

# Define timezone for location (Pacific Time)
local_timezone = pytz.timezone("America/Los_Angeles")
observer = eph["earth"] + location

# Define the planets of interest
planets = {
    "Mars": eph["mars"],
    "Venus": eph["venus"],
    "Saturn": eph["saturn barycenter"],
    "Jupiter": eph["jupiter barycenter"],
}

# Set the date range: from today to tomorrow (UTC)
today = datetime.now(timezone.utc).date()
t0 = ts.utc(today.year, today.month, today.day)
t1 = ts.utc(today.year, today.month, today.day + 1)


# Helper function to get astronomical events for a planet
def get_planet_events(planet_obj, ephemeris, location, observer, time_start, time_end):
    # Get rise/set times
    f_rise_set = risings_and_settings(ephemeris, planet_obj, location)
    times_rs, events_rs = find_discrete(time_start, time_end, f_rise_set)

    rise_time = None
    set_time = None
    for t, event in zip(times_rs, events_rs):
        if event == 1:  # Rise event
            rise_time = t.utc_datetime().strftime("%Y-%m-%d %H:%M UTC")
        elif event == 0:  # Set event
            set_time = t.utc_datetime().strftime("%Y-%m-%d %H:%M UTC")

    # Get meridian (transit) time
    f_transit = meridian_transits(ephemeris, planet_obj, location)
    times_tr, events_tr = find_discrete(time_start, time_end, f_transit)

    transit_time = None
    altitude = None

    if times_tr:
        transit_time_obj = times_tr[0]
        transit_time = transit_time_obj.utc_datetime().strftime("%Y-%m-%d %H:%M UTC")
        alt, _, _ = observer.at(transit_time_obj).observe(planet_obj).apparent().altaz()
        altitude = alt.degrees

    return {
        "rise_time": rise_time,
        "set_time": set_time,
        "transit_time": transit_time,
        "altitude": altitude,
        "is_visible": altitude is not None and altitude > 0,
    }


# Helper function to format time in local timezone
def format_local_time(utc_time_str, tz, visible=True):
    if not utc_time_str or "No" in utc_time_str or not visible:
        return "Not visible today"

    # Parse UTC time string
    utc_time = datetime.strptime(utc_time_str, "%Y-%m-%d %H:%M UTC")
    utc_time = utc_time.replace(tzinfo=timezone.utc)

    # Convert to local time
    local_time = utc_time.astimezone(tz)

    # Format in a friendly way (e.g., "2:45 PM")
    return local_time.strftime("%I:%M %p").lstrip("0")


# Loop through planets and compute rise/set/transit
for name, planet in planets.items():
    print(f"\n{name}")

    # Get planet events
    planet_data = get_planet_events(planet, eph, location, observer, t0, t1)

    # Extract data
    rise_time = planet_data["rise_time"]
    set_time = planet_data["set_time"]
    transit_time = planet_data["transit_time"]
    zenith_angle_deg = planet_data["altitude"]
    planet_visible = planet_data["is_visible"]

    # Print results
    visibility_status = "Visible today" if planet_visible else "Not visible today"
    print(f"  Status      : {visibility_status}")

    if planet_visible:
        print(f"  Rise time   : {format_local_time(rise_time, local_timezone)}")
        print(f"  Set time    : {format_local_time(set_time, local_timezone)}")
        print(f"  Transit time: {format_local_time(transit_time, local_timezone)}")
        print(f"  Altitude    : {zenith_angle_deg:.2f}°")
    else:
        print(f"  Altitude    : {zenith_angle_deg:.2f}° (below horizon)")
