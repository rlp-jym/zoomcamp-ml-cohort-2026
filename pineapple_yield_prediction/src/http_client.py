"""Small HTTP helper with retries, provenance recording, and atomic writes."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

USER_AGENT = (
    "pineapple-yield-forecast/0.1 "
    "(educational research; PSA OpenSTAT API)"
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def display_path(path: Path) -> str:
    """Return a repo-relative path when possible, for portable provenance."""
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    """Write text byte-for-byte (no newline translation)."""
    ensure_parent(path)
    path.write_text(text, encoding="utf-8", newline="")


def write_json(path: Path, obj: Any) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="",
    )


def request(
    method: str,
    url: str,
    *,
    timeout: int = 90,
    retries: int = 5,
    backoff: float = 2.0,
    **kwargs: Any,
) -> requests.Response:
    """HTTP request with retry/backoff on transient failures."""
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("User-Agent", USER_AGENT)

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
            if resp.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"HTTP {resp.status_code} from {url}")
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001 - intentional retry wrapper
            last_exc = exc
            if attempt == retries - 1:
                break
            time.sleep(backoff * (2 ** attempt))

    assert last_exc is not None
    raise last_exc


def record_provenance(
    prov_dir: Path,
    name: str,
    *,
    url: str,
    method: str,
    request_body: Any = None,
    response: requests.Response | None = None,
    file_path: Path | None = None,
    extra: dict | None = None,
) -> dict:
    """Persist a provenance record for one artifact."""
    record: dict[str, Any] = {
        "artifact": name,
        "url": url,
        "method": method,
        "request_body": request_body,
        "request_body_sha256": (
            sha256_text(json.dumps(request_body, sort_keys=True, default=str))
            if request_body is not None
            else None
        ),
        "retrieved_at_utc": utc_now_iso(),
        "status_code": response.status_code if response is not None else None,
        "content_type": response.headers.get("Content-Type") if response is not None else None,
        "bytes": len(response.content) if response is not None else None,
    }
    if file_path is not None and file_path.exists():
        record["file"] = display_path(file_path)
        record["file_sha256"] = sha256_bytes(file_path.read_bytes())
    if extra:
        record.update(extra)
    write_json(prov_dir / f"{name}.json", record)
    return record
