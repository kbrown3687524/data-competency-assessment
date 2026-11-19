# C3 "No Power" service requests: extraction and suburb counts

> **AI-generated solution.** Everything in this `ai_solution/` folder was written by
> Claude (AI) on the `AI_enabled_codebase_to_address_data_competency_assessment` branch.
> It is kept apart from the hand-written work on `main`.

This pipeline pulls every City of Cape Town C3 service request with complaint type
**`No Power`** from the City's ArcGIS feature service. It saves the raw records
locally, counts reports per suburb after cleaning the suburb field, and checks the
result against the API.

**Result:** 584,665 records extracted (equal to the API's own count). They are
counted into 4,814 suburb rows in
[`data/output/no_power_by_suburb.csv`](data/output/no_power_by_suburb.csv), and
all 10 validation checks pass.

---

## Quick start (one command)

Requires Python 3.10+. From the repository root:

```bash
cd ai_solution && pip install -r requirements.txt && python run_pipeline.py
```

| Command | What it does |
|---|---|
| `python run_pipeline.py` | Extract (only if `data/raw/` has no extract yet), then transform, then validate |
| `python run_pipeline.py --refresh` | Force a fresh download from the API |
| `python -m pytest` | Run the unit tests (offline, about 1 s) |

A fresh extract takes about 5 minutes (585 requests). The process exits with a
non-zero code if extraction fails or any validation check fails, so it is safe to
use in CI or a scheduler.

## Project layout

```
ai_solution/
├── run_pipeline.py            # Entry point: extract -> transform -> validate
├── requirements.txt
├── pytest.ini
├── pipeline/
│   ├── config.py              # Endpoint, filter, paths, retry settings (edit here)
│   ├── api.py                 # HTTP client: retries, back-off, ArcGIS error handling
│   ├── extract.py             # Step 1: schema, server-side filter, paging, raw save
│   ├── transform.py           # Step 2: suburb cleaning and counting
│   ├── validate.py            # Step 2: reconciliation checks
│   └── suburb_aliases.csv     # Reviewed spelling-variant -> canonical suburb map
├── tests/test_pipeline.py     # Unit tests (no network)
├── data/
│   ├── raw/                   # Git-ignored: raw extract + extract metadata
│   └── output/                # Committed: results, schema, audit trail, validation
└── logs/                      # Git-ignored: pipeline.log
```

| Output file | Contents |
|---|---|
| `data/raw/no_power_service_requests.jsonl` | Raw records, one JSON object per line, exactly as the API returned them (about 242 MB, **git-ignored**) |
| `data/raw/no_power_extract_metadata.json` | When the extract ran, the query used, the API count and the records retrieved |
| `data/output/schema.json` | Layer schema: field names, types, lengths, and the page-size limit |
| `data/output/no_power_by_suburb.csv` | **The deliverable**: `suburb,report_count`, sorted by count descending |
| `data/output/suburb_cleaning_map.csv` | Audit trail: every raw suburb value, its cleaned value, and its record count |
| `data/output/validation_report.json` | Every validation check with expected and actual values, plus data quality counts |

---

## Step 0: Setup decisions

* **No manual download and no committed dataset.** The data only ever comes from
  the API. `data/raw/*` is in `.gitignore`. Small derived outputs (the counts,
  schema and validation report) *are* committed so a reviewer can see the
  results without running anything.
* **Dependencies:** `requests` (HTTP), `pandas` (aggregation), and `pytest` (tests).
* **Single command:** `run_pipeline.py` runs every step in order. Step 1 is skipped
  when a raw extract already exists, so later steps don't call the API again
  (the challenge asks for this). Use `--refresh` to download again.
* **Logging, not print:** every module uses `logging`. Output goes to the
  console and to `logs/pipeline.log`.

## Step 1: Data extraction

### How the endpoint was found

1. An ArcGIS Hub site exposes a public search API. I queried it for the dataset:
   ```
   GET https://odp-cctegis.opendata.arcgis.com/api/search/v1/collections/dataset/items?q=service requests 2023
   ```
   The result included item `90711027d33940b5a06e96ad8a8f7ede`, titled
   *"Service Requests 2023 until 06 October 2026 (Deprecated)"*. Its `url`
   property is the backing feature service:
   ```
   https://services6.arcgis.com/nyYfO9SxHU2ChQd9/arcgis/rest/services/Service_Requests_2023_until_20_May_2026/FeatureServer
   ```
   The same URL appears on the dataset page under *I want to use this → View API
   Resources*. **Note:** the service is still named `..._until_20_May_2026`
   although the portal title says "06 October 2026". The item was renamed on
   the portal, but the service behind it was not.
2. `GET <FeatureServer>?f=json` shows the service has **no spatial layers and one
   table, id `0`**. Queries therefore go to `<FeatureServer>/0/query`.
3. `GET <FeatureServer>/0?f=json` returns the layer definition (the schema below).

### Schema (layer 0, `Service_Requests_2023_until_20_May_2026`)

This is a non-spatial **Table** (`geometryType: null`). The coordinates are plain
numeric attributes. The object ID field is `ObjectId`. **`maxRecordCount` = 1000**,
which is the most rows one request can return. Pagination is supported.

| Field | ArcGIS type | Length | Notes |
|---|---|---|---|
| `Sub_Council` | String | 4000 | e.g. `Not assigned` |
| `Ward` | String | 256 | Stored as text, e.g. `000` |
| `Suburb` | String | 4000 | **Free text**, so many quality issues (see step 2) |
| `C3_Complaint_Type` | String | 4000 | Filter field, e.g. `No Power` |
| `Work_Center` | String | 4000 | e.g. `Electricity - FLR-Muizenberg-Contractor` |
| `Notification` | Integer | | SAP notification number |
| `Notification_type` | String | 4000 | |
| `X_Y_Co_ordinate_1` | Double | | Often `0` (no location captured) |
| `X_Y_Co_ordinate_2` | Double | | Often `0` |
| `Created_On_Date` | Date | 8 | Epoch milliseconds in the JSON |
| `Changed_on` | Date | 8 | Epoch milliseconds |
| `Completed_Date` | Date | 8 | Epoch milliseconds |
| `Notifications_Created` | Integer | | |
| `ObjectId` | OID | | Unique, not nullable; used for paging |

The pipeline writes this schema to `data/output/schema.json` on every extract,
so any upstream schema change shows up as a git diff.

### Record counts reported by the API

| Query (`returnCountOnly=true`) | Count |
|---|---|
| `where=1=1` (whole table) | 5,372,466 |
| `where=C3_Complaint_Type = 'No Power'` | **584,665** |

### Server-side filter

Every request sends `where=C3_Complaint_Type = 'No Power'`, so the server applies
the filter and only matching rows are transferred. Nothing is filtered after
download. Validation confirms that every saved record has this complaint type.

### Paging (handling the 1000-record limit)

At 1000 rows per request, 584,665 records need 585 requests. I tested both paging
methods the service supports:

* **Offset paging** (`resultOffset=N`): a page near the end (`resultOffset=580000`)
  took **about 5 s**, because the server has to skip all the earlier rows. Results
  can also skip or repeat rows if the data changes between requests.
* **Keyset paging** (used): `where=(<filter>) AND ObjectId > <last id seen>`,
  `orderByFields=ObjectId ASC`, `resultRecordCount=1000`. Each page took
  **about 0.8 s** however deep it was, and pages can never overlap.

The loop stops when a page comes back empty. The page size is read from the
layer's `maxRecordCount` rather than hard-coded. The whole extract took about 5
minutes.

### Error handling

`pipeline/api.py::get_json` wraps every request:

| Failure | Behaviour |
|---|---|
| Connection error, timeout (10 s connect, 120 s read) | Retry |
| HTTP 429 / 500 / 502 / 503 / 504 | Retry |
| HTTP 200 carrying an ArcGIS `{"error": ...}` body (ArcGIS often reports errors this way) | Retry |
| Invalid JSON, or a JSON body that isn't an object | Retry |
| Other HTTP 4xx (e.g. 400 bad query, 404) | Fail immediately, since retrying can't fix it |
| A query response with no `features` or `count` key | Fail with a clear error |

Retries use exponential back-off: 5 attempts, waiting 2, 4, 8 and 16 s between
them. All retry settings are in `config.py`. Each retry is logged as a warning,
and giving up is logged as an error.

**Integrity safeguards:**

* Records are written to a `.tmp` file, which is renamed to its final name only
  when the extract finishes. An interrupted run can't leave a truncated file
  that later steps would treat as complete.
* Before the rename, the number of **unique ObjectIds** retrieved must equal the
  API's `returnCountOnly` figure. If it doesn't, the run fails.

### Raw output

The records are saved as JSON Lines (`data/raw/no_power_service_requests.jsonl`):
one API `attributes` object per line, unchanged. JSON Lines keeps the API's
types (integers, epoch dates, nulls), so nothing is lost by converting to CSV,
and it can be streamed line by line. The extract metadata (time, query, counts)
is saved next to it.

---

## Step 2: Initial data transformation

### Suburb data quality: what was found

These are measured over all 584,665 records and written to
`validation_report.json` → `suburb_quality_issues`:

| Issue | Records | Example(s) |
|---|---|---|
| Null | 1,427 | `null` |
| Blank / whitespace only | 145 | `" "` |
| Placeholder with no letters | 25,674 | `#` (25,638 of them), `0`, `000`, `.`, a phone number |
| Literal "unknown" | 159 | `UNKNOWN`, `Unknown` |
| Leading/trailing whitespace | 802 | `"   New Crossroads"` |
| Not upper case (the City's values are upper case) | 63,615 | `Gugulethu`, `philippi` |
| Contains a digit (mostly street addresses typed into the suburb field) | 7,338 | `15 Lukhanyo Street,Mfuleni` |
| Distinct raw values | 7,919 | |

There are also **spelling variants** (`GUGULETHU`/`GUGULETU`, `PHILLIPI`/`PHILIPPI`),
**spacing and punctuation variants** (`HOUTBAY`/`HOUT BAY`, `Athlone.`),
**Afrikaans and English forms** (`KUILSRIVIER`/`KUILS RIVER`), and **values cut
off at 25 characters** (`WESTRIDGE - MITCHELLS PLA`).

### Cleaning decisions and why

The guiding principle is to **fix what is unambiguous, merge only what has been
reviewed, and never guess.** A wrong merge silently moves reports to the wrong
suburb, which is worse than leaving a messy value visible.

The rules are applied in this order (`pipeline/transform.py`):

1. **Formatting (automatic).** Unicode NFKC normalisation, upper case, collapse
   runs of whitespace, strip stray punctuation from both ends (`.,;:/\-_*=#` and
   similar), and standardise spaced hyphens to ` - `. Brackets and apostrophes
   are kept because they are often part of the name (`SIMON'S TOWN`).
   *Why:* these differences carry no meaning. The City's own values are upper case.
2. **Missing values → `UNKNOWN` (automatic).** Null, blank, values with no
   letters (`#`, `0`, ...), and literal `unknown` all go into a single
   **`UNKNOWN`** row (27,405 records, 4.7%).
   *Why:* dropping them would undercount the total. Keeping them as an explicit
   row means the suburb counts still add up to the number of records extracted.
   `#` is clearly a system placeholder, not a suburb.
3. **Reviewed aliases ([`pipeline/suburb_aliases.csv`](pipeline/suburb_aliases.csv)).**
   21 explicit `variant → canonical` mappings, each with a stated reason.
   Examples: `GUGULETHU → GUGULETU`, `PHILLIPI → PHILIPPI`,
   `KUILSRIVIER → KUILS RIVER`, `WESTRIDGE - MITCHELLS PLA → WESTRIDGE - MITCHELLS PLAIN`.
   The canonical form is always the City's dominant spelling in this data.
   *How they were found:* `difflib` similarity of at least 0.85 between suburbs
   with 15 or more records and suburbs with 100 or more records. Each candidate
   was then **reviewed by hand**.
   *Deliberately not merged* (they look alike but are different places):
   `BEACONVALE` (Parow) vs `BEACON VALLEY` (Mitchells Plain), `STELLENBERG` vs
   `STEENBERG`, `WESTRIDGE` vs `EASTRIDGE`, `PEERLESS PARK EAST` vs `WEST`,
   numbered areas (`BELHAR EXT 21` vs `EXT 23`, `PLATTEKLOOF 1/2/3`,
   `WELGELEGEN 1/2/3`), `CAPE FARMS - DISTRICT B/C/H`, `MITCHELLS PLAIN CBD`,
   `STRAND INDUSTRIA`, and `BLOUBERGSTRAND` vs `BLAAUWBERGSTRAND`.
4. **Spacing/punctuation variants (automatic).** Values that are identical once
   spaces and punctuation are removed (`HOUTBAY` = `HOUT BAY`,
   `MITCHELL'S PLAIN` = `MITCHELLS PLAIN`) are merged into whichever spelling is
   most frequent. Ties are broken alphabetically so the output is deterministic.
   *Why:* the letters are identical, so there is no ambiguity about which place
   is meant.

**Not done, on purpose: parsing free-text addresses.** About 2,800 suburb rows
have a single report each. Most are full addresses typed into the suburb field
(`15 Lukhanyo Street,Mfuleni`). Pulling a suburb out of these would need
geocoding or fuzzy matching against an official suburb list, which can quietly
assign reports to the wrong suburb. These values are kept, cleaned for
formatting, as their own rows so the problem stays visible. Together they make
up a small share of reports: **566 suburbs with 50 or more reports account for
92.7% of all records.** The next improvement would be to match these addresses
against the City's official suburb boundaries, or use the X/Y coordinates where
they aren't 0.

Every decision can be audited: `data/output/suburb_cleaning_map.csv` lists each
of the 7,919 raw values, what it became, and how many records it covers.

### Result

[`data/output/no_power_by_suburb.csv`](data/output/no_power_by_suburb.csv) has
4,814 rows with columns `suburb,report_count`, sorted by count descending (ties
alphabetically). The top 12:

| suburb | report_count |
|---|---|
| PHILIPPI | 35,263 |
| UNKNOWN | 27,405 |
| GUGULETU | 26,845 |
| MFULENI | 26,019 |
| LANSDOWNE | 12,398 |
| LANGA | 10,767 |
| STRAND | 9,643 |
| CLAREMONT | 9,381 |
| NYANGA | 8,842 |
| HOUT BAY | 8,361 |
| RONDEBOSCH | 8,013 |
| BONTEHEUWEL | 7,532 |

### Validation

`pipeline/validate.py` runs every check below after each transform and writes
the results to `data/output/validation_report.json`. If any check fails, the
pipeline exits non-zero. Results from the latest run:

| # | Check | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | Sum of suburb counts = total records extracted | 584,665 | 584,665 | ✅ |
| 2 | `UNKNOWN` row = null + blank + placeholder + literal "unknown" | 27,405 | 27,405 | ✅ |
| 3 | Known-suburb counts + `UNKNOWN` = total | 584,665 | 584,665 | ✅ |
| 4 | One row per suburb (no duplicates after cleaning) | true | true | ✅ |
| 5 | Sorted by count descending | true | true | ✅ |
| 6 | No duplicate `ObjectId`s in the extract | 584,665 | 584,665 | ✅ |
| 7 | Every record has `C3_Complaint_Type = 'No Power'` | 584,665 | 584,665 | ✅ |
| 8 | Records extracted = API count at extract time | 584,665 | 584,665 | ✅ |
| 9 | Records extracted = **live** API count (queried again) | 584,665 | 584,665 | ✅ |
| 10 | Raw per-suburb counts = **server-side group-by** (`outStatistics` count grouped by `Suburb`, paged) | 0 mismatches | 0 mismatches (6,224 groups) | ✅ |

Check 10 is an independent cross-check: the server does the aggregation itself.
It turned up one detail worth recording: **the service groups strings
case-insensitively** (`Gugulethu` and `GUGULETHU` come back as one group). The
local counts are therefore compared case-insensitively too. Checks 9 and 10 need
network access. If the API is unreachable they are marked "skipped" rather than
failing an otherwise valid offline run.

---

## Processing log (what was done, in order)

1. Cleared the branch to a blank slate, keeping `main` untouched. The AI branch
   was checked out in its own folder (a git worktree), so files on `main` were
   never modified. All AI work lives in `ai_solution/`.
2. Found the dataset through the Hub search API, then its feature service URL,
   then its single table (layer 0).
3. Read the layer definition: 14 fields, non-spatial table, `maxRecordCount` 1000.
4. Asked the API for counts: 5,372,466 records in total, 584,665 for `No Power`.
5. Timed offset paging (about 5 s for a deep page) against keyset paging (about
   0.8 s) and chose keyset paging.
6. Wrote `api.py` (retries and back-off), `extract.py` (schema, filter, paging,
   atomic save, count check) and `config.py`.
7. Ran the extraction: 585 pages in about 5 minutes. 584,665 unique records
   saved, matching the API count.
8. Profiled the `Suburb` field: nulls, `#` placeholders, case and whitespace
   problems, addresses, spelling variants. Initially 4,832 distinct values after
   formatting.
9. Generated spelling-variant candidates with `difflib`, reviewed them by hand,
   and recorded 21 aliases with reasons. The count fell to 4,814 suburb rows.
10. Wrote `transform.py` (cleaning, counting, audit map) and `validate.py`.
11. The first validation run found two things: 159 literal "Unknown" values (now
    counted in `UNKNOWN`), and the server's case-insensitive grouping (the
    comparison is now case-insensitive). After those fixes, all 10 checks pass.
12. Wrote 26 offline unit tests covering normalisation, placeholder handling,
    aliases, aggregation and sorting, retry and back-off behaviour, and keyset
    paging. All pass.

## Maintenance notes

* **Change the filter or endpoint:** edit `pipeline/config.py` (`WHERE_CLAUSE`,
  `FEATURE_SERVICE_URL`).
* **Add a suburb merge:** add a row to `pipeline/suburb_aliases.csv` with a
  reason, then run `python run_pipeline.py`. A unit test checks that aliases
  never point to another alias. Use `suburb_cleaning_map.csv` to find variants.
* **The dataset is deprecated**, so counts should stay stable. If check 9 ever
  fails, the upstream data has changed: re-run with `--refresh`.
* **Dates** in the raw file are epoch milliseconds (UTC). Convert them with
  `pd.to_datetime(col, unit="ms")`.
