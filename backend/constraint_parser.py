"""Natural-language constraint parsing via the LLM.

Converts a student's plain-language DM into a structured ConstraintSet and
classifies each item as hard (never violate) or soft (negotiable). All LLM output
is validated deterministically; malformed items are dropped.
"""

import store
from models import Constraint, ConstraintSet, WEEKDAYS

_DAY_ALIASES = {
    "monday": "mon", "mon": "mon",
    "tuesday": "tue", "tue": "tue", "tues": "tue",
    "wednesday": "wed", "wed": "wed",
    "thursday": "thu", "thu": "thu", "thurs": "thu",
    "friday": "fri", "fri": "fri",
    "saturday": "sat", "sat": "sat",
    "sunday": "sun", "sun": "sun",
}
_DAY_GROUPS = {
    "daily": WEEKDAYS, "everyday": WEEKDAYS, "every day": WEEKDAYS, "all": WEEKDAYS,
    "weekday": ["mon", "tue", "wed", "thu", "fri"], "weekdays": ["mon", "tue", "wed", "thu", "fri"],
    "weekend": ["sat", "sun"], "weekends": ["sat", "sun"],
}

SYSTEM_PROMPT = (
    "You convert a student's description of their schedule and preferences into "
    "structured scheduling constraints. Classify each constraint as 'hard' (a fixed "
    "commitment that must never be scheduled over, e.g. a class or work shift) or "
    "'soft' (a negotiable preference, e.g. dislikes mornings). Keep any private "
    "reason in the 'note' field. Respond with a single JSON object only."
)


def _schema_hint():
    return (
        'Respond as JSON: {"constraints": [{"kind": "hard|soft", '
        '"days": ["mon","wed"], "start": "HH:MM", "end": "HH:MM", '
        '"note": "<short private label>"}]}. '
        "Use 24-hour HH:MM times. days may use mon..sun or words like weekdays/daily."
    )


def _normalize_days(raw_days):
    days = []
    for d in raw_days or []:
        key = str(d).strip().lower()
        if key in _DAY_GROUPS:
            days.extend(_DAY_GROUPS[key])
        elif key in _DAY_ALIASES:
            days.append(_DAY_ALIASES[key])
    # de-duplicate, preserve weekday order
    return [d for d in WEEKDAYS if d in set(days)]


def _is_hhmm(v):
    if not isinstance(v, str) or ":" not in v:
        return False
    try:
        h, m = v.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except ValueError:
        return False


def validate(raw):
    """Turn raw LLM JSON into a ConstraintSet, dropping malformed entries.
    Returns None if nothing valid was produced."""
    items = (raw or {}).get("constraints", [])
    if not isinstance(items, list):
        return None
    cs = ConstraintSet()
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).lower()
        if kind not in ("hard", "soft"):
            continue
        days = _normalize_days(item.get("days"))
        start, end = item.get("start"), item.get("end")
        if not days or not _is_hhmm(start) or not _is_hhmm(end) or start >= end:
            continue
        c = Constraint(kind, days, start, end, str(item.get("note", ""))[:60])
        (cs.hard if kind == "hard" else cs.soft).append(c)
    if not cs.hard and not cs.soft:
        return None
    return cs


def parse(text):
    """Parse free text into a ConstraintSet using the LLM. Returns None on failure."""
    if not store.LLM.enabled:
        return None
    user = f"{_schema_hint()}\n\nStudent message: {text!r}"
    data = store.LLM.chat_json(SYSTEM_PROMPT, user)
    return validate(data)


def parse_and_store(student, text):
    """Parse and, if successful, REPLACE and persist the student's ConstraintSet."""
    cs = parse(text)
    if cs is None:
        return None
    student.constraints = cs
    store.persist_constraints(student)  # update SQLite in place
    return cs


# ---------------------------------------------------------------------------
# Incremental editing (keep the rest, change only what was asked)
# ---------------------------------------------------------------------------

UPDATE_SYSTEM = (
    "You edit a student's existing scheduling constraints based on a change "
    "request. Only add or remove what the request mentions; keep everything else "
    "unchanged. To change an existing constraint, remove it by index and add the "
    "new version. Respond with a single JSON object only."
)


def _combined(constraint_set):
    """Flatten to a stable indexed list: hard constraints first, then soft."""
    return ([("hard", c) for c in constraint_set.hard]
            + [("soft", c) for c in constraint_set.soft])


def _format_current(constraint_set):
    combined = _combined(constraint_set)
    lines = [
        f"{i}. [{kind}] {'/'.join(c.days)} {c.start}-{c.end}" + (f" ({c.note})" if c.note else "")
        for i, (kind, c) in enumerate(combined)
    ]
    return combined, ("\n".join(lines) or "(none)")


def _validate_delta(raw, current_count):
    """Turn raw LLM delta JSON into (add_list, remove_indices) or None."""
    if not isinstance(raw, dict):
        return None
    add_cs = validate({"constraints": raw.get("add", [])})
    add_list = (add_cs.hard + add_cs.soft) if add_cs else []
    remove = []
    for r in raw.get("remove", []):
        try:
            idx = int(r)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < current_count:
            remove.append(idx)
    if not add_list and not remove:
        return None
    return add_list, sorted(set(remove))


def parse_delta(constraint_set, text):
    """Ask the LLM for a precise add/remove delta. Returns (adds, remove_indices)."""
    if not store.LLM.enabled:
        return None
    combined, listing = _format_current(constraint_set)
    user = (
        f"Current constraints:\n{listing}\n\n"
        f"Change request: {text!r}\n"
        'Respond as JSON: {"add": [{"kind": "hard|soft", "days": ["mon"], '
        '"start": "HH:MM", "end": "HH:MM", "note": "..."}], '
        '"remove": [<indices from the list above to delete>]}.'
    )
    data = store.LLM.chat_json(UPDATE_SYSTEM, user)
    return _validate_delta(data, len(combined))


def apply_delta(constraint_set, add_list, remove_indices):
    """Pure, deterministic application of a delta. Unremoved items are preserved."""
    combined = _combined(constraint_set)
    remove = set(remove_indices)
    new = ConstraintSet()
    for i, (kind, c) in enumerate(combined):
        if i in remove:
            continue
        (new.hard if kind == "hard" else new.soft).append(c)
    for c in add_list:
        (new.hard if c.kind == "hard" else new.soft).append(c)
    return new


def apply_update(student, text):
    """Apply an incremental change and persist. Returns the new ConstraintSet or None."""
    delta = parse_delta(student.constraints, text)
    if delta is None:
        return None
    add_list, remove_indices = delta
    student.constraints = apply_delta(student.constraints, add_list, remove_indices)
    store.persist_constraints(student)
    return student.constraints
