import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

MIN_MW_CAPACITY = 20
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (lead-gen-agent)"}
REQUEST_TIMEOUT = 120
