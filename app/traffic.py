from fastapi import APIRouter
import httpx
import asyncio
import sys
from datetime import datetime
import pytz
from anthropic import Anthropic
import os
import base64
from bs4 import BeautifulSoup
import re
from io import BytesIO
from app.prompts import get_traffic_system_prompt, TRAFFIC_CAMERA_PROMPT

# Define traffic cameras along the route from South Lake Tahoe to SF
TRAFFIC_CAMERAS = [
    # Sierra Nevada Mountains
    {
        "name": "US-50 at Echo Summit",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy50atechosummit/hwy50atechosummit.jpg",
        "description": "Echo Summit (7,382 ft) - First major pass leaving South Lake Tahoe",
        "segment": "Sierra"
    },
    {
        "name": "US-50 at Twin Bridges",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy50attwinbridges/hwy50attwinbridges.jpg",
        "description": "Twin Bridges - Mountain section near Sierra-at-Tahoe resort",
        "segment": "Sierra"
    },
    
    # Foothills
    {
        "name": "US-50 at Placerville",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy50atbedford/hwy50atbedford.jpg",
        "description": "Placerville - Last mountain town before reaching Sacramento Valley",
        "segment": "Foothills"
    },
    
    # Sacramento Valley
    {
        "name": "US-50 at Sacramento",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy50atjct51992/hwy50atjct51992.jpg",
        "description": "Sacramento - US-50 at Business 80/Capital City Freeway junction",
        "segment": "Valley"
    },
    {
        "name": "I-80 at Davis",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy80atchiles/hwy80atchiles.jpg",
        "description": "Davis - I-80 at Chiles Road, west of Sacramento",
        "segment": "Valley"
    },
    
    # Central Valley to Bay Area
    {
        "name": "I-80 at Vacaville",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv998i80nuttreeroad/tv998i80nuttreeroad.jpg",
        "description": "Vacaville - I-80 at Nut Tree Road",
        "segment": "Central Valley"
    },
    {
        "name": "I-80 at Fairfield",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv501i80oliverroad/tv501i80oliverroad.jpg",
        "description": "Fairfield - I-80 at Oliver Road",
        "segment": "Central Valley"
    },
    
    # Bay Area
    {
        "name": "I-80 at Vallejo",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv962i80atjworedwoodpkwy/tv962i80atjworedwoodpkwy.jpg",
        "description": "Vallejo - I-80 at Redwood Parkway, entering the Bay Area",
        "segment": "Bay Area"
    },
    {
        "name": "I-80 at Emeryville",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv516i80westofashbyavenue/tv516i80westofashbyavenue.jpg",
        "description": "Emeryville - I-80 west of Ashby Avenue, approaching the Bay Bridge",
        "segment": "Bay Area"
    },
    {
        "name": "San Francisco (Ocean Beach)",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv211us101greatgwyoceanbeach/tv211us101greatgwyoceanbeach.jpg",
        "description": "Final destination - Ocean Beach in San Francisco's Outer Sunset district",
        "segment": "Bay Area"
    }
]

# Group cameras by segment for organization
SIERRA_CAMERAS = [cam for cam in TRAFFIC_CAMERAS if cam["segment"] == "Sierra"]
FOOTHILLS_CAMERAS = [cam for cam in TRAFFIC_CAMERAS if cam["segment"] == "Foothills"]
VALLEY_CAMERAS = [cam for cam in TRAFFIC_CAMERAS if cam["segment"] == "Valley"]
CENTRAL_VALLEY_CAMERAS = [cam for cam in TRAFFIC_CAMERAS if cam["segment"] == "Central Valley"]
BAY_AREA_CAMERAS = [cam for cam in TRAFFIC_CAMERAS if cam["segment"] == "Bay Area"]

# Combined segments for analysis
MOUNTAIN_CAMERAS = SIERRA_CAMERAS + FOOTHILLS_CAMERAS
VALLEY_CAMERAS = VALLEY_CAMERAS + CENTRAL_VALLEY_CAMERAS + BAY_AREA_CAMERAS

router = APIRouter()
anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

async def extract_camera_image(http_client, camera):
    """
    Fetch the camera image directly from the provided URL
    """
    try:
        # Use Pacific time for timestamps
        pacific_tz = pytz.timezone('America/Los_Angeles')
        current_time = datetime.now(pacific_tz)
        timestamp = current_time.strftime("%I:%M %p")
        print(f"Fetching camera image: {camera['name']} at {timestamp}")
        
        # Add a cache-busting query parameter to avoid caching
        cache_buster = int(current_time.timestamp() * 1000)
        image_url = f"{camera['url']}?{cache_buster}"
        
        # Directly fetch the image
        response = await http_client.get(image_url)
        
        if response.status_code == 200:
            # Convert to base64 for embedding
            image_bytes = response.content
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            print(f"Successfully fetched image for {camera['name']} ({len(image_bytes)} bytes)")
            return {
                "camera": camera,
                "image": base64_image,
                "timestamp": timestamp,
                "success": True
            }
        else:
            print(f"Failed to fetch image for {camera['name']}: HTTP {response.status_code}")
            return {
                "camera": camera,
                "image": None,
                "timestamp": timestamp,
                "success": False,
                "error": f"HTTP {response.status_code}"
            }
    except Exception as e:
        print(f"Error processing camera {camera['name']}: {str(e)}")
        return {
            "camera": camera,
            "image": None,
            "timestamp": datetime.now(pytz.timezone('America/Los_Angeles')).strftime("%I:%M %p"),
            "success": False,
            "error": str(e)
        }

async def analyze_camera_image(camera_data):
    """
    Use Claude to analyze a traffic camera image
    """
    if not camera_data["success"] or not camera_data["image"]:
        return {
            "camera": camera_data["camera"],
            "analysis": "Image not available",
            "success": False
        }
    
    try:
        # Prepare the prompt with the image
        camera_text = TRAFFIC_CAMERA_PROMPT.format(
            camera_name=camera_data['camera']['name'],
            camera_description=camera_data['camera']['description']
        )
        
        messages = [
            {
                "role": "user", 
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": camera_data["image"]
                        }
                    },
                    {
                        "type": "text",
                        "text": camera_text
                    }
                ]
            }
        ]
        
        # Use Claude to analyze the image
        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=100,
            temperature=0,
            messages=messages
        )
        
        return {
            "camera": camera_data["camera"],
            "analysis": response.content[0].text,
            "success": True
        }
    except Exception as e:
        print(f"Error analyzing image for {camera_data['camera']['name']}: {str(e)}")
        return {
            "camera": camera_data["camera"],
            "analysis": f"Error analyzing image: {str(e)}",
            "success": False
        }

async def generate_traffic_summary(mountain_analyses, valley_analyses):
    """
    Generate a comprehensive summary of traffic conditions for the drive to SF
    """
    try:
        # Create a prompt with all the camera analyses by segment
        sierra_analyses = [a for a in mountain_analyses if a['camera']['segment'] == 'Sierra' and a['success']]
        foothills_analyses = [a for a in mountain_analyses if a['camera']['segment'] == 'Foothills' and a['success']]
        sacramento_analyses = [a for a in valley_analyses if a['camera']['segment'] == 'Valley' and a['success']]
        central_analyses = [a for a in valley_analyses if a['camera']['segment'] == 'Central Valley' and a['success']]
        bay_analyses = [a for a in valley_analyses if a['camera']['segment'] == 'Bay Area' and a['success']]
        
        # Format each segment's analysis text
        sierra_text = "\n".join([f"{a['camera']['name']}: {a['analysis']}" for a in sierra_analyses])
        foothills_text = "\n".join([f"{a['camera']['name']}: {a['analysis']}" for a in foothills_analyses])
        sacramento_text = "\n".join([f"{a['camera']['name']}: {a['analysis']}" for a in sacramento_analyses])
        central_text = "\n".join([f"{a['camera']['name']}: {a['analysis']}" for a in central_analyses])
        bay_text = "\n".join([f"{a['camera']['name']}: {a['analysis']}" for a in bay_analyses])
        
        messages = [
            {"role": "user", "content": f"Here are the current conditions in the Sierra Nevada mountains on US-50 from South Lake Tahoe:\n{sierra_text}"},
            {"role": "user", "content": f"Conditions in the foothills near Placerville:\n{foothills_text}"},
            {"role": "user", "content": f"Conditions in Sacramento and Davis where US-50 meets I-80:\n{sacramento_text}"},
            {"role": "user", "content": f"Conditions in the Central Valley on I-80 (Vacaville, Fairfield):\n{central_text}"},
            {"role": "user", "content": f"Conditions in the Bay Area (Vallejo, Emeryville, San Francisco):\n{bay_text}"},
            {"role": "user", "content": "Based on this information, provide a casual, conversational summary of the drive from South Lake Tahoe to Ocean Beach in San Francisco. The route goes from South Lake on US-50 to Sacramento, then switches to I-80 through Davis, Vacaville, Fairfield, Vallejo, across the Bay Bridge to SF, then to Ocean Beach in the Outer Sunset district. Mention any issues like snow, chain controls, or traffic congestion spots. Estimate total drive time based on current conditions. Keep it concise but informative, like you're texting a friend about the drive."}
        ]
        
        # Get the summary from Claude with a focused system prompt
        # Use Pacific time
        pacific_tz = pytz.timezone('America/Los_Angeles')
        current_time = datetime.now(pacific_tz)
        date_time_str = current_time.strftime('%A, %B %d at %I:%M %p Pacific')
        day_of_week = current_time.strftime('%A')
        
        # Use the system prompt from prompts module
        system_prompt = get_traffic_system_prompt(day_of_week, date_time_str)
        
        response = anthropic_client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=300,
            temperature=0,
            system=system_prompt,
            messages=messages
        )
        
        return response.content[0].text
    except Exception as e:
        print(f"Error generating traffic summary: {str(e)}")
        return f"Unable to generate traffic summary: {str(e)}"

async def analyze_traffic():
    """Custom analyzer for traffic context that processes camera images"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch images from all cameras in parallel
            print("Fetching camera images...")
            mountain_results = await asyncio.gather(*[extract_camera_image(client, camera) for camera in MOUNTAIN_CAMERAS])
            valley_results = await asyncio.gather(*[extract_camera_image(client, camera) for camera in VALLEY_CAMERAS])
            
            # Analyze each image with Claude Haiku (concurrently)
            print("Analyzing camera images...")
            mountain_analyses = await asyncio.gather(*[analyze_camera_image(result) for result in mountain_results])
            valley_analyses = await asyncio.gather(*[analyze_camera_image(result) for result in valley_results])
            
            # Combine all results
            all_analyses = mountain_analyses + valley_analyses
            
            # Generate comprehensive summary with Claude Opus
            print("Generating traffic summary...")
            summary = await generate_traffic_summary(mountain_analyses, valley_analyses)
            
            return summary
    except Exception as e:
        print(f"Error in traffic analysis pipeline: {str(e)}")
        return f"Unable to analyze traffic conditions: {str(e)}"

def get_traffic_context():
    """Return the traffic context dictionary."""
    from app.prompts import get_contexts
    return get_contexts()["traffic"]

def install_routes(app, templates):
    """Install the traffic module routes if needed."""
    # No routes needed for traffic analyzer currently
    pass