import asyncio
import httpx
from typing import List
from bs4 import BeautifulSoup

http_client = httpx.AsyncClient(timeout=300)  # 5 minute timeout


def remove_javascript(html_content):
    """Remove JavaScript blocks from HTML content"""
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script tags
    for script in soup.find_all("script"):
        script.decompose()

    # Return the cleaned HTML
    return str(soup)


async def fetch(url):
    """
    Fetch data from a URL using the app's HTTP client.
    Accepts an optional custom_app parameter to support CLI usage.
    """
    print(f"Fetching {url}...")
    response = await http_client.get(url)
    text = response.text
    return remove_javascript(text)


async def fetch_all(urls: List[str]):
    return await asyncio.gather(*map(fetch, urls))
