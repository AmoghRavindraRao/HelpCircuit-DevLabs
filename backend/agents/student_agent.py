"""StudentAgent: evaluates slots for its own student and phrases its messages.

The agent delegates the authoritative feasibility decision to the deterministic
ConstraintChecker (over its own student's constraints only). It chooses what to
disclose (an allowlisted public reason) and how to ask its own human to confirm.
"""

from agents.base import BaseAgent
from constraints import PUBLIC_HARD_REASON, PUBLIC_SOFT_REASON


class StudentAgent(BaseAgent):

    def evaluate(self, checker, slot):
        """Evaluate a candidate slot against this student's own constraints."""
        hard = checker.violates_hard(self._student, slot)
        soft = checker.violates_soft(self._student, slot)
        return {"feasible": not hard, "hard": hard, "soft": soft}

    def public_reason(self, hard, soft):
        """Allowlisted, privacy-safe reason for the group channel."""
        if hard:
            return PUBLIC_HARD_REASON
        if soft:
            return PUBLIC_SOFT_REASON
        return "is available"

    def confirmation_prompt(self, slot, soft_violated):
        """The DM an agent sends its own student to confirm a slot."""
        if soft_violated:
            return (
                f"The best time for your group is **{slot.label()}**, but it clashes "
                f"with one of your preferences. Are you OK with it? Use the buttons below."
            )
        return f"Your group's proposed time is **{slot.label()}**. Use the buttons below to confirm."
