from skyfield.almanac import find_discrete, risings_and_settings, meridian_transits
from skyfield.framelib import ecliptic_frame
from datetime import datetime, timedelta, timezone
from .weather import get_meyers_weather_forecast
from .utils import (
    LOCAL_TIMEZONE as local_timezone,
    TS as ts,
    EPH as eph,
    OBSERVER as observer,
    LOCATION as location,
    PLANETS as planets,
    MOON,
    format_local_time,
    get_sunrise_sunset,
)
from .api import call_anthropic_api, stream_anthropic_api
from .prompts import get_standard_system_prompt
from .cache import cached

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
    set_time = None
    altitude = None

    if rise_time_obj is not None:
        # Find the next transit after rise
        for t in times_tr:
            try:
                if t.tt >= rise_time_obj.tt:
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
    f_rise_set = risings_and_settings(eph, MOON, location)
    times_rs, events_rs = find_discrete(current_time, extended_end, f_rise_set)

    # Get all transit times in the extended period
    f_transit = meridian_transits(eph, MOON, location)
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
                    alt, _, _ = observer.at(t).observe(MOON).apparent().altaz()
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
    alt, az, distance = observer.at(current_time).observe(MOON).apparent().altaz()
    current_altitude = alt.degrees

    # Calculate moon phase
    # Get positions of sun and moon as seen from Earth
    e = observer.at(current_time)
    s = e.observe(eph["sun"]).apparent()
    m = e.observe(MOON).apparent()

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


def get_local_sunset():
    # Get current time in local timezone
    current_time = datetime.now().astimezone(local_timezone)

    # Get today's sunset time
    _, sunset_time = get_sunrise_sunset(current_time.date())

    # Convert sunset to local time
    assert sunset_time
    return sunset_time.replace(tzinfo=timezone.utc).astimezone(local_timezone)


def is_good_time_for_viewing():
    """
    Determine if it's currently a good time for planetary viewing.
    Conditions for good viewing:
    - After sunset
    - Before midnight (most people don't want to stargaze after midnight)
    - Moon illumination < 70% (less light pollution for viewing planets)
    """
    # Get current time in local timezone
    current_time = datetime.now().astimezone(local_timezone)

    # Convert sunset to local time
    sunset_local = get_local_sunset()

    # Check if current time is after sunset
    after_sunset = current_time > sunset_local

    # Check if it's before midnight
    before_midnight = current_time.hour < 23  # Before 11 PM

    return after_sunset and before_midnight


def get_report():
    lines = []
    lines.append("Moon")
    moon_data = get_moon_data()

    moon_visible = moon_data["is_visible"]
    visibility_status = "Visible now" if moon_visible else "Not currently visible"
    lines.append(f"  Status      : {visibility_status}")
    lines.append(f"  Current alt : {moon_data['current_altitude']:.2f}°")
    lines.append(
        f"  Phase       : {moon_data['phase_name']} ({moon_data['illumination']:.1f}% illuminated)"
    )

    # Print sequential moon events
    if moon_data["rise_time"]:
        lines.append(
            f"  Next rise   : {format_local_time(moon_data['rise_time'], local_timezone, True)}"
        )
        if moon_data["transit_time"]:
            lines.append(
                f"  Then transit: {format_local_time(moon_data['transit_time'], local_timezone, True)}"
            )
            lines.append(f"  Max altitude: {moon_data['zenith_angle']:.2f}°")
        if moon_data["set_time"]:
            lines.append(
                f"  Then set    : {format_local_time(moon_data['set_time'], local_timezone, True)}"
            )
    else:
        lines.append("  No rise time found in the next few days")

    # Loop through planets and compute rise/set/transit
    for name, planet in planets.items():
        lines.append(f"{name}")

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
        lines.append(f"  Status      : {visibility_status}")
        lines.append(f"  Current alt : {current_altitude:.2f}°")

        # Print sequential rise, transit, set times
        if rise_time:
            lines.append(
                f"  Next rise   : {format_local_time(rise_time, local_timezone, True)}"
            )
            if transit_time:
                lines.append(
                    f"  Then transit: {format_local_time(transit_time, local_timezone, True)}"
                )
                lines.append(f"  Max altitude: {zenith_angle_deg:.2f}°")
            if set_time:
                lines.append(
                    f"  Then set    : {format_local_time(set_time, local_timezone, True)}"
                )
        else:
            lines.append("  No rise time found in the next few days")

    return "\n".join(lines)


def get_prompt():
    current = (
        "right now."
        if is_good_time_for_viewing()
        else f"tonight. Sunset will be at {get_local_sunset().strftime('%I:%M %p')}."
    )
    return f"""
Give a casual, friendly description of the opportunities for celestial viewing in the backyard in Meyers {current}
The observations will be done with an 8" Dobsonian telescope with a 9mm 52° eyepiece.
Consider the weather forecast, as clouds or cold temps may impact viewing conditions.
There are some trees in the backyard, especially to the east and west, so bodies must be high overhead to be observed.
Just focus on night-time viewing. No early rising. Ignore what will happen after midnight.
Here's some information about the position of the planets and moon.
{get_report()}
"""


@cached(600)  # Cache for 10 minutes
async def get_planet_summary():
    """Generate a planet viewing summary that can be cached"""
    print(get_prompt())
    messages = [
        {
            "role": "user",
            "content": "Here's the current weather forecast for Meyers, near South Lake Tahoe:",
        },
        {"role": "user", "content": await get_meyers_weather_forecast()},
        {"role": "user", "content": get_prompt()},
    ]

    response = await call_anthropic_api(
        model="claude-3-7-sonnet-latest",
        system=get_standard_system_prompt(),
        messages=messages,
        max_tokens=800,
        temperature=0.2,
    )

    # Extract and return the content as a string
    return response.content[0].text


async def gen_summary():
    """Stream the planet summary for compatibility with existing code"""
    summary = await get_planet_summary()
    # Yield the whole summary at once since we're not streaming anymore
    yield summary


def install_routes(app, templates):
    """Install routes to the FastAPI app"""
    import markdown
    from fastapi import Request
    from fastapi.responses import HTMLResponse
    import traceback

    @app.get("/planets")
    async def get_planets_html(request: Request):
        """Get planets info as HTML"""
        try:
            # Get the summary as markdown
            planets_md = await get_planet_summary()

            # Convert markdown to HTML
            planets_html = markdown.markdown(planets_md, extensions=["extra"])

            # Return the HTML directly
            return HTMLResponse(planets_html)
        except Exception as e:
            print(f"Error generating planets HTML: {e}")
            traceback.print_exc()
            return HTMLResponse(f"<p>Error loading planet data: {str(e)}</p>")


async def main():
    async for text_chunk in gen_summary():
        print(text_chunk, end="", flush=True)
    print()


if __name__ == "__main__":
    # Run the main function when script is executed directly
    import asyncio

    asyncio.run(main())
