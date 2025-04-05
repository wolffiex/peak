from datetime import datetime
from app.utils import localize_time, LOCAL_TIMEZONE
# from typing import List

"""
Prompt templates for the Peak application.
This module contains all the prompts used across different contexts.
"""

KIRKWOOD_WEATHER_PROMPT = """
Give a casual, conversational description of the weather ahead for Kirkwood.
Start with today and tomorrow, then mention anything notable later in the week.
Keep it natural and get excited about snow conditions.
"""

# Roads context prompt
ROADS_PROMPT = """
Based on these road conditions, is the drive from Meyers to Kirkwood open?
We need SR-89 to be open between Meyers and Pickets Junction (Luther Pass),
and SR-88 to be open between Pickets Junction and Kirkwood (Carson Pass).
Only mention closures if they specifically affect these sections.
If these specific sections aren't mentioned in the alerts, then the road is open.
"""

# Backcountry context prompt
BACKCOUNTRY_PROMPT = """
Give a quick, casual update on backcountry conditions - like you're telling a friend what to expect today.
"""

# Kirkwood context prompt
KIRKWOOD_PROMPT = """
Give a quick overview of what's open at Kirkwood today. Focus on the main areas:
frontside, backside, Timber Creek, and the bowls. Mention overall lift and trail stats,
but don't list specific lift or trail names unless they're really important.
If there are any groomer's picks or featured groomed runs for today, mention those.
End with a brief, enthusiastic summary of the overall situation.
"""

# Traffic context prompts
TRAFFIC_CAMERA_PROMPT = """
This is a traffic camera image from {camera_name} ({camera_description}).
Describe the current road conditions very briefly (1-2 sentences max).
Focus on traffic flow, weather impacts on the road, and any visible issues. Be concise.
"""

TRAFFIC_FINAL_PROMPT = """
Give a casual, conversational summary of the drive from South Lake Tahoe to Ocean Beach in San Francisco.
Describe the route: US-50 from Tahoe to Sacramento, then I-80 through Davis, Vacaville, Fairfield, Vallejo,
across the Bay Bridge to SF, and then to Ocean Beach in the Outer Sunset.
Mention any issues like snow at Echo Summit, chain controls, or traffic congestion spots.
What's the expected drive time and are there any problem areas today?
"""


# System prompts
def get_standard_system_prompt():
    """Get the standard system prompt with the current datetime."""
    # Use the localize_time utility to get the correct local time
    local_time = localize_time(datetime.now())
    datetime_str = local_time.strftime("%A, %B %d at %I:%M %p %Z")
    return f"""
You are an expert local providing clear, practical information about current conditions in the mountains.
The current date and time is {datetime_str}.
You are based in South Lake Tahoe (specifically Meyers). When discussing events or locations:
- South Lake Tahoe, Meyers, and Stateline (Nevada) are considered local.
- North Lake Tahoe areas like Tahoe City, Kings Beach, Incline Village, and Truckee are considered separate.
- Palisades Tahoe (formerly Squaw Valley) and Northstar are in North Lake Tahoe, about 45-60 minutes away.
Present information in a natural, conversational way that helps people plan their day. Focus on what's relevant and actionable.
When describing events, be casual and engaging - mention what makes each event special in a brief, lively way.
Write like you're texting a friend about cool things happening in town - relaxed, personal, and enthusiastic.
Avoid technical jargon unless it's essential for safety or clarity.
Never start responses with greetings like "Hey there", "Hi", or "Here's" - jump straight into the information.
Don't end responses with a follow-up.
"""


def get_traffic_system_prompt(day_of_week, datetime_str):
    """Get the traffic system prompt with the current datetime."""
    return f"""
You are providing traffic information for the drive from South Lake Tahoe to Ocean Beach in San Francisco.
Today is {day_of_week}, {datetime_str}.
Present information in a natural, conversational way that helps people plan their drive.
Focus on what's relevant and actionable about road conditions.
Never start responses with greetings like "Hey there", "Hi", or "Here's" - jump straight into the information.
Don't end with questions or follow-ups.
"""


# Source definitions
def get_weather_sources():
    """Get the weather context sources."""
    return [
        {
            "url": "https://forecast.weather.gov/MapClick.php?lat=38.8504&lon=-120.019&unit=0&lg=english&FcstType=dwml",
            "intro": "Here's the current weather forecast for Strawberry/South Lake Tahoe:",
        },
        {
            "url": "http://localhost:8000/weather",
            "intro": "Here are the current readings from our local weather station:",
        },
    ]


def get_kirkwood_weather_sources():
    """Get the Kirkwood weather context sources."""
    return [
        {
            "url": "https://forecast.weather.gov/MapClick.php?lat=38.7369&lon=-120.2385&unit=0&lg=english&FcstType=dwml",
            "intro": "Here's the current weather forecast for Kirkwood:",
        }
    ]


def get_roads_sources():
    """Get the roads context sources."""
    return [
        {
            "url": "https://roads.dot.ca.gov/roadscell.php?roadnumber=89",
            "intro": "Here are the current conditions for SR-89. For the drive to Kirkwood, we only care about the section between Meyers and Pickets Junction (Luther Pass):",
        },
        {
            "url": "https://roads.dot.ca.gov/roadscell.php?roadnumber=88",
            "intro": "And here are the conditions for SR-88. For the drive to Kirkwood, we only care about the section between Pickets Junction and Kirkwood (Carson Pass):",
        },
    ]


def get_backcountry_sources():
    """Get the backcountry context sources."""
    return [
        {
            "url": "https://www.sierraavalanchecenter.org/forecasts#/all",
            "intro": "Here's today's Sierra Avalanche Center forecast:",
        }
    ]


def get_kirkwood_sources():
    """Get the Kirkwood context sources."""
    return [
        {
            "url": "https://www.kirkwood.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx",
            "intro": "Here's the current status of Kirkwood's lifts and terrain:",
        }
    ]


def get_traffic_sources():
    """Get the traffic context sources."""
    return [
        # We'll use custom fetch logic, but need this for structure
        {"url": "traffic_cameras", "intro": "Here are the current traffic conditions:"}
    ]


# Full context definitions
def get_contexts():
    """Get all context definitions."""
    return {
        # Weather context for the home page
        "weather": {
            "sources": get_weather_sources(),
            "final_prompt": weather.WEATHER_PROMPT.strip(),
        },
        # Weather context for the Kirkwood page
        "kirkwood_weather": {
            "sources": get_kirkwood_weather_sources(),
            "final_prompt": KIRKWOOD_WEATHER_PROMPT.strip(),
        },
        "roads": {"sources": get_roads_sources(), "final_prompt": ROADS_PROMPT.strip()},
        "events": {
            "name": "events",  # Used to identify this context for special processing
            "sources": events.get_sources(),
            "preprocessing_prompt": events.EVENTS_PREPROCESSING_PROMPT.strip(),
            "final_prompt": events.EVENTS_FINAL_PROMPT.strip(),
        },
        "backcountry": {
            "sources": get_backcountry_sources(),
            "final_prompt": BACKCOUNTRY_PROMPT.strip(),
        },
        "kirkwood": {
            "sources": get_kirkwood_sources(),
            "final_prompt": KIRKWOOD_PROMPT.strip(),
        },
        "traffic": {
            "name": "traffic",  # Used to identify this context for special processing
            "sources": get_traffic_sources(),
            "final_prompt": TRAFFIC_FINAL_PROMPT.strip(),
        },
    }
