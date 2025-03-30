#!/usr/bin/env python3
import asyncio
import argparse
import sys
import os
import httpx
from fastapi import FastAPI
from app.main import CONTEXT, analyze_section
from app.traffic import analyze_traffic

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

async def generate_traffic_summary():
    """
    Generate a traffic summary by calling the analyzer directly.
    """
    print("Generating traffic summary...")
    
    # Use the analyzer function directly
    summary = await analyze_traffic()
    
    # Print the summary
    print("\nTraffic Summary:\n" + "-"*80)
    print(summary)
    print("-"*80)
    
    return summary

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="CLI tool for testing Peak modules")
    parser.add_argument("module", choices=["events", "traffic"], 
                      help="Module to test (events or traffic)")
    parser.add_argument("-o", "--output", help="Optional file path to save the output")
    args = parser.parse_args()
    
    try:
        # Run the appropriate generator function based on the module argument
        if args.module == "events":
            summary = await generate_events_summary()
        elif args.module == "traffic":
            summary = await generate_traffic_summary()
        
        # Optionally save to file if specified
        if args.output:
            with open(args.output, 'w') as f:
                f.write(summary)
            print(f"\nSummary saved to {args.output}")
        
        return summary
    except Exception as e:
        print(f"Error in {args.module} analysis: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up HTTP client
        await mock_app.state.http_client.aclose()
        
if __name__ == "__main__":
    # Create event loop and run the main function
    asyncio.run(main())