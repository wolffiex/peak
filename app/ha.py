import os
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

HA_HOST = os.environ["HA_HOST"]
HA_API_URL = f"http://{HA_HOST}:8123/api"
HA_ACCESS_TOKEN = os.environ["HA_ACCESS_TOKEN"]
CONTROLS = {
    "tree": "switch.living_switch_2",
    "candycane": "switch.tahoe_media_extension_switch_1",
}

def install_routes(app, templates):
    @app.get("/controls", response_class=HTMLResponse)
    async def controls(request: Request):
        return templates.TemplateResponse("controls.html", {"request": request})

async def ha_info():
    headers = {
        "Authorization": f"Bearer {ha_access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        urls = [f"{HA_API_URL}/states/{switch}" for switch in CONTROLS.values()]
        responses = await asyncio.gather(
            *[client.get(url, headers=headers) for url in urls]
        )
        t_switch, h_switch, h_power = [
            response.json()["state"] for response in responses
        ]
        return {
            "tidbyt_switch": convert_switch_state(t_switch),
            "heat_switch": convert_switch_state(h_switch),
            "heat_power": h_power,
        }
