"""Thin, resilient client for an ArcGIS feature service REST endpoint."""

import logging
import time
from typing import Any

import requests

from pipeline import config

logger = logging.getLogger(__name__)


class ArcGISError(RuntimeError):
    """Raised when the API keeps failing or returns an unusable response."""


def build_session() -> requests.Session:
    """Return a session (reuses TCP connections across the many page requests)."""
    session = requests.Session()
    session.headers.update({"User-Agent": "c3-no-power-pipeline/1.0"})
    return session


def get_json(
    session: requests.Session, url: str, params: dict[str, Any]
) -> dict[str, Any]:
    """GET ``url`` and return the decoded JSON body, retrying on failure.

    ArcGIS often reports errors with HTTP 200 and an ``{"error": {...}}`` body,
    so the payload is checked as well as the status code. Network errors,
    timeouts, retryable HTTP statuses (429/5xx), invalid JSON and ArcGIS error
    payloads are retried with exponential back-off. Other HTTP errors (e.g. 400
    or 404, which retrying cannot fix) fail immediately.
    """
    params = {**params, "f": "json"}
    last_error: Exception | None = None

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            response = session.get(
                url, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS
            )
            status = response.status_code
            if status >= 400 and status not in config.RETRYABLE_STATUS_CODES:
                logger.error("Non-retryable HTTP %s from %s", status, url)
                raise ArcGISError(f"HTTP {status} from {url}")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"Expected a JSON object, got {type(payload).__name__}")
            if "error" in payload:
                raise ValueError(f"ArcGIS error payload: {payload['error']}")
            return payload
        except ArcGISError:
            raise
        except (requests.RequestException, ValueError) as exc:
            # ValueError also covers invalid JSON (requests' JSONDecodeError).
            last_error = exc

        if attempt < config.MAX_RETRIES:
            wait = config.BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
            logger.warning(
                "Request failed (attempt %d/%d): %s. Retrying in %ds.",
                attempt, config.MAX_RETRIES, last_error, wait,
            )
            time.sleep(wait)

    logger.error("Giving up on %s after %d attempts", url, config.MAX_RETRIES)
    raise ArcGISError(f"Request to {url} failed: {last_error}") from last_error
