import requests
import pandas as pd
from .base import BaseScraper
from ..config import HTTP_HEADERS, REQUEST_TIMEOUT
from ..transform import transform_miso

MISO_API_URL = "https://www.misoenergy.org/api/giqueue/getprojects"


class MISOScraper(BaseScraper):
    iso_region = "MISO"

    def fetch_and_transform(self) -> pd.DataFrame:
        resp = requests.get(
            MISO_API_URL,
            headers=HTTP_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return transform_miso(data)
