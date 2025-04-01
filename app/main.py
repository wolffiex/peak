from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from datetime import datetime
import asyncio
import traceback

# Create a FastAPI app and set up routes
BASE_PATH = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))
app = FastAPI()
app.mount("/dist", StaticFiles(directory="dist"), name="dist")

# Import modules after initializing CONTEXT and registration functions
# to avoid circular dependencies
from app import ha
from app import photos
from app import weather
from app import traffic

# Now install routes from each module
ha.install_routes(app, templates)
photos.install_routes(app, templates)
weather.install_routes(app, templates)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    context_names = ["controls", "weather", "traffic", "events", "backcountry"]
    return templates.TemplateResponse(
        "home.html", {"request": request, "context_names": context_names}
    )


@app.get("/kirkwood", response_class=HTMLResponse)
async def kirkwood(request: Request):
    return templates.TemplateResponse(
        "kirkwood.html", {"request": request, "contexts_data": CONTEXT}
    )


async def analyze_section(context, custom_app=None):
    print(f"Analyzing data for context: {context.get('name', 'unnamed')}")

    # Standard processing path - fetch all sources
    results = await asyncio.gather(
        *[fetch(source["url"], custom_app) for source in context["sources"]]
    )

    # Special handling for events context - use pre-processing with a smaller model
    if context.get("name") == "events":
        print("Using special events processing pipeline...")

        try:
            # First, extract a raw list of events using a smaller model
            raw_events_list = await preprocess_events_data(context["sources"], results)

            # Then pass this condensed list to the main model
            messages = [
                {
                    "role": "user",
                    "content": "Here's a processed list of upcoming events in Lake Tahoe:",
                },
                {"role": "user", "content": raw_events_list},
                {"role": "user", "content": context["final_prompt"]},
            ]
        except Exception as e:
            print(f"Error in events pipeline, falling back to standard processing: {e}")
            # If the events pipeline fails, fall back to standard processing with truncated data
            messages = []
            MAX_CHARS = 30000  # Even more conservative limit for fallback

            for source, data in zip(context["sources"], results):
                truncated_data = data[:MAX_CHARS] if len(data) > MAX_CHARS else data
                messages.extend(
                    [
                        {"role": "user", "content": source["intro"]},
                        {"role": "user", "content": truncated_data},
                    ]
                )

            messages.append(
                {
                    "role": "user",
                    "content": context["final_prompt"]
                    + " Note: Some event data may have been truncated due to size constraints.",
                }
            )
    else:
        # Standard processing for other contexts
        # Build messages list with intros and data
        messages = []
        for source, data in zip(context["sources"], results):
            messages.extend(
                [
                    {"role": "user", "content": source["intro"]},
                    {"role": "user", "content": data},
                ]
            )

        # Add the final prompt
        messages.append({"role": "user", "content": context["final_prompt"]})

    # Use standard system prompt for most contexts
    current_time_str = datetime.now().strftime("%A, %B %d at %I:%M %p Pacific")
    system_prompt = get_standard_system_prompt(current_time_str)

    message = await call_anthropic_api(
        model="claude-3-opus-20240229",
        messages=messages,
        system=system_prompt,
        max_tokens=1024,
        temperature=0,
        stream=True,
    )
    return message


@app.get("/stream/{context_id}")
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
