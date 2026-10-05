"""UK Carbon Intensity API (regional, London) -> snapshot tier (METHODOLOGY §2, ADR-0007).

Public, keyless, CC BY 4.0 (© National Energy System Operator). Network is used only by the human-
approved `emissiongate grid-snapshot` command; runs read the committed snapshot file.
Regional endpoints publish modelled half-hourly values (`intensity.forecast`); there are no regional
actuals, so the 7-day history is the API's regional estimate. The snapshot says so.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx

API = "https://api.carbonintensity.org.uk"
LONDON_SHORTNAME = "London"
TIMEOUT_S = 5.0
RETRIES = 2


class GridApiError(RuntimeError):
    pass


def _get(client: httpx.Client, path: str) -> dict:
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            resp = client.get(API + path, timeout=TIMEOUT_S, headers={"Accept": "application/json"})
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
            time.sleep(1.0 * (attempt + 1))
    raise GridApiError(f"GET {path} failed: {last}")


def _fmt(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%MZ")


def find_region_id(client: httpx.Client, shortname: str = LONDON_SHORTNAME) -> int:
    doc = _get(client, "/regional")
    for region in doc["data"][0]["regions"]:
        if region.get("shortname") == shortname:
            return int(region["regionid"])
    raise GridApiError(f"region {shortname!r} not found in /regional")


def _slots(doc: dict) -> list[dict]:
    data = doc["data"]
    rows = data["data"] if isinstance(data, dict) else data[0]["data"]
    out = []
    for row in rows:
        value = row["intensity"].get("forecast")
        if value is None:
            continue
        start = datetime.strptime(row["from"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
        out.append({"from": start.isoformat(), "g_per_kwh": float(value)})
    return out


def snapshot(now: datetime, client: httpx.Client | None = None) -> dict:
    """7 days of half-hourly history + 48 h forecast for London, as a snapshot document."""
    own = client is None
    client = client or httpx.Client()
    try:
        region_id = find_region_id(client)
        end = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
        start = end - timedelta(days=7)
        history = _slots(
            _get(client, f"/regional/intensity/{_fmt(start)}/{_fmt(end)}/regionid/{region_id}")
        )
        forecast = _slots(
            _get(client, f"/regional/intensity/{_fmt(end)}/fw48h/regionid/{region_id}")
        )
    finally:
        if own:
            client.close()
    seen: set[str] = set()
    history = [h for h in history if not (h["from"] in seen or seen.add(h["from"]))]
    history = [h for h in history if h["from"] < end.isoformat()]
    return {
        "region": "eu-west-2",
        "source": f"uk-carbon-intensity-api:regional/regionid/{region_id} ({LONDON_SHORTNAME})",
        "retrieved_at": now.isoformat(),
        "note": "Regional half-hourly values are modelled estimates (no regional actuals).",
        "licence": "CC BY 4.0",
        "attribution": "© National Energy System Operator, Carbon Intensity API "
        "(https://carbonintensity.org.uk)",
        "synthetic": False,
        "history": history,
        "forecast": forecast,
    }
