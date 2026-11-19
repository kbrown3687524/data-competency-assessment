#!/usr/bin/env python3
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
import re
import logging

logger = logging.basicConfig(level = logging.INFO,                                                                  # This line sets up the basic configuration for logging. It specifies the logging level as INFO, which means that messages with a severity level of INFO and above will be logged.
    format = "%(asctime)s %(levelname)-8s %(message)s",                                                             # This line defines the format of the log messages. It includes the timestamp, the log level, and the actual log message. The timestamp is formatted to show the date and time.
    datefmt = "%Y-%m-%d %H-%M-%S",                                                                                  # This line specifies the format of the timestamp in the log messages. It shows the year, month, day, hour, minute, and second.
    handlers=[                                                                                                      
        logging.FileHandler("arcgis_fetch.log", encoding="utf-8"),                                                  # This line adds a file handler to the logging configuration. It specifies that log messages will be written to a file named "arcgis_fetch.log" with UTF-8 encoding. This allows for persistent logging of messages to a file.
        logging.StreamHandler()                                                                                     # This line adds a stream handler to the logging configuration. It specifies that log messages will also be output to the console (standard output). This allows for real-time monitoring of log messages while the program is running.
    ],
    )
logger = logging.getLogger("arcgis_fetch")

def read_data(file_path):                                                                                           # This line defines a function named 'read_data' that takes a single parameter 'file_path'. The purpose of this function is to read CSV data from the specified file path and return it as a pandas DataFrame.
    """
    Reads the CSV data from the given file path and returns a pandas DataFrame.
    
    Parameters:
        file_path (str): The path to the CSV file.
    
    Returns:
        pandas.DataFrame: The data from the CSV file.
    """
    return pd.read_csv(file_path)

def aggregate_reports_by_suburb_data(df):                                                                            # This line defines a function named 'aggregate_reports_by_suburb_data' that takes a single parameter 'df', which is expected to be a pandas DataFrame. The purpose of this function is to aggregate the number of service requests by suburb and return a new DataFrame with the counts.
    """
    Aggregates the number of service requests by suburb and returns a DataFrame with the counts.
    """
    counts = df.groupby(df['Suburb'].fillna('Unknown')).size().reset_index(name='count')                                                   # This line groups the input DataFrame 'df' by the 'Suburb' column and calculates the size of each group (i.e., the number of records for each suburb). The result is a new DataFrame with two columns: 'Suburb' and 'count', where 'count' represents the number of service requests for each suburb. The 'reset_index' method is used to convert the groupby object back into a DataFrame, and the 'name' parameter specifies the name of the new column that will hold the counts.
    total = counts['count'].sum()                                                                                    # This line calculates the total number of service requests by summing the 'count' column of the 'counts' DataFrame. The result is stored in the variable 'total'.
    logging.info("Total number of service requests: %d", total)                                                      # This line logs an informational message that displays the total number of service requests calculated in the previous line. The '%d' is a placeholder for the integer value of 'total', which is passed as an argument to the logging function.
    return total                                                                                                    # This line returns the 'counts' DataFrame, which contains the

def split_records_by_suburb(df):
    """
    Splits the DataFrame into a dictionary of DataFrames, each containing records for a specific suburb.
    
    Parameters:
        df (pandas.DataFrame): The input DataFrame containing service request records.
    """
    output_dir = Path(__file__).resolve().parent.parent / "data" / "raw" / "suburb_records"                            # This line defines the output directory where the split records will be saved. It constructs the path by navigating to the parent directory of the current file, then into the "data/raw/suburb_records" directory. The resulting path is stored in the variable 'output_dir'.          
    output_dir.mkdir(parents=True, exist_ok=True)                                                                      # This line creates the output directory specified by 'output_dir'. The 'parents=True' argument allows the creation of any necessary parent directories, and 'exist_ok=True' prevents an error if the directory already exists. This ensures that the output directory is ready for saving the split records.

    for suburb, group in df.groupby(df['Suburb'].fillna('Unknown')):                                                   # This line iterates over the groups of the DataFrame 'df' that are created by grouping the records based on the 'Suburb' column. The 'fillna('Unknown')' method is used to replace any missing values in the 'Suburb' column with the string 'Unknown'. For each unique suburb, the loop provides the suburb name and the corresponding group of records as a DataFrame.
        safe_name = re.sub(r'[^\w\-]', '', suburb).strip() or 'Unknown'                                                # This line creates a safe filename for the suburb by removing any characters that are not alphanumeric or hyphens using a regular expression. The 'strip()' method removes any leading or trailing whitespace, and if the resulting name is empty, it defaults to 'Unknown'. The safe filename is stored in the variable 'safe_name'.
        group.to_csv(output_dir / f"{safe_name}.csv", index=False)                                                     # This line saves the group of records for the current suburb to a CSV file. The filename is constructed using the 'safe_name' variable, and the file is saved in the 'output_dir' directory. The 'index=False' argument ensures that the DataFrame index is not included in the CSV file. This allows for easy access to records for each suburb in separate files.

    logger.info("Records split by suburb and saved to %s", output_dir)


def transform(file_path):
    """
    Transforms the data by aggregating reports by suburb and splitting records by suburb.
    """
    # Read the data
    df = read_data(file_path)
    suburb_counts = aggregate_reports_by_suburb_data(df)
    split_records_by_suburb(df)