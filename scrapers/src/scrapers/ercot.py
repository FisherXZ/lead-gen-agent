import io
import requests
import pandas as pd
from .base import BaseScraper
from ..config import HTTP_HEADERS, REQUEST_TIMEOUT
from ..transform import transform_ercot

ERCOT_DOC_LIST_URL = "https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId=15933"
ERCOT_DOWNLOAD_URL = "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId={doc_id}"
HEADER_ROW = 30
DATA_START_ROW = 35


class ERCOTScraper(BaseScraper):
    iso_region = "ERCOT"

    def _get_latest_doc_id(self) -> str:
        """Find the most recent GIS Report doclookupId."""
        resp = requests.get(
            ERCOT_DOC_LIST_URL,
            headers=HTTP_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        docs = resp.json()["ListDocsByRptTypeRes"]["DocumentList"]

        # Find the most recent GIS_Report (not Co-located Battery)
        for doc in docs:
            name = doc["Document"]["FriendlyName"]
            if name.startswith("GIS_Report"):
                return doc["Document"]["DocID"]

        raise RuntimeError("No GIS Report found in ERCOT document listing")

    def fetch_and_transform(self) -> pd.DataFrame:
        doc_id = self._get_latest_doc_id()
        print(f"[ERCOT] Downloading GIS Report (DocID={doc_id})...")

        resp = requests.get(
            ERCOT_DOWNLOAD_URL.format(doc_id=doc_id),
            headers=HTTP_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

        content = io.BytesIO(resp.content)
        df = pd.read_excel(
            content,
            sheet_name="Project Details - Large Gen",
            header=None,
        )

        # Extract header from row 30 and data from row 35 onward
        header = df.iloc[HEADER_ROW].values
        data = df.iloc[DATA_START_ROW:].copy()
        data.columns = header

        # Drop rows where INR is empty (footer/junk rows)
        data = data.dropna(subset=["INR"])

        return transform_ercot(data)
