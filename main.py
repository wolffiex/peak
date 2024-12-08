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
        # Fetch weather data
        weather_response = await client.get(
            "https://forecast.weather.gov/MapClick.php?lat=38.7369&lon=-120.2385&unit=0&lg=english&FcstType=dwml"
        )
        weather_data = weather_response.text

        # Fetch road conditions
        roads_response = await client.get(
            "https://roads.dot.ca.gov/roadscell.php?roadnumber=89"
        )
        roads_data = roads_response.text

        return {
            "weather": weather_data,
            "roads": roads_data
        }

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get('/stream')
async def stream(request: Request):
    async def event_generator():
        # Gather context before making the API call
        context = await gather_context()
        
        prompt = f"""Analyze this data about the South Lake Tahoe area and provide a brief summary:

Weather Data:
{context['weather']}

Road Conditions:
{context['roads']}

Provide a concise summary of current conditions."""

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
        
        for chunk in message:
            if chunk.type == "content_block_delta":
                yield {
                    "data": chunk.delta.text
                }
            await asyncio.sleep(0.05)  # Small delay between chunks
    
    return EventSourceResponse(event_generator())