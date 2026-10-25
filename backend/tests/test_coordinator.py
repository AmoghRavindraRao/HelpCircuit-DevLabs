import coordinator
import store
from models import Constraint, ConstraintSet, SchedulingSession, Slot

MON = "2026-01-05"  # Monday
GRID = [Slot(MON, 9), Slot(MON, 10), Slot(MON, 11)]


def setup_function():
    store.reset()


def _make(uid, name, hard=None, soft=None):
    st, _ = store.register(uid, name)
    st.constraints = ConstraintSet(hard=hard or [], soft=soft or [])
    return st


def _session(participant_ids, grid=None):
    sess = SchedulingSession(
        id=store.new_session_id(), channel_id=1, requester_id=participant_ids[0],
        participant_ids=list(participant_ids), window="today", grid=grid or GRID,
    )
    store.SESSIONS[sess.id] = sess
    return sess


def test_selection_prefers_fewest_soft_violations():
    _make(1, "A")
    _make(2, "B")
    _make(3, "C", soft=[Constraint("soft", ["mon"], "09:00", "10:00", "late riser")])
    sess = _session([1, 2, 3])
    coordinator._negotiate(sess)
    assert sess.state == "AWAITING_CONFIRMATION"
    assert sess.selected.hour == 10  # avoids the 9:00 soft hit, earliest of the clean slots


def test_no_solution_when_all_slots_hard_blocked():
    _make(1, "A", hard=[Constraint("hard", ["mon"], "08:00", "20:00", "busy")])
    _make(2, "B")
    sess = _session([1, 2])
    coordinator._negotiate(sess)
    assert sess.state == "NO_SOLUTION"
    assert sess.selected is None


def test_everyone_confirms_commits():
    _make(1, "A"); _make(2, "B"); _make(3, "C")
    sess = _session([1, 2, 3])
    coordinator._negotiate(sess)
    for uid in (1, 2, 3):
        coordinator.record_confirmation(sess.id, uid, True)
    assert sess.state == "CONFIRMED"


def test_decline_excludes_slot_and_reselects():
    _make(1, "A"); _make(2, "B")
    sess = _session([1, 2])
    coordinator._negotiate(sess)
    first = sess.selected.key
    coordinator.record_confirmation(sess.id, 1, False)  # decline -> re-select
    assert sess.state == "AWAITING_CONFIRMATION"
    assert first in sess.excluded
    assert sess.selected.key != first


def test_decline_until_exhausted_is_no_solution():
    _make(1, "A"); _make(2, "B")
    sess = _session([1, 2], grid=[Slot(MON, 9)])  # only one slot
    coordinator._negotiate(sess)
    coordinator.record_confirmation(sess.id, 1, False)
    assert sess.state == "NO_SOLUTION"


def test_non_participant_cannot_confirm():
    _make(1, "A"); _make(2, "B")
    sess = _session([1, 2])
    coordinator._negotiate(sess)
    _, detail = coordinator.record_confirmation(sess.id, 999, True)
    assert "not a participant" in detail.lower()


def test_validate_participants():
    _make(1, "A")
    ok, err = coordinator.validate_participants([1])
    assert not ok  # need at least two
    ok, err = coordinator.validate_participants([1, 2])
    assert not ok and err.startswith("unregistered:")
