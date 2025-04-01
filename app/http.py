import asyncio
import httpx
from typing import List

# Set browser-like headers to avoid getting the "Loading" page
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

http_client = httpx.AsyncClient(timeout=300, headers=headers)  # 5 minute timeout


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
