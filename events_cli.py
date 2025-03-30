#!/usr/bin/env python3
import asyncio
import sys
import os
import httpx
from datetime import datetime
from app.main import CONTEXT, anthropic

# Create a custom fetch function without relying on FastAPI app state
async def custom_fetch(url):
    print(f"Fetching {url}...")
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.get(url)
        print(f"Got response from {url}: {response.status_code}")
        text = response.text
        print(f"Response length: {len(text)} characters")
        return text

# Copy of preprocess_events_data from main.py but using our custom fetch
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
        # Use Claude Haiku for faster preprocessing
        haiku_response = anthropic.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=4000,
            temperature=0,
            system="""You extract and list events from provided sources without adding commentary.
            You know South Lake Tahoe geography well. South Lake Tahoe refers to the city on the California side 
            and Stateline refers to the Nevada side with casinos (Harrah's, Harvey's, Hard Rock, and Bally's).
            Meyers is just south of South Lake Tahoe.
            Heavenly Village, Lakeview Commons, MontBleu, and the Shops at Heavenly are all in South Lake Tahoe/Stateline area.
            When an event's location is listed as "Lake Tahoe" with no further specification, check the venue name to determine if it's in South Lake.""",
            messages=messages
        )
        
        # Return the extracted list of events
        return haiku_response.content[0].text
    except Exception as e:
        print(f"Error in preprocessing events: {e}")
        # Fallback to a simple message if preprocessing fails
        return "Unable to extract events due to content size limitations. Please check the original sources for complete event listings."

# Custom analyze_section function based on main.py but without FastAPI dependency
async def custom_analyze_section(context):
    print(f"Analyzing data for context...")
    
    # Fetch all sources in parallel
    results = await asyncio.gather(*[custom_fetch(source["url"]) for source in context["sources"]])
    
    # Special handling for events context - use pre-processing with a smaller model
    if context.get("name") == "events":
        print("Using special events processing pipeline...")
        
        try:
            # First, extract a raw list of events using a smaller model
            raw_events_list = await preprocess_events_data(context["sources"], results)
            print("\nRaw events list:\n" + "-"*80)
            print(raw_events_list[:1000] + "..." if len(raw_events_list) > 1000 else raw_events_list)
            print("-"*80 + "\n")
            
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
    
    message = anthropic.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        temperature=0,
        system = f"""
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
        """.strip(),
        messages=messages,
        stream=True
    )
    return message

async def generate_events_summary():
    """
    Generate the events summary using the exact same pipeline as the web app.
    This reuses the analyze_section function from main.py to ensure consistency.
    """
    print("Generating events summary...")
    
    # Get the events context
    events_context = CONTEXT["events"]
    
    # Use the custom analyze_section function
    message_stream = await custom_analyze_section(events_context)
    
    # Collect the streamed response into a complete message
    full_response = ""
    for chunk in message_stream:
        if chunk.type == "content_block_delta":
            text_chunk = chunk.delta.text
            full_response += text_chunk
            # Print the chunk to show progress
            print(text_chunk, end="", flush=True)
    
    print("\n\n" + "="*80)
    return full_response

if __name__ == "__main__":
    # Create event loop and run the main function
    summary = asyncio.run(generate_events_summary())
    
    # Optionally save to file if specified
    if len(sys.argv) > 1:
        output_file = sys.argv[1]
        with open(output_file, 'w') as f:
            f.write(summary)
        print(f"\nSummary saved to {output_file}")