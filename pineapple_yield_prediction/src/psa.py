"""PSA OpenSTAT PxWeb client: metadata discovery and CSV queries."""

from __future__ import annotations

from requests import Response

from .http_client import request


def fetch_metadata(api_base: str, table_path: str) -> tuple[dict, str, Response]:
    """Return (parsed metadata, raw response text, response)."""
    url = f"{api_base}/{table_path}"
    resp = request("GET", url)
    return resp.json(), resp.text, resp


def resolve_codes(meta: dict, dimension: str, wanted: list[str]) -> list[str]:
    """Map display labels or source codes to source codes for one dimension."""
    var = next((v for v in meta["variables"] if v["code"] == dimension), None)
    if var is None:
        raise KeyError(f"Dimension {dimension!r} not present in table")

    by_label = dict(zip(var["valueTexts"], var["values"]))
    valid_codes = set(var["values"])

    resolved: list[str] = []
    for item in wanted:
        if item in valid_codes:
            resolved.append(item)
        elif item in by_label:
            resolved.append(by_label[item])
        else:
            sample = ", ".join(var["valueTexts"][:8])
            raise KeyError(f"{item!r} not found in dimension {dimension!r}. Sample: {sample}")
    return resolved


def resolve_years(meta: dict, start: int, end: int) -> list[str]:
    """Return source codes for every Year value in [start, end]."""
    var = next((v for v in meta["variables"] if v["code"] == "Year"), None)
    if var is None:
        raise KeyError("No Year dimension in this table")

    out: list[str] = []
    for code, text in zip(var["values"], var["valueTexts"]):
        text = text.strip()
        if text.isdigit() and start <= int(text) <= end:
            out.append(code)
    if not out:
        raise ValueError(f"No Year values between {start} and {end}")
    return out


def build_query(meta: dict, selections: dict[str, list[str] | None]) -> dict:
    """Build a PxWeb POST body.

    ``selections`` maps dimension code -> list of source codes.
    A missing key (or ``None``) means "select all values".
    """
    query = []
    for var in meta["variables"]:
        code = var["code"]
        sel = selections.get(code)
        if sel is None:
            query.append({"code": code, "selection": {"filter": "all", "values": ["*"]}})
        else:
            if not sel:
                raise ValueError(f"Empty selection for dimension {code!r}")
            query.append({"code": code, "selection": {"filter": "item", "values": list(sel)}})

    return {"query": query, "response": {"format": "csv"}}


def fetch_table(api_base: str, table_path: str, query: dict) -> tuple[str, str, Response]:
    """POST a query and return (csv_text, url, response)."""
    url = f"{api_base}/{table_path}"
    resp = request("POST", url, json=query)
    return resp.text, url, resp
