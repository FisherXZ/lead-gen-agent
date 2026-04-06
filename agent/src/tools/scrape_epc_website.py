"""Scrape an EPC company's team or about page to discover named personnel."""

from __future__ import annotations

from pydantic import BaseModel, Field

from . import fetch_page


class Input(BaseModel):
    url: str = Field(
        ..., min_length=1, description="URL of EPC team/about/project page to scrape for contacts"
    )


DEFINITION = {
    "name": "scrape_epc_website",
    "description": (
        "Fetch an EPC company's team, about, or project page to find named personnel. "
        "Use this to discover contacts from the EPC's own website. The page content "
        "will contain names, titles, and roles that you should extract."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL of EPC team/about/project page to scrape for contacts",
            },
        },
        "required": ["url"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Fetch an EPC website page and return page content for contact extraction."""
    url = tool_input.get("url", "")

    result = await fetch_page.execute({"url": url})

    if "error" in result:
        return {
            "status": "error",
            "error": result["error"],
            "error_category": "fetch_error",
        }

    return {
        "status": "success",
        "data": {
            "url": result.get("url", url),
            "content": result.get("text", ""),
            "title": result.get("title", ""),
        },
        "source": "epc_website",
    }
