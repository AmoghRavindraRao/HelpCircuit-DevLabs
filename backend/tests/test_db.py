"""Persistence: schedules are remembered and updated in place."""

import db
import store
from models import Constraint, ConstraintSet


def setup_function():
    store.reset()


def test_register_persists_and_reloads():
    store.register(1, "Alice")
    reloaded = db.load_all()
    assert 1 in reloaded
    assert reloaded[1][0] == "Alice"


def test_constraints_persist_and_reload():
    st, _ = store.register(2, "Bob")
    st.constraints = ConstraintSet(hard=[Constraint("hard", ["mon"], "09:00", "17:00", "class")])
    store.persist_constraints(st)

    data = db.load_all()
    assert len(data[2][1].hard) == 1
    assert data[2][1].hard[0].note == "class"


def test_update_replaces_previous_constraints():
    st, _ = store.register(3, "Carol")
    st.constraints = ConstraintSet(soft=[Constraint("soft", ["mon"], "08:00", "09:00", "mornings")])
    store.persist_constraints(st)
    # User changes their schedule entirely.
    st.constraints = ConstraintSet(hard=[Constraint("hard", ["fri"], "12:00", "13:00", "lab")])
    store.persist_constraints(st)

    data = db.load_all()
    assert len(data[3][1].soft) == 0
    assert len(data[3][1].hard) == 1
    assert data[3][1].hard[0].note == "lab"


def test_load_from_db_restores_memory():
    store.register(4, "Dana")
    st = store.student(4)
    st.constraints = ConstraintSet(hard=[Constraint("hard", ["tue"], "10:00", "11:00", "x")])
    store.persist_constraints(st)

    store.STUDENTS.clear()
    store.AGENTS.clear()
    store._load_from_db()
    assert store.student(4) is not None
    assert len(store.student(4).constraints.hard) == 1
