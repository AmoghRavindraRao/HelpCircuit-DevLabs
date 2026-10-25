# HelpCircuit

Personal AI scheduling agents for campus life, used entirely through **Discord**.
Each student registers and gets their own agent that privately holds their real
schedule. When someone asks the group to find a meeting time, the agents negotiate
among themselves to land on a time that works for everyone — disclosing only what
they must, and asking their own human to confirm when a genuine tradeoff comes up.

There is **no web frontend**. Discord is the whole interface; one Python process
runs the bot and the agent "brain" together.

## How it works

- **Register** with `/register`, then set your schedule with `/setschedule` in
  plain language. The reply is private (ephemeral), so only you see it.
- Your **agent** uses an LLM to turn that into structured constraints and labels
  each as **hard** (never schedule over — a class) or **soft** (a preference —
  "I dislike mornings"). This stays private to your agent.
- In a group channel, anyone runs `/schedule user1:@you user2:@friend window:thisweek`.
- A **coordinator** asks every participant's agent to evaluate candidate times.
  A time is only viable if it breaks **nobody's** hard constraints; among viable
  times it picks the one that steps on the fewest soft preferences.
- The bot **DMs each participant** a **Yes/No button** to confirm. If the chosen
  time trips your soft preference, your agent frames it as a tradeoff ("you dislike
  mornings — OK?"). Everyone must click **Yes** to lock it in; any **No** drops that
  time and re-plans.
- If no time clears everyone's hard constraints, the bot says so honestly instead
  of forcing a bad slot.

### Where the AI is central (and where it is not)
- **LLM**: parses natural-language constraints, classifies hard vs. soft, phrases
  DMs, and interprets replies.
- **Deterministic code (final authority)**: all time-overlap and hard-constraint
  math, slot selection, the state machine, and the privacy guard. The LLM can
  never finalize a time that violates a hard constraint, and a `DisclosureGuard`
  strips private reasons/times from anything posted to the group.

## Setup

1. Create a bot at https://discord.com/developers/applications
   - Copy the bot token.
   - Invite it with the **`bot`** and **`applications.commands`** scopes and
     permission to send messages. Allow members to receive its DMs.
   - No privileged intents are needed (slash commands + buttons).
2. Copy `.env.example` to `.env` at the repo root and fill in:
   ```ini
   DISCORD_BOT_TOKEN=...            # from the Developer Portal
   DISCORD_GUILD_ID=...             # your server id → instant slash-command sync
   OPENAI_API_KEY=...               # or ANTHROPIC_API_KEY=...
   # optional: LLM_MODEL=gpt-4o-mini
   ```
   The LLM key is required for natural-language schedule parsing. Without
   `DISCORD_GUILD_ID`, commands sync globally and can take up to ~1 hour to appear.
3. Install deps and run the bot (Windows, existing `.venv` at repo root):
   ```powershell
   .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   .venv\Scripts\python.exe backend\discord_bot.py
   ```

## Commands (slash)

| Command | What it does |
|---|---|
| `/register` | Register yourself |
| `/setschedule text:<...>` | Set (replace) your whole schedule; reply is private |
| `/update change:<...>` | Edit your schedule while keeping the rest |
| `/clear` | Wipe your whole schedule |
| `/mytimes` | Show your parsed constraints (private) |
| `/schedule user1 user2 [user3..5] [window]` | Find a time for only the people you pick |
| `/status` | Show the current session in this channel |
| `/help` | Usage |

Personal commands reply **ephemerally** (only you see them), so your schedule
stays private even in a server channel. `/schedule` includes only the users you
select (mention yourself if you're attending); minimum two. `window` is one of
`today | tomorrow | 3days | thisweek | 7days` (default `7days`).

## Demo script (campus scenario)

1. Three friends each run `/register`, then `/setschedule` with their schedule
   (e.g. *"class Mon/Wed 9–5, practice Tue/Thu evenings, I hate mornings"*).
2. One runs `/schedule user1:@you user2:@b user3:@c window:thisweek`.
3. The bot posts that the agents compared schedules (and how many times were ruled
   out by hard conflicts), proposes a time, and DMs everyone a **Yes/No button**.
4. Whoever has a soft clash gets a tradeoff-framed prompt; everyone clicks **Yes**.
5. The bot announces the locked-in time to the group. No one's private schedule
   ever appears in the channel.

## Project layout

```
backend/
  config.py            # .env loading + LLM provider/model + Discord token
  models.py            # Student, Constraint(Set), Slot, SchedulingSession
  slots.py             # slot-grid generation + time-window resolution
  constraint_parser.py # LLM natural-language -> structured hard/soft constraints
  constraints.py       # ConstraintChecker + DisclosureGuard (deterministic authority)
  coordinator.py       # session lifecycle, slot selection, confirmations
  store.py             # in-memory students / agents / sessions (dynamic)
  agents/
    llm_adapter.py     # provider-agnostic LLM client (OpenAI / Anthropic / compatible)
    base.py            # BaseAgent: owns only its own student
    student_agent.py   # evaluate slots, phrase reasons/confirmations
  discord_bot.py       # the entire user interface
  tests/               # deterministic pytest suite (LLM mocked/disabled)
.env.example           # configuration template
```

## Tests

```powershell
.venv\Scripts\python.exe -m pytest backend -q
```

Covers slot-grid generation, hard/soft constraint checking, disclosure
sanitization, LLM-output validation, deterministic selection, the session state
machine, the decline/re-select flow, and an end-to-end soft-tradeoff scenario.

## Notes & limits

- State is in-memory; restarting the bot clears registrations and sessions.
- Identity is the Discord user id (no other auth — a deliberate scope choice).
- Scheduling is over a bounded hourly grid (08:00–20:00, America/Phoenix), not
  arbitrary datetimes. Works best with 3+ participants.
