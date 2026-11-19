# Response to Provincial Health Data Centre – Data Engineer Challenge

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
3. The same request can be made programmatically. In `code/challenge_part_1.py`, the `fetch_dataset_schema()` function sends a GET request to `<FeatureServer URL>/layers?f=json` and returns the combined `layers` and `tables` lists. The script then prints each field's name and type, so the schema can be checked every time the script runs without opening the browser:

   ```python
   for item in fetch_dataset_schema(base_url):
       for field in item.get("fields", []):
           print(f"  Field: {field['name']} ({field['type']})")
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

- The number of matching records was checked with `returnCountOnly=true` before downloading, then compared with the number of rows actually retrieved to confirm the download was complete.
- Total records: **5,372,466** | "No Power" records: **_TBC_**

### Data storage

- Raw outputs are written to `data/raw/`, which is git-ignored (`data/raw/*` with an exception for `data/raw/.gitkeep`), so the folder structure is tracked but the data files are never committed.
- Run logs are written to `arcgis_fetch.log`.

### Running the script

```bash
pip install -r requirements.txt
python code/challenge_part_1.py
```

## Challenge Part 2 – Analysing Records by Suburb

### Overview

`code/challenge_part_2.py` reads the records downloaded in Part 1, aggregates the number of service requests per suburb, and splits the records into a separate CSV file for each suburb.

### Input

- `data/raw/0_Service_Requests_2023_until_20_May_2026.csv`: the output of `challenge_part_1.py`.
- The path is built relative to the script's location (`Path(__file__).resolve().parent.parent`), so the script runs correctly from any working directory.

### Functions

| Function | Purpose |
|---|---|
| `read_data(file_path)` | Reads the CSV into a pandas DataFrame. |
| `aggregate_reports_by_suburb_data(df)` | Groups records by `Suburb` and counts the requests per suburb, returning a DataFrame with `Suburb` and `count` columns. |
| `split_records_by_suburb(df)` | Writes each suburb's records to its own CSV in `data/raw/suburb_records/`. |

### Splitting records by suburb

1. Records are grouped on the `Suburb` column. Missing suburb values are first replaced with `"Unknown"` (`df['Suburb'].fillna('Unknown')`), because pandas' `groupby` would otherwise drop those rows silently and the records would be lost.
2. Each suburb name is converted into a safe filename with a regular expression (`re.sub(r'[^\w\-]', '', suburb)`). This removes any character that isn't a letter, digit, underscore or hyphen, such as spaces, `/`, `.` and `'`, since some of these aren't allowed in Windows filenames. If nothing is left after cleaning, the file is named `Unknown.csv`.
3. Each group is saved as `data/raw/suburb_records/<Suburb>.csv`. Because these files sit inside `data/raw/`, they are git-ignored along with the rest of the raw data.

### Logging

Progress messages are written to the console and to `arcgis_fetch.log` using the same logging configuration as Part 1.

### Data quality: the `Suburb` field

> _In progress._ Findings and handling decisions for the `Suburb` field (missing or blank values, numeric placeholders such as `0`/`00`, inconsistent capitalisation, stray whitespace, spelling variants and physical addresses) will be documented here, including how many records each decision affected.

### Running the script

```bash
python code/challenge_part_2.py
```

