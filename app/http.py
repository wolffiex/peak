import asyncio
import httpx
from typing import List

http_client = httpx.AsyncClient(timeout=300)  # 5 minute timeout


async def fetch(url):
    """
    Fetch data from a URL using the app's HTTP client.
    Accepts an optional custom_app parameter to support CLI usage.
    """
    print(f"Fetching {url}...")
    response = await http_client.get(url)
    text = response.text
    return text


async def fetch_all(urls: List[str]):
    return await asyncio.gather(*map(fetch, urls))
