"""SQLite persistence for students and their schedules.

Stores each registered student and their parsed constraints so schedules survive
restarts and update in place whenever a student changes them. Sessions remain
in-memory (they are short-lived). The DB path can be overridden with the
HELPCIRCUIT_DB env var (used by tests to avoid touching the real database).
"""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from models import Constraint, ConstraintSet

DB_PATH = os.getenv("HELPCIRCUIT_DB") or str(Path(__file__).resolve().parent / "helpcircuit.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with closing(_conn()) as c, c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS students ("
            " discord_user_id INTEGER PRIMARY KEY,"
            " display_name TEXT NOT NULL)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS constraints ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " student_id INTEGER NOT NULL,"
            " kind TEXT NOT NULL,"
            " days TEXT NOT NULL,"
            " start TEXT NOT NULL,"
            " end TEXT NOT NULL,"
            " note TEXT)"
        )


def upsert_student(user_id, name):
    with closing(_conn()) as c, c:
        c.execute(
            "INSERT INTO students(discord_user_id, display_name) VALUES (?, ?) "
            "ON CONFLICT(discord_user_id) DO UPDATE SET display_name=excluded.display_name",
            (user_id, name),
        )


def save_constraints(user_id, constraint_set):
    """Replace all stored constraints for a student (update-in-place)."""
    rows = []
    for kind, items in (("hard", constraint_set.hard), ("soft", constraint_set.soft)):
        for con in items:
            rows.append((user_id, kind, ",".join(con.days), con.start, con.end, con.note))
    with closing(_conn()) as c, c:
        c.execute("DELETE FROM constraints WHERE student_id=?", (user_id,))
        if rows:
            c.executemany(
                "INSERT INTO constraints(student_id, kind, days, start, end, note) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )


def load_all():
    """Return {user_id: (display_name, ConstraintSet)} for all stored students."""
    out = {}
    with closing(_conn()) as c:
        for row in c.execute("SELECT discord_user_id, display_name FROM students"):
            out[row["discord_user_id"]] = (row["display_name"], ConstraintSet())
        for row in c.execute("SELECT student_id, kind, days, start, end, note FROM constraints"):
            entry = out.get(row["student_id"])
            if not entry:
                continue
            con = Constraint(
                row["kind"],
                row["days"].split(",") if row["days"] else [],
                row["start"], row["end"], row["note"] or "",
            )
            (entry[1].hard if row["kind"] == "hard" else entry[1].soft).append(con)
    return out


def reset():
    with closing(_conn()) as c, c:
        c.execute("DELETE FROM constraints")
        c.execute("DELETE FROM students")
