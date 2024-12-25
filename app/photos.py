import os
import asyncio
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import httpx

PHOTOS_DIR = "/var/www/photos"
def install_routes(app, templates):
    @app.get("/next_photo", response_class=HTMLResponse)
    async def next_photo(request: Request):
        files = [(f, os.path.getatime(os.path.join(PHOTOS_DIR, f))) 
                 for f in os.listdir(PHOTOS_DIR) ]
        
        if not files:
            return "No photos found"
            
        oldest_file = min(files, key=lambda x: x[1])[0]
        return RedirectResponse(url=f"/photos/{oldest_file}", status_code=307)
