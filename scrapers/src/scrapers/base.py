from abc import ABC, abstractmethod
import pandas as pd
from ..db import get_client, upsert_projects, log_scrape_start, log_scrape_end
from ..filters import filter_solar_projects
from ..geocoder import geocode_projects
from ..scoring import score_projects
from ..transform import finalize


class BaseScraper(ABC):
    iso_region: str

    @abstractmethod
    def fetch_and_transform(self) -> pd.DataFrame:
        """Fetch raw data and return a DataFrame with standardized columns.

        Must include at minimum: queue_id, iso_region, project_name, developer,
        state, county, mw_capacity, fuel_type, queue_date, expected_cod, status,
        source, raw_data. May also include facility_type, generation_type for filtering.
        """

    def run(self) -> dict:
        """Execute the full pipeline: fetch → filter → score → upsert → log."""
        client = get_client()
        run_id = log_scrape_start(client, self.iso_region)

        try:
            print(f"[{self.iso_region}] Fetching queue data...")
            df = self.fetch_and_transform()
            print(f"[{self.iso_region}] Raw projects: {len(df)}")

            df = filter_solar_projects(df)
            print(f"[{self.iso_region}] Solar projects >= 20MW: {len(df)}")

            df = score_projects(df)
            records = finalize(df)
            records = geocode_projects(records)

            # Upsert in batches
            batch_size = 500
            total_upserted = 0
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                total_upserted += upsert_projects(client, batch)

            print(f"[{self.iso_region}] Upserted: {total_upserted}")

            log_scrape_end(
                client, run_id,
                status="success",
                projects_found=len(df),
                projects_upserted=total_upserted,
            )
            return {
                "iso_region": self.iso_region,
                "status": "success",
                "found": len(df),
                "upserted": total_upserted,
            }

        except Exception as e:
            print(f"[{self.iso_region}] ERROR: {e}")
            log_scrape_end(
                client, run_id,
                status="error",
                error_message=str(e)[:500],
            )
            return {
                "iso_region": self.iso_region,
                "status": "error",
                "error": str(e),
            }
