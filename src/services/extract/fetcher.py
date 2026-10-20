"""
HTTP Fetcher Module.
Handles HTTP requests, custom headers, timeout, and exponential backoff retry.
"""

import time
import requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_page(url: str, retries: int = 3, timeout: int = 10, delay: float = 1.0) -> str:
    """
    Fetch raw HTML from a target URL with retry mechanism and rate-limit delay.

    Args:
        url: The web URL to request.
        retries: Number of retry attempts upon request failure.
        timeout: HTTP request timeout in seconds.
        delay: Base pause time (in seconds) between retries and requests.

    Returns:
        Raw HTML response content as a string.

    Raises:
        RuntimeError: If all retry attempts fail.
    """
    time.sleep(delay)

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            if attempt == retries:
                raise RuntimeError(
                    f"Failed to fetch {url} after {retries} attempts: {exc}"
                ) from exc

            backoff_delay = delay * (2 ** attempt)
            time.sleep(backoff_delay)
