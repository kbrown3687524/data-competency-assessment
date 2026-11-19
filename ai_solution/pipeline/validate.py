"""Step 2 validation: reconcile the suburb counts against the raw data and API.

Each check is recorded in ``validation_report.json`` with its expected and
actual values. The pipeline fails (non-zero exit) if any check fails, so a bad
result can never be published silently.
"""

import json
import logging
from typing import Any

import pandas as pd
import requests

from pipeline import api, config, extract, transform

logger = logging.getLogger(__name__)


def fetch_server_suburb_counts(session: requests.Session) -> dict[Any, int]:
    """Count records per raw suburb value on the server (group-by statistics).

    Aggregated queries are capped at ``maxRecordCount`` groups too, so this
    pages through the groups with ``resultOffset``.
    """
    counts: dict[Any, int] = {}
    offset = 0
    page_size = 1000
    statistic = [{
        "statisticType": "count",
        "onStatisticField": config.OBJECT_ID_FIELD,
        "outStatisticFieldName": "report_count",
    }]
    while True:
        payload = api.get_json(session, config.QUERY_URL, {
            "where": config.WHERE_CLAUSE,
            "outStatistics": json.dumps(statistic),
            "groupByFieldsForStatistics": config.SUBURB_FIELD,
            "orderByFields": config.SUBURB_FIELD,
            "resultOffset": offset,
            "resultRecordCount": page_size,
        })
        features = payload.get("features", [])
        for feature in features:
            attributes = feature["attributes"]
            counts[attributes[config.SUBURB_FIELD]] = attributes["report_count"]
        if not features or not payload.get("exceededTransferLimit"):
            return counts
        offset += len(features)


def _upper_keys(counts: dict[Any, int]) -> dict[Any, int]:
    """Merge count keys case-insensitively; missing (None/NaN) keys become None."""
    merged: dict[Any, int] = {}
    for key, value in counts.items():
        norm = None if key is None or (isinstance(key, float) and pd.isna(key)) else str(key).upper()
        merged[norm] = merged.get(norm, 0) + int(value)
    return merged


def _check(name: str, expected: Any, actual: Any, note: str = "") -> dict[str, Any]:
    passed = expected == actual
    log = logger.info if passed else logger.error
    log("%s %s: expected=%s actual=%s", "PASS" if passed else "FAIL", name, expected, actual)
    return {"check": name, "passed": passed, "expected": expected, "actual": actual, "note": note}


def validate(counts: pd.DataFrame, session: requests.Session | None = None) -> dict[str, Any]:
    """Run every reconciliation check and write the validation report."""
    records = transform.load_raw_records()
    metadata = json.loads(config.RAW_METADATA_FILE.read_text(encoding="utf-8"))
    quality = transform.summarise_quality(records)
    total = len(records)
    unknown = int(counts.loc[counts["suburb"] == config.UNKNOWN_SUBURB, "report_count"].sum())
    missing_suburb = (
        quality["null"] + quality["blank_or_whitespace_only"]
        + quality["placeholder_no_letters"] + quality["literal_unknown"]
    )

    checks = [
        _check("suburb counts sum to total records", total, int(counts["report_count"].sum())),
        _check(
            "UNKNOWN bucket equals records with no usable suburb", missing_suburb, unknown,
            "null + blank + placeholder (no letters, e.g. '#') + literal 'Unknown'",
        ),
        _check(
            "known-suburb counts + UNKNOWN reconcile to total", total,
            int(counts.loc[counts["suburb"] != config.UNKNOWN_SUBURB, "report_count"].sum()) + unknown,
        ),
        _check("one row per suburb", True, bool(counts["suburb"].is_unique)),
        _check(
            "sorted by count descending", True,
            bool(counts["report_count"].is_monotonic_decreasing),
        ),
        _check(
            "no duplicate ObjectIds in extract", total,
            int(records[config.OBJECT_ID_FIELD].nunique()),
        ),
        _check(
            "every record is a 'No Power' complaint", total,
            int((records["C3_Complaint_Type"] == config.COMPLAINT_TYPE).sum()),
        ),
        _check(
            "records extracted equal API count at extract time",
            metadata["api_reported_count"], total,
        ),
    ]

    # Live checks against the API. If the API is unreachable these are
    # recorded as skipped rather than failing an otherwise offline-valid run.
    session = session or api.build_session()
    try:
        live_count = extract.fetch_record_count(session, config.WHERE_CLAUSE)
        checks.append(_check("records extracted equal live API count", live_count, total))

        # The service groups strings case-insensitively (its collation treats
        # "Gugulethu" and "GUGULETHU" as one group), so compare on upper case.
        server = _upper_keys(fetch_server_suburb_counts(session))
        local = _upper_keys(records[config.SUBURB_FIELD].value_counts(dropna=False).to_dict())
        mismatched = sorted(
            str(k) for k in set(server) | set(local) if server.get(k) != local.get(k)
        )
        checks.append(_check(
            "raw per-suburb counts match server-side group-by", [], mismatched[:20],
            f"{len(server)} server groups vs {len(local)} local groups (case-insensitive)",
        ))
    except api.ArcGISError as exc:
        logger.warning("Skipping live API checks: %s", exc)
        checks.append({"check": "live API checks", "passed": None, "note": f"skipped: {exc}"})

    report = {
        "total_records": total,
        "distinct_suburbs_after_cleaning": int(len(counts)),
        "unknown_suburb_records": unknown,
        "suburb_quality_issues": quality,
        "all_passed": all(c["passed"] is not False for c in checks),
        "checks": checks,
    }
    transform.write_json(config.VALIDATION_FILE, report)
    logger.info("Validation report written to %s", config.VALIDATION_FILE)
    return report
