import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

MIN_MW_CAPACITY = 20
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (lead-gen-agent)"}
REQUEST_TIMEOUT = 120

# GEM (Global Energy Monitor) Solar Power Tracker
GEM_GEOJSON_FALLBACK_URL = "https://publicgemdata.nyc3.cdn.digitaloceanspaces.com/solar/2026-02/solar_map_2026-02-05.geojson"
GEM_CONFIG_URL = "https://raw.githubusercontent.com/GlobalEnergyMonitor/maps/gitpages-production/trackers/solar/config.js"
GEM_REQUEST_TIMEOUT = 300  # Large file download
