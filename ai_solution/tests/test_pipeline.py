"""Unit tests for the offline parts of the pipeline (no network needed).

Run from the ai_solution/ folder:  python -m pytest
"""

from unittest import mock

import pandas as pd
import pytest
import requests

from pipeline import api, config, extract, transform

UNKNOWN = config.UNKNOWN_SUBURB


# --- Suburb normalisation -------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Gugulethu", "GUGULETHU"),
    ("   New Crossroads", "NEW CROSSROADS"),
    ("Athlone.", "ATHLONE"),
    (", Bonteheuwel", "BONTEHEUWEL"),
    ("PHILLIPI    WEST", "PHILLIPI WEST"),
    ("AVONDALE- WESFLEUR", "AVONDALE - WESFLEUR"),
    ("BEACONVALE-PAROW", "BEACONVALE-PAROW"),  # unspaced hyphen left alone
    ("SIMON'S TOWN", "SIMON'S TOWN"),
    ("RETREAT( R381 OVERCOME HEIGHTS)", "RETREAT( R381 OVERCOME HEIGHTS)"),
])
def test_normalise_format_fixes_formatting_only(raw, expected):
    assert transform.normalise_format(raw) == expected


@pytest.mark.parametrize("raw", [None, float("nan"), "", "   ", "#", " # ", "123", "-"])
def test_missing_and_placeholder_values_become_unknown(raw):
    assert transform.normalise_format(raw) == UNKNOWN


def test_aliases_are_applied_after_formatting():
    aliases = {"GUGULETU": "GUGULETHU"}
    assert transform.clean_suburb("  guguletu ", aliases) == "GUGULETHU"
    assert transform.clean_suburb("Langa", aliases) == "LANGA"


def test_alias_file_entries_are_normalised_and_non_circular():
    aliases = transform.load_aliases()
    for variant, canonical in aliases.items():
        assert variant != canonical
        assert canonical not in aliases, f"{canonical} is itself aliased"


# --- Aggregation ---------------------------------------------------------------

def test_count_by_suburb_merges_variants_and_reconciles():
    records = pd.DataFrame({config.SUBURB_FIELD: [
        "Langa", "LANGA ", " langa", "Guguletu", "GUGULETHU", None, "#", "  ",
    ]})
    counts, audit = transform.count_by_suburb(records, {"GUGULETU": "GUGULETHU"})

    assert counts.to_dict("records") == [
        {"suburb": "LANGA", "report_count": 3},
        {"suburb": UNKNOWN, "report_count": 3},
        {"suburb": "GUGULETHU", "report_count": 2},
    ]
    assert counts["report_count"].sum() == len(records)
    assert audit["record_count"].sum() == len(records)


def test_ties_are_sorted_alphabetically():
    records = pd.DataFrame({config.SUBURB_FIELD: ["B", "A", "C", "C"]})
    counts, _ = transform.count_by_suburb(records, {})
    assert counts["suburb"].tolist() == ["C", "A", "B"]


# --- API client ----------------------------------------------------------------

def _response(status=200, payload=None):
    response = mock.Mock(status_code=status)
    response.json.return_value = payload if payload is not None else {}
    response.raise_for_status.side_effect = (
        requests.HTTPError(response=response) if status >= 400 else None
    )
    return response


@mock.patch("pipeline.api.time.sleep")
def test_get_json_retries_timeouts_and_arcgis_errors(_sleep):
    session = mock.Mock()
    session.get.side_effect = [
        requests.Timeout("slow"),
        _response(200, {"error": {"code": 500, "message": "busy"}}),
        _response(503),
        _response(200, {"count": 7}),
    ]
    assert api.get_json(session, "http://x", {}) == {"count": 7}
    assert session.get.call_count == 4


@mock.patch("pipeline.api.time.sleep")
def test_get_json_gives_up_after_max_retries(_sleep):
    session = mock.Mock()
    session.get.side_effect = requests.ConnectionError("down")
    with pytest.raises(api.ArcGISError):
        api.get_json(session, "http://x", {})
    assert session.get.call_count == config.MAX_RETRIES


def test_get_json_does_not_retry_client_errors():
    session = mock.Mock()
    session.get.return_value = _response(404)
    with pytest.raises(api.ArcGISError):
        api.get_json(session, "http://x", {})
    assert session.get.call_count == 1


def test_iter_pages_uses_keyset_paging_until_empty_page():
    pages = [
        {"features": [{"attributes": {"ObjectId": 1}}, {"attributes": {"ObjectId": 5}}]},
        {"features": [{"attributes": {"ObjectId": 9}}]},
        {"features": []},
    ]
    with mock.patch("pipeline.api.get_json", side_effect=pages) as get_json:
        result = list(extract.iter_pages(mock.Mock(), "X = 1", page_size=2))

    assert [len(page) for page in result] == [2, 1]
    wheres = [call.args[2]["where"] for call in get_json.call_args_list]
    assert wheres == ["(X = 1) AND ObjectId > -1", "(X = 1) AND ObjectId > 5",
                      "(X = 1) AND ObjectId > 9"]


def test_spacing_and_punctuation_variants_merge_to_most_common_spelling():
    records = pd.DataFrame({config.SUBURB_FIELD: [
        "HOUT BAY", "HOUT BAY", "Houtbay", "MITCHELLS PLAIN", "Mitchell's Plain",
        "MITCHELL'S PLAIN",
    ]})
    counts, _ = transform.count_by_suburb(records, {})
    assert dict(zip(counts["suburb"], counts["report_count"])) == {
        "HOUT BAY": 3, "MITCHELL'S PLAIN": 3,
    }
