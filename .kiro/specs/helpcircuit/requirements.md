# Requirements Document

## Introduction

HelpCircuit is a multi-agent campus scheduling assistant built for a hackathon (Track 2: Agent-to-Agent Coordination). Each real student who participates registers through Discord and is represented by their own personal AI agent. Each agent privately holds that student's real scheduling constraints, expressed in natural language and parsed by a large language model into structured hard and soft constraints. When a student requests a group meeting time, a coordinator routes candidate time slots to every participant's agent. The agents negotiate to converge on a slot that satisfies everyone's hard constraints, disclosing only minimal public reasons when they decline, and asking their own human for confirmation only when a genuine tradeoff (a soft-preference violation) is at stake. A deterministic safety net performs all time-overlap and hard-constraint math and is the final authority: the system never finalizes a slot that violates any participant's hard constraint, regardless of LLM output.

Discord is the entire user interface. There is no web frontend. Registration and private constraint intake happen in direct messages so private data never reaches a group channel. Scheduling requests, the visible (sanitized) negotiation, and final results happen in a group channel. The backend runs headless as the agents' brain.

This document specifies every functional requirement needed to implement the system end-to-end, expressed in EARS patterns with testable acceptance criteria. The requirements directly support the three judging criteria: handling conflicting constraints, controlling what agents share, and knowing when agents ask their students to confirm.

## Glossary

- **HelpCircuit**: The complete system comprising the Discord_Interface, the Student_Agents, the Coordinator, the Constraint_Parser, the Constraint_Checker, the Disclosure_Guard, the LLM_Adapter, and the Persistence_Store.
- **Student**: A real person who has registered with HelpCircuit through Discord. A Student is uniquely identified by their Discord user id.
- **Discord_User_Id**: The unique identifier assigned by Discord to a real user, used as the sole identity for a Student.
- **Student_Agent** (also **Agent**): The software actor that represents exactly one Student, privately holds that Student's Constraint_Set, evaluates candidate Slots on that Student's behalf, and decides what to disclose and when to ask that Student to confirm.
- **Constraint_Set**: The structured private data for one Student, consisting of a list of Hard_Constraints and a list of Soft_Constraints, derived by the Constraint_Parser from the Student's natural-language input.
- **Hard_Constraint**: A structured constraint that must never be violated by any finalized Slot (for example, a fixed class or practice). A Hard_Constraint marks one or more Slots as unavailable for a Student.
- **Soft_Constraint**: A structured, negotiable preference that may be violated only with the explicit confirmation of the Student (for example, dislikes mornings). A Soft_Constraint marks one or more Slots as disfavored for a Student.
- **Constraint_Parser**: The component that uses the LLM_Adapter to convert a Student's natural-language message into a Constraint_Set and to classify each resulting constraint as Hard_Constraint or Soft_Constraint.
- **Slot**: A discrete, bounded candidate time window drawn from the Slot_Grid.
- **Slot_Grid**: The bounded, finite set of discrete candidate Slots generated for a Scheduling_Session, covering the requested Time_Window.
- **Time_Window**: The bounded interval (for example, "before Friday") within which a Scheduling_Session must find a meeting time.
- **Scheduling_Session** (also **Session**): A single instance of group scheduling, bound to a named set of Participants and a Time_Window, carrying a Session_State and a chosen Slot when resolved.
- **Participant**: A Student included in a specific Scheduling_Session by the requesting Student.
- **Coordinator**: The component that generates the Slot_Grid, routes candidate Slots to each Participant's Student_Agent, collects evaluations, and drives the Session toward a resolution.
- **Constraint_Checker**: The deterministic component that evaluates whether a given Slot violates a Student's Hard_Constraints or Soft_Constraints. The Constraint_Checker is the final authority on Hard_Constraint satisfaction.
- **Disclosure_Guard**: The deterministic component that sanitizes every message destined for the group channel, removing private constraint text and raw Slot or calendar identifiers before the message is shared.
- **Public_Reason**: A short, sanitized, human-readable string an Agent discloses when it declines a Slot, which never contains private constraint text or raw calendar detail.
- **LLM_Adapter**: The provider-agnostic component that calls a configured large language model (OpenAI, Anthropic, or an OpenAI-compatible provider) using an API key supplied through a .env file.
- **Persistence_Store**: The storage that holds registered Students, their private Constraint_Sets, and active Scheduling_Sessions.
- **Session_State** (also **State**): One of COLLECTING, NEGOTIATING, AWAITING_CONFIRMATION, CONFIRMED, NO_SOLUTION.
- **Direct_Message** (also **DM**): A private Discord message between the bot and a single Student, used for registration, constraint intake, and confirmation requests.
- **Group_Channel**: The shared Discord channel where scheduling requests, sanitized negotiation, and final results appear.
- **Confirmation_Request**: A DM an Agent sends to its own Student asking the Student to accept or decline a specific tradeoff or a final chosen Slot.

## Requirements

### Requirement 1: Register real Discord users as participants

**User Story:** As a student, I want to register myself through Discord, so that I become a participant with my own personal agent without any hardcoded setup.

#### Acceptance Criteria

1. WHEN a Discord user sends the registration command to the Discord_Interface, THE HelpCircuit SHALL create a Student identified by that user's Discord_User_Id.
2. THE HelpCircuit SHALL instantiate exactly one Student_Agent for each registered Student.
3. IF a Discord user who is already registered sends the registration command again, THEN THE HelpCircuit SHALL retain the existing Student and SHALL report that the Student is already registered.
4. THE HelpCircuit SHALL use the Discord_User_Id as the sole identity for a Student and SHALL NOT require any additional authentication.
5. WHERE no students have registered, THE HelpCircuit SHALL contain no Student records and no Student_Agents.

### Requirement 2: Operate entirely through Discord with no web frontend

**User Story:** As an operator, I want Discord to be the only interface, so that the backend runs headless and private data never needs a separate UI.

#### Acceptance Criteria

1. THE HelpCircuit SHALL expose all user-facing interactions through the Discord_Interface.
2. THE HelpCircuit SHALL NOT require a web frontend for any user-facing interaction.
3. THE HelpCircuit SHALL conduct registration and private constraint intake through Direct_Messages.
4. THE HelpCircuit SHALL conduct scheduling requests, sanitized negotiation, and final results through the Group_Channel.
5. WHEN a Student_Agent needs a confirmation from its own Student, THE HelpCircuit SHALL send a Direct_Message to that Student.

### Requirement 3: Parse natural-language constraints privately via DM

**User Story:** As a student, I want to tell my agent my schedule in plain language through a private DM, so that my real constraints are captured without exposing them to the group.

#### Acceptance Criteria

1. WHEN a Student sends a natural-language constraint message to the Discord_Interface through a Direct_Message, THE Constraint_Parser SHALL use the LLM_Adapter to convert the message into a structured Constraint_Set for that Student.
2. WHEN the Constraint_Parser produces a Constraint_Set, THE Constraint_Parser SHALL classify each resulting constraint as exactly one of Hard_Constraint or Soft_Constraint.
3. THE HelpCircuit SHALL store each Student's Constraint_Set in the Persistence_Store associated with that Student's Discord_User_Id.
4. THE HelpCircuit SHALL restrict read access to a Student's Constraint_Set to that Student's own Student_Agent.
5. THE HelpCircuit SHALL NOT disclose any Student's Constraint_Set in the Group_Channel.
6. WHEN a Student sends a new constraint message through a Direct_Message, THE HelpCircuit SHALL update that Student's stored Constraint_Set to reflect the new message.

### Requirement 4: Accept group scheduling requests over a bounded slot grid

**User Story:** As a student, I want to ask the assistant in the group channel to find a meeting time for named participants within a time window, so that the group can schedule without manual back-and-forth.

#### Acceptance Criteria

1. WHEN a Student sends a scheduling request in the Group_Channel naming a set of Participants and a Time_Window, THE HelpCircuit SHALL create a Scheduling_Session bound to those Participants and that Time_Window.
2. WHEN a Scheduling_Session is created, THE Coordinator SHALL generate a bounded, finite Slot_Grid of discrete candidate Slots contained within the Time_Window.
3. IF a named Participant is not a registered Student, THEN THE HelpCircuit SHALL report the unregistered Participant in the Group_Channel and SHALL NOT start negotiation for the Scheduling_Session.
4. IF a scheduling request names fewer than two Participants, THEN THE HelpCircuit SHALL reject the request and SHALL report that at least two Participants are required.
5. WHEN a Scheduling_Session is created, THE HelpCircuit SHALL set its initial Session_State to COLLECTING.
6. WHERE a named Participant has no stored Constraint_Set, THE Coordinator SHALL treat that Participant as having no Hard_Constraints and no Soft_Constraints for the Scheduling_Session.

### Requirement 5: Negotiate agent-to-agent to converge on a feasible slot

**User Story:** As a participant, I want the agents to negotiate candidate times among themselves, so that the group converges on a slot that works for everyone without my manual effort.

#### Acceptance Criteria

1. WHEN a Scheduling_Session enters negotiation, THE Coordinator SHALL set the Session_State to NEGOTIATING and SHALL route each candidate Slot from the Slot_Grid to each Participant's Student_Agent for evaluation.
2. WHEN a Student_Agent evaluates a candidate Slot, THE Student_Agent SHALL use the Constraint_Checker to determine whether the Slot violates that Student's Hard_Constraints or Soft_Constraints.
3. THE Coordinator SHALL classify a candidate Slot as feasible if and only if the Constraint_Checker reports that the Slot violates no Participant's Hard_Constraints.
4. WHEN at least one candidate Slot in the Slot_Grid is feasible, THE Coordinator SHALL select from the feasible Slots the Slot that violates the fewest Participants' Soft_Constraints.
5. WHEN two or more feasible Slots violate the same fewest number of Participants' Soft_Constraints, THE Coordinator SHALL select among them deterministically by the Slot's position in the Slot_Grid.
6. WHEN the Coordinator processes the same Slot_Grid and the same Participant Constraint_Sets, THE Coordinator SHALL select the same Slot.

### Requirement 6: Report an honest no-solution when hard constraints conflict

**User Story:** As a participant, I want the system to tell the group honestly when no time works, so that nobody is committed to an impossible slot and the conflict is explained without exposing private detail.

#### Acceptance Criteria

1. IF no candidate Slot in the Slot_Grid is feasible, THEN THE Coordinator SHALL set the Session_State to NO_SOLUTION.
2. WHEN a Scheduling_Session reaches NO_SOLUTION, THE HelpCircuit SHALL report in the Group_Channel that no time satisfies every Participant's Hard_Constraints.
3. WHEN HelpCircuit reports a NO_SOLUTION outcome, THE Disclosure_Guard SHALL ensure the report describes the conflict only at a non-private granularity and excludes every Participant's private constraint text and raw Slot or calendar identifiers.
4. WHEN a Scheduling_Session reaches NO_SOLUTION, THE HelpCircuit SHALL NOT finalize any Slot for that Scheduling_Session.

### Requirement 7: Enforce selective disclosure of decline reasons

**User Story:** As a participant, I want my agent to share only a minimal public reason when it declines a time, so that my private schedule details are never revealed to the group.

#### Acceptance Criteria

1. WHEN a Student_Agent declines a candidate Slot, THE Student_Agent SHALL produce a Public_Reason that states only that a conflict or preference prevents the Slot.
2. WHEN a Student_Agent produces a Public_Reason, THE Disclosure_Guard SHALL remove any private constraint text and any raw Slot or calendar identifier before the Public_Reason is shared in the Group_Channel.
3. THE Disclosure_Guard SHALL exclude from every Group_Channel message the specific private reason underlying a decline.
4. WHERE the LLM_Adapter generates the wording of a Public_Reason, THE Disclosure_Guard SHALL validate the generated wording and SHALL remove any content that matches a Participant's private constraint text or raw calendar detail before sharing.
5. THE HelpCircuit SHALL share in the Group_Channel only Participant identities, candidate Slot references needed for coordination, and sanitized Public_Reasons.

### Requirement 8: Never violate hard constraints automatically

**User Story:** As a participant, I want my hard constraints to be absolute, so that I am never scheduled over a class or other fixed commitment without my involvement.

#### Acceptance Criteria

1. THE HelpCircuit SHALL NOT finalize a Slot that violates any Participant's Hard_Constraint.
2. WHEN the Coordinator selects a Slot for confirmation, THE Constraint_Checker SHALL have reported that the Slot violates no Participant's Hard_Constraint.
3. IF the LLM_Adapter proposes a Slot that the Constraint_Checker reports as violating any Participant's Hard_Constraint, THEN THE HelpCircuit SHALL discard the proposed Slot and SHALL use the deterministic result.
4. THE Constraint_Checker SHALL be the final authority on whether a Slot violates a Hard_Constraint.

### Requirement 9: Ask the student to confirm a soft-constraint tradeoff

**User Story:** As a participant, I want my agent to ask me before accepting a time that breaks one of my preferences, so that I stay in control of genuine tradeoffs.

#### Acceptance Criteria

1. WHEN the Slot the Coordinator selects violates a Participant's Soft_Constraint but no Participant's Hard_Constraint, THE affected Participant's Student_Agent SHALL send a Confirmation_Request as a Direct_Message to its own Student describing the tradeoff.
2. THE HelpCircuit SHALL set the Session_State to AWAITING_CONFIRMATION while any Confirmation_Request for a soft-constraint tradeoff is outstanding.
3. WHEN a Student replies to a soft-constraint Confirmation_Request with acceptance, THE Student_Agent SHALL treat the selected Slot as acceptable for that Student.
4. WHEN a Student replies to a soft-constraint Confirmation_Request with a decline, THE Student_Agent SHALL treat the selected Slot as not acceptable for that Student and THE Coordinator SHALL exclude that Slot and re-select from the remaining feasible Slots.
5. THE Student_Agent SHALL send a soft-constraint Confirmation_Request only through a Direct_Message to its own Student.
6. IF every feasible Slot is declined by at least one Participant on a soft-constraint Confirmation_Request, THEN THE Coordinator SHALL set the Session_State to NO_SOLUTION.

### Requirement 10: Require explicit confirmation from every participant to commit

**User Story:** As a participant, I want the final time to be locked only after everyone explicitly confirms, so that no one is bound to a time they have not agreed to.

#### Acceptance Criteria

1. WHEN the Coordinator has a selected Slot that violates no Participant's Hard_Constraint, THE HelpCircuit SHALL set the Session_State to AWAITING_CONFIRMATION and SHALL request an explicit confirmation from every Participant.
2. WHEN every Participant has explicitly confirmed the selected Slot, THE HelpCircuit SHALL set the Session_State to CONFIRMED and SHALL announce the confirmed Slot in the Group_Channel.
3. WHILE fewer than all Participants have confirmed the selected Slot, THE HelpCircuit SHALL keep the Session_State as AWAITING_CONFIRMATION.
4. IF any Participant declines the selected Slot during confirmation, THEN THE Coordinator SHALL exclude that Slot and SHALL re-select from the remaining feasible Slots.
5. WHEN a Scheduling_Session reaches CONFIRMED, THE HelpCircuit SHALL NOT change the confirmed Slot for that Scheduling_Session.

### Requirement 11: Keep deterministic code the final authority

**User Story:** As a developer, I want all time-overlap and hard-constraint math done by deterministic code, so that the system is safe even when the LLM produces incorrect output.

#### Acceptance Criteria

1. THE Constraint_Checker SHALL perform all time-overlap and Hard_Constraint checks in deterministic code.
2. THE HelpCircuit SHALL use the LLM_Adapter only for natural-language parsing, hard-or-soft classification, disclosure wording, negotiation phrasing, and when-to-ask decisions.
3. IF any LLM_Adapter output would cause a finalized Slot to violate a Participant's Hard_Constraint, THEN THE HelpCircuit SHALL override the LLM_Adapter output with the deterministic result.
4. WHEN the Coordinator selects a Slot and the Constraint_Checker is given the same Slot_Grid and Participant Constraint_Sets, THE Constraint_Checker SHALL return the same feasibility result on every evaluation.

### Requirement 12: Use a provider-agnostic LLM configured via .env

**User Story:** As a developer, I want the LLM provider to be configurable through an API key in a .env file, so that I can use OpenAI, Anthropic, or an OpenAI-compatible provider without code changes.

#### Acceptance Criteria

1. THE LLM_Adapter SHALL read its provider selection and API key from a .env file.
2. THE LLM_Adapter SHALL support OpenAI, Anthropic, and OpenAI-compatible providers through a common interface.
3. WHEN a Student submits a natural-language constraint message and the LLM_Adapter is available, THE Constraint_Parser SHALL parse the message using the LLM_Adapter.
4. IF the LLM_Adapter is unavailable or no API key is configured, THEN THE HelpCircuit SHALL report a clear message that natural-language parsing is unavailable and SHALL NOT crash.
5. WHERE the LLM_Adapter is unavailable, THE HelpCircuit SHALL continue to perform deterministic Hard_Constraint checking and Slot selection for any Constraint_Sets already stored.

### Requirement 13: Enforce the scheduling session state machine

**User Story:** As a developer, I want a precise session state machine, so that every scheduling session has exactly one valid state and transitions are predictable.

#### Acceptance Criteria

1. THE HelpCircuit SHALL assign every Scheduling_Session exactly one Session_State from the set {COLLECTING, NEGOTIATING, AWAITING_CONFIRMATION, CONFIRMED, NO_SOLUTION} at all times.
2. WHEN a Scheduling_Session is created, THE HelpCircuit SHALL set its Session_State to COLLECTING.
3. WHEN the Coordinator begins routing candidate Slots to Participant Student_Agents, THE HelpCircuit SHALL transition the Scheduling_Session from COLLECTING to NEGOTIATING.
4. WHEN the Coordinator has a selected feasible Slot requiring confirmation, THE HelpCircuit SHALL transition the Scheduling_Session from NEGOTIATING to AWAITING_CONFIRMATION.
5. WHEN every Participant confirms the selected Slot, THE HelpCircuit SHALL transition the Scheduling_Session from AWAITING_CONFIRMATION to CONFIRMED.
6. IF no candidate Slot is feasible, OR IF every feasible Slot is ultimately declined, THEN THE HelpCircuit SHALL transition the Scheduling_Session to NO_SOLUTION.
7. THE HelpCircuit SHALL treat CONFIRMED and NO_SOLUTION as terminal States that permit no further transition for that Scheduling_Session.

### Requirement 14: Deliver the campus value proposition in the demo scenario

**User Story:** As a group of students, I want our agents to find a study time privately and quickly, so that we avoid painful back-and-forth that exposes our personal details.

#### Acceptance Criteria

1. WHEN a group of at least three registered Students requests a study session over a Time_Window, THE HelpCircuit SHALL converge on a confirmed Slot or an honest NO_SOLUTION without any Participant manually comparing schedules in the Group_Channel.
2. THE HelpCircuit SHALL conduct constraint intake and confirmation privately through Direct_Messages so that no Participant's personal schedule detail appears in the Group_Channel.
3. WHEN agents resolve conflicting schedules, THE HelpCircuit SHALL ask a Participant to confirm only when the only remaining tradeoff is a Soft_Constraint violation.
4. WHEN a Scheduling_Session reaches CONFIRMED, THE HelpCircuit SHALL announce only the agreed Slot and the Participants in the Group_Channel.

### Requirement 15: Respect the declared non-goals

**User Story:** As a stakeholder, I want the system to exclude out-of-scope features, so that the hackathon build stays focused on the agent-to-agent coordination track.

#### Acceptance Criteria

1. THE HelpCircuit SHALL NOT implement any authentication beyond the Discord_User_Id identity.
2. THE HelpCircuit SHALL NOT integrate with any external calendar service.
3. THE HelpCircuit SHALL NOT provide a web frontend.
4. THE HelpCircuit SHALL NOT process any payment.
5. THE HelpCircuit SHALL schedule only over the bounded Slot_Grid and SHALL NOT accept arbitrary datetimes outside the Slot_Grid.
6. THE HelpCircuit SHALL support Scheduling_Sessions with a minimum of two Participants and SHALL operate best with three or more Participants.
