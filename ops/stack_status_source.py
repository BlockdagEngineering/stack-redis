#!/usr/bin/env python3
"""Shared status source for local BlockDAG stack agents.

This module keeps status acquisition behind one interface. Repair actors should
consume stack status here instead of each choosing between dashboard HTTP,
status-sampler reuse, and direct in-process collection on their own.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pool_ops import collect_status_cached


DEFAULT_STATUS_URL = "http://127.0.0.1:8088/api/status"
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("BDAG_STATUS_SOURCE_TIMEOUT", "20"))
REPAIR_STATUS_REQUIRED_KEYS = ("failures", "warnings", "overall")


class StackStatusUnavailable(RuntimeError):
    """Raised when every status adapter fails."""


def _env_urls() -> list[str]:
    raw = (
        os.environ.get("BDAG_STATUS_SOURCE_URLS")
        or os.environ.get("BDAG_STATUS_SOURCE_URL")
        or os.environ.get("BDAG_DASHBOARD_STATUS_URL")
        or os.environ.get("BDAG_COLLECTOR_STATUS_URL")
        or DEFAULT_STATUS_URL
    )
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def _fixture_payload() -> dict[str, Any] | None:
    raw = os.environ.get("BDAG_STATUS_SOURCE_FIXTURE") or os.environ.get("BDAG_STATUS_SOURCE_FIXTURE_FILE")
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    try:
        if candidate.exists():
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        else:
            payload = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        raise StackStatusUnavailable(f"fixture status payload is unreadable: {raw}")
    if not isinstance(payload, dict):
        raise StackStatusUnavailable("fixture status payload must be a JSON object")
    return payload


def _annotate(payload: dict[str, Any], source: str, errors: list[str]) -> dict[str, Any]:
    result = dict(payload)
    result["stack_status_source"] = {
        "source": source,
        "errors": list(errors),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    return result


def fetch_http_status(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read(8_000_000).decode("utf-8", "replace"))
    if not isinstance(payload, dict):
        raise StackStatusUnavailable(f"status API returned non-object payload from {url}")
    return payload


def validate_repair_status_payload(payload: dict[str, Any], source: str) -> None:
    """Reject compact dashboard payloads that are not safe for repair actors."""
    missing: list[str] = []
    if not isinstance(payload.get("failures"), list):
        missing.append("failures")
    if not isinstance(payload.get("warnings"), list):
        missing.append("warnings")
    if not str(payload.get("overall") or "").strip():
        missing.append("overall")
    if missing:
        raise StackStatusUnavailable(
            f"status payload from {source} is missing repair schema key(s): {', '.join(missing)}"
        )


def normalize_repair_status_payload(payload: dict[str, Any], source: str) -> dict[str, Any]:
    """Accept Redis live dashboard payloads that carry repair-grade ASIC data.

    Older dashboard payloads were too compact for repair actors and must still
    fall back to in-process collection. Redis live status includes full
    miner_health/pool health, but not the legacy failures/warnings keys.
    """
    if isinstance(payload.get("failures"), list) and isinstance(payload.get("warnings"), list):
        return payload
    if str(payload.get("source") or "") != "redis-live":
        return payload
    if not isinstance(payload.get("miner_health"), dict):
        return payload
    if not str(payload.get("overall") or "").strip():
        return payload
    result = dict(payload)
    result.setdefault("failures", [])
    result.setdefault("warnings", result.get("degraded_reasons") if isinstance(result.get("degraded_reasons"), list) else [])
    if not isinstance(result.get("failures"), list):
        result["failures"] = []
    if not isinstance(result.get("warnings"), list):
        result["warnings"] = []
    result["repair_schema_normalized_from"] = source
    return result


def collect_stack_status(
    *,
    include_logs: bool = True,
    max_age_seconds: float | None = None,
    collector_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    prefer_collector: bool = True,
) -> dict[str, Any]:
    """Return the best available stack status payload.

    Adapter order:
    1. Dashboard/status HTTP, unless the caller explicitly requests a live local sample
       with max_age_seconds <= 0.
    2. In-process collect_status_cached, which already reuses the status sampler
       and short shared status cache when they are fresh.
    """

    errors: list[str] = []
    force_live_local = max_age_seconds is not None and max_age_seconds <= 0

    fixture = _fixture_payload()
    if fixture is not None:
        return _annotate(fixture, "fixture", errors)

    if prefer_collector and not force_live_local:
        urls = [collector_url] if collector_url else _env_urls()
        for url in [item for item in urls if item]:
            try:
                payload = normalize_repair_status_payload(fetch_http_status(url, timeout=timeout), url)
                validate_repair_status_payload(payload, url)
                return _annotate(payload, "status-http", errors)
            except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, StackStatusUnavailable) as exc:
                errors.append(f"status API {url}: {exc}")

    try:
        return _annotate(
            collect_status_cached(include_logs=include_logs, max_age_seconds=max_age_seconds),
            "in-process",
            errors,
        )
    except Exception as exc:  # noqa: BLE001 - callers need a single status-source failure.
        errors.append(f"in-process collect_status_cached: {exc}")

    raise StackStatusUnavailable("; ".join(errors) or "stack status unavailable")
