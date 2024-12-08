from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from anthropic import Anthropic
import asyncio
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")
anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get('/stream')
async def stream(request: Request):
    async def event_generator():
        message = anthropic.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1024,
            temperature=0,
            system="You are a helpful AI assistant. Keep your responses concise.",
            messages=[{
                "role": "user",
                "content": "Tell me an interesting fact about space exploration."
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