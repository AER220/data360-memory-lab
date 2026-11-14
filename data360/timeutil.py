# Small time helpers. Memory depends heavily on time (recency, supersede, forgetting), so I keep all
# date handling in one place.
from __future__ import annotations

from datetime import datetime, timezone


# I turn every timestamp (text, datetime or nothing) into a timezone-aware datetime, so comparing
# dates never mixes naive and aware times.
def parse(ts: str | datetime | None) -> datetime:
    # An empty timestamp means 'right now'.
    if ts is None or ts == "":
        return now()
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    # Python's fromisoformat does not accept a trailing Z on older versions, so I swap it for +00:00.
    d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# The current time in the machine's local zone, still timezone-aware.
def now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


# I store times as ISO text to the second, which sorts correctly as plain strings in SQLite.
def iso(d: datetime) -> str:
    return parse(d).isoformat(timespec="seconds")


# Recency and forgetting both work in days, so I convert the difference into fractional days.
def days_between(a, b) -> float:
    return (parse(b) - parse(a)).total_seconds() / 86400.0
