from collections import defaultdict
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import httpx

# Define traffic cameras along the route from South Lake Tahoe to SF
TRAFFIC_CAMERAS = [
    # Sierra Nevada Mountains
    {
        "name": "US-50 at Echo Summit",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy50atechosummit/hwy50atechosummit.jpg",
        "description": "Echo Summit (7,382 ft) - First major pass leaving South Lake Tahoe",
        "segment": "Sierra",
    },
    {
        "name": "US-50 at Sierra",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy50atsierraeb/hwy50atsierraeb.jpg?1743362080190",
        "description": "Sierra-at-Tahoe I-50 intersection",
        "segment": "Sierra",
    },
    {
        "name": "US-50 at Twin Bridges",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy50attwinbridges/hwy50attwinbridges.jpg",
        "description": "Twin Bridges - Mountain section near Sierra-at-Tahoe resort",
        "segment": "Sierra",
    },
    # Foothills
    {
        "name": "US-50 at Placerville",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy50atbedford/hwy50atbedford.jpg",
        "description": "Placerville - Last mountain town before reaching Sacramento Valley",
        "segment": "Foothills",
    },
    # Sacramento Valley
    {
        "name": "US-50 at Sacramento",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy50atjct51992/hwy50atjct51992.jpg",
        "description": "Sacramento - US-50 at Business 80/Capital City Freeway junction",
        "segment": "Valley",
    },
    {
        "name": "I-80 at Davis",
        "url": "https://cwwp2.dot.ca.gov/data/d3/cctv/image/hwy80atchiles/hwy80atchiles.jpg",
        "description": "Davis - I-80 at Chiles Road, west of Sacramento",
        "segment": "Valley",
    },
    # Central Valley to Bay Area
    {
        "name": "I-80 at Vacaville",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv998i80nuttreeroad/tv998i80nuttreeroad.jpg",
        "description": "Vacaville - I-80 at Nut Tree Road",
        "segment": "Central Valley",
    },
    {
        "name": "I-80 at Fairfield",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv501i80oliverroad/tv501i80oliverroad.jpg",
        "description": "Fairfield - I-80 at Oliver Road",
        "segment": "Central Valley",
    },
    # Bay Area
    {
        "name": "I-80 at Vallejo",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv962i80atjworedwoodpkwy/tv962i80atjworedwoodpkwy.jpg",
        "description": "Vallejo - I-80 at Redwood Parkway, entering the Bay Area",
        "segment": "Bay Area",
    },
    {
        "name": "I-80 at Emeryville",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv516i80westofashbyavenue/tv516i80westofashbyavenue.jpg",
        "description": "Emeryville - I-80 west of Ashby Avenue, approaching the Bay Bridge",
        "segment": "Bay Area",
    },
    {
        "name": "US 101 : After Bay Bridge",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv316i806thstreet/tv316i806thstreet.jpg?1743361635041",
        "description": "San Francisco, looking towards Bay Bridge",
        "segment": "Bay Area",
    },
    {
        "name": "US-101 : San Francisco",
        "url": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv312us101atcesarchavezbl/tv312us101atcesarchavezbl.jpg?1743361669105",
        "description": "South bound 101 at Ceasar Chavez before 280 exit",
        "segment": "Bay Area",
    },
]


def get_sections():
    sections = defaultdict(list)
    for cam in TRAFFIC_CAMERAS:
        sections[cam["segment"]].append(cam)
    return sections


async def fetch_image(url):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                return response.content
            return None
    except Exception as e:
        print(f"Error fetching image {url}: {e}")
        return None


def install_routes(app, templates):
    router = APIRouter()

    @router.get("/traffic", response_class=HTMLResponse)
    async def traffic_page(request: Request):
        sections = get_sections()
        return templates.TemplateResponse(
            "traffic.html", {"request": request, "sections": sections}
        )

    @router.get("/traffic/img")
    async def get_traffic_image(url: str):
        from fastapi.responses import Response

        try:
            if url:
                image_data = await fetch_image(url)
                if image_data:
                    return Response(content=image_data, media_type="image/jpeg")
        except Exception as e:
            print(f"Error serving traffic image: {e}")
        return Response(status_code=404)

    if app:
        app.include_router(router)
