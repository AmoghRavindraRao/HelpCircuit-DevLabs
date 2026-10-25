"""Slot grid generation and time-window resolution.

Discrete 1-hour blocks between DAY_START and DAY_END in a single fixed timezone
(America/Phoenix, UTC-7, no DST — a fixed offset avoids an IANA tzdata dependency
on Windows). A bounded window keyword resolves to a finite ordered grid.
"""

from datetime import datetime, timedelta, timezone

from models import Slot, WEEKDAYS

PHOENIX = timezone(timedelta(hours=-7))  # fixed offset, no DST
DAY_START = 8       # first block starts 08:00
DAY_END = 20        # last block starts 20:00 (ends 21:00)

WINDOWS = ("today", "tomorrow", "3days", "thisweek", "7days")
_DEFAULT_WINDOW = "7days"


def now():
    return datetime.now(PHOENIX)


def resolve_window(text) -> str:
    """Map a keyword or free-text window phrase to a known window keyword."""
    t = (text or "").lower().strip()
    if not t:
        return _DEFAULT_WINDOW
    for w in WINDOWS:
        if w in t:
            return w
    if "today" in t or "tonight" in t:
        return "today"
    if "tomorrow" in t:
        return "tomorrow"
    if "week" in t or "friday" in t or "thu" in t or "wed" in t:
        return "thisweek"
    return _DEFAULT_WINDOW


def _date_range(window, ref):
    today = ref.date()
    if window == "today":
        return [today]
    if window == "tomorrow":
        return [today + timedelta(days=1)]
    if window == "3days":
        return [today + timedelta(days=i) for i in range(3)]
    if window == "thisweek":
        days_to_sunday = 6 - today.weekday()  # Monday=0 .. Sunday=6
        return [today + timedelta(days=i) for i in range(days_to_sunday + 1)]
    return [today + timedelta(days=i) for i in range(7)]  # 7days / default


def build_grid(window, ref=None):
    """Return the ordered list of candidate Slots for the window."""
    ref = ref or now()
    grid = []
    for d in _date_range(window, ref):
        for hour in range(DAY_START, DAY_END + 1):
            # Skip hours already past on the first day.
            if d == ref.date() and hour <= ref.hour:
                continue
            grid.append(Slot(d.isoformat(), hour))
    return grid


def slot_weekday(slot) -> str:
    return WEEKDAYS[datetime.strptime(slot.date, "%Y-%m-%d").weekday()]
