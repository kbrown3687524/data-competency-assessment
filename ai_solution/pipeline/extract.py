"""Step 1: extract 'No Power' service requests from the ArcGIS feature service.

The filter is applied on the server (``where`` parameter), and results are paged
because the service returns at most ``maxRecordCount`` (1000) rows per request.

Paging uses *keyset pagination* on the ObjectId field (``ObjectId > last_seen``,
ordered by ObjectId) rather than ``resultOffset``. Both are supported by the
service, but offset paging gets slower the deeper it goes (about 5 s per page
near the end of this 585-page result set, because the server must skip all the
earlier rows) and can skip or repeat rows if the data shifts between requests.
Keyset paging is constant-time per page and cannot overlap.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterator

import requests

from pipeline import api, config

logger = logging.getLogger(__name__)


def fetch_layer_metadata(session: requests.Session) -> dict[str, Any]:
    """Return the layer definition (fields, types, maxRecordCount, ...)."""
    logger.info("Fetching layer metadata from %s", config.LAYER_URL)
    return api.get_json(session, config.LAYER_URL, {})


def summarise_schema(metadata: dict[str, Any]) -> dict[str, Any]:
    """Reduce the layer definition to the parts worth recording."""
    return {
        "layer_name": metadata.get("name"),
        "layer_type": metadata.get("type"),
        "geometry_type": metadata.get("geometryType"),
        "object_id_field": metadata.get("objectIdField"),
        "max_record_count": metadata.get("maxRecordCount"),
        "supports_pagination": metadata.get("advancedQueryCapabilities", {}).get(
            "supportsPagination"
        ),
        "fields": [
            {
                "name": field["name"],
                "alias": field.get("alias"),
                "type": field["type"],
                "length": field.get("length"),
                "nullable": field.get("nullable"),
            }
            for field in metadata.get("fields", [])
        ],
    }


def fetch_record_count(session: requests.Session, where: str) -> int:
    """Ask the server how many records match ``where`` (no rows transferred)."""
    payload = api.get_json(
        session, config.QUERY_URL, {"where": where, "returnCountOnly": "true"}
    )
    if "count" not in payload:
        raise api.ArcGISError(f"Count response had no 'count' key: {payload}")
    return int(payload["count"])


def iter_pages(
    session: requests.Session, where: str, page_size: int
) -> Iterator[list[dict[str, Any]]]:
    """Yield lists of record attributes, one list per page, until exhausted."""
    last_object_id = -1
    while True:
        params = {
            "where": f"({where}) AND {config.OBJECT_ID_FIELD} > {last_object_id}",
            "outFields": "*",
            "orderByFields": f"{config.OBJECT_ID_FIELD} ASC",
            "resultRecordCount": page_size,
            "returnGeometry": "false",
        }
        payload = api.get_json(session, config.QUERY_URL, params)
        if "features" not in payload:
            raise api.ArcGISError(f"Query response had no 'features' key: {payload}")

        records = [feature["attributes"] for feature in payload["features"]]
        if not records:
            return
        yield records
        last_object_id = records[-1][config.OBJECT_ID_FIELD]


def extract(session: requests.Session | None = None) -> dict[str, Any]:
    """Run the extraction and write raw records, metadata and schema to disk.

    Returns the extract metadata (also written to ``RAW_METADATA_FILE``).
    Raises ``ArcGISError`` if the number of records retrieved does not match the
    count the API reports for the same filter.
    """
    session = session or api.build_session()
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    metadata = fetch_layer_metadata(session)
    schema = summarise_schema(metadata)
    config.SCHEMA_FILE.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    logger.info("Schema (%d fields) written to %s", len(schema["fields"]), config.SCHEMA_FILE)

    page_size = int(metadata.get("maxRecordCount") or 1000)
    expected = fetch_record_count(session, config.WHERE_CLAUSE)
    logger.info("API reports %d records for filter: %s", expected, config.WHERE_CLAUSE)

    # Write to a temporary file and rename at the end, so an interrupted run
    # never leaves a truncated file that later steps would mistake for complete.
    tmp_file = config.RAW_RECORDS_FILE.with_suffix(".jsonl.tmp")
    seen_ids: set[int] = set()
    with tmp_file.open("w", encoding="utf-8") as handle:
        for page_number, records in enumerate(
            iter_pages(session, config.WHERE_CLAUSE, page_size), start=1
        ):
            for record in records:
                seen_ids.add(record[config.OBJECT_ID_FIELD])
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            if page_number % 50 == 0:
                logger.info("Page %d: %d / %d records", page_number, len(seen_ids), expected)

    retrieved = len(seen_ids)
    if retrieved != expected:
        raise api.ArcGISError(
            f"Retrieved {retrieved} unique records but the API reports {expected}. "
            f"Partial data left in {tmp_file}."
        )
    tmp_file.replace(config.RAW_RECORDS_FILE)

    extract_metadata = {
        "extracted_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query_url": config.QUERY_URL,
        "where": config.WHERE_CLAUSE,
        "page_size": page_size,
        "api_reported_count": expected,
        "records_retrieved": retrieved,
    }
    config.RAW_METADATA_FILE.write_text(json.dumps(extract_metadata, indent=2), encoding="utf-8")
    logger.info("Saved %d records to %s", retrieved, config.RAW_RECORDS_FILE)
    return extract_metadata
