import pandas as pd
from .config import MIN_MW_CAPACITY

SOLAR_KEYWORDS = ["solar", "photovoltaic"]


def is_solar(row: pd.Series) -> bool:
    """Check if a project is solar or solar+storage."""
    text = " ".join(
        str(row.get(col, "")).lower()
        for col in ["fuel_type", "facility_type", "generation_type", "project_name"]
        if row.get(col)
    )
    return any(kw in text for kw in SOLAR_KEYWORDS)


def classify_fuel_type(row: pd.Series) -> str:
    """Classify as Solar or Solar+Storage."""
    text = " ".join(
        str(row.get(col, "")).lower()
        for col in ["fuel_type", "facility_type", "generation_type", "project_name"]
        if row.get(col)
    )
    if "battery" in text or "storage" in text:
        return "Solar+Storage"
    return "Solar"


def filter_solar_projects(df: pd.DataFrame, mw_col: str = "mw_capacity") -> pd.DataFrame:
    """Filter to solar projects >= MIN_MW_CAPACITY."""
    mask = df.apply(is_solar, axis=1)
    df = df[mask].copy()
    df = df[df[mw_col] >= MIN_MW_CAPACITY]
    df["fuel_type"] = df.apply(classify_fuel_type, axis=1)
    return df.reset_index(drop=True)
