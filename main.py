from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
import asyncio

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get('/stream')
async def stream(request: Request):
    async def event_generator():
        message = "Hello from the server! This message is being streamed one character at a time..."
        for char in message:
            yield {
                "data": char
            }
            await asyncio.sleep(0.1)  # Add delay between characters
    
    return EventSourceResponse(event_generator())