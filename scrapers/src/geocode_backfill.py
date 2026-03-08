"""Backfill geocoding for existing projects that have NULL coordinates.

Usage:
    python -m scrapers.src.geocode_backfill [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from .db import get_client
from .geocoder import geocode_county


def backfill(dry_run: bool = False) -> None:
    client = get_client()

    # Fetch projects with NULL latitude
    resp = (
        client.table("projects")
        .select("id, state, county, latitude, geocode_source")
        .is_("latitude", "null")
        .execute()
    )
    projects = resp.data
    print(f"Found {len(projects)} projects without coordinates")

    if not projects:
        return

    geocoded = 0
    failed = 0
    updates = []

    for p in projects:
        coords = geocode_county(p.get("state"), p.get("county"))
        if coords:
            geocoded += 1
            updates.append({
                "id": p["id"],
                "latitude": coords[0],
                "longitude": coords[1],
                "geocode_source": "county_centroid",
            })
        else:
            failed += 1
            if failed <= 10:
                print(f"  No match: state={p.get('state')!r} county={p.get('county')!r}")

    print(f"Geocoded: {geocoded}, No match: {failed}")

    if dry_run:
        print("Dry run — no database updates")
        return

    # Batch update
    batch_size = 100
    updated = 0
    for i in range(0, len(updates), batch_size):
        batch = updates[i : i + batch_size]
        for u in batch:
            pid = u.pop("id")
            client.table("projects").update(u).eq("id", pid).execute()
            updated += 1

    print(f"Updated {updated} projects in database")


def main():
    parser = argparse.ArgumentParser(description="Backfill geocoding for projects")
    parser.add_argument("--dry-run", action="store_true", help="Preview without updating DB")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
