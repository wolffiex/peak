from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from anthropic import Anthropic
import httpx
import asyncio
import os
import traceback

CONTEXT = {
    "weather": ("https://forecast.weather.gov/MapClick.php?lat=38.7369&lon=-120.2385&unit=0&lg=english&FcstType=dwml",
        "Give a casual, conversational description of the weather ahead. " +
        "Start with today and tomorrow, then mention anything notable later in the week. " +
        "Keep it natural and get excited about snow."),
    "roads": ("https://roads.dot.ca.gov/roadscell.php?roadnumber=89",
              "Summarize the conditions on State Route 89 in the Sierra Nevada. "+
              "If they are clear, say something enthusiastic about the conditions."),
    "events": ("https://visitlaketahoe.com/events/?event-duration=next-7-days&page-num=1&event-category=167+160+168",
               "Make a list of the top upcoming events in the next week. "+
               "Follow the list with an enthusiastic pick for one of the events."),
    "backcountry": ("https://www.sierraavalanchecenter.org/forecasts#/all",
                "Give a quick, casual update on backcountry conditions - like you're telling a friend what to expect today."),
    "kirkwood": ("https://www.kirkwood.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx",
        "Give an informal update on what's running and what terrain is open, like telling a friend what to expect. " +
        "Keep it natural but skip any greetings or follow-up offers."),
}

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/build", StaticFiles(directory="build"), name="build")
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

async def analyze_section(data: str, prompt: str):
    print(f"Analyzing data of length {len(data)} with prompt: {prompt[:100]}...")
    message = anthropic.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        temperature=0,
        system = """
You are an expert local providing clear, practical information about current conditions in the mountains.
Present information in a natural, conversational way that helps people plan their day. Focus on what's relevant and actionable.
Avoid technical jargon unless it's essential for safety or clarity.
Never start responses with greetings like "Hey there", "Hi", or "Here's" - jump straight into the information.
Don't end responses with a follow-up.
        """.strip(),
        messages=[{
            "role": "user",
            "content": f"{prompt}\n\n<html>{data}</html>"
        }],
        stream=True
    )
    return message

@app.get('/stream/{context_id}')
async def stream(request: Request, context_id: str):
    context = CONTEXT[context_id]

    url, prompt = context
    print(f"\nStarting stream for {context_id}...")

    async def event_generator():
        try:
            data = await fetch(url)
            message_stream = await analyze_section(data, prompt)
            for chunk in message_stream:
                if chunk.type == "content_block_delta":
                    yield {"data": chunk.delta.text}
                await asyncio.sleep(0.05)
        except Exception as e:
            print(f"\nError in stream {context_id}:")
            traceback.print_exc()
            yield {"data": f"\nError: {str(e)}\n{traceback.format_exc()}"}

    return EventSourceResponse(event_generator())
