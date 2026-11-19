# Response to Provincial Health Data Centre – Data Engineer Challenge

## Running the pipeline

Both parts run end-to-end with a single command from the project root:

```bash
pip install -r requirements.txt
python run_pipeline.py
```

- `run_pipeline.py` sets up logging, downloads the "No Power" records (Part 1) if `data/raw/0_Service_Requests_2023_until_20_May_2026.csv` does not exist yet, and then always runs the suburb transformation (Part 2).
- If the raw extract already exists, the download is skipped so the API is not called again. To force a fresh download, run:

  ```bash
  python run_pipeline.py --refresh
  ```

- The script exits with code `0` on success and `1` if any step fails (the error and traceback are written to the log).

## Challenge Part 0 – Exploring the Data

- I forked the `data-competency-assessment` repository to my personal GitHub so I had a safe backup to revert to if issues arose.
- I opened the provided URL in Chrome, which led to the City of Cape Town Open Data Portal page for service requests.
- Although the brief gave some context on what to expect, browsing the data in the portal first gave me a clearer picture of what I would be working with.

## Challenge Part 1

### Working out the API endpoint

I used two approaches to identify the API endpoint behind the portal.

**Approach 1: Browser Developer Tools (preferred)**

1. Open Chrome's Developer Tools (`Ctrl + Shift + I`) and go to the **Network** tab.
2. Apply the **Fetch/XHR** filter, clear the list, and reload the data view. This shows only the background data requests the page makes as new data appears.
3. Inspecting each request's **Preview/Response** tab showed that most calls (`self`, `settings`, `groups`, `datasets`, `metadata.xml`) only return app configuration or metadata.
4. The `FeatureServer` request was the one serving the data the frontend displays, which made it the main route to pull data from:

   ```
   https://services6.arcgis.com/nyYfO9SxHU2ChQd9/arcgis/rest/services/Service_Requests_2023_until_20_May_2026/FeatureServer
   ```

5. Opening this URL in the browser loads the ArcGIS REST Services page, which describes the service and its layers.
6. Records are queried from the layer's `/query` endpoint:

   ```
   …/FeatureServer/0/query?where=1=1&outFields=*&f=json
   ```

   The query parameters (everything after the `?`, separated by `&`) are:
   - `where=1=1`: a condition that is always true, so all records are returned
   - `outFields=*`: returns all attribute fields
   - `f=json`: sets the response format (`f=geojson` is also supported)

7. Because the dataset is large (**5,372,466 records**, confirmed with `returnCountOnly=true`), each response is capped at the service's `maxRecordCount`, so records must be retrieved in pages using `resultOffset` and `resultRecordCount`.
8. I confirmed the endpoint was publicly accessible by pasting the query URL into a new browser tab and testing additional query parameters. It returned data without needing an authentication token.

**Approach 2: Portal interface**

This option isn't available on every portal, so the Developer Tools approach is the more reliable default.

1. On the dataset page, click **View Full Details** in the left-hand navigation panel.
2. This opens the dataset's **About** page (the URL now ends in `/about`). Scroll down to the **View API Resources** card on the right-hand side, which lists ready-made endpoints for each response format (e.g. GeoService, GeoJSON).
3. The **GeoService** URL listed there is the same `FeatureServer` endpoint identified in the Network tab, which confirms it as the main route.

### Inspecting the dataset's schema

1. Using the same Network-tab approach, I inspected the `layers` request (`<FeatureServer URL>/layers?f=json`). This endpoint returns every layer in the service along with any associated tables.
2. Opening this URL directly in a browser tab returns the same JSON response. It contains a `layers` array (spatial data) and a `tables` array (non-spatial data), and each entry has a `fields` array describing the schema.
3. The same request can be made programmatically. In `code/challenge_part_1.py`, the `fetch_dataset_schema()` function sends a GET request to `<FeatureServer URL>/layers?f=json` and returns the combined `layers` and `tables` lists. The script then logs each field's name and type, so the schema can be checked every time the script runs without opening the browser:

   ```python
   for item in fetch_dataset_schema(base_url):
       for field in item.get("fields", []):
           logger.info(f"  Field: {field['name']} ({field['type']})")
   ```

4. Layer `0` contains the following fields:

| Field | Type | Alias | Length | Nullable |
|---|---|---|---|---|
| `Sub_Council` | String | Sub Council | 4000 | Yes |
| `Ward` | String | Ward | 256 | Yes |
| `Suburb` | String | Suburb | 4000 | Yes |
| `C3_Complaint_Type` | String | C3 Complaint Type | 4000 | Yes |
| `Work_Center` | String | Work Center | 4000 | Yes |
| `Notification` | Integer | Notification | – | Yes |
| `Notification_type` | String | Notification type | 4000 | Yes |
| `X_Y_Co_ordinate_1` | Double | X-Y Co ordinate 1 | – | Yes |
| `X_Y_Co_ordinate_2` | Double | X-Y Co ordinate 2 | – | Yes |
| `Created_On_Date` | Date | Created On Date | 8 | Yes |
| `Changed_on` | Date | Changed on | 8 | Yes |
| `Completed_Date` | Date | Completed Date | 8 | Yes |
| `Notifications_Created` | Integer | Notifications Created | – | Yes |
| `ObjectId` | OID | ObjectId | – | No (unique ID) |

> Date fields are returned as Unix timestamps in milliseconds and need converting (e.g. `pd.to_datetime(df["Created_On_Date"], unit="ms")`).

### Filtering on the server side

- Rather than downloading all 5.37M records and filtering locally, the filter is passed in the `where` parameter so ArcGIS only returns matching records:

  ```
  where=C3_Complaint_Type = 'No Power'
  ```

- The number of matching records can be checked with `returnCountOnly=true` (e.g. in the browser) and compared with the number of rows actually retrieved to confirm the download was complete. This comparison is not yet automated in the pipeline.
- Total records: **5,372,466** | "No Power" records downloaded: **584,665**

### Data storage

- Raw outputs are written to `data/raw/`, which is git-ignored (`data/raw/*` with an exception for `data/raw/.gitkeep`), so the folder structure is tracked but the data files are never committed.
- The raw "No Power" extract is saved as `data/raw/0_Service_Requests_2023_until_20_May_2026.csv`.
- Run logs are written to the console and to `logs/pipeline.log`.

## Challenge Part 2 – Analysing Records by Suburb

### Overview

`code/challenge_part_2.py` reads the records downloaded in Part 1, standardises the `Suburb` field, counts the "No Power" reports per suburb, writes the counts to a CSV sorted by count (highest first), and checks that the counts reconcile to the number of records extracted. It also splits the records into a separate CSV file for each suburb.

### Input and output

| File | Description |
|---|---|
| `data/raw/0_Service_Requests_2023_until_20_May_2026.csv` | Input: the raw extract from Part 1. |
| `data/no_power_by_suburb.csv` | Output: one row per suburb (`Suburb`, `count`), sorted by `count` in descending order. |
| `data/raw/suburb_records/<Suburb>.csv` | Extra output: each suburb's records in its own file (git-ignored). |

All paths are built relative to the script's location (`Path(__file__).resolve().parent.parent`), so the pipeline runs correctly from any working directory.

### Functions

| Function | Purpose |
|---|---|
| `read_data(file_path)` | Reads the CSV into a pandas DataFrame. |
| `aggregate_reports_by_suburb_data(df)` | Counts the records per suburb (missing suburbs as `Unknown`), writes the sorted counts to `data/no_power_by_suburb.csv`, raises an error if the counts don't add up to the number of records, and returns the total. |
| `split_records_by_suburb(df)` | Writes each suburb's records to its own CSV in `data/raw/suburb_records/`. |
| `transform(file_path)` | Runs the steps above in order, after standardising the `Suburb` field. |

### Splitting records by suburb

1. Records are grouped on the `Suburb` column. Missing suburb values are first replaced with `"Unknown"` (`df['Suburb'].fillna('Unknown')`), because pandas' `groupby` would otherwise drop those rows silently and the records would be lost.
2. Each suburb name is converted into a safe filename with a regular expression (`re.sub(r'[^\w\-]', '', suburb)`). This removes any character that isn't a letter, digit, underscore or hyphen, such as spaces, `/`, `.` and `'`, since some of these aren't allowed in Windows filenames. If nothing is left after cleaning, the file is named `Unknown.csv`.
3. Each group is saved as `data/raw/suburb_records/<Suburb>.csv`. Because these files sit inside `data/raw/`, they are git-ignored along with the rest of the raw data.

### Logging

Progress messages are written to the console and to `logs/pipeline.log`. Logging is configured once in `run_pipeline.py`; each module gets its own logger with `logging.getLogger(__name__)`.

### Data quality: the `Suburb` field

A total of **584,665** "No Power" records were retrieved from the API, and the `Suburb` field of every record was assessed for data quality. Before cleaning, the field held **7,918** distinct values.

| Issue found | Records affected | Example |
|---|---|---|
| Missing (null) suburb | 1,427 | – |
| Blank (only whitespace) | 145 | `" "` |
| Numeric placeholders | 28 | `0`, `00`, `000` |
| Placeholder town name | 165 | `GENERIC TOWN 0000` |
| Leading, trailing or double spaces | 2,304 | `MASIPHUMELE  SITE -5` |
| Inconsistent capitalisation | – (see below) | `PLATTEKLOOF 3` (492) vs `Plattekloof 3` (170) |
| `#` used as a placeholder | 25,638 | `#` |
| Street addresses instead of suburbs | ~384 | `13 DOVER ROAD,MUIZENBERG` |
| Spelling variants of the same suburb | not yet quantified | – |

Suburb names that contain numbers, such as `BELHAR EXT 23`, `PLATTEKLOOF 3` or `N1-STAD`, are real suburb or extension names and are kept as they are. Each extension is counted as its own suburb rather than being rolled up into a parent suburb (e.g. `Belhar`), because these are official suburb names and rolling them up would lose detail.

### Data Quality Issues

There are several ways to handle these issues:

1. **Relabel invalid values as `Unknown`.** Blank values, numeric placeholders (`0`, `00`, `000`) and street addresses are replaced with a single label such as `Unknown`. This keeps every record in the dataset, so overall totals stay accurate, but it loses the location information for those records, so they can't be attributed to a specific suburb.

2. **Standardising.** Values are standardised to one format before counting: whitespace is stripped, capitalisation is made consistent, and any variations in naming are mapped to a single canonical name.

3. **Suburb recovery.** The dataset has other location fields, such as `Ward` and the X/Y coordinates, so it is possible to infer the correct suburb by comparing with other records or with the City of Cape Town's official suburb boundaries.

4. **Removal of records.** Dropping invalid records is the simplest option, but it reduces the true number of complaints and may bias the counts for certain suburbs.

**Final decision:** I combined the first and second approaches. In `transform()`, one line standardises the `Suburb` field before counting:

```python
df['Suburb'] = (df['Suburb'].str.strip()
                .str.replace(r'\s+', ' ', regex=True)
                .str.upper()
                .replace(r'^(0*|#|GENERIC TOWN 0+)$', pd.NA, regex=True))
```

- **Whitespace:** leading and trailing spaces are removed and repeated spaces are collapsed to one, so `MASIPHUMELE  SITE -5` and `MASIPHUMELE SITE -5` are counted together (2,304 records changed).
- **Capitalisation:** all names are converted to uppercase, so `Plattekloof 3` and `PLATTEKLOOF 3` are counted as one suburb. Together with the whitespace fix, this reduced the number of distinct suburb values from **7,918** to **5,857**.
- **Placeholders:** blank values, `0`/`00`/`000`, `#` and `GENERIC TOWN 0000` are set to missing and then counted as `Unknown` together with the null values. In total **27,403** records (about 4.7%) are counted as `Unknown`: 1,427 null + 145 blank + 28 numeric + 25,638 `#` + 165 `GENERIC TOWN 0000`. After cleaning, the output has **5,850** suburbs, including `Unknown`.

Records are relabelled rather than dropped, so every extracted record is still counted.

**Known limitations (not yet handled):**

- About 384 values are street addresses (e.g. `13 DOVER ROAD,MUIZENBERG`). They are currently counted as separate suburbs. Many end with the suburb name, which could be extracted, or the coordinates could be used to recover the suburb.
- Spelling variants of the same suburb (e.g. differences in hyphenation or abbreviations such as `EXT`/`EXTENSION`) are not yet mapped to a single name.

### Validation of Analyses

- `aggregate_reports_by_suburb_data()` counts the records per suburb and sums those counts across all suburbs.
- The pipeline checks this automatically: if the sum of the suburb counts does not equal the number of records extracted, it raises a `ValueError` and the run fails.
- Records with no valid suburb are kept under the `Unknown` label rather than dropped. With them included, the suburb counts add up to **584,665**, which matches the total number of "No Power" records downloaded from the API.
- Without the `Unknown` label, pandas' `groupby` silently drops the **1,427** records that have no suburb in the raw data, and the counts add up to only **583,238**. After cleaning, **27,403** records are counted as `Unknown`, which makes it the second-largest group in the output after Philippi. Labelling them `Unknown` is what keeps the totals in line.
- So no records are lost during the aggregation. As noted above, though, the records grouped under `Unknown` cannot be attributed to a specific suburb.
- **Not yet done:** comparing the downloaded total with the count the API reports for the same filter (`returnCountOnly=true`) is not yet automated in the pipeline.
