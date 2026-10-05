"""Default IANA time zone per AWS region, used for schedule recurrences (INTERVENTIONS `schedule`).

Configuration, not a coefficient: it only decides the `time_zone` written into a schedule.
"""

from __future__ import annotations

REGION_TIME_ZONES: dict[str, str] = {
    "us-east-1": "America/New_York",
    "us-east-2": "America/New_York",
    "us-west-1": "America/Los_Angeles",
    "us-west-2": "America/Los_Angeles",
    "ca-central-1": "America/Toronto",
    "eu-west-1": "Europe/Dublin",
    "eu-west-2": "Europe/London",
    "eu-west-3": "Europe/Paris",
    "eu-central-1": "Europe/Berlin",
    "eu-north-1": "Europe/Stockholm",
    "ap-south-1": "Asia/Kolkata",
    "ap-southeast-1": "Asia/Singapore",
    "ap-northeast-1": "Asia/Tokyo",
}


def region_time_zone(region: str) -> str:
    try:
        return REGION_TIME_ZONES[region]
    except KeyError as exc:
        raise KeyError(f"no default time zone for region {region!r}") from exc


def provider_alias(region: str) -> str:
    return region.replace("-", "_")
