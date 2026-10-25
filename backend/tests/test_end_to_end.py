"""Scripted 3-participant scenario including a soft-constraint confirmation,
asserting the outcome and that no private data would leak to the group."""

import coordinator
import store
from constraints import DisclosureGuard
from models import Constraint, ConstraintSet, SchedulingSession, Slot

MON = "2026-01-05"
GRID = [Slot(MON, 8), Slot(MON, 9), Slot(MON, 10)]


def setup_function():
    store.reset()


def _make(uid, name, hard=None, soft=None):
    st, _ = store.register(uid, name)
    st.constraints = ConstraintSet(hard=hard or [], soft=soft or [])
    return st


def test_soft_tradeoff_flow_commits_and_stays_private():
    # Alice is free all morning. Bob has class 9-11 (hard). Carol dislikes 8am (soft).
    _make(1, "Alice")
    _make(2, "Bob", hard=[Constraint("hard", ["mon"], "09:00", "11:00", "lecture")])
    _make(3, "Carol", soft=[Constraint("soft", ["mon"], "08:00", "09:00", "not a morning person")])
    sess = SchedulingSession(
        id=store.new_session_id(), channel_id=1, requester_id=1,
        participant_ids=[1, 2, 3], window="today", grid=GRID,
    )
    store.SESSIONS[sess.id] = sess

    coordinator._negotiate(sess)
    # Only 8:00 avoids Bob's hard class, but it trips Carol's soft preference.
    assert sess.selected.hour == 8
    assert coordinator.soft_violated_for(sess, 3) is True
    assert coordinator.soft_violated_for(sess, 1) is False

    # Everyone (including Carol, who accepts the tradeoff) confirms.
    for uid in (1, 2, 3):
        coordinator.record_confirmation(sess.id, uid, True)
    assert sess.state == "CONFIRMED"

    # A group-bound summary must not leak private notes.
    guard = DisclosureGuard()
    students = [store.student(i) for i in (1, 2, 3)]
    leaky = "Bob can't do lecture time and Carol is not a morning person"
    assert "lecture" not in guard.sanitize(leaky, students)
    assert "not a morning person" not in guard.sanitize(leaky, students)
