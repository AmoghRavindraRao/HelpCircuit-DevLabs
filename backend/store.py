"""In-memory working set backed by SQLite persistence.

Students and their constraints are loaded from SQLite on startup and written back
whenever they change, so schedules are remembered across restarts. Sessions are
kept in memory only (they are short-lived).
"""

import itertools

import db
from models import Student, ConstraintSet
from agents.llm_adapter import LLMAdapter
from agents.student_agent import StudentAgent

STUDENTS = {}   # discord_user_id -> Student
AGENTS = {}     # discord_user_id -> StudentAgent
SESSIONS = {}   # session_id -> SchedulingSession

LLM = LLMAdapter()
_counter = itertools.count(1)


def _add_to_memory(student):
    STUDENTS[student.discord_user_id] = student
    AGENTS[student.discord_user_id] = StudentAgent(student)


def _load_from_db():
    STUDENTS.clear()
    AGENTS.clear()
    for user_id, (name, constraint_set) in db.load_all().items():
        _add_to_memory(Student(user_id, name, constraint_set))


def register(user_id, display_name):
    """Register a Discord user (persisted). Returns (student, created_bool)."""
    if user_id in STUDENTS:
        return STUDENTS[user_id], False
    student = Student(user_id, display_name, ConstraintSet())
    _add_to_memory(student)
    db.upsert_student(user_id, display_name)
    return student, True


def persist_constraints(student):
    """Write a student's current constraints back to SQLite."""
    db.save_constraints(student.discord_user_id, student.constraints)


def student(user_id):
    return STUDENTS.get(user_id)


def agent(user_id):
    return AGENTS.get(user_id)


def session(session_id):
    return SESSIONS.get(session_id)


def new_session_id():
    return f"sess_{next(_counter):03d}"


def reset():
    """Clear memory and persisted data (used by tests and demo resets)."""
    STUDENTS.clear()
    AGENTS.clear()
    SESSIONS.clear()
    db.reset()


# Initialize persistence and load any remembered students on startup.
db.init()
_load_from_db()
