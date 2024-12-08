from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from anthropic import Anthropic
import httpx
import asyncio
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")
anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

async def gather_context():
    async with httpx.AsyncClient() as client:
        # Fetch all data concurrently
        responses = await asyncio.gather(
            client.get(
                "https://forecast.weather.gov/MapClick.php?lat=38.7369&lon=-120.2385&unit=0&lg=english&FcstType=dwml"
            ),
            client.get(
                "https://roads.dot.ca.gov/roadscell.php?roadnumber=89"
            ),
            client.get(
                "https://visitlaketahoe.com/events/?event-duration=next-7-days&page-num=1&event-category=167+160+168"
            ),
            client.get(
                "https://www.sierraavalanchecenter.org/forecasts#/all"
            ),
            client.get(
                "https://www.kirkwood.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx"
            )
        )

        return {
            "weather": responses[0].text,
            "roads": responses[1].text,
            "events": responses[2].text,
            "avalanche": responses[3].text,
            "kirkwood": responses[4].text
        }

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

async def analyze_section(title: str, data: str):
    prompt = f"""Analyze this {title} data about the South Lake Tahoe area and provide a brief summary:

{data}

Provide a very concise summary focusing only on the most important points."""

    message = anthropic.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        temperature=0,
        system="You are a helpful AI assistant. Keep your responses concise.",
        messages=[{
            "role": "user",
            "content": prompt
        }],
        stream=True
    )
    
    return message

@app.get('/stream')
async def stream(request: Request):
    async def event_generator():
        # Gather context before making the API call
        context = await gather_context()
        
        sections = [
            ("Weather", context['weather']),
            ("Roads", context['roads']),
            ("Events", context['events']),
            ("Avalanche", context['avalanche']),
            ("Kirkwood", context['kirkwood'])
        ]

        for title, data in sections:
            yield {"data": f"\n\n## {title}\n"}
            message_stream = await analyze_section(title, data)
            for chunk in message_stream:
                if chunk.type == "content_block_delta":
                    yield {"data": chunk.delta.text}
                await asyncio.sleep(0.05)  # Small delay between chunks
    
    return EventSourceResponse(event_generator())