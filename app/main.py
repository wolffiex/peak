from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from anthropic import Anthropic
from datetime import datetime
import httpx
import asyncio
import os
import traceback
from contextlib import asynccontextmanager
from app.prompts import get_contexts, get_standard_system_prompt

# Initialize CONTEXT from prompts module
CONTEXT = get_contexts()

# Dictionary to store custom analyzers for specific contexts
CUSTOM_ANALYZERS = {}

def register_custom_analyzer(context_name, analyzer_function):
    """Register a custom analyzer function for a specific context"""
    CUSTOM_ANALYZERS[context_name] = analyzer_function
    print(f"Registered custom analyzer for context: {context_name}")

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

# Register the traffic analyzer explicitly
CONTEXT["traffic"] = traffic.get_traffic_context()
register_custom_analyzer("traffic", traffic.analyze_traffic)
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
    from app.prompts import EVENTS_PREPROCESSING_SYSTEM
    
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
        haiku_response = await call_anthropic_api(
            model="claude-3-5-haiku-20241022",
            messages=messages,
            system=EVENTS_PREPROCESSING_SYSTEM,
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
    
    # Use standard system prompt for most contexts
    current_time_str = datetime.now().strftime('%A, %B %d at %I:%M %p Pacific')
    system_prompt = get_standard_system_prompt(current_time_str)
    
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
