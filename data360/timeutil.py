from __future__ import annotations

from datetime import datetime, timezone


def parse(ts: str | datetime | None) -> datetime:
    if ts is None or ts == "":
        return now()
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def iso(d: datetime) -> str:
    return parse(d).isoformat(timespec="seconds")


def days_between(a, b) -> float:
    return (parse(b) - parse(a)).total_seconds() / 86400.0
