from typing import AsyncGenerator, Any
from .api import call_anthropic_api, stream_anthropic_api
from .http_client import fetch_all
from .prompts import get_standard_system_prompt
import asyncio

# Events context prompts
EVENTS_PREPROCESSING_PROMPT = """
Extract all upcoming events from these sources. ONLY include events in South Lake Tahoe, Meyers, or Stateline.
Strictly exclude events from North Lake Tahoe areas (Truckee, Tahoe City, Palisades Tahoe, Northstar, Incline Village, etc).
For each event, include: 1) Name of event 2) Date and time 3) Specific venue name and location 4) Brief description if available.
Format as a simple list with date, name, and venue. Do not add any introduction or conclusion text.
"""

EVENTS_PREPROCESSING_SYSTEM = """
You extract and list events from provided sources without adding commentary.
You know South Lake Tahoe geography well. South Lake Tahoe refers to the city on the California side 
and Stateline refers to the Nevada side with casinos (Harrah's, Harvey's, Hard Rock, and Bally's).
Meyers is just south of South Lake Tahoe.
Heavenly Village, Lakeview Commons, MontBleu, and the Shops at Heavenly are all in South Lake Tahoe/Stateline area.
When an event's location is listed as "Lake Tahoe" with no further specification, check the venue name to determine if it's in South Lake.
"""

EVENTS_FINAL_PROMPT = """
Create a casual, conversational list of the most interesting upcoming events in South Lake Tahoe for the next 7-10 days.
There ARE events happening in South Lake Tahoe, Meyers, and Stateline - the casinos like Harrah's and Harvey's always have shows and entertainment.
Only list events that are actually in South Lake Tahoe, Meyers, or Stateline - exclude North Lake Tahoe.
Organize the events chronologically by date and include the specific venue for each.
Include at least 5 different events if available across different venues.
Focus on a diverse mix of entertainment, music, arts, and outdoor activities.
For each event, mention the day, date, name, venue, and a brief, casual description that captures what makes it fun or interesting.
Mention time but DON'T focus on ticket prices or technical details. Keep descriptions short, conversational and engaging.
End with an enthusiastic recommendation for your top pick of the events.
"""


def get_sources():
    from datetime import datetime, timedelta

    # Get today's date and 10 days from now
    today = datetime.now().strftime("%Y-%m-%d")
    ten_days_later = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")

    return [
        {
            "url": "https://visitlaketahoe.com/events/?event-duration=next-7-days&page-num=1&event-category=167+160+168",
            "intro": "Here are the upcoming events from Visit Lake Tahoe. Many of these events could be in North Lake Tahoe or other areas - ONLY extract events specifically in South Lake Tahoe, Meyers, or Stateline:",
        },
        {
            "url": f"https://tahoe.com/content-embed/get-content?s=all&type=event&cb=1743481352&start={today}&end={ten_days_later}",
            "intro": "Here are the events from Tahoe Daily Tribune calendar. "
            + "ONLY extract events that are specifically in South Lake Tahoe, Meyers, or Stateline - discard any events in other locations.",
        },
    ]


def preprocess_events_data(intros, results):
    """
    Returns a list of awaitables that will extract and summarize events data
    using a smaller, faster model before passing to the main model for curation.
    """

    print("Preprocessing events data with Haiku...")

    # Build messages lists for each source
    awaitables = []
    MAX_CHARS_PER_SOURCE = 50000  # Conservative limit per source

    for intro, data in zip(intros, results):
        # Truncate data if it's too long
        if len(data) > MAX_CHARS_PER_SOURCE:
            truncated_data = (
                data[:MAX_CHARS_PER_SOURCE] + "\n\n[Content truncated due to length...]"
            )
        else:
            truncated_data = data

        # Create messages for this source
        messages = [
            {"role": "user", "content": intro},
            {"role": "user", "content": truncated_data},
            {"role": "user", "content": EVENTS_PREPROCESSING_PROMPT},
        ]

        # Create an actual coroutine for each source and add it to awaitables
        # This is key - we're creating a coroutine object, not calling the API yet
        coroutine = call_anthropic_api(
            model="claude-3-5-haiku-20241022",
            messages=messages,
            system=EVENTS_PREPROCESSING_SYSTEM,
            max_tokens=4000,
            temperature=0,
        )
        awaitables.append(coroutine)

    return awaitables


async def gen_events() -> AsyncGenerator[Any, None]:
    # Get the dynamic sources
    sources = get_sources()

    # First, extract a raw list of events using a smaller model
    results = await fetch_all([source["url"] for source in sources])

    # Get awaitables for preprocessing each source
    preprocessing_awaitables = preprocess_events_data(
        [source["intro"] for source in sources], results
    )

    # Await all preprocessing tasks
    preprocessing_responses = await asyncio.gather(*preprocessing_awaitables)

    # Combine results from all sources
    raw_events_list = "\n\n".join(
        [response.content[0].text for response in preprocessing_responses]
    )
    print(raw_events_list)

    # Then pass this condensed list to the main model
    messages = [
        {
            "role": "user",
            "content": "Here's a processed list of upcoming events in Lake Tahoe:",
        },
        {"role": "user", "content": raw_events_list},
        {"role": "user", "content": EVENTS_FINAL_PROMPT},
    ]
    async for chunk in stream_anthropic_api(
        model="claude-3-7-sonnet-latest",
        messages=messages,
        system=get_standard_system_prompt(),
        max_tokens=1024,
        temperature=0.0,
    ):
        yield chunk


async def main():
    """Run the events generator and print results when script is run directly."""
    async for text_chunk in gen_events():
        print(text_chunk, end="", flush=True)
    print()


if __name__ == "__main__":
    # Run the main function when script is executed directly
    asyncio.run(main())
