import os, sys, argparse, logging                                                                    
from code import challenge_part_1, challenge_part_2
from pathlib import Path

base_url = "https://services6.arcgis.com/nyYfO9SxHU2ChQd9/ArcGIS/rest/services/Service_Requests_2023_until_20_May_2026/FeatureServer"
raw_dir = Path(__file__).resolve().parent / "data" / "raw"                                                  # This line defines the path to the directory where raw data will be stored. It uses the 'Path' class from the 'pathlib' module to construct the path relative to the current script's location. The 'resolve()' method ensures that the path is absolute, and 'parent.parent' navigates up two levels in the directory structure to reach the desired location. The final path points to a "data/raw" directory, which is intended for storing raw data files fetched from the ArcGIS REST API.
raw_dir.mkdir(parents=True, exist_ok=True)                                                                  # This line creates the directory specified by 'raw_dir' if it does not already exist. The 'parents=True' argument allows for the creation of any necessary parent directories, and 'exist_ok=True' prevents an error from being raised if the directory already exists. This ensures that the directory structure is in place for storing raw data files.
log_dir = Path(__file__).resolve().parent / "logs"                                                          # This line defines the path to the directory where log files will be stored. It uses the 'Path' class from the 'pathlib' module to construct the path relative to the current script's location. The 'resolve()' method ensures that the path is absolute, and 'parent.parent' navigates up two levels in the directory structure to reach the desired location. The final path points to a "logs" directory, which is intended for storing log files generated during the execution of the pipeline.

def logging_setup():
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f"{log_dir}/pipeline.log", encoding="utf-8"),
        ],
    )

def main(argv: list[str] | None = None) -> int:                                                                                 # This function runs the whole C3 'No Power' pipeline: extract -> transform -> validate.
    parser = argparse.ArgumentParser(description="Run the whole C3 'No Power' pipeline: extract -> transform -> validate.")     # This function takes an optional list of command-line arguments (argv) and returns an integer exit code.
    parser.add_argument(                                                                                                        # This function sets up an argument parser to handle command-line arguments. It adds a "--refresh" argument that, when specified, will force the pipeline to re-download data from the API even if a raw extract already exists.
        "--refresh", action="store_true",
        help="re-download from the API even if a raw extract already exists",
    )
    args = parser.parse_args(argv)                                                                                              # This function parses the command-line arguments and stores them in the args variable.
    logger = logging.getLogger("run_pipeline")                                                                                  # This function creates a logger object named "run_pipeline" that can be used to log messages throughout the pipeline.
    
    extract_file = raw_dir / "0_Service_Requests_2023_until_20_May_2026.csv"                                                    # This line defines the absolute path of the raw extract so the check works no matter which folder the script is run from.

    try:
        if args.refresh or not extract_file.is_file():                                                                          # This checks if the "--refresh" argument was specified or if the raw extract file does not exist. If either is true, the data is downloaded from the API.
            challenge_part_1.fetch_dataset_metadata(base_url, raw_dir)                                                          # This calls fetch_dataset_metadata() from challenge_part_1 to download the 'No Power' records and save them into raw_dir.
        else:
            logger.info("Using existing extract %s (pass --refresh to re-download)", extract_file)                              # This logs that the existing raw extract will be used instead of downloading new data.
        challenge_part_2.transform(extract_file)                                                                                # This always runs the transform step on the raw extract, whether it was just downloaded or already existed.
    except Exception:
        logger.exception("Pipeline failed")                                                                                     # This logs the exception (with traceback) if any step fails.
        return 1                                                                                                                # This returns an exit code of 1 to indicate that the pipeline failed.
    logger.info("Pipeline finished successfully")
    return 0                                                                                                                    # This returns an exit code of 0 to indicate success.

if __name__ == "__main__":
    logging_setup()                                                                                                             # Logging must be configured before main() runs, otherwise all INFO messages are discarded.
    sys.exit(main())