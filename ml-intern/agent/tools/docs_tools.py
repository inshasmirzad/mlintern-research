"""
Documentation fetch tool for exploring any documentation.
"""
import httpx
from bs4 import BeautifulSoup
from typing import Any

FETCH_DOCS_TOOL_SPEC = {
    "name": "fetch_docs",
    "description": (
        "Fetch full markdown or text content of any documentation page from a URL."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the documentation page to fetch.",
            },
        },
        "required": ["url"],
    },
}

async def fetch_docs_handler(arguments: dict[str, Any], session=None) -> tuple[str, bool]:
    """Fetch full markdown content of a documentation page."""
    url = arguments.get("url", "")
    if not url:
        return "Error: No URL provided", False

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            
        # If it's markdown, return it
        if url.endswith(".md") or "text/markdown" in resp.headers.get("Content-Type", ""):
            return f"Documentation from: {url}\n\n{resp.text}", True
            
        # Parse HTML to text
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Try to find main content areas
        main_content = soup.find("main") or soup.find("article") or soup.body
        
        if not main_content:
            return f"Documentation from: {url}\n\n{resp.text[:2000]}...", True
            
        text = main_content.get_text(separator="\n", strip=True)
        return f"Documentation from: {url}\n\n{text}", True
        
    except httpx.HTTPStatusError as e:
        return (
            f"HTTP error fetching {url}: {e.response.status_code} - {e.response.text[:200]}",
            False,
        )
    except httpx.RequestError as e:
        return f"Request error fetching {url}: {str(e)}", False
    except Exception as e:
        return f"Error fetching documentation: {str(e)}", False
