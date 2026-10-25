"""Core data models for HelpCircuit (dynamic, Discord-based scheduling)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Session states
COLLECTING = "COLLECTING"
NEGOTIATING = "NEGOTIATING"
AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
CONFIRMED = "CONFIRMED"
NO_SOLUTION = "NO_SOLUTION"
TERMINAL = {CONFIRMED, NO_SOLUTION}


@dataclass
class Constraint:
    kind: str            # "hard" | "soft"
    days: list           # subset of WEEKDAYS
    start: str           # "HH:MM" inclusive
    end: str             # "HH:MM" exclusive
    note: str = ""       # PRIVATE label (e.g. "class"); never shared to the group


@dataclass
class ConstraintSet:
    hard: list = field(default_factory=list)
    soft: list = field(default_factory=list)

    def summary(self) -> str:
        """Owner-facing (DM-only) human-readable summary."""
        def fmt(cs):
            return "; ".join(
                f"{'/'.join(c.days)} {c.start}-{c.end}" + (f" ({c.note})" if c.note else "")
                for c in cs
            ) or "none"
        return f"Hard (never schedule over): {fmt(self.hard)}\nSoft (prefer not): {fmt(self.soft)}"


@dataclass
class Student:
    discord_user_id: int
    display_name: str
    constraints: ConstraintSet = field(default_factory=ConstraintSet)


@dataclass(frozen=True)
class Slot:
    date: str            # "YYYY-MM-DD"
    hour: int            # start hour of a 1-hour block

    @property
    def key(self):
        return (self.date, self.hour)

    def label(self) -> str:
        d = datetime.strptime(self.date, "%Y-%m-%d")
        hour12 = self.hour % 12 or 12
        ampm = "AM" if self.hour < 12 else "PM"
        return f"{d.strftime('%a %b %d')}, {hour12}:00 {ampm}"


@dataclass
class SchedulingSession:
    id: str
    channel_id: int
    requester_id: int
    participant_ids: list
    window: str
    grid: list                                  # list[Slot]
    state: str = COLLECTING
    excluded: set = field(default_factory=set)  # set of Slot.key tuples
    selected: Optional[Slot] = None
    confirmations: dict = field(default_factory=dict)   # user_id -> True/False/None
    pending_confirm: set = field(default_factory=set)   # user_ids still to answer
    notified_for: Optional[tuple] = None        # Slot.key we've already DM'd about
    stats: dict = field(default_factory=dict)   # ruled_out_hard, soft_hits, etc.
    log: list = field(default_factory=list)     # sanitized event strings
