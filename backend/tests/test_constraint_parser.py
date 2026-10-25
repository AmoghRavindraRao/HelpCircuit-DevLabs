import constraint_parser
import store


class FakeLLM:
    enabled = True

    def __init__(self, payload):
        self.payload = payload

    def chat_json(self, system, user, retries=1):
        return self.payload


def test_validate_keeps_valid_drops_invalid():
    raw = {"constraints": [
        {"kind": "hard", "days": ["mon", "wed"], "start": "09:00", "end": "17:00", "note": "class"},
        {"kind": "soft", "days": ["weekdays"], "start": "08:00", "end": "10:00", "note": "no mornings"},
        {"kind": "bogus", "days": ["mon"], "start": "09:00", "end": "10:00"},     # bad kind
        {"kind": "hard", "days": [], "start": "09:00", "end": "10:00"},           # no days
        {"kind": "hard", "days": ["mon"], "start": "10:00", "end": "09:00"},      # start>=end
    ]}
    cs = constraint_parser.validate(raw)
    assert len(cs.hard) == 1
    assert len(cs.soft) == 1
    assert cs.soft[0].days == ["mon", "tue", "wed", "thu", "fri"]  # 'weekdays' expanded


def test_validate_returns_none_when_all_invalid():
    assert constraint_parser.validate({"constraints": [{"kind": "x"}]}) is None
    assert constraint_parser.validate({}) is None


def test_parse_and_store_updates_student(monkeypatch):
    store.reset()
    st, _ = store.register(42, "Dana")
    monkeypatch.setattr(store, "LLM", FakeLLM(
        {"constraints": [{"kind": "hard", "days": ["tue"], "start": "18:00", "end": "20:00", "note": "practice"}]}
    ))
    cs = constraint_parser.parse_and_store(st, "practice tuesday evenings")
    assert cs is not None
    assert st.constraints.hard[0].note == "practice"


def test_parse_returns_none_when_llm_disabled(monkeypatch):
    class Off:
        enabled = False
    monkeypatch.setattr(store, "LLM", Off())
    assert constraint_parser.parse("anything") is None
