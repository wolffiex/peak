import os
import asyncio
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import httpx

def install_routes(app, templates):
    @app.get("/next_photo", response_class=HTMLResponse)
    async def next_photo(request: Request):
        photos_dir = "photos"  # adjust path as needed
        files = [(f, os.path.getmtime(os.path.join(photos_dir, f))) 
                 for f in os.listdir(photos_dir) 
                 if f.endswith(('.jpg', '.jpeg', '.png'))]
        
        if not files:
            return "No photos found"
            
        oldest_file = min(files, key=lambda x: x[1])[0]
        return RedirectResponse(url=f"/photos/{oldest_file}", status_code=307)
