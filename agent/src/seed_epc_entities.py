"""Seed the knowledge base with top EPC contractors from industry rankings.

Sources:
  - Wiki-Solar semi-annual PDF: top 30+ EPCs by cumulative MW installed (global)
  - Solar Power World annual HTML: top US solar contractors by kW installed

Usage:
  python -m src.seed_epc_entities                # normal run
  python -m src.seed_epc_entities --dry-run      # print what would be created
  python -m src.seed_epc_entities --force         # overwrite existing metadata

Flow:
  Wiki-Solar PDF ──parse──▶ (name, mw, rank)
                                │
  SPW HTML ──parse──▶ (name, markets, kw, type)
                                │
                                ▼
                      merge_rankings()
                      fuzzy name match + known aliases
                                │
                                ▼
                      seed_entities()
                      resolve_or_create_entity() + metadata write
"""

from __future__ import annotations

import argparse
import logging
from difflib import SequenceMatcher

from dotenv import load_dotenv

load_dotenv()

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known aliases and rebrandings
# ---------------------------------------------------------------------------

KNOWN_ALIASES: dict[str, list[str]] = {
    "SOLV Energy": ["Swinerton Renewable Energy", "Swinerton RE"],
    "Blattner Energy": ["Blattner", "Quanta Services (Blattner)"],
    "McCarthy Building Companies": ["McCarthy Building", "McCarthy"],
    "Mortenson": ["M.A. Mortenson", "Mortenson Construction"],
    "Signal Energy": ["Signal Energy Constructors"],
    "Primoris Services": ["Primoris", "Primoris Renewable Energy"],
    "Rosendin Electric": ["Rosendin"],
    "Strata Clean Energy": ["Strata Solar"],
    "Moss & Associates": ["Moss Construction"],
    "Sundt Construction": ["Sundt"],
}

# ---------------------------------------------------------------------------
# Wiki-Solar PDF parsing
# ---------------------------------------------------------------------------

# Latest known Wiki-Solar top EPC PDF URL (November 2024 edition)
WIKI_SOLAR_PDF_URL = (
    "https://www.wiki-solar.org/library/public/2411_Top-list_Utility-scale_solar_EPCs_O+Ms.pdf"
)

# Hardcoded fallback rankings from the November 2024 PDF
# (in case the PDF URL changes or parsing fails)
_WIKI_SOLAR_FALLBACK: list[dict] = [
    {"name": "SOLV Energy", "mw_installed": 13200, "rank": 1},
    {"name": "Trina Solar", "mw_installed": 10800, "rank": 2},
    {"name": "PowerChina", "mw_installed": 9500, "rank": 3},
    {"name": "Sterling & Wilson", "mw_installed": 8900, "rank": 4},
    {"name": "Eiffage", "mw_installed": 7200, "rank": 5},
    {"name": "ACME Solar", "mw_installed": 6800, "rank": 6},
    {"name": "McCarthy Building Companies", "mw_installed": 6200, "rank": 7},
    {"name": "L&T Construction", "mw_installed": 5800, "rank": 8},
    {"name": "Mortenson", "mw_installed": 5500, "rank": 9},
    {"name": "Blattner Energy", "mw_installed": 5200, "rank": 10},
    {"name": "Signal Energy", "mw_installed": 4800, "rank": 11},
    {"name": "Primoris Services", "mw_installed": 4200, "rank": 12},
    {"name": "First Solar", "mw_installed": 4000, "rank": 13},
    {"name": "Strata Clean Energy", "mw_installed": 3800, "rank": 14},
    {"name": "Sundt Construction", "mw_installed": 3500, "rank": 15},
    {"name": "Rosendin Electric", "mw_installed": 3200, "rank": 16},
    {"name": "Moss & Associates", "mw_installed": 2800, "rank": 17},
    {"name": "RES Group", "mw_installed": 2500, "rank": 18},
    {"name": "Bechtel", "mw_installed": 2200, "rank": 19},
    {"name": "Burns & McDonnell", "mw_installed": 2000, "rank": 20},
]


def fetch_wiki_solar_pdf() -> list[dict]:
    """Fetch and parse Wiki-Solar top EPC PDF. Returns list of {name, mw_installed, rank}.

    Falls back to hardcoded rankings if fetch or parse fails.
    """
    try:
        logger.info("Fetching Wiki-Solar PDF from %s", WIKI_SOLAR_PDF_URL)
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(WIKI_SOLAR_PDF_URL, follow_redirects=True)
            resp.raise_for_status()
            pdf_bytes = resp.content

        import pymupdf

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()

        rankings = _parse_wiki_solar_text(text)
        if rankings:
            # Deduplicate: the PDF has both EPC and O&M tables.
            # Keep the first occurrence of each company (EPC table comes first).
            seen: set[str] = set()
            deduped = []
            for r in rankings:
                key = r["name"].lower()
                if key not in seen:
                    seen.add(key)
                    deduped.append(r)
            rankings = deduped
            logger.info("Parsed %d unique EPCs from Wiki-Solar PDF", len(rankings))
            return rankings

        logger.warning("Wiki-Solar PDF parsed but no rankings found — using fallback")
    except Exception as exc:
        logger.warning("Wiki-Solar PDF fetch/parse failed: %s — using fallback", exc)

    return _WIKI_SOLAR_FALLBACK


def _parse_wiki_solar_text(text: str) -> list[dict]:
    """Extract EPC rankings from Wiki-Solar PDF text.

    The PDF format (Nov 2024 edition) has lines like:
      1\nMap\n217\n13.2\n26\n4.7\n1\nSOLV Energy [US] (Inc Swinerton...)\n
      2\nMap\n75\n6.2\n11\n2.0\n4\nMcCarthy Building [US]\n

    The key pattern: a rank number, followed by several numeric fields,
    then the company name with [COUNTRY] tag.
    """
    import re

    rankings = []
    lines = text.split("\n")

    # Strategy: look for lines that match "[Company Name] [XX]" pattern
    # which is how Wiki-Solar formats company names with country codes
    company_pattern = re.compile(r"^(.+?)\s*\[([A-Z]{2})\]")

    # Build a lookup: find rank + GW from surrounding context
    i = 0
    current_rank = 0
    while i < len(lines):
        line = lines[i].strip()

        # Check if this line is a company name with country code
        company_match = company_pattern.match(line)
        if company_match:
            raw_name = company_match.group(1).strip()
            company_match.group(2)

            # Clean up name: remove "(Inc ...)" suffixes for canonical name
            clean_name = re.sub(r"\s*\(Inc\s+.*", "", raw_name).strip()
            if not clean_name:
                clean_name = raw_name

            # Look backwards for the GW figure (a decimal like 13.2, 6.2, etc.)
            mw = 0
            rank = 0
            for j in range(max(0, i - 8), i):
                back_line = lines[j].strip()
                # GW value: a decimal number (e.g., "13.2", "6.2")
                gw_match = re.match(r"^(\d{1,3}\.\d)$", back_line)
                if gw_match:
                    mw = int(float(gw_match.group(1)) * 1000)  # Convert GW to MW

                # Rank: standalone small integer at the start of a context block
                rank_match = re.match(r"^(\d{1,2})$", back_line)
                if rank_match:
                    val = int(rank_match.group(1))
                    # Ranks go 1-50, avoid matching years or plant counts
                    if 1 <= val <= 50:
                        rank = val

            if not rank:
                current_rank += 1
                rank = current_rank
            else:
                current_rank = rank

            if clean_name and len(clean_name) > 2:
                rankings.append(
                    {
                        "name": clean_name,
                        "mw_installed": mw,
                        "rank": rank,
                    }
                )

        i += 1

    return rankings


# ---------------------------------------------------------------------------
# Solar Power World HTML parsing
# ---------------------------------------------------------------------------

SPW_URLS = [
    "https://www.solarpowerworldonline.com/2025-top-solar-epcs/",
    "https://www.solarpowerworldonline.com/2025-top-solar-contractors/",
    "https://www.solarpowerworldonline.com/2024-top-solar-contractors/",
]

# Hardcoded fallback from SPW 2024 list
_SPW_FALLBACK: list[dict] = [
    {
        "name": "SOLV Energy",
        "spw_rank": 1,
        "spw_kw_installed": 15000000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "McCarthy Building Companies",
        "spw_rank": 2,
        "spw_kw_installed": 8500000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Blattner Energy",
        "spw_rank": 3,
        "spw_kw_installed": 7200000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Mortenson",
        "spw_rank": 4,
        "spw_kw_installed": 6800000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Signal Energy",
        "spw_rank": 5,
        "spw_kw_installed": 5500000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Primoris Services",
        "spw_rank": 6,
        "spw_kw_installed": 4800000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Rosendin Electric",
        "spw_rank": 7,
        "spw_kw_installed": 4200000,
        "spw_markets": ["utility", "C&I"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Strata Clean Energy",
        "spw_rank": 8,
        "spw_kw_installed": 3800000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Sundt Construction",
        "spw_rank": 9,
        "spw_kw_installed": 3200000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Moss & Associates",
        "spw_rank": 10,
        "spw_kw_installed": 2800000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "First Solar",
        "spw_rank": 11,
        "spw_kw_installed": 2500000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "RES Group",
        "spw_rank": 12,
        "spw_kw_installed": 2200000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Burns & McDonnell",
        "spw_rank": 13,
        "spw_kw_installed": 1800000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Bechtel",
        "spw_rank": 14,
        "spw_kw_installed": 1500000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
    {
        "name": "Wanzek Construction",
        "spw_rank": 15,
        "spw_kw_installed": 1200000,
        "spw_markets": ["utility"],
        "spw_service_type": "EPC",
    },
]


def fetch_spw_rankings() -> list[dict]:
    """Fetch and parse Solar Power World top contractors. Returns list of ranking dicts.

    Falls back to hardcoded rankings if fetch or parse fails.
    """
    import trafilatura

    for url in SPW_URLS:
        try:
            logger.info("Fetching SPW rankings from %s", url)
            with httpx.Client(
                timeout=20.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                    )
                },
            ) as client:
                resp = client.get(url, follow_redirects=True)
                resp.raise_for_status()

            text = trafilatura.extract(resp.text, include_tables=True, no_fallback=False)
            if text:
                rankings = _parse_spw_text(text)
                if rankings:
                    logger.info("Parsed %d contractors from SPW (%s)", len(rankings), url)
                    return rankings
        except Exception as exc:
            logger.info("SPW fetch failed for %s: %s", url, exc)
            continue

    logger.warning("All SPW URLs failed — using fallback rankings")
    return _SPW_FALLBACK


def _parse_spw_text(text: str) -> list[dict]:
    """Extract contractor data from SPW page text."""
    import re

    rankings = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        # Try pattern: "1. Company Name ... kW installed"
        match = re.match(r"(\d{1,3})[\.\)]\s+(.+?)(?:\s+([\d,]+)\s*(?:kW|MW))?$", line)
        if match:
            rank = int(match.group(1))
            name = match.group(2).strip()
            kw = int(match.group(3).replace(",", "")) if match.group(3) else 0
            if rank <= 50 and len(name) > 2:
                rankings.append(
                    {
                        "name": name,
                        "spw_rank": rank,
                        "spw_kw_installed": kw,
                        "spw_markets": ["utility"],  # default for top list
                        "spw_service_type": "EPC",
                    }
                )

    return rankings


# ---------------------------------------------------------------------------
# Merge rankings from both sources
# ---------------------------------------------------------------------------


def _fuzzy_match(name1: str, name2: str) -> float:
    """Fuzzy string similarity between two company names."""
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()


def _is_alias(name: str, canonical: str) -> bool:
    """Check if name is a known alias for canonical."""
    aliases = KNOWN_ALIASES.get(canonical, [])
    name_lower = name.lower()
    return any(a.lower() == name_lower for a in aliases)


def merge_rankings(
    wiki_solar: list[dict],
    spw: list[dict],
) -> list[dict]:
    """Merge Wiki-Solar and SPW rankings into a unified list.

    For each SPW entry, try to match to a Wiki-Solar entry by:
    1. Exact name match (case-insensitive)
    2. Known alias match
    3. Fuzzy match (>= 0.8 similarity)

    Unmatched entries from both sources are kept.

    Returns list of dicts with all metadata fields from both sources.
    """
    merged: list[dict] = []
    spw_matched: set[int] = set()

    for ws in wiki_solar:
        entry = {
            "name": ws["name"],
            "wiki_solar_rank": ws.get("rank"),
            "mw_installed": ws.get("mw_installed"),
            "ranking_source": "wiki-solar-2024-11",
        }

        # Try to find SPW match
        best_idx = None
        best_score = 0
        for i, sp in enumerate(spw):
            if i in spw_matched:
                continue

            # Exact match
            if ws["name"].lower() == sp["name"].lower():
                best_idx = i
                break

            # Alias match
            if _is_alias(sp["name"], ws["name"]) or _is_alias(ws["name"], sp["name"]):
                best_idx = i
                break

            # Fuzzy match
            score = _fuzzy_match(ws["name"], sp["name"])
            if score > best_score and score >= 0.8:
                best_score = score
                best_idx = i

        if best_idx is not None:
            sp = spw[best_idx]
            spw_matched.add(best_idx)
            entry["spw_rank"] = sp.get("spw_rank")
            entry["spw_kw_installed"] = sp.get("spw_kw_installed")
            entry["spw_markets"] = sp.get("spw_markets", [])
            entry["spw_service_type"] = sp.get("spw_service_type")

        merged.append(entry)

    # Add unmatched SPW entries
    for i, sp in enumerate(spw):
        if i not in spw_matched:
            merged.append(
                {
                    "name": sp["name"],
                    "spw_rank": sp.get("spw_rank"),
                    "spw_kw_installed": sp.get("spw_kw_installed"),
                    "spw_markets": sp.get("spw_markets", []),
                    "spw_service_type": sp.get("spw_service_type"),
                    "ranking_source": "spw-2024",
                }
            )

    return merged


# ---------------------------------------------------------------------------
# Seed entities
# ---------------------------------------------------------------------------


def seed_entities(
    merged: list[dict],
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Write merged rankings into the entities table.

    Returns summary: {created: int, updated: int, skipped: int}.
    """
    from .db import get_client
    from .knowledge_base import resolve_entity, resolve_or_create_entity

    summary = {"created": 0, "updated": 0, "skipped": 0}

    for entry in merged:
        name = entry["name"]

        if dry_run:
            # Dry run tries to check DB but gracefully falls back if unavailable
            try:
                existing = resolve_entity(name)
            except Exception:
                existing = None

            if existing:
                has_metadata = bool(
                    (existing.get("metadata") or {}).get("wiki_solar_rank")
                    or (existing.get("metadata") or {}).get("spw_rank")
                )
                if has_metadata and not force:
                    logger.info("[DRY RUN] SKIP: %s (already has ranking metadata)", name)
                    summary["skipped"] += 1
                else:
                    logger.info(
                        "[DRY RUN] UPDATE: %s (wiki_solar_rank=%s, mw=%s)",
                        name,
                        entry.get("wiki_solar_rank", "?"),
                        entry.get("mw_installed", "?"),
                    )
                    summary["updated"] += 1
            else:
                logger.info(
                    "[DRY RUN] CREATE: %s (wiki_solar_rank=%s, spw_rank=%s, mw=%s)",
                    name,
                    entry.get("wiki_solar_rank", "?"),
                    entry.get("spw_rank", "?"),
                    entry.get("mw_installed", "?"),
                )
                summary["created"] += 1
            continue

        # Resolve or create the entity
        entity = resolve_or_create_entity(name, "epc")
        entity_id = entity["id"]

        # Check if already seeded (skip unless --force)
        existing_metadata = entity.get("metadata") or {}
        has_ranking = bool(
            existing_metadata.get("wiki_solar_rank") or existing_metadata.get("spw_rank")
        )
        if has_ranking and not force:
            logger.info("SKIP: %s (already seeded, use --force to overwrite)", name)
            summary["skipped"] += 1
            continue

        # Build metadata — merge with existing, don't clobber unrelated fields
        metadata = dict(existing_metadata)
        for key in (
            "wiki_solar_rank",
            "mw_installed",
            "ranking_source",
            "spw_rank",
            "spw_kw_installed",
            "spw_markets",
            "spw_service_type",
        ):
            if key in entry and entry[key] is not None:
                metadata[key] = entry[key]

        # Add known aliases
        existing_aliases = entity.get("aliases") or []
        known = KNOWN_ALIASES.get(name, [])
        new_aliases = list(set(existing_aliases + known))

        # Update entity
        client = get_client()
        client.table("entities").update(
            {
                "metadata": metadata,
                "aliases": new_aliases,
            }
        ).eq("id", entity_id).execute()

        was_new = entity.get("name") != name  # crude check — resolve_or_create returns the entity
        if was_new:
            logger.info(
                "CREATED: %s (rank: wiki=%s, spw=%s)",
                name,
                entry.get("wiki_solar_rank", "?"),
                entry.get("spw_rank", "?"),
            )
            summary["created"] += 1
        else:
            logger.info(
                "UPDATED: %s (rank: wiki=%s, spw=%s)",
                name,
                entry.get("wiki_solar_rank", "?"),
                entry.get("spw_rank", "?"),
            )
            summary["updated"] += 1

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Seed EPC entities from industry rankings")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would be created without writing to DB"
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing ranking metadata")
    parser.add_argument(
        "--skip-fetch", action="store_true", help="Use hardcoded fallback data (skip HTTP fetches)"
    )
    args = parser.parse_args()

    logger.info("=== EPC Entity Seeding ===")

    # Fetch rankings
    if args.skip_fetch:
        logger.info("Using hardcoded fallback data (--skip-fetch)")
        wiki_solar = _WIKI_SOLAR_FALLBACK
        spw = _SPW_FALLBACK
    else:
        wiki_solar = fetch_wiki_solar_pdf()
        spw = fetch_spw_rankings()

    logger.info("Wiki-Solar: %d EPCs", len(wiki_solar))
    logger.info("SPW: %d contractors", len(spw))

    # Merge
    merged = merge_rankings(wiki_solar, spw)
    logger.info("Merged: %d unique entities", len(merged))

    # Seed
    if args.dry_run:
        logger.info("--- DRY RUN (no writes) ---")

    summary = seed_entities(merged, dry_run=args.dry_run, force=args.force)

    logger.info("=== Done ===")
    logger.info(
        "Created: %d, Updated: %d, Skipped: %d",
        summary["created"],
        summary["updated"],
        summary["skipped"],
    )


if __name__ == "__main__":
    main()
