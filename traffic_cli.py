#!/usr/bin/env python3
import asyncio
import sys
import os
from app.traffic import analyze_traffic

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
    try:
        # Run our generator function
        summary = await generate_traffic_summary()
        
        # Optionally save to file if specified
        if len(sys.argv) > 1:
            output_file = sys.argv[1]
            with open(output_file, 'w') as f:
                f.write(summary)
            print(f"\nSummary saved to {output_file}")
        
        return summary
    except Exception as e:
        print(f"Error in traffic analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        
if __name__ == "__main__":
    # Create event loop and run the main function
    asyncio.run(main())