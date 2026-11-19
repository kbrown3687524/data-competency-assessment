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
            logging.FileHandler(f"{raw_dir}/logs/pipeline.log", encoding="utf-8"),
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
    
    try:
        if args.refresh or not os.path.isfile("data/raw/0_Service_Requests_2023_until_20_May_2026.csv"):                        # This function checks if the "--refresh" argument was specified or if the raw extract file does not exist. If either condition is true, it calls the pipeline.extract.extract() function to download data from the API.
            challenge_part_1.fetch_dataset_metadata(base_url, "layer_id")
        else:
            challenge_part_2.transform("data/raw/0_Service_Requests_2023_until_20_May_2026.csv")                                    # This function calls the fetch_and_save_data() function from the challenge_part_1 module to download and save data from the API.                                                                                               
            logger.info("Using existing extract data/raw/0_Service_Requests_2023_until_20_May_2026.csv (pass --refresh to re-download)")  # This function logs a message indicating that the existing raw extract file will be used instead of downloading new data.    
    except Exception:
        logger.exception("Pipeline failed")                                                                                     # This function logs an exception message if any error
    return 1                                                                                                                    # This function returns an exit code of 1 to indicate that the pipeline failed

if __name__ == "__main__":
    sys.exit(main())