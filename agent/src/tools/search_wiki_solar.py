"""Wiki-Solar EPC rankings — query seeded entity metadata.

Thin tool that queries the entities table for Wiki-Solar ranking data
populated by the seed_epc_entities.py script. No external HTTP calls
at runtime — just a DB lookup.

Use during research to verify: "Is this candidate EPC a real utility-scale
contractor? What's their global MW installed?"
"""

from __future__ import annotations

DEFINITION = {
    "name": "search_wiki_solar",
    "description": (
        "Check if an EPC contractor appears in Wiki-Solar's global utility-scale "
        "solar EPC rankings. Wiki-Solar tracks 25,000+ projects and ranks EPCs by "
        "cumulative MW installed. Use this to verify an EPC candidate's credibility: "
        "a company ranked in the top 30 with gigawatts of installed capacity is "
        "almost certainly a real utility-scale EPC. Returns rank, MW installed, and "
        "ranking year. If not found, the company may still be legitimate — Wiki-Solar "
        "only tracks the largest firms."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "epc_name": {
                "type": "string",
                "description": (
                    "EPC company name to look up (e.g., 'SOLV Energy', 'McCarthy', 'Blattner')."
                ),
            },
        },
        "required": ["epc_name"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Look up EPC in seeded Wiki-Solar rankings from entities table."""
    epc_name = tool_input.get("epc_name", "").strip()
    if not epc_name:
        return {"error": "Empty EPC name."}

    from ..knowledge_base import resolve_entity

    entity = resolve_entity(epc_name)
    if not entity:
        return {
            "found": False,
            "note": (
                f"'{epc_name}' not found in entity database. "
                "May not be seeded yet or may be under a different name."
            ),
        }

    metadata = entity.get("metadata") or {}
    wiki_solar_rank = metadata.get("wiki_solar_rank")
    mw_installed = metadata.get("mw_installed")
    ranking_source = metadata.get("ranking_source")

    if wiki_solar_rank is not None:
        return {
            "found": True,
            "epc_name": entity["name"],
            "wiki_solar_rank": wiki_solar_rank,
            "mw_installed": mw_installed,
            "ranking_source": ranking_source,
            "entity_type": entity.get("entity_type", []),
            "aliases": entity.get("aliases", []),
            "source_type": "wiki_solar_ranking",
        }

    # Entity exists but no Wiki-Solar data
    return {
        "found": True,
        "ranked": False,
        "epc_name": entity["name"],
        "entity_type": entity.get("entity_type", []),
        "note": f"'{entity['name']}' is in our knowledge base but not in Wiki-Solar rankings.",
    }
