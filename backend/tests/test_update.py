"""Incremental schedule editing: change a few things, keep the rest."""

import constraint_parser
import store
from models import Constraint, ConstraintSet


class FakeLLM:
    enabled = True

    def __init__(self, payload):
        self.payload = payload

    def chat_json(self, system, user, retries=1):
        return self.payload


def _base():
    return ConstraintSet(
        hard=[Constraint("hard", ["mon", "wed"], "09:00", "17:00", "class")],
        soft=[Constraint("soft", ["mon", "tue", "wed", "thu", "fri"], "08:00", "10:00", "mornings")],
    )


def test_apply_delta_adds_without_touching_existing():
    cs = _base()
    new_item = Constraint("hard", ["fri"], "14:00", "16:00", "lab")
    out = constraint_parser.apply_delta(cs, [new_item], [])
    assert len(out.hard) == 2          # original class + new lab
    assert len(out.soft) == 1          # mornings preserved
    notes = {c.note for c in out.hard}
    assert {"class", "lab"} == notes


def test_apply_delta_removes_only_targeted_index():
    cs = _base()
    # Combined order: index 0 = hard class, index 1 = soft mornings.
    out = constraint_parser.apply_delta(cs, [], [1])  # remove the soft 'mornings'
    assert len(out.hard) == 1 and out.hard[0].note == "class"
    assert len(out.soft) == 0


def test_apply_delta_change_is_remove_plus_add():
    cs = _base()
    updated_class = Constraint("hard", ["mon", "wed"], "10:00", "16:00", "class")
    out = constraint_parser.apply_delta(cs, [updated_class], [0])  # replace class
    assert len(out.hard) == 1
    assert out.hard[0].start == "10:00"
    assert len(out.soft) == 1          # mornings untouched


def test_apply_update_end_to_end_with_mock_llm(monkeypatch):
    store.reset()
    st, _ = store.register(7, "Eve")
    st.constraints = _base()
    store.persist_constraints(st)

    # LLM delta: add a Friday lab, remove nothing.
    monkeypatch.setattr(store, "LLM", FakeLLM({
        "add": [{"kind": "hard", "days": ["fri"], "start": "14:00", "end": "16:00", "note": "lab"}],
        "remove": [],
    }))
    out = constraint_parser.apply_update(st, "add a lab Friday 2-4pm")
    assert out is not None
    assert {c.note for c in out.hard} == {"class", "lab"}
    # Persisted too.
    import db
    reloaded = db.load_all()
    assert len(reloaded[7][1].hard) == 2


def test_invalid_delta_returns_none(monkeypatch):
    monkeypatch.setattr(store, "LLM", FakeLLM({"add": [], "remove": []}))
    assert constraint_parser.parse_delta(_base(), "do nothing") is None
