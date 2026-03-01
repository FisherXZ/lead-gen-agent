from datetime import datetime, timezone
from supabase import create_client, Client
from .config import SUPABASE_URL, SUPABASE_SERVICE_KEY


def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def upsert_projects(client: Client, records: list[dict]) -> int:
    """Upsert projects into Supabase. Returns count of upserted rows."""
    if not records:
        return 0
    # Supabase upsert with conflict on unique_iso_queue
    result = client.table("projects").upsert(
        records,
        on_conflict="iso_region,queue_id",
    ).execute()
    return len(result.data)


def log_scrape_start(client: Client, iso_region: str) -> str:
    """Log the start of a scrape run. Returns the run ID."""
    result = client.table("scrape_runs").insert({
        "iso_region": iso_region,
        "status": "running",
    }).execute()
    return result.data[0]["id"]


def log_scrape_end(
    client: Client,
    run_id: str,
    status: str,
    projects_found: int = 0,
    projects_upserted: int = 0,
    error_message: str | None = None,
):
    """Log the completion of a scrape run."""
    client.table("scrape_runs").update({
        "status": status,
        "projects_found": projects_found,
        "projects_upserted": projects_upserted,
        "error_message": error_message,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", run_id).execute()
