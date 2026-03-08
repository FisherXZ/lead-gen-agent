"""County-centroid geocoder using Census Bureau Gazetteer data.

Tier 3 of the geocoding cascade (see plans/roadmap/06-geocoding-cascade.md).
Provides every project with at least county-level coordinates from day one.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

# State name → USPS abbreviation for ISOs that report full state names
STATE_ABBREV = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}

# Gazetteer data file ships with the repo
_DATA_FILE = Path(__file__).parent.parent / "data" / "2024_Gaz_counties_national.txt"

# Module-level cache
_centroid_cache: dict[tuple[str, str], tuple[float, float]] | None = None


def _normalize_county(name: str) -> str:
    """Normalize a county name for matching.

    Census format: "Travis County" → "travis"
    ISO format:    "Travis" → "travis"
    Handles: "St." vs "Saint", "DeWitt" vs "De Witt", extra whitespace.
    """
    name = name.lower().strip()
    # Remove "county", "parish" (LA), "borough" (AK), "census area" (AK)
    for suffix in ["county", "parish", "borough", "census area", "municipality"]:
        name = re.sub(rf"\s+{suffix}\s*$", "", name)
    # Normalize "St." / "St " → "saint"
    name = re.sub(r"\bst\.?\s", "saint ", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _normalize_state(state: str) -> str:
    """Normalize state to 2-letter USPS abbreviation."""
    state = state.strip()
    if len(state) == 2:
        return state.upper()
    return STATE_ABBREV.get(state.lower(), state.upper())


def _load_centroids() -> dict[tuple[str, str], tuple[float, float]]:
    """Load Census Gazetteer into a lookup dict.

    Key: (state_abbrev, normalized_county_name)
    Value: (latitude, longitude)
    """
    global _centroid_cache
    if _centroid_cache is not None:
        return _centroid_cache

    centroids: dict[tuple[str, str], tuple[float, float]] = {}

    with open(_DATA_FILE, "r") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)  # Skip header
        for row in reader:
            if len(row) < 10:
                continue
            state_abbrev = row[0].strip()
            county_name = _normalize_county(row[3])
            lat = float(row[8].strip())
            lon = float(row[9].strip())
            centroids[(state_abbrev, county_name)] = (lat, lon)

    _centroid_cache = centroids
    return centroids


def geocode_county(state: str | None, county: str | None) -> tuple[float, float] | None:
    """Look up county centroid coordinates.

    Args:
        state: State abbreviation or full name (e.g., "TX" or "Texas")
        county: County name, with or without "County" suffix

    Returns:
        (latitude, longitude) tuple, or None if no match found.
    """
    if not state or not county:
        return None

    centroids = _load_centroids()
    state_norm = _normalize_state(state)

    # Handle multi-county values like "Kenosha County,Racine County"
    # and duplicate forms like "St. Mary,St. Mary Parish"
    candidates = [c.strip() for c in county.split(",") if c.strip()]

    for candidate in candidates:
        county_norm = _normalize_county(candidate)
        result = centroids.get((state_norm, county_norm))
        if result:
            return result

    return None


def geocode_project(project: dict) -> dict:
    """Add lat/lon/geocode_source to a project dict if coordinates are missing.

    Only sets coordinates if latitude is currently None/missing.
    Does NOT overwrite coordinates from higher-tier sources.

    Returns the same dict, mutated in place.
    """
    # Don't overwrite existing coordinates from better sources
    if project.get("latitude") is not None:
        return project

    coords = geocode_county(project.get("state"), project.get("county"))
    if coords:
        project["latitude"] = coords[0]
        project["longitude"] = coords[1]
        project["geocode_source"] = "county_centroid"

    return project


def geocode_projects(records: list[dict]) -> list[dict]:
    """Geocode a batch of project records. Mutates in place."""
    for record in records:
        geocode_project(record)
    return records
