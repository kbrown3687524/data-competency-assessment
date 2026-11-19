"""Step 2: clean the suburb field and count 'No Power' reports per suburb.

Cleaning is deliberately conservative: it fixes *formatting* problems that are
unambiguous (case, whitespace, stray punctuation, placeholder values) and only
merges spelling variants that are listed explicitly in ``suburb_aliases.csv``,
so every merge is visible and reviewable. Free-text addresses typed into the
suburb field are not parsed, because guessing at them would hide data quality
problems instead of surfacing them. See README.md, "Suburb data quality".
"""

import csv
import json
import logging
import re
import unicodedata
from pathlib import Path

import pandas as pd

from pipeline import config

logger = logging.getLogger(__name__)

ALIASES_FILE = Path(__file__).resolve().parent / "suburb_aliases.csv"

# Characters stripped from the start/end of a value. Brackets and apostrophes
# are kept because they are usually part of the name ("SIMON'S TOWN").
_EDGE_CHARS = " \t.,;:/\\-_*=#[]{}|`~!?+"
_WHITESPACE = re.compile(r"\s+")
_SPACED_HYPHEN = re.compile(r"\s*-\s+|\s+-\s*")  # "A -B", "A- B", "A - B"
_HAS_LETTER = re.compile(r"[A-Z]")


def load_aliases(path: Path = ALIASES_FILE) -> dict[str, str]:
    """Load the variant -> canonical suburb mapping (both already normalised)."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["variant"].strip()]
    return {
        normalise_format(row["variant"]): normalise_format(row["canonical"])
        for row in rows
    }


def normalise_format(value: object) -> str:
    """Fix formatting only: case, whitespace, edge punctuation, placeholders.

    Returns ``config.UNKNOWN_SUBURB`` for missing, blank or placeholder values
    (e.g. ``None``, ``"   "``, ``"#"``): anything that contains no letter.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return config.UNKNOWN_SUBURB
    text = unicodedata.normalize("NFKC", str(value)).upper()
    text = _WHITESPACE.sub(" ", text).strip(_EDGE_CHARS)
    text = _SPACED_HYPHEN.sub(" - ", text)
    if not _HAS_LETTER.search(text):
        return config.UNKNOWN_SUBURB
    return text


def clean_suburb(value: object, aliases: dict[str, str]) -> str:
    """Normalise formatting, then apply the explicit alias mapping."""
    formatted = normalise_format(value)
    return aliases.get(formatted, formatted)


def load_raw_records(path: Path = config.RAW_RECORDS_FILE) -> pd.DataFrame:
    """Load the raw JSON Lines extract written by ``extract.py``."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run the extraction first: python run_pipeline.py"
        )
    return pd.read_json(path, lines=True, dtype={config.SUBURB_FIELD: "object"})


def letters_only_key(value: str) -> str:
    """Key that ignores spaces and punctuation: "MITCHELL'S PLAIN" -> "MITCHELLSPLAIN"."""
    return re.sub(r"[^A-Z0-9]", "", value)


def merge_spacing_variants(clean_counts: pd.DataFrame) -> dict[str, str]:
    """Map each spelling to the most common spelling with the same letters.

    "HOUTBAY", "HOUT BAY" and "HOUT-BAY" differ only in spacing/punctuation,
    so they are unambiguously the same place and merge to whichever form is
    most frequent (the City's own spelling, since it dominates the counts).
    ``clean_counts`` has columns ``clean_suburb`` and ``record_count``.
    """
    totals = clean_counts.groupby("clean_suburb")["record_count"].sum()
    # Visit most frequent first (ties alphabetically), so the first spelling
    # seen for each key is the one everything else merges into.
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    canonical_for_key: dict[str, str] = {}
    for name, _count in ordered:
        canonical_for_key.setdefault(letters_only_key(name), name)
    return {name: canonical_for_key[letters_only_key(name)] for name in totals.index}


def count_by_suburb(records: pd.DataFrame, aliases: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (suburb counts, raw-to-clean audit map).

    Counts are sorted by count descending, then suburb name for stable ties.
    """
    raw = records[config.SUBURB_FIELD]
    raw_counts = raw.value_counts(dropna=False).rename("record_count").reset_index()
    raw_counts.columns = ["raw_suburb", "record_count"]
    raw_counts["clean_suburb"] = [clean_suburb(v, aliases) for v in raw_counts["raw_suburb"]]
    spacing_map = merge_spacing_variants(raw_counts)
    raw_counts["clean_suburb"] = raw_counts["clean_suburb"].map(spacing_map)

    counts = (
        raw_counts.groupby("clean_suburb", as_index=False)["record_count"].sum()
        .rename(columns={"clean_suburb": "suburb", "record_count": "report_count"})
        .sort_values(["report_count", "suburb"], ascending=[False, True], ignore_index=True)
    )
    audit = raw_counts.sort_values(
        ["clean_suburb", "record_count"], ascending=[True, False], ignore_index=True
    )[["raw_suburb", "clean_suburb", "record_count"]]
    return counts, audit


def transform() -> pd.DataFrame:
    """Run step 2 end to end and write the outputs. Returns the suburb counts."""
    records = load_raw_records()
    logger.info("Loaded %d raw records from %s", len(records), config.RAW_RECORDS_FILE)

    aliases = load_aliases()
    logger.info("Loaded %d suburb aliases from %s", len(aliases), ALIASES_FILE)
    counts, audit = count_by_suburb(records, aliases)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    counts.to_csv(config.SUBURB_COUNTS_FILE, index=False)
    audit.to_csv(config.SUBURB_CLEANING_FILE, index=False)
    logger.info(
        "Wrote %d suburbs (from %d distinct raw values) to %s",
        len(counts), len(audit), config.SUBURB_COUNTS_FILE,
    )
    return counts


def summarise_quality(records: pd.DataFrame) -> dict[str, int]:
    """Count the suburb data quality problems found in the raw extract."""
    raw = records[config.SUBURB_FIELD]
    as_text = raw.dropna().astype(str)
    stripped = as_text.str.strip()
    return {
        "records": int(len(raw)),
        "null": int(raw.isna().sum()),
        "blank_or_whitespace_only": int((stripped == "").sum()),
        "placeholder_no_letters": int(((stripped != "") & ~stripped.str.upper().str.contains("[A-Z]")).sum()),
        "literal_unknown": int((stripped.str.upper() == config.UNKNOWN_SUBURB).sum()),
        "leading_or_trailing_whitespace": int((as_text != stripped).sum()),
        "not_upper_case": int((stripped != stripped.str.upper()).sum()),
        "contains_digit": int(stripped.str.contains(r"\d").sum()),
        "distinct_raw_values": int(raw.nunique(dropna=False)),
    }


def write_json(path: Path, payload: dict) -> None:
    """Write ``payload`` as pretty-printed JSON."""
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
