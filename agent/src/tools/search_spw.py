"""Solar Power World top contractors — query seeded entity metadata.

Thin tool that queries the entities table for SPW ranking data populated
by the seed_epc_entities.py script. No external HTTP calls at runtime.

SPW rankings are US-specific and categorize companies as EPC, developer,
or installer — useful for confirming a company's role.
"""

from __future__ import annotations

DEFINITION = {
    "name": "search_spw",
    "description": (
        "Check if an EPC contractor appears in Solar Power World's annual US "
        "top solar contractors ranking. SPW categorizes companies as EPC, developer, "
        "or installer and tracks kW installed. Use this to verify: (1) Is this "
        "company actually an EPC or are they a developer/installer? (2) What scale "
        "do they operate at? Returns rank, kW installed, markets (utility/C&I/resi), "
        "and primary service type. If not found, the company may still be legitimate."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "epc_name": {
                "type": "string",
                "description": (
                    "Company name to look up (e.g., 'SOLV Energy', 'McCarthy', 'Blattner')."
                ),
            },
        },
        "required": ["epc_name"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Look up company in seeded SPW rankings from entities table."""
    epc_name = tool_input.get("epc_name", "").strip()
    if not epc_name:
        return {"error": "Empty company name."}

    from ..knowledge_base import resolve_entity

    entity = resolve_entity(epc_name)
    if not entity:
        return {
            "found": False,
            "note": f"'{epc_name}' not found in entity database.",
        }

    metadata = entity.get("metadata") or {}
    spw_rank = metadata.get("spw_rank")
    spw_kw_installed = metadata.get("spw_kw_installed")
    spw_markets = metadata.get("spw_markets")
    spw_service_type = metadata.get("spw_service_type")

    if spw_rank is not None:
        return {
            "found": True,
            "epc_name": entity["name"],
            "spw_rank": spw_rank,
            "spw_kw_installed": spw_kw_installed,
            "spw_markets": spw_markets,
            "spw_service_type": spw_service_type,
            "entity_type": entity.get("entity_type", []),
            "aliases": entity.get("aliases", []),
            "source_type": "spw_ranking",
        }

    return {
        "found": True,
        "ranked": False,
        "epc_name": entity["name"],
        "entity_type": entity.get("entity_type", []),
        "note": f"'{entity['name']}' is in our knowledge base but not in SPW rankings.",
    }
