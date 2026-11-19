import requests, time, logging
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

base_url = "https://services6.arcgis.com/nyYfO9SxHU2ChQd9/ArcGIS/rest/services/Service_Requests_2023_until_20_May_2026/FeatureServer"
raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw"                                       # This line defines the path to the directory where raw data will be stored. It uses the 'Path' class from the 'pathlib' module to construct the path relative to the current script's location. The 'resolve()' method ensures that the path is absolute, and 'parent.parent' navigates up two levels in the directory structure to reach the desired location. The final path points to a "data/raw" directory, which is intended for storing raw data files fetched from the ArcGIS REST API.
raw_dir.mkdir(parents=True, exist_ok=True)                                                              # This line creates the directory specified by 'raw_dir' if it does not already exist. The 'parents=True' argument allows for the creation of any necessary parent directories, and 'exist_ok=True' prevents an error from being raised if the directory already exists. This ensures that the directory structure is in place for storing raw data files.

logger = logging.basicConfig(level = logging.INFO,
    format = "%(asctime)s %(levelname)-8s %(message)s", 
    datefmt = "%Y-%m-%d %H-%M-%S",
    handlers=[
        logging.FileHandler("arcgis_fetch.log", encoding="utf-8"),
        logging.StreamHandler()
    ],
    )
logger = logging.getLogger("arcgis_fetch")

def fetch_dataset_schema(base_url):
    """ 
    This fetches the dataset schema from the 
    ArcGIS REST API and returns it as a dictionary. 
    """
    logger.info("Fetching schema from %s", base_url)                                                                 # This line logs an informational message indicating that the dataset schema is being fetched from the specified base URL. It provides feedback to the user about the progress of the data fetching process.
    try:
        r = requests.get(f"{base_url}/layers", params={"f": "json"}, timeout=3000)                         # This line fetches the dataset schema from the ArcGIS REST API using a GET request. The 'f' parameter specifies the format of the response, which is set to 'json'. The timeout is set to 30 seconds to prevent hanging requests.
        r.raise_for_status()       
    except requests.RequestException:
        logger.exception("HTTP request for schema failed")                                               # logger.exception logs at ERROR level and includes the traceback.
        raise                                                                                            # This line raises an HTTPError if the request returned an unsuccessful status code. It ensures that any issues with the request are caught and handled appropriately.     
    data = r.json()                                                                                      # This line parses the JSON response from the API into a Python dictionary. The 'json()' method converts the JSON string into a Python data structure (in this case, a dictionary).                                 
    if "error" in data:
        raise RuntimeError(f"There was an error fetching the dataset schema: {data['error']}")           # This line checks if the 'error' key is present in the response data. If it is, it raises a RuntimeError with a message indicating that there was an error fetching the dataset schema, along with the error details from the response.
    return data.get("layers", []) + data.get("tables", [])                                               # This line returns a list of layers and tables from the dataset schema. It combines the 'layers' and 'tables' keys from the dictionary, defaulting to empty lists if they are not present.

def fetch_dataset_records(base_url, layer_id, page_size=1000):
    """ 
    This fetches the dataset records from the 
    ArcGIS REST API and returns them, paging past 
    the maximum record count if necessary. 
    """
    url = f"{base_url}/{layer_id}/query"      
    logger.info("Fetching schema from %s", url)
    rows, offset = [], 0                                                                                 # This line initializes an empty list 'rows' to store the fetched records and sets the 'offset' to 0 for pagination. The offset is used to keep track of how many records have been fetched so far.
    while True:
        params = {
            "where": "1=1",                                                                              # This line sets the 'where' parameter to "1=1", which is a common SQL trick to select all records. It effectively means "select all records" from the dataset.
            "outFields": "*",                                                                            # This line sets the 'outFields' parameter to "*", which means that all fields of the records should be returned in the response. It ensures that no data is omitted from the fetched records.
            "returnGeometry": "false",                                                                   # This line sets the 'returnGeometry' parameter to "false", indicating that the geometry of the features should not be included in the response. It is useful when only attribute data is needed.
            "resultOffset": offset,                                                                      # This line sets the 'resultOffset' parameter to the current value of 'offset'. It tells the API to start returning records from this offset, allowing for pagination through the dataset.
            "f": "json",                                                                                 # This line sets the 'f' parameter to "json", specifying that the response format should be JSON. It ensures that the data is returned in a structured format that can be easily parsed.
        }
        try:
            r = requests.get(url, params=params, timeout=30)                                             # The same as before, this line sends a GET request to the constructed URL with the specified parameters and a timeout of 30 seconds. It fetches a page of records from the dataset.
            r.raise_for_status()                                                                         # The same as before, this line raises an HTTPError if the request returned an unsuccessful status code. It ensures that any issues with the request are caught and handled appropriately.
        except requests.RequestException:
            logger.exception("HTTP request for schema failed")                                               # logger.exception logs at ERROR level and includes the traceback.
            raise
        dataset = r.json()                                                                               # The same as before, this line parses the JSON response from the API into a Python dictionary. The 'json()' method converts the JSON string into a Python data structure (in this case, a dictionary).
        if "error" in dataset:
            logger.error("ArcGIS returned an error for the schema: %s", dataset["error"])
            raise RuntimeError(f"There was an error fetching records: {dataset['error']}")               # This line checks if the 'error' key is present in the response data. If it is, it raises a RuntimeError with a message indicating that there was an error fetching records, along with the error details from the response.
        features = dataset.get("features", [])                                                           # This line retrieves the list of features (records) from the response data. It uses the 'get' method to access the 'features' key, defaulting to an empty list if the key is not present.
        logger.info("Layer %s: %d records fetched so far", layer_id, len(rows))
        rows.extend(f["attributes"] for f in features)                                                   # This line extends the 'rows' list with the attributes of each feature in the fetched page. It uses a list comprehension to extract the 'attributes' dictionary from each feature and adds them to the 'rows' list.

        if not dataset.get("exceededTransferLimit") or not features:                                     # This line checks if the 'exceededTransferLimit' key is not present or if there are no features returned in the current page. If either condition is true, it means that all records have been fetched, and the loop can be exited.
            break
        offset += len(features)                                                                          # This line increments the 'offset' by the number of features fetched in the current page. It prepares the offset for the next iteration of the loop, allowing the next page of records to be fetched.
    return pd.DataFrame(rows) 
    
def fetch_filtered_dataset_records(base_url, layer_id, where="1=1", page_size=1000):
    """ 
    This fetches the dataset records from the 
    ArcGIS REST API and returns them, paging past 
    the maximum record count if necessary. 
    """
    url = f"{base_url}/{layer_id}/query"                                                                 # This line constructs the URL for fetching records from a specific layer in the dataset. It appends the layer ID to the base URL and specifies the 'query' endpoint.  
    logger.info("Fetching schema from %s", url)
    rows, offset = [], 0                                                                                 # This line initializes an empty list 'rows' to store the fetched records and sets the 'offset' to 0 for pagination. The offset is used to keep track of how many records have been fetched so far.
    while True:
        params = {
            "where": where,                                                                              # This line sets the 'where' parameter, which is a common SQL trick to select all records. It effectively means "select all records" from the dataset.
            "outFields": "*",                                                                            # This line sets the 'outFields' parameter to "*", which means that all fields of the records should be returned in the response. It ensures that no data is omitted from the fetched records.
            "returnGeometry": "false",                                                                   # This line sets the 'returnGeometry' parameter to "false", indicating that the geometry of the features should not be included in the response. It is useful when only attribute data is needed.
            "resultOffset": offset,                                                                      # This line sets the 'resultOffset' parameter to the current value of 'offset'. It tells the API to start returning records from this offset, allowing for pagination through the dataset.
            "f": "json",                                                                                 # This line sets the 'f' parameter to "json", specifying that the response format should be JSON. It ensures that the data is returned in a structured format that can be easily parsed.
        }
        try:
            r = requests.get(url, params=params, timeout=30)                                             # The same as before, this line sends a GET request to the constructed URL with the specified parameters and a timeout of 30 seconds. It fetches a page of records from the dataset.
            r.raise_for_status()                                                                         # The same as before, this line raises an HTTPError if the request returned an unsuccessful status code. It ensures that any issues with the request are caught and handled appropriately.
        except requests.RequestException:
            logger.exception("HTTP request for schema failed")                                            # logger.exception logs at ERROR level and includes the traceback.
            raise                                                                                         # The same as before, this line parses the JSON response from the API into a Python dictionary. The 'json()' method converts the JSON string into a Python data structure (in this case, a dictionary).
        dataset = r.json()
        if "error" in dataset:
            logger.error("ArcGIS returned an error for the schema: %s", dataset["error"])
            raise RuntimeError(f"There was an error fetching records: {dataset['error']}")               # This line checks if the 'error' key is present in the response data. If it is, it raises a RuntimeError with a message indicating that there was an error fetching records, along with the error details from the response.
        features = dataset.get("features", [])                                                           # This line retrieves the list of features (records) from the response data. It uses the 'get' method to access the 'features' key, defaulting to an empty list if the key is not present.
        rows.extend(f["attributes"] for f in features)                                                   # This line extends the 'rows' list with the attributes of each feature in the fetched page. It uses a list comprehension to extract the 'attributes' dictionary from each feature and adds them to the 'rows' list.
        logger.info("Layer %s: %d records fetched so far", layer_id, len(rows))
        if not dataset.get("exceededTransferLimit") or not features:                                     # This line checks if the 'exceededTransferLimit' key is not present or if there are no features returned in the current page. If either condition is true, it means that all records have been fetched, and the loop can be exited.
            break
        offset += len(features)                                                                          # This line increments the 'offset' by the number of features fetched in the current page. It prepares the offset for the next iteration of the loop, allowing the next page of records to be fetched.
    return pd.DataFrame(rows)                                                                            # This line converts the list of fetched records (rows) into a pandas DataFrame and returns it. The DataFrame provides a convenient tabular structure for further analysis and manipulation of the dataset records.

if __name__ == "__main__":
    for item in fetch_dataset_schema(base_url):                                                          # This line calls the 'fetch_dataset_schema' function with the 'base_url' and iterates over each item (layer or table) in the returned list. It allows for processing each layer or table in the dataset schema.
        layer_id, layer_name = item["id"], item["name"]                                                  # This line extracts the 'id' and 'name' of the current layer or table from the item dictionary. The 'layer_id' is used to fetch records for that specific layer, and the 'layer_name' is used for display purposes.
        print(f"Fetching records for layer '{layer_name}' (ID: {layer_id})...")                          # This line prints a message indicating that records are being fetched for the current layer or table, including its name and ID. It provides feedback to the user about the progress of the data fetching process.
        for field in item.get('fields',[]):                                                              # This line iterates over the list of fields in the current layer or table. It uses the 'get' method to access the 'fields' key, defaulting to an empty list if the key is not present. Each field contains metadata about the attributes of the records in the layer or table.
            print(f"  Field: {field['name']} ({field['type']})")                                         # This line prints the name and type of each field in the current layer or table. It provides information about the structure of the data, including the names of the attributes and their corresponding data types.
        #df = fetch_dataset_records(base_url, layer_id)                                                   # This line calls the 'fetch_dataset_records' function with the 'base_url' and the current 'layer_id' to fetch all records for that specific layer or table. The returned DataFrame is stored in the variable 'df'.
        #output = raw_dir /f"{layer_id}_{layer_name.replace(' ', '_')}.csv"                               # This line constructs the output filename for the CSV file by combining the 'layer_id' and 'layer_name', replacing spaces in the layer name with underscores. It ensures that the filename is valid and descriptive.
        #df.to_csv(output, index=False)                                                                   # This line saves the fetched records DataFrame 'df' to a CSV file with the constructed filename 'output'. The 'index=False' argument ensures that the DataFrame index is not included in the CSV file.
        #print(f"Saved {len(df)} records to '{output}'")                                                  # This line prints a message indicating that the records have been successfully saved to the specified CSV file, along with the number of records saved. It provides feedback to the user about the completion of the data fetching and saving process.
        where_clause="C3_Complaint_Type = 'No Power'"
        df2 = fetch_filtered_dataset_records(base_url, layer_id, where=where_clause)
        logger.info("Layer %s: %s records downloaded", layer_id, f"{len(df2):,}")
