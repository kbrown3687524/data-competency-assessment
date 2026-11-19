"""Central configuration for the C3 'No Power' pipeline.

Everything a maintainer is likely to need to change (endpoint, filter, file
locations, retry behaviour) lives here, so the other modules contain only logic.
"""

from pathlib import Path

# --- API ----------------------------------------------------------------------
# ArcGIS Hub item 90711027d33940b5a06e96ad8a8f7ede ("Service Requests 2023 until
# 06 October 2026 (Deprecated)") is backed by this hosted feature service. The
# service name still says "20_May_2026": the item was renamed on the portal but
# the underlying service was not. See README.md, "How the endpoint was found".
FEATURE_SERVICE_URL = (
    "https://services6.arcgis.com/nyYfO9SxHU2ChQd9/arcgis/rest/services/"
    "Service_Requests_2023_until_20_May_2026/FeatureServer"
)
LAYER_ID = 0  # The service exposes a single non-spatial table with id 0.
LAYER_URL = f"{FEATURE_SERVICE_URL}/{LAYER_ID}"
QUERY_URL = f"{LAYER_URL}/query"

COMPLAINT_TYPE = "No Power"
# Server-side filter: a SQL-92 WHERE clause evaluated by ArcGIS.
WHERE_CLAUSE = f"C3_Complaint_Type = '{COMPLAINT_TYPE}'"

OBJECT_ID_FIELD = "ObjectId"
SUBURB_FIELD = "Suburb"

# --- HTTP behaviour ----------------------------------------------------------
REQUEST_TIMEOUT_SECONDS = (10, 120)  # (connect, read)
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2  # Waits 2, 4, 8, 16 seconds between the 5 attempts.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# --- Files -------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output"
LOG_DIR = PROJECT_ROOT / "logs"

RAW_RECORDS_FILE = RAW_DIR / "no_power_service_requests.jsonl"
RAW_METADATA_FILE = RAW_DIR / "no_power_extract_metadata.json"
SCHEMA_FILE = OUTPUT_DIR / "schema.json"
SUBURB_COUNTS_FILE = OUTPUT_DIR / "no_power_by_suburb.csv"
SUBURB_CLEANING_FILE = OUTPUT_DIR / "suburb_cleaning_map.csv"
VALIDATION_FILE = OUTPUT_DIR / "validation_report.json"

# Label for records with no usable suburb, so they stay in the counts.
UNKNOWN_SUBURB = "UNKNOWN"
