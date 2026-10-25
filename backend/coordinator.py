"""Coordinator: session lifecycle, deterministic slot selection, confirmations.

Drives a SchedulingSession through COLLECTING -> NEGOTIATING ->
AWAITING_CONFIRMATION -> CONFIRMED / NO_SOLUTION. Slot selection and hard-constraint
feasibility are deterministic; the result never violates a hard constraint.
"""

import store
from models import (
    SchedulingSession, AWAITING_CONFIRMATION, CONFIRMED, NEGOTIATING, NO_SOLUTION,
)
from slots import build_grid, resolve_window
from constraints import ConstraintChecker, DisclosureGuard

CHECKER = ConstraintChecker()
GUARD = DisclosureGuard()


# ---------------------------------------------------------------------------
# Session creation + negotiation
# ---------------------------------------------------------------------------

def validate_participants(participant_ids):
    """Return (ok, error_message). Checks registration and minimum count."""
    if len(set(participant_ids)) < 2:
        return False, "A scheduling request needs at least two participants."
    unregistered = [p for p in participant_ids if store.student(p) is None]
    if unregistered:
        return False, "unregistered:" + ",".join(str(p) for p in unregistered)
    return True, None


def start_session(channel_id, requester_id, participant_ids, window_text):
    """Create a session and run the first negotiation pass."""
    window = resolve_window(window_text)
    sess = SchedulingSession(
        id=store.new_session_id(),
        channel_id=channel_id,
        requester_id=requester_id,
        participant_ids=list(dict.fromkeys(participant_ids)),  # de-dupe, keep order
        window=window,
        grid=build_grid(window),
    )
    store.SESSIONS[sess.id] = sess
    _negotiate(sess)
    return sess


def _students(sess):
    return [store.student(p) for p in sess.participant_ids]


def _select(sess):
    """Deterministically pick the feasible slot with the fewest soft violations.
    Also records how many slots were ruled out by hard conflicts."""
    students = _students(sess)
    best = None
    ruled_out_hard = 0
    for index, slot in enumerate(sess.grid):
        if slot.key in sess.excluded:
            continue
        evals = [store.agent(p).evaluate(CHECKER, slot) for p in sess.participant_ids]
        if any(e["hard"] for e in evals):
            ruled_out_hard += 1
            continue
        soft_hits = sum(1 for e in evals if e["soft"])
        key = (soft_hits, index)
        if best is None or key < best[0]:
            best = (key, slot, soft_hits)
    sess.stats["ruled_out_hard"] = ruled_out_hard
    sess.stats["grid_size"] = len(sess.grid)
    if best is None:
        return None, 0
    return best[1], best[2]


def _negotiate(sess):
    sess.state = NEGOTIATING
    slot, soft_hits = _select(sess)
    if slot is None:
        sess.state = NO_SOLUTION
        sess.log.append("No time satisfies everyone's hard constraints.")
        return sess
    sess.selected = slot
    sess.stats["selected_soft_hits"] = soft_hits
    sess.state = AWAITING_CONFIRMATION
    sess.confirmations = {p: None for p in sess.participant_ids}
    sess.pending_confirm = set(sess.participant_ids)
    sess.notified_for = None  # bot will DM for this selected slot
    return sess


# ---------------------------------------------------------------------------
# Confirmation handling
# ---------------------------------------------------------------------------

def soft_violated_for(sess, user_id):
    """Whether the currently selected slot trips this participant's soft preference."""
    if sess.selected is None:
        return False
    return store.agent(user_id).evaluate(CHECKER, sess.selected)["soft"]


def record_confirmation(session_id, user_id, accept):
    """Record a yes/no from a participant. Returns (session, detail)."""
    sess = store.session(session_id)
    if sess is None:
        return None, "Unknown session."
    if sess.state != AWAITING_CONFIRMATION:
        return sess, f"Session is {sess.state}, not awaiting confirmation."
    if user_id not in sess.participant_ids:
        return sess, "You are not a participant of this session."

    sess.confirmations[user_id] = bool(accept)
    sess.pending_confirm.discard(user_id)

    if not accept:
        # Exclude this slot and re-select (may yield a new slot or NO_SOLUTION).
        sess.excluded.add(sess.selected.key)
        _negotiate(sess)
        return sess, "declined"

    if all(sess.confirmations.get(p) is True for p in sess.participant_ids):
        sess.state = CONFIRMED
        return sess, "confirmed"
    return sess, "recorded"
