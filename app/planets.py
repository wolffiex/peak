from skyfield.api import load, Topos
from skyfield.almanac import find_discrete, risings_and_settings, meridian_transits
from skyfield.framelib import ecliptic_frame
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


# Helper function to get sequential astronomical events for a planet
def get_planet_events(planet_obj, ephemeris, location, observer, time_start, time_end):
    # Extend the time range to get more events
    extended_end = ts.utc((time_end.utc_datetime() + timedelta(days=2)))

    # Get all rise/set times in the extended period
    f_rise_set = risings_and_settings(ephemeris, planet_obj, location)
    times_rs, events_rs = find_discrete(time_start, extended_end, f_rise_set)

    # Get all transit times in the extended period
    f_transit = meridian_transits(ephemeris, planet_obj, location)
    times_tr, events_tr = find_discrete(time_start, extended_end, f_transit)

    # Find the next rise time (from now)
    current_time = ts.now()
    rise_time = None
    rise_time_obj = None

    # Find next rise event
    for t, event in zip(times_rs, events_rs):
        try:
            if event == 1 and t.tt >= current_time.tt:  # Rise event after current time
                rise_time_obj = t
                rise_time = t.utc_datetime().strftime("%Y-%m-%d %H:%M UTC")
                break
        except (TypeError, AttributeError):
            # Skip if time comparison fails
            continue

    # If we found a rise time, find the next transit and set after that
    transit_time = None
    transit_time_obj = None
    set_time = None
    altitude = None

    if rise_time_obj is not None:
        # Find the next transit after rise
        for t in times_tr:
            try:
                if t.tt >= rise_time_obj.tt:
                    transit_time_obj = t
                    transit_time = t.utc_datetime().strftime("%Y-%m-%d %H:%M UTC")
                    alt, _, _ = observer.at(t).observe(planet_obj).apparent().altaz()
                    altitude = alt.degrees
                    break
            except (TypeError, AttributeError):
                # Skip if time comparison fails
                continue

        # Find the next set after rise
        for t, event in zip(times_rs, events_rs):
            try:
                if event == 0 and t.tt >= rise_time_obj.tt:  # Set event after rise
                    set_time = t.utc_datetime().strftime("%Y-%m-%d %H:%M UTC")
                    break
            except (TypeError, AttributeError):
                # Skip if time comparison fails
                continue

    # Calculate current altitude to determine visibility
    current_alt, _, _ = observer.at(current_time).observe(planet_obj).apparent().altaz()
    current_altitude = current_alt.degrees

    return {
        "rise_time": rise_time,
        "set_time": set_time,
        "transit_time": transit_time,
        "altitude": altitude,  # altitude at transit
        "current_altitude": current_altitude,
        "is_visible": current_altitude > 0,
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


# Helper function to get moon phase name
def get_moon_phase_name(phase):
    """Convert a phase value (0-1) to a descriptive name"""
    if phase < 0.025 or phase >= 0.975:
        return "New Moon"
    elif phase < 0.25:
        return "Waxing Crescent"
    elif phase < 0.275:
        return "First Quarter"
    elif phase < 0.475:
        return "Waxing Gibbous"
    elif phase < 0.525:
        return "Full Moon"
    elif phase < 0.725:
        return "Waning Gibbous"
    elif phase < 0.775:
        return "Last Quarter"
    else:
        return "Waning Crescent"


# Function to get moon data
def get_moon_data():
    moon = eph["moon"]

    # Extend the time range to get more events
    extended_end = ts.utc((t1.utc_datetime() + timedelta(days=2)))

    # Find the next rise time (from now)
    current_time = ts.now()
    rise_time = None
    rise_time_obj = None
    set_time = None
    transit_time = None
    zenith_angle_deg = None

    # Get all rise/set times in the extended period
    f_rise_set = risings_and_settings(eph, moon, location)
    times_rs, events_rs = find_discrete(current_time, extended_end, f_rise_set)

    # Get all transit times in the extended period
    f_transit = meridian_transits(eph, moon, location)
    times_tr, events_tr = find_discrete(current_time, extended_end, f_transit)

    # Find next rise event
    for t, event in zip(times_rs, events_rs):
        try:
            if event == 1:  # Rise event after current time
                rise_time_obj = t
                rise_time = t.utc_datetime().strftime("%Y-%m-%d %H:%M UTC")
                break
        except (TypeError, AttributeError):
            # Skip if time comparison fails
            continue

    # If we found a rise time, find the next transit and set after that
    if rise_time_obj is not None:
        # Find the next transit after rise
        for t in times_tr:
            try:
                if t.tt >= rise_time_obj.tt:
                    transit_time = t.utc_datetime().strftime("%Y-%m-%d %H:%M UTC")
                    alt, _, _ = observer.at(t).observe(moon).apparent().altaz()
                    zenith_angle_deg = alt.degrees
                    break
            except (TypeError, AttributeError):
                # Skip if time comparison fails
                continue

        # Find the next set after rise
        for t, event in zip(times_rs, events_rs):
            try:
                if event == 0 and t.tt >= rise_time_obj.tt:  # Set event after rise
                    set_time = t.utc_datetime().strftime("%Y-%m-%d %H:%M UTC")
                    break
            except (TypeError, AttributeError):
                # Skip if time comparison fails
                continue

    # Get current altitude
    current_time = ts.now()
    alt, az, distance = observer.at(current_time).observe(moon).apparent().altaz()
    current_altitude = alt.degrees

    # Calculate moon phase
    sun = eph["sun"]

    # Get positions of sun and moon as seen from Earth
    e = observer.at(current_time)
    s = e.observe(sun).apparent()
    m = e.observe(moon).apparent()

    # Calculate sun-earth-moon angle in ecliptic coordinates
    _, slon, _ = s.frame_latlon(ecliptic_frame)
    _, mlon, _ = m.frame_latlon(ecliptic_frame)

    # Calculate phase angle (0=new, 180=full)
    phase_angle = (mlon.degrees - slon.degrees) % 360

    # Convert to phase value (0.0 to 1.0)
    phase = phase_angle / 360.0

    # Get phase name
    phase_name = get_moon_phase_name(phase)

    # Calculate illumination percentage (approximate)
    illumination = abs(50 - phase * 100) * 2
    if illumination > 100:
        illumination = 200 - illumination

    return {
        "rise_time": rise_time,
        "set_time": set_time,
        "transit_time": transit_time,
        "zenith_angle": zenith_angle_deg,
        "current_altitude": current_altitude,
        "is_visible": current_altitude > 0,
        "phase": phase,
        "phase_name": phase_name,
        "illumination": illumination,
    }


# Display moon data
print("\nMoon")
moon_data = get_moon_data()

# Format and display moon data
moon_visible = moon_data["is_visible"]
visibility_status = "Visible now" if moon_visible else "Not currently visible"
print(f"  Status      : {visibility_status}")
print(f"  Current alt : {moon_data['current_altitude']:.2f}°")
print(
    f"  Phase       : {moon_data['phase_name']} ({moon_data['illumination']:.1f}% illuminated)"
)

# Print sequential moon events
if moon_data["rise_time"]:
    print(
        f"  Next rise   : {format_local_time(moon_data['rise_time'], local_timezone, True)}"
    )
    if moon_data["transit_time"]:
        print(
            f"  Then transit: {format_local_time(moon_data['transit_time'], local_timezone, True)}"
        )
        print(f"  Max altitude: {moon_data['zenith_angle']:.2f}°")
    if moon_data["set_time"]:
        print(
            f"  Then set    : {format_local_time(moon_data['set_time'], local_timezone, True)}"
        )
else:
    print("  No rise time found in the next few days")

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
    current_altitude = planet_data["current_altitude"]
    planet_visible = planet_data["is_visible"]

    # Print results
    visibility_status = "Visible now" if planet_visible else "Not currently visible"
    print(f"  Status      : {visibility_status}")
    print(f"  Current alt : {current_altitude:.2f}°")

    # Print sequential rise, transit, set times
    if rise_time:
        print(f"  Next rise   : {format_local_time(rise_time, local_timezone, True)}")
        if transit_time:
            print(
                f"  Then transit: {format_local_time(transit_time, local_timezone, True)}"
            )
            print(f"  Max altitude: {zenith_angle_deg:.2f}°")
        if set_time:
            print(
                f"  Then set    : {format_local_time(set_time, local_timezone, True)}"
            )
    else:
        print("  No rise time found in the next few days")
