from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import OfficialStatusSettings

log = logging.getLogger("monitor.official_status")

MAX_BODY_BYTES = 1024 * 1024
MAX_COMPONENTS = 40
MAX_INCIDENTS = 10
MAX_TEXT = 240
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

INDICATOR_STATUS = {
    "none": "operational",
    "minor": "degraded",
    "major": "outage",
    "critical": "outage",
}
COMPONENT_STATUSES = {
    "operational",
    "degraded_performance",
    "partial_outage",
    "major_outage",
    "under_maintenance",
}
INCIDENT_STATUSES = {"investigating", "identified", "monitoring", "resolved", "postmortem"}
IMPACTS = {"none", "minor", "major", "critical"}


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _epoch(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()


def unknown(
    settings: OfficialStatusSettings,
    fetched_at: float | None,
    description: str = "官方状态暂时无法获取",
) -> dict[str, Any]:
    return {
        "provider": "OpenAI",
        "status": "unknown",
        "indicator": None,
        "description": description,
        "page_updated_at": None,
        "fetched_at": fetched_at,
        "stale": True,
        "source_url": settings.page_url,
        "components": [],
        "incidents": [],
    }


def normalize(payload: Any, settings: OfficialStatusSettings, fetched_at: float) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return unknown(settings, fetched_at)
    page = payload.get("page")
    status = payload.get("status")
    if not isinstance(page, dict) or not isinstance(status, dict):
        return unknown(settings, fetched_at)
    page_updated_at = _epoch(page.get("updated_at"))
    if page_updated_at is None:
        return unknown(settings, fetched_at)
    indicator = status.get("indicator")
    normalized = INDICATOR_STATUS.get(indicator, "unknown")
    components = []
    raw_components = payload.get("components")
    if isinstance(raw_components, list):
        for item in raw_components[:MAX_COMPONENTS]:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            name = _text(item.get("name"))
            if not isinstance(item_id, str) or not ID_RE.fullmatch(item_id) or not name:
                continue
            component_status = item.get("status")
            components.append(
                {
                    "id": item_id,
                    "name": name,
                    "status": component_status if component_status in COMPONENT_STATUSES else "unknown",
                }
            )
    incidents = []
    raw_incidents = payload.get("incidents")
    if isinstance(raw_incidents, list):
        for item in raw_incidents:
            if len(incidents) >= MAX_INCIDENTS:
                break
            if not isinstance(item, dict):
                continue
            incident_id = item.get("id")
            name = _text(item.get("name"))
            if not isinstance(incident_id, str) or not ID_RE.fullmatch(incident_id) or not name:
                continue
            incident_status = item.get("status")
            impact = item.get("impact")
            if incident_status in {"resolved", "postmortem"}:
                continue
            incidents.append(
                {
                    "id": incident_id,
                    "name": name,
                    "status": incident_status if incident_status in INCIDENT_STATUSES else "unknown",
                    "impact": impact if impact in IMPACTS else "unknown",
                    "created_at": _epoch(item.get("created_at")),
                    "updated_at": _epoch(item.get("updated_at")),
                    "url": f"https://status.openai.com/incidents/{incident_id}",
                }
            )
    if indicator not in INDICATOR_STATUS:
        normalized = "unknown"
    return {
        "provider": "OpenAI",
        "status": normalized,
        "indicator": indicator if indicator in INDICATOR_STATUS else None,
        "description": _text(status.get("description")) or "官方状态待核对",
        "page_updated_at": page_updated_at,
        "fetched_at": fetched_at,
        "stale": False,
        "source_url": settings.page_url,
        "components": components,
        "incidents": incidents,
    }


def fetch(settings: OfficialStatusSettings, now: float, client_factory=httpx.Client) -> dict[str, Any] | None:
    if not settings.enabled:
        return None
    try:
        deadline = time.monotonic() + 5
        with client_factory(timeout=2, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", settings.url, headers={"Accept": "application/json"}) as response:
                if response.status_code != 200:
                    return unknown(settings, now)
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    return unknown(settings, now)
                body = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        return unknown(settings, now)
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        return unknown(settings, now)
                    body.extend(chunk)
        return normalize(json.loads(bytes(body)), settings, now)
    except Exception as exc:
        # A provider payload is an optional observer. It must never abort the
        # local collection cycle when its transport or schema changes.
        log.debug("Official status fetch unavailable (%s)", type(exc).__name__)
        return unknown(settings, now)
