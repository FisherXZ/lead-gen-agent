import re
import requests
import pandas as pd
from .base import BaseScraper
from ..config import (
    HTTP_HEADERS,
    GEM_GEOJSON_FALLBACK_URL,
    GEM_CONFIG_URL,
    GEM_REQUEST_TIMEOUT,
)
from ..transform import transform_gem

# Statuses worth ingesting (projects where an EPC might be findable)
INGEST_STATUSES = {"construction", "pre-construction", "announced"}


def _discover_geojson_url() -> str:
    """Try to find the latest GeoJSON URL from GEM's map config."""
    try:
        resp = requests.get(
            GEM_CONFIG_URL,
            headers=HTTP_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        # Look for the CDN URL pattern in the JS config
        match = re.search(
            r'(https://publicgemdata\.nyc3\.cdn\.digitaloceanspaces\.com/solar/[^"\'\s]+\.geojson)',
            resp.text,
        )
        if match:
            return match.group(1)
    except Exception:
        pass
    return GEM_GEOJSON_FALLBACK_URL


class GEMScraper(BaseScraper):
    iso_region = "GEM"

    def fetch_and_transform(self) -> pd.DataFrame:
        url = _discover_geojson_url()
        print(f"[GEM] Downloading GeoJSON from {url}")

        resp = requests.get(
            url,
            headers=HTTP_HEADERS,
            timeout=GEM_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        print(f"[GEM] Total features in GeoJSON: {len(features)}")

        # Filter: US only, solar, statuses we care about
        us_solar = []
        for f in features:
            props = f.get("properties", {})
            country = (props.get("areas") or "").strip().rstrip(";")
            if country != "United States":
                continue
            status = (props.get("status") or "").strip().lower()
            if status not in INGEST_STATUSES:
                continue
            # Technology filter: skip CSP (concentrated solar power) — we want PV
            tech = (props.get("technology-type") or "").lower()
            if "csp" in tech:
                continue
            us_solar.append(f)

        print(f"[GEM] US solar features (construction/pre-construction/announced): {len(us_solar)}")

        # Deduplicate multi-phase projects: aggregate by pid, sum capacity,
        # keep the most advanced status
        STATUS_RANK = {"construction": 3, "pre-construction": 2, "announced": 1}
        by_pid: dict[str, dict] = {}
        for f in us_solar:
            props = f.get("properties", {})
            pid = str(props.get("pid") or props.get("id", ""))
            status = (props.get("status") or "").strip().lower()
            capacity = props.get("capacity") or 0
            try:
                capacity = float(capacity)
            except (ValueError, TypeError):
                capacity = 0

            if pid in by_pid:
                # Sum capacity
                existing = by_pid[pid]
                existing_cap = existing.get("properties", {}).get("capacity") or 0
                existing["properties"]["capacity"] = float(existing_cap) + capacity
                # Keep higher-rank status
                existing_status = (existing["properties"].get("status") or "").strip().lower()
                if STATUS_RANK.get(status, 0) > STATUS_RANK.get(existing_status, 0):
                    existing["properties"]["status"] = props.get("status")
            else:
                # Copy so we don't mutate the original
                by_pid[pid] = {
                    "properties": dict(props),
                    "geometry": f.get("geometry", {}),
                }

        deduped = list(by_pid.values())
        print(f"[GEM] After dedup (multi-phase merge): {len(deduped)}")
        return transform_gem(deduped)
