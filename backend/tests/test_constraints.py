from constraints import ConstraintChecker, DisclosureGuard
from models import Constraint, ConstraintSet, Slot, Student

MON = "2026-01-05"  # Monday
TUE = "2026-01-06"

checker = ConstraintChecker()
guard = DisclosureGuard()


def _student(hard=None, soft=None):
    return Student(1, "Test", ConstraintSet(hard=hard or [], soft=soft or []))


def test_hard_conflict_detected():
    st = _student(hard=[Constraint("hard", ["mon"], "09:00", "17:00", "class")])
    assert checker.violates_hard(st, Slot(MON, 10)) is True
    assert checker.violates_hard(st, Slot(MON, 18)) is False
    assert checker.violates_hard(st, Slot(TUE, 10)) is False


def test_soft_preference_detected():
    st = _student(soft=[Constraint("soft", ["mon", "tue"], "08:00", "10:00", "dislikes mornings")])
    assert checker.violates_soft(st, Slot(MON, 8)) is True
    assert checker.violates_soft(st, Slot(MON, 11)) is False


def test_disclosure_guard_strips_private_note():
    st = _student(hard=[Constraint("hard", ["mon"], "09:00", "17:00", "therapy")])
    text = "Can't do it because of therapy on 2026-01-05_10 at 10:00"
    out = guard.sanitize(text, [st])
    assert "therapy" not in out.lower()
    assert "2026-01-05_10" not in out
    assert "10:00" not in out


def test_disclosure_guard_passes_safe_text():
    st = _student()
    assert guard.sanitize("has a scheduling conflict", [st]) == "has a scheduling conflict"
