import os
import asyncio
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import httpx

HA_HOST = os.environ["HA_HOST"]
HA_API_URL = f"http://{HA_HOST}:8123/api"
HA_ACCESS_TOKEN = os.environ["HA_ACCESS_TOKEN"]
CONTROLS = {
    "Tree lights": "switch.living_switch_2",
    "Candy cane lights": "switch.tahoe_media_extension_switch_1",
}

def install_routes(app, templates):
    @app.get("/controls", response_class=HTMLResponse)
    async def controls(request: Request):
        controls = await ha_info()
        return templates.TemplateResponse("controls.html", {
            "request": request,
            "controls": controls
        })

async def ha_info():
    headers = {
        "Authorization": f"Bearer {HA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    control_list = [
        {"name": name, "entity_id": entity_id}
        for name, entity_id in CONTROLS.items()
    ]

    try:
        async with httpx.AsyncClient() as client:
            responses = await asyncio.gather(*[
                client.get(f"{HA_API_URL}/states/{control['entity_id']}", headers=headers)
                for control in control_list
            ])
            
            for control, response in zip(control_list, responses):
                if response.status_code == 200:
                    state = response.json()
                    control["state"] = state["state"]
                else:
                    control["state"] = "error"
            
            return control_list
    except Exception as e:
        print(f"Error in ha_info: {str(e)}")
        return [{"name": name, "entity_id": id, "state": "error"}
                for name, id in CONTROLS.items()]
