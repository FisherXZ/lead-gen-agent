import pandas as pd

# Target DB columns (excluding auto-generated ones)
DB_COLUMNS = [
    "queue_id",
    "iso_region",
    "project_name",
    "developer",
    "state",
    "county",
    "mw_capacity",
    "fuel_type",
    "queue_date",
    "expected_cod",
    "status",
    "source",
    "lead_score",
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
        rows.append({
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
        })
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

        rows.append({
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
        })
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

            all_rows.append({
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
            })
    return pd.DataFrame(all_rows)


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
