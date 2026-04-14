import re

import pandas as pd

# Utility allow-list — matches triage module's list
_UTILITY_NAMES = {
    "SCE", "SOUTHERN CALIFORNIA EDISON",
    "PGAE", "PG&E", "PACIFIC GAS & ELECTRIC", "PACIFIC GAS AND ELECTRIC",
    "SDGE", "SAN DIEGO GAS & ELECTRIC",
    "DCRT",
    "ENTERGY ARKANSAS", "ENTERGY LOUISIANA", "ENTERGY MISSISSIPPI",
    "ENTERGY TEXAS", "ENTERGY NEW ORLEANS",
    "AMEREN ILLINOIS", "AMEREN MISSOURI",
    "AMEREN TRANSMISSION COMPANY OF ILLINOIS",
    "AEP", "AMERICAN ELECTRIC POWER", "AEP INDIANA MICHIGAN", "I&M",
    "JCPL", "JERSEY CENTRAL POWER & LIGHT",
    "HOOSIER ENERGY",
    "CENTERPOINT ENERGY INDIANA SOUTH",
    "SOUTHERN COMPANY", "ALABAMA POWER", "GEORGIA POWER", "MISSISSIPPI POWER",
    "DOMINION", "DOMINION ENERGY",
    "APS", "ARIZONA PUBLIC SERVICE",
}

# POI regex patterns — matches triage module's patterns
_POI_PATTERNS = [
    re.compile(r"^[\w\s\./&-]+ ?- ?[\w\s\./&-]+ ?\d+(\.\d+)? ?kV$", re.IGNORECASE),
    re.compile(r"^\d+[A-Z]+ ?- ?\d+[A-Z]+ ?\d+(\.\d+)? ?kV$", re.IGNORECASE),
    re.compile(r"\d+(\.\d+)? ?kV (Switching Station|Substation|SS)$", re.IGNORECASE),
    re.compile(r"^Taping .+ to .+ \d+kV", re.IGNORECASE),
    re.compile(r"^[\w\s]+ - [\w\s]+ \d+/\d+ SS \d+(\.\d+)? ?kV$", re.IGNORECASE),
]


def _classify_name(name: str | None) -> str:
    """Classify project name as 'poi' or 'marketing'."""
    if not name:
        return "marketing"
    return "poi" if any(p.search(name) for p in _POI_PATTERNS) else "marketing"


def _detect_utility(developer: str | None) -> str | None:
    """Return the developer string if it's a known utility, else None."""
    if not developer:
        return None
    normalized = developer.strip().upper()
    return developer if normalized in _UTILITY_NAMES else None


# Target DB columns (excluding auto-generated ones)
DB_COLUMNS = [
    "queue_id",
    "iso_region",
    "project_name",
    "developer",
    "state",
    "county",
    "latitude",
    "longitude",
    "mw_capacity",
    "fuel_type",
    "queue_date",
    "expected_cod",
    "status",
    "source",
    "lead_score",
    "construction_status",
    "geocode_source",
    "interconnecting_utility",
    "name_type",
    "raw_data",
]


def safe_date(val) -> str | None:
    """Convert a value to ISO date string or None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        ts = pd.to_datetime(val)
        if pd.isna(ts):
            return None
        return ts.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def transform_miso(raw: list[dict]) -> pd.DataFrame:
    """Transform raw MISO API records to DB schema."""
    rows = []
    for r in raw:
        row = {
            "queue_id": r.get("projectNumber", ""),
            "iso_region": "MISO",
            "project_name": r.get("poiName") or None,
            "developer": r.get("transmissionOwner") or None,
            "state": r.get("state") or None,
            "county": r.get("county") or None,
            "mw_capacity": r.get("summerNetMW") or 0,
            "fuel_type": r.get("fuelType", ""),
            "facility_type": r.get("facilityType", ""),
            "generation_type": "",
            "queue_date": safe_date(r.get("queueDate")),
            "expected_cod": safe_date(r.get("inService")),
            "status": r.get("applicationStatus") or None,
            "source": "iso_queue",
            "raw_data": r,
        }
        row["name_type"] = _classify_name(row.get("project_name"))
        rows.append(row)
    return pd.DataFrame(rows)


ERCOT_FUEL_MAP = {
    "SOL": "Solar",
    "WIN": "Wind",
    "GAS": "Gas",
    "MWH": "Battery Storage",
    "OIL": "Oil",
    "WAT": "Hydro",
    "HYD": "Hydrogen",
    "OTH": "Other",
}

ERCOT_TECH_MAP = {
    "PV": "Photovoltaic",
    "BA": "Battery Energy Storage",
    "WT": "Wind Turbine",
    "CC": "Combined-Cycle",
    "GT": "Gas Turbine",
    "ST": "Steam Turbine",
    "IC": "Internal Combustion",
    "OT": "Other",
}


def transform_ercot(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Transform raw ERCOT GIS Report DataFrame to DB schema."""
    rows = []
    for _, r in df_raw.iterrows():
        fuel_code = str(r.get("Fuel", "")).strip()
        tech_code = str(r.get("Technology", "")).strip()
        # Determine status: if IA Signed has a date, it's Completed
        ia_signed = r.get("IA Signed")
        if pd.notna(ia_signed) and str(ia_signed).strip():
            status = "Completed"
        else:
            status = "Active"

        raw = {k: (str(v) if pd.notna(v) else None) for k, v in r.items() if k is not None and str(k) != "nan"}

        row = {
            "queue_id": str(r.get("INR", "")).strip(),
            "iso_region": "ERCOT",
            "project_name": str(r.get("Project Name", "")).strip() or None,
            "developer": str(r.get("Interconnecting Entity", "")).strip() or None,
            "state": "TX",
            "county": str(r.get("County", "")).strip() or None,
            "mw_capacity": float(r.get("Capacity (MW)", 0) or 0),
            "fuel_type": ERCOT_FUEL_MAP.get(fuel_code, fuel_code),
            "facility_type": ERCOT_TECH_MAP.get(tech_code, tech_code),
            "generation_type": "",
            "queue_date": safe_date(r.get("Screening Study Started")),
            "expected_cod": safe_date(r.get("Projected COD")),
            "status": status,
            "source": "iso_queue",
            "raw_data": raw,
        }
        row["name_type"] = _classify_name(row.get("project_name"))
        rows.append(row)
    return pd.DataFrame(rows)


def transform_caiso(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Transform raw CAISO Excel sheets to DB schema."""
    all_rows = []

    for sheet_name, df_raw in sheets.items():
        # Determine status from sheet name
        if "Withdrawn" in sheet_name:
            sheet_status = "Withdrawn"
        elif "Completed" in sheet_name:
            sheet_status = "Completed"
        else:
            sheet_status = "Active"

        for _, r in df_raw.iterrows():
            # Build generation_type from Type-1/2/3
            types = []
            for col in ["Type-1", "Type-2", "Type-3"]:
                val = r.get(col)
                if pd.notna(val) and str(val).strip():
                    types.append(str(val).strip())
            generation_type = " + ".join(types)

            # Get project name (different column name in Withdrawn sheet)
            project_name = r.get("Project Name") or r.get("Project Name - Confidential")

            raw = {k: (str(v) if pd.notna(v) else None) for k, v in r.items() if str(k) != "nan"}

            row = {
                "queue_id": str(r.get("Queue Position", "")).strip(),
                "iso_region": "CAISO",
                "project_name": str(project_name).strip() if pd.notna(project_name) else None,
                "developer": str(r.get("Utility", "")).strip() if pd.notna(r.get("Utility")) else None,
                "state": str(r.get("State", "")).strip() if pd.notna(r.get("State")) else None,
                "county": str(r.get("County", "")).strip() if pd.notna(r.get("County")) else None,
                "mw_capacity": float(r.get("Net MWs to Grid", 0) or 0),
                "fuel_type": generation_type,
                "facility_type": "",
                "generation_type": generation_type,
                "queue_date": safe_date(r.get("Queue Date")),
                "expected_cod": safe_date(r.get("Current\nOn-line Date", r.get("Proposed\nOn-line Date\n(as filed with IR)"))),
                "status": str(r.get("Application Status", sheet_status)).strip() if pd.notna(r.get("Application Status")) else sheet_status,
                "source": "iso_queue",
                "raw_data": raw,
            }
            # Detect utility-as-developer
            utility = _detect_utility(row.get("developer"))
            if utility:
                row["interconnecting_utility"] = utility
                row["developer"] = None
            # Classify project name
            row["name_type"] = _classify_name(row.get("project_name"))
            all_rows.append(row)
    return pd.DataFrame(all_rows)


def transform_pjm(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Transform raw PJM Excel DataFrame to DB schema."""
    rows = []
    for _, r in df_raw.iterrows():
        # mw_capacity = min(MFO, MW In Service), ignoring NaN
        mfo = r.get("MFO")
        mw_in_service = r.get("MW In Service")
        mw_vals = [v for v in [mfo, mw_in_service] if pd.notna(v) and v]
        if mw_vals:
            try:
                mw_capacity = float(min(mw_vals))
            except (ValueError, TypeError):
                mw_capacity = 0
        else:
            mw_capacity = 0

        raw = {k: (str(v) if pd.notna(v) else None) for k, v in r.items() if k is not None and str(k) != "nan"}

        row = {
            "queue_id": str(r.get("Project ID", "")).strip(),
            "iso_region": "PJM",
            "project_name": str(r.get("Name", "")).strip() or None,
            "developer": str(r.get("Transmission Owner", "")).strip() if pd.notna(r.get("Transmission Owner")) else None,
            "state": str(r.get("State", "")).strip() if pd.notna(r.get("State")) else None,
            "county": str(r.get("County", "")).strip() if pd.notna(r.get("County")) else None,
            "mw_capacity": mw_capacity,
            "fuel_type": str(r.get("Fuel", "")).strip() if pd.notna(r.get("Fuel")) else None,
            "facility_type": "",
            "generation_type": "",
            "queue_date": safe_date(r.get("Submitted Date")),
            "expected_cod": safe_date(r.get("Projected In Service Date")),
            "status": str(r.get("Status", "")).strip() if pd.notna(r.get("Status")) else None,
            "source": "iso_queue",
            "raw_data": raw,
        }
        row["name_type"] = _classify_name(row.get("project_name"))
        rows.append(row)
    return pd.DataFrame(rows)


US_STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
    "Puerto Rico": "PR", "Guam": "GU", "American Samoa": "AS",
    "U.S. Virgin Islands": "VI", "Northern Mariana Islands": "MP",
}

GEM_STATUS_MAP = {
    "construction": "under_construction",
    "pre-construction": "pre_construction",
    "announced": "pre_construction",
    "operating": "completed",
    "shelved": "cancelled",
    "cancelled": "cancelled",
    "retired": "completed",
    "mothballed": "cancelled",
}


def transform_gem(features: list[dict]) -> pd.DataFrame:
    """Transform GEM GeoJSON features to DB schema."""
    rows = []
    for f in features:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [None, None])

        gem_status = (props.get("status") or "").strip().lower()
        capacity = props.get("capacity") or 0
        try:
            capacity = float(capacity)
        except (ValueError, TypeError):
            capacity = 0

        owner = props.get("owner") or None
        # Clean owner: strip percentage like "Acme Corp [100%]"
        if owner and "[" in owner:
            owner = owner.split("[")[0].strip()

        raw = {k: v for k, v in props.items()}
        raw["gem_coordinates"] = coords

        rows.append({
            "queue_id": str(props.get("pid") or props.get("id", "")),
            "iso_region": "GEM",
            "project_name": props.get("name") or None,
            "developer": owner,
            "state": US_STATE_ABBREV.get(props.get("subnat", ""), props.get("subnat")) or None,
            "county": None,
            "latitude": coords[1] if len(coords) >= 2 and coords[1] else None,
            "longitude": coords[0] if len(coords) >= 2 and coords[0] else None,
            "mw_capacity": capacity,
            "fuel_type": props.get("technology-type") or "Solar",
            "facility_type": "Solar",
            "generation_type": "",
            "queue_date": None,
            "expected_cod": safe_date(props.get("start-year")),
            "status": gem_status.title(),
            "source": "gem_tracker",
            "construction_status": GEM_STATUS_MAP.get(gem_status, "unknown"),
            "geocode_source": "gem_native",
            "raw_data": raw,
        })
    return pd.DataFrame(rows)


def finalize(df: pd.DataFrame) -> list[dict]:
    """Convert filtered/scored DataFrame to list of dicts for Supabase upsert."""
    records = []
    for _, row in df.iterrows():
        record = {}
        for col in DB_COLUMNS:
            val = row.get(col)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                record[col] = None
            else:
                record[col] = val
        # Ensure raw_data is serializable
        if record["raw_data"] is not None:
            record["raw_data"] = dict(record["raw_data"])
        records.append(record)
    return records
