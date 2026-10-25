"""Base agent: represents exactly one student and sees only that student's data."""


class BaseAgent:
    def __init__(self, student):
        # The agent holds a reference to its OWN student only.
        self._student = student

    @property
    def id(self):
        return self._student.discord_user_id

    @property
    def name(self):
        return self._student.display_name

    @property
    def student(self):
        return self._student
