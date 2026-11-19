"""Run the whole C3 'No Power' pipeline: extract -> transform -> validate.

Usage (from the ai_solution/ folder):
    python run_pipeline.py              # reuse data/raw if present, else extract
    python run_pipeline.py --refresh    # force a fresh extract from the API
"""

import argparse
import logging
import sys

from pipeline import config, extract, transform, validate


def configure_logging() -> None:
    """Log to the console and to logs/pipeline.log."""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.LOG_DIR / "pipeline.log", encoding="utf-8"),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--refresh", action="store_true",
        help="re-download from the API even if a raw extract already exists",
    )
    args = parser.parse_args(argv)
    configure_logging()
    logger = logging.getLogger("run_pipeline")

    try:
        if args.refresh or not config.RAW_RECORDS_FILE.exists():
            extract.extract()
        else:
            logger.info("Using existing extract %s (pass --refresh to re-download)",
                        config.RAW_RECORDS_FILE)
        counts = transform.transform()
        report = validate.validate(counts)
    except Exception:
        logger.exception("Pipeline failed")
        return 1

    if not report["all_passed"]:
        logger.error("One or more validation checks failed - see %s", config.VALIDATION_FILE)
        return 1
    logger.info("Pipeline finished: all validation checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
