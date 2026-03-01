import io
import requests
import pandas as pd
from .base import BaseScraper
from ..config import HTTP_HEADERS, REQUEST_TIMEOUT
from ..transform import transform_caiso

CAISO_QUEUE_URL = "http://www.caiso.com/PublishedDocuments/PublicQueueReport.xlsx"

# Footer rows to trim from each sheet
SHEET_CONFIG = {
    "Grid GenerationQueue": {"trim_footer": 8},
    "Completed Generation Projects": {"trim_footer": 2},
    "Withdrawn Generation Projects": {"trim_footer": 2},
}


class CAISOScraper(BaseScraper):
    iso_region = "CAISO"

    def fetch_and_transform(self) -> pd.DataFrame:
        resp = requests.get(
            CAISO_QUEUE_URL,
            headers=HTTP_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

        content = io.BytesIO(resp.content)
        sheets = {}

        for sheet_name, config in SHEET_CONFIG.items():
            content.seek(0)
            df = pd.read_excel(content, sheet_name=sheet_name, skiprows=3)
            trim = config["trim_footer"]
            if trim:
                df = df.iloc[:-trim]
            # Rename confidential column in withdrawn sheet
            if "Project Name - Confidential" in df.columns:
                df = df.rename(columns={"Project Name - Confidential": "Project Name"})
            sheets[sheet_name] = df

        return transform_caiso(sheets)
