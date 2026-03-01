import pandas as pd
from datetime import date


def score_lead(row: pd.Series) -> int:
    """Score a solar lead 0-100 based on basic heuristics."""
    score = 0

    # Capacity: bigger projects are higher value
    mw = row.get("mw_capacity") or 0
    if mw >= 500:
        score += 30
    elif mw >= 200:
        score += 25
    elif mw >= 100:
        score += 20
    elif mw >= 50:
        score += 15
    else:
        score += 10

    # Status: active is better
    status = str(row.get("status", "")).lower()
    if "active" in status:
        score += 25
    elif "completed" in status or "done" in status:
        score += 10
    else:
        score += 5

    # Timeline: projects expected to complete within 3 years score higher
    cod = row.get("expected_cod")
    if cod and not pd.isna(cod):
        try:
            if isinstance(cod, str):
                cod = pd.to_datetime(cod).date()
            elif isinstance(cod, pd.Timestamp):
                cod = cod.date()
            years_out = (cod - date.today()).days / 365
            if 0 < years_out <= 2:
                score += 30
            elif 2 < years_out <= 3:
                score += 20
            elif 3 < years_out <= 5:
                score += 10
        except (ValueError, TypeError):
            pass

    # Solar+Storage is higher value
    if row.get("fuel_type") == "Solar+Storage":
        score += 15
    else:
        score += 5

    return min(score, 100)


def score_projects(df: pd.DataFrame) -> pd.DataFrame:
    """Add lead_score column to DataFrame."""
    df["lead_score"] = df.apply(score_lead, axis=1)
    return df
