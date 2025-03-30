#!/usr/bin/env python3
import asyncio
import sys
import os
import httpx
from fastapi import FastAPI
from app.main import CONTEXT, analyze_section

# Create a mock FastAPI app with http_client for CLI use
mock_app = FastAPI()
mock_app.state = type('obj', (object,), {
    'http_client': httpx.AsyncClient(timeout=300)
})

async def generate_events_summary():
    """
    Generate the events summary by calling the same analyze_section function
    that the web app uses, avoiding code duplication.
    """
    print("Generating events summary...")
    
    # Get the events context
    events_context = CONTEXT["events"]
    
    # Use the same analyze_section function as the web app, passing our mock app
    message_stream = await analyze_section(events_context, mock_app)
    
    # Collect the streamed response into a complete message
    full_response = ""
    print("\nEvents Summary:\n" + "-"*80)
    for chunk in message_stream:
        if chunk.type == "content_block_delta":
            text_chunk = chunk.delta.text
            full_response += text_chunk
            # Print the chunk to show progress
            print(text_chunk, end="", flush=True)
    
    print("\n" + "="*80)
    return full_response

async def main():
    try:
        # Run our generator function
        summary = await generate_events_summary()
        
        # Optionally save to file if specified
        if len(sys.argv) > 1:
            output_file = sys.argv[1]
            with open(output_file, 'w') as f:
                f.write(summary)
            print(f"\nSummary saved to {output_file}")
        
        return summary
    finally:
        # Clean up HTTP client
        await mock_app.state.http_client.aclose()
        
if __name__ == "__main__":
    # Create event loop and run the main function
    asyncio.run(main())