from datetime import datetime

import slots
from slots import PHOENIX, build_grid, resolve_window, slot_weekday

REF = datetime(2026, 1, 5, 0, 0, tzinfo=PHOENIX)  # a Monday, hour 0


def test_resolve_window_keywords():
    assert resolve_window("today") == "today"
    assert resolve_window("before friday") == "thisweek"
    assert resolve_window("") == "7days"
    assert resolve_window("sometime 3days please") == "3days"


def test_today_grid_is_one_day_of_blocks():
    grid = build_grid("today", ref=REF)
    assert len({s.date for s in grid}) == 1
    assert [s.hour for s in grid] == list(range(8, 21))  # 13 blocks


def test_three_days_has_three_dates():
    grid = build_grid("3days", ref=REF)
    assert len({s.date for s in grid}) == 3


def test_past_hours_skipped_on_first_day():
    midday = datetime(2026, 1, 5, 14, 0, tzinfo=PHOENIX)
    grid = build_grid("today", ref=midday)
    assert all(s.hour > 14 for s in grid)


def test_grid_is_deterministic():
    assert build_grid("thisweek", ref=REF) == build_grid("thisweek", ref=REF)


def test_slot_weekday_mapping():
    from models import Slot
    assert slot_weekday(Slot("2026-01-05", 9)) == "mon"
    assert slot_weekday(Slot("2026-01-06", 9)) == "tue"
