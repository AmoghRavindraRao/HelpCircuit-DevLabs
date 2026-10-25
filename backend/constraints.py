"""Deterministic safety net: constraint checking and disclosure sanitization.

This module is authoritative. The LLM may parse constraints and phrase messages,
but whether a slot violates a hard/soft constraint, and whether a shared message
leaks private data, is decided here.
"""

import re

from slots import slot_weekday

# Public reasons are drawn only from this allowlist, so nothing private leaks.
PUBLIC_HARD_REASON = "has a scheduling conflict"
PUBLIC_SOFT_REASON = "prefers a different time"


def _to_min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _overlaps(constraint, slot):
    if slot_weekday(slot) not in constraint.days:
        return False
    cs, ce = _to_min(constraint.start), _to_min(constraint.end)
    bs, be = slot.hour * 60, (slot.hour + 1) * 60
    return cs < be and ce > bs


class ConstraintChecker:
    """The final authority on slot feasibility."""

    def violates_hard(self, student, slot) -> bool:
        return any(_overlaps(c, slot) for c in student.constraints.hard)

    def violates_soft(self, student, slot) -> bool:
        return any(_overlaps(c, slot) for c in student.constraints.soft)


class DisclosureGuard:
    """Removes private data from any text bound for the group channel."""

    def sanitize(self, text, students) -> str:
        if not text:
            return text
        out = text
        # Strip private constraint notes (e.g. "therapy", "class").
        for st in students:
            for c in list(st.constraints.hard) + list(st.constraints.soft):
                if c.note:
                    out = re.sub(re.escape(c.note), "[private]", out, flags=re.IGNORECASE)
        # Strip raw slot identifiers like 2026-10-28_14 and explicit clock times.
        out = re.sub(r"\d{4}-\d{2}-\d{2}[_ ]\d{1,2}", "[time]", out)
        out = re.sub(r"\b\d{1,2}:\d{2}\b", "[time]", out)
        return out
