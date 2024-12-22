from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from anthropic import Anthropic
from datetime import datetime
from app import ha
import httpx
import asyncio
import os
import traceback

CONTEXT = {
    "weather": {
        "sources": [{
            "url": "https://forecast.weather.gov/MapClick.php?lat=38.7369&lon=-120.2385&unit=0&lg=english&FcstType=dwml",
            "intro": "Here's the current weather forecast for Kirkwood:"
        }],
        "final_prompt": "Give a casual, conversational description of the weather ahead. " +
                       "Start with today and tomorrow, then mention anything notable later in the week. " +
                       "Keep it natural and get excited about snow."
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
        "sources": [{
            "url": "https://visitlaketahoe.com/events/?event-duration=next-7-days&page-num=1&event-category=167+160+168",
            "intro": "Here are the upcoming events in Lake Tahoe:"
        }],
        "final_prompt": "Make a list of the top upcoming events in the next week. " +
                       "Follow the list with an enthusiastic pick for one of the events."
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
anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
http_client = httpx.AsyncClient(timeout=300)  # 5 minute timeout

@app.on_event("startup")
async def startup_event():
    app.state.http_client = httpx.AsyncClient(timeout=300)  # 5 minute timeout

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.http_client.aclose()

async def fetch(url):
    print(f"Fetching {url}...")
    response = await app.state.http_client.get(url)
    print(f"Got response from {url}: {response.status_code}")
    text = response.text
    print(f"Response length: {len(text)} characters")
    return text

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "contexts": CONTEXT.keys()})

async def analyze_section(context):
    print(f"Analyzing data for context...")
    
    # Fetch all sources in parallel
    results = await asyncio.gather(*[fetch(source["url"]) for source in context["sources"]])
    
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
    
    message = anthropic.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        temperature=0,
        system = f"""
You are an expert local providing clear, practical information about current conditions in the mountains.
The current date and time is {datetime.now().strftime('%A, %B %d at %I:%M %p Pacific')}.
Present information in a natural, conversational way that helps people plan their day. Focus on what's relevant and actionable.
Avoid technical jargon unless it's essential for safety or clarity.
Never start responses with greetings like "Hey there", "Hi", or "Here's" - jump straight into the information.
Don't end responses with a follow-up.
        """.strip(),
        messages=messages,
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
