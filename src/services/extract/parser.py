"""
HTML / JSON Parser Module.
Extracts raw fixture payloads from FotMob HTML pageProps without premature transformation.
"""

import json
from typing import Any, Dict, List
from bs4 import BeautifulSoup


def _extract_next_data(html: str) -> Dict[str, Any]:
    """
    Extract and decode the __NEXT_DATA__ JSON script tag from HTML page.

    Args:
        html: Raw HTML string.

    Returns:
        Decoded pageProps dictionary.

    Raises:
        ValueError: If __NEXT_DATA__ script tag cannot be found.
    """
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        raise ValueError("Could not find __NEXT_DATA__ script tag in HTML.")

    payload = json.loads(script_tag.string)
    return payload.get("props", {}).get("pageProps", {})


def parse_items(html: str) -> List[Dict[str, Any]]:
    """
    Extract raw fixture/match records from HTML.
    Keeps original raw provider fields intact for downstream transformation.

    Args:
        html: Raw HTML content of the fixtures page.

    Returns:
        List of raw match dictionaries from the provider payload.
    """
    page_props = _extract_next_data(html)
    fixtures_data = page_props.get("fixtures", {})
    all_matches = fixtures_data.get("allMatches", [])

    return all_matches
