from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from anthropic import Anthropic
from datetime import datetime
from app import ha
from app import photos
from app import weather
from app import traffic
import httpx
import asyncio
import os
import traceback
from contextlib import asynccontextmanager

CONTEXT = {
    # Weather context for the home page
    "weather": {
        "sources": [
            {
                "url": "https://forecast.weather.gov/MapClick.php?lat=38.8504&lon=-120.019&unit=0&lg=english&FcstType=dwml",
                "intro": "Here's the current weather forecast for Strawberry/South Lake Tahoe:"
            },
            {
                "url": "http://localhost:8000/weather",
                "intro": "Here are the current readings from our local weather station:"
            }
        ],
        "final_prompt": "Give a casual, friendly description of the weather right here in Meyers. " +
                       "Start with a conversational mention of the current temperature and conditions - like you're chatting with a neighbor. " +
                       "For example: 'It's a chilly 38° here in Meyers right now with clear skies.' " +
                       "Blend in the weather station data naturally without listing statistics. " +
                       "Mention if it's particularly humid, if the barometer is rising/falling, or if there's barely any wind. " +
                       f"The current time is {datetime.now().strftime('%A, %B %d at %I:%M %p')}. " +
                       "After the current conditions, tell us what to expect today/tomorrow and through the week. " +
                       "Be enthusiastic about any exciting weather patterns coming - especially snow! " +
                       "End with a casual recommendation for outdoor activities given the forecast."
    },
    
    # Weather context for the Kirkwood page
    "kirkwood_weather": {
        "sources": [{
            "url": "https://forecast.weather.gov/MapClick.php?lat=38.7369&lon=-120.2385&unit=0&lg=english&FcstType=dwml",
            "intro": "Here's the current weather forecast for Kirkwood:"
        }],
        "final_prompt": "Give a casual, conversational description of the weather ahead for Kirkwood. " +
                       "Start with today and tomorrow, then mention anything notable later in the week. " +
                       "Keep it natural and get excited about snow conditions.",
    },
    "roads": {
        "sources": [
            {
                "url": "https://roads.dot.ca.gov/roadscell.php?roadnumber=89",
                "intro": "Here are the current conditions for SR-89. For the drive to Kirkwood, we only care about the section between Meyers and Pickets Junction (Luther Pass):"
            },
            {
                "url": "https://roads.dot.ca.gov/roadscell.php?roadnumber=88",
                "intro": "And here are the conditions for SR-88. For the drive to Kirkwood, we only care about the section between Pickets Junction and Kirkwood (Carson Pass):"
            }
        ],
        "final_prompt": "Based on these road conditions, is the drive from Meyers to Kirkwood open? " +
                       "We need SR-89 to be open between Meyers and Pickets Junction (Luther Pass), " +
                       "and SR-88 to be open between Pickets Junction and Kirkwood (Carson Pass). " +
                       "Only mention closures if they specifically affect these sections. " +
                       "If these specific sections aren't mentioned in the alerts, then the road is open."
    },
    "events": {
        "name": "events", # Used to identify this context for special processing
        "sources": [
            {
                "url": "https://visitlaketahoe.com/events/?event-duration=next-7-days&page-num=1&event-category=167+160+168",
                "intro": "Here are the upcoming events from Visit Lake Tahoe. Many of these events could be in North Lake Tahoe or other areas - ONLY extract events specifically in South Lake Tahoe, Meyers, or Stateline:"
            },
            {
                "url": "https://www.tahoedailytribune.com/entertainment/calendar/",
                "intro": "Here are the events from Tahoe Daily Tribune calendar. " +
                "ONLY extract events that are specifically in South Lake Tahoe, Meyers, or Stateline - discard any events in other locations."
            },
            {
                "url": "https://www.caesars.com/harrahs-tahoe/things-to-do/events",
                "intro": "Here are the events from Harrah's Lake Tahoe:"
            },
            {
                "url": "https://www.caesars.com/harveys-tahoe/shows",
                "intro": "Here are the shows at Harvey's Lake Tahoe:"
            },
            {
                "url": "https://casinos.ballys.com/lake-tahoe/entertainment.htm",
                "intro": "Here are events from Bally's Lake Tahoe:"
            }
        ],
        "preprocessing_prompt": "Extract all upcoming events from these sources. Include events that are ACTUALLY happening in South Lake Tahoe, Meyers, or Stateline. " +
                              "Pay special attention to the event venue and location. Harrah's, Harvey's, Hard Rock, and Bally's are all located in Stateline. " +
                              "South Lake Tahoe has many venues including Lakeview Commons, Heavenly Village, Valhalla, and South Lake Brewing. " +
                              "Exclude events from North Lake Tahoe areas (Truckee, Tahoe City, Palisades Tahoe, Northstar, Incline Village, etc). " +
                              "For each event, include: " +
                              "1) Name of event 2) Date and time 3) Specific venue name and location 4) Brief description if available. " +
                              "Format as a simple list with date, name, and venue. Do not add any introduction or conclusion text.",
        "final_prompt": "Create a casual, conversational list of the most interesting upcoming events in South Lake Tahoe for the next 7-10 days. " +
                       "There ARE events happening in South Lake Tahoe, Meyers, and Stateline - the casinos like Harrah's and Harvey's always have shows and entertainment. " +
                       "Only list events that are actually in South Lake Tahoe, Meyers, or Stateline - exclude North Lake Tahoe. " +
                       "Organize the events chronologically by date and include the specific venue for each. " +
                       "Include at least 5 different events if available across different venues. " +
                       "Focus on a diverse mix of entertainment, music, arts, and outdoor activities. " +
                       "For each event, mention the day, date, name, venue, and a brief, casual description that captures what makes it fun or interesting. " +
                       "Mention time but DON'T focus on ticket prices or technical details. Keep descriptions short, conversational and engaging. " +
                       "End with an enthusiastic recommendation for your top pick of the events."
    },
    "backcountry": {
        "sources": [{
            "url": "https://www.sierraavalanchecenter.org/forecasts#/all",
            "intro": "Here's today's Sierra Avalanche Center forecast:"
        }],
        "final_prompt": "Give a quick, casual update on backcountry conditions - like you're telling a friend what to expect today."
    },
    "kirkwood": {
        "sources": [{
            "url": "https://www.kirkwood.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx",
            "intro": "Here's the current status of Kirkwood's lifts and terrain:"
        }],
        "final_prompt": "Give a quick overview of what's open at Kirkwood today. Focus on the main areas: " +
                       "frontside, backside, Timber Creek, and the bowls. Mention overall lift and trail stats, " +
                       "but don't list specific lift or trail names unless they're really important. " +
                       "If there are any groomer's picks or featured groomed runs for today, mention those. " +
                       "End with a brief, enthusiastic summary of the overall situation."
    },
}

BASE_PATH = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))
app = FastAPI()
app.mount("/dist", StaticFiles(directory="dist"), name="dist")
ha.install_routes(app, templates)
photos.install_routes(app, templates)
weather.install_routes(app, templates)
traffic.install_routes(app, templates)
# Set up Anthropic client
anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Create a semaphore to limit concurrent API calls
# Anthropic's rate limits vary by model, but we'll use a conservative limit
anthropic_semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent API calls

# HTTP client with timeout
http_client = httpx.AsyncClient(timeout=300)  # 5 minute timeout

# Dictionary to store custom analyzers for specific contexts
CUSTOM_ANALYZERS = {}

def register_custom_analyzer(context_name, analyzer_function):
    """Register a custom analyzer function for a specific context"""
    CUSTOM_ANALYZERS[context_name] = analyzer_function
    print(f"Registered custom analyzer for context: {context_name}")

async def call_anthropic_api(model, messages, system=None, max_tokens=1024, temperature=0, stream=False):
    """
    Centralized function for all Anthropic API calls with concurrency control.
    
    Args:
        model: The Claude model to use
        messages: The conversation messages
        system: Optional system prompt
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        stream: Whether to stream the response
        
    Returns:
        The API response
    """
    print(f"Calling Anthropic API with model: {model}")
    
    # Use semaphore to control concurrency
    async with anthropic_semaphore:
        try:
            # Create the API parameters
            params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
                "stream": stream
            }
            
            # Add system prompt if provided
            if system:
                params["system"] = system
                
            # Make the API call
            response = anthropic.messages.create(**params)
            return response
        except Exception as e:
            print(f"Error calling Anthropic API: {e}")
            raise

@app.on_event("startup")
async def startup_event():
    app.state.http_client = httpx.AsyncClient(timeout=300)  # 5 minute timeout

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.http_client.aclose()

async def fetch(url, custom_app=None):
    """
    Fetch data from a URL using the app's HTTP client.
    Accepts an optional custom_app parameter to support CLI usage.
    """
    print(f"Fetching {url}...")
    # Use the provided custom_app or the global app
    client_app = custom_app or app
    response = await client_app.state.http_client.get(url)
    print(f"Got response from {url}: {response.status_code}")
    text = response.text
    print(f"Response length: {len(text)} characters")
    return text

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("home.html", {"request": request, "contexts_data": CONTEXT})

@app.get("/kirkwood", response_class=HTMLResponse)
async def kirkwood(request: Request):
    return templates.TemplateResponse("kirkwood.html", {"request": request, "contexts_data": CONTEXT})

async def preprocess_events_data(sources, results):
    """
    Uses a smaller, faster model to extract and summarize events data
    before passing to the main model for curation.
    """
    print("Preprocessing events data with Haiku...")
    
    # Build messages list with intro data pairs, but truncate long content
    messages = []
    MAX_CHARS_PER_SOURCE = 50000  # Conservative limit per source
    
    for source, data in zip(sources, results):
        # Truncate data if it's too long
        if len(data) > MAX_CHARS_PER_SOURCE:
            print(f"Truncating source data from {len(data)} to {MAX_CHARS_PER_SOURCE} characters...")
            truncated_data = data[:MAX_CHARS_PER_SOURCE] + "\n\n[Content truncated due to length...]"
        else:
            truncated_data = data
            
        messages.extend([
            {"role": "user", "content": source["intro"]},
            {"role": "user", "content": truncated_data}
        ])
    
    # Add the preprocessing prompt
    messages.append({
        "role": "user", 
        "content": CONTEXT["events"]["preprocessing_prompt"]
    })
    
    try:
        # Use Claude Haiku for faster preprocessing through our centralized API function
        haiku_system = """You extract and list events from provided sources without adding commentary.
            You know South Lake Tahoe geography well. South Lake Tahoe refers to the city on the California side 
            and Stateline refers to the Nevada side with casinos (Harrah's, Harvey's, Hard Rock, and Bally's).
            Meyers is just south of South Lake Tahoe.
            Heavenly Village, Lakeview Commons, MontBleu, and the Shops at Heavenly are all in South Lake Tahoe/Stateline area.
            When an event's location is listed as "Lake Tahoe" with no further specification, check the venue name to determine if it's in South Lake."""
            
        haiku_response = await call_anthropic_api(
            model="claude-3-5-haiku-20241022",
            messages=messages,
            system=haiku_system,
            max_tokens=4000,
            temperature=0,
            stream=False
        )
        
        # Return the extracted list of events
        return haiku_response.content[0].text
    except Exception as e:
        print(f"Error in preprocessing events: {e}")
        # Fallback to a simple message if preprocessing fails
        return "Unable to extract events due to content size limitations. Please check the original sources for complete event listings."

async def analyze_section(context, custom_app=None):
    print(f"Analyzing data for context: {context.get('name', 'unnamed')}")
    
    # Check if there's a custom analyzer for this context
    if context.get("name") in CUSTOM_ANALYZERS:
        print(f"Using custom analyzer for {context.get('name')}")
        try:
            # Use the custom analyzer and return its streaming response
            custom_result = await CUSTOM_ANALYZERS[context.get("name")]()
            
            # For custom analyzers that don't return a stream, wrap the result in a stream
            if isinstance(custom_result, str):
                class SimpleStream:
                    def __init__(self, text):
                        self.text = text
                        self.sent = False
                        
                    def __aiter__(self):
                        return self
                        
                    async def __anext__(self):
                        if self.sent:
                            raise StopAsyncIteration
                        self.sent = True
                        return type('ContentBlockDelta', (), {
                            'type': 'content_block_delta',
                            'delta': type('TextDelta', (), {'text': self.text})
                        })
                
                return SimpleStream(custom_result)
            
            # If it's already a stream, return it directly
            return custom_result
        except Exception as e:
            print(f"Error in custom analyzer for {context.get('name')}: {e}")
            # Fall back to standard processing
            
    # Standard processing path - fetch all sources
    results = await asyncio.gather(*[fetch(source["url"], custom_app) for source in context["sources"]])
    
    # Special handling for events context - use pre-processing with a smaller model
    if context.get("name") == "events":
        print("Using special events processing pipeline...")
        
        try:
            # First, extract a raw list of events using a smaller model
            raw_events_list = await preprocess_events_data(context["sources"], results)
            
            # Then pass this condensed list to the main model
            messages = [
                {"role": "user", "content": "Here's a processed list of upcoming events in Lake Tahoe:"},
                {"role": "user", "content": raw_events_list},
                {"role": "user", "content": context["final_prompt"]}
            ]
        except Exception as e:
            print(f"Error in events pipeline, falling back to standard processing: {e}")
            # If the events pipeline fails, fall back to standard processing with truncated data
            messages = []
            MAX_CHARS = 30000  # Even more conservative limit for fallback
            
            for source, data in zip(context["sources"], results):
                truncated_data = data[:MAX_CHARS] if len(data) > MAX_CHARS else data
                messages.extend([
                    {"role": "user", "content": source["intro"]},
                    {"role": "user", "content": truncated_data}
                ])
            
            messages.append({
                "role": "user",
                "content": context["final_prompt"] + " Note: Some event data may have been truncated due to size constraints."
            })
    else:
        # Standard processing for other contexts
        # Build messages list with intros and data
        messages = []
        for source, data in zip(context["sources"], results):
            messages.extend([
                {"role": "user", "content": source["intro"]},
                {"role": "user", "content": data}
            ])
        
        # Add the final prompt
        messages.append({
            "role": "user",
            "content": context["final_prompt"]
        })
    
    system_prompt = f"""
You are an expert local providing clear, practical information about current conditions in the mountains.
The current date and time is {datetime.now().strftime('%A, %B %d at %I:%M %p Pacific')}.
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
        """.strip()

    # Use our centralized function with concurrency control
    message = await call_anthropic_api(
        model="claude-3-opus-20240229",
        messages=messages,
        system=system_prompt,
        max_tokens=1024,
        temperature=0,
        stream=True
    )
    return message

@app.get('/stream/{context_id}')
async def stream(request: Request, context_id: str):
    context = CONTEXT[context_id]
    print(f"\nStarting stream for {context_id}...")

    async def event_generator():
        try:
            message_stream = await analyze_section(context)
            for chunk in message_stream:
                if chunk.type == "content_block_delta":
                    yield {"data": chunk.delta.text}
                await asyncio.sleep(0.05)
        except Exception as e:
            print(f"\nError in stream {context_id}:")
            traceback.print_exc()
            yield {"data": f"\nError: {str(e)}\n{traceback.format_exc()}"}

    return EventSourceResponse(event_generator())
