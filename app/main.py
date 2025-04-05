from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from datetime import datetime
import asyncio
import traceback
from app import ha
from app import weather
from app import traffic

# Create a FastAPI app and set up routes
BASE_PATH = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))
app = FastAPI()
app.mount("/dist", StaticFiles(directory="dist"), name="dist")

ha.install_routes(app, templates)
weather.install_routes(app, templates)
traffic.install_routes(app, templates)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


# @app.get("/kirkwood", response_class=HTMLResponse)
# async def kirkwood(request: Request):
#     return templates.TemplateResponse(
#         "kirkwood.html", {"request": request, "contexts_data": get_contexts()}
#     )
