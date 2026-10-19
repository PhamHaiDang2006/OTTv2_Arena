from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

SAIGON = ZoneInfo('Asia/Saigon')


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime | None) -> str | None:
    """Wire timestamps are UTC with a literal Z (contract pattern 'Z$')."""
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed.astimezone(UTC)


def saigon_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Start and end (UTC) of the Asia/Saigon calendar day containing `now`; quota resets at 00:00 local."""
    local = now.astimezone(SAIGON)
    start = datetime.combine(local.date(), time(0), tzinfo=SAIGON)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)
