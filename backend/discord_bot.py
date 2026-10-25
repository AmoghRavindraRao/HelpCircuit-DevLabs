"""HelpCircuit Discord bot — slash commands + button confirmations.

Single process: this bot imports the coordinator/agent modules directly and
shares one in-memory + SQLite-backed store. Personal commands reply privately
(ephemeral); scheduling happens in the channel and confirmations arrive as DM
buttons. No Message Content intent is required.

Setup:
  1. Create a bot at https://discord.com/developers/applications and copy the token.
  2. Invite it with the "applications.commands" and "bot" scopes.
  3. .env: DISCORD_BOT_TOKEN=... , an LLM key (OPENAI_API_KEY/ANTHROPIC_API_KEY),
     and optionally DISCORD_GUILD_ID=<your server id> for instant command sync.
  4. Run:  python backend/discord_bot.py

Slash commands:
  /register                         register yourself
  /setschedule text:<...>           set (replace) your whole schedule
  /update change:<...>              edit your schedule, keeping the rest
  /clear                            wipe your schedule
  /mytimes                          show your parsed constraints (private)
  /schedule user1 user2 [user3..5] [window]   find a time for the people you pick
  /status                           show the current session in this channel
  /help                             usage
"""

import asyncio
import sys

import config
import store
import coordinator
import constraint_parser
from models import ConstraintSet

try:
    import discord
    from discord import app_commands
except ImportError:  # pragma: no cover
    print("discord.py is not installed. Run: pip install -r backend/requirements.txt")
    sys.exit(1)

WINDOW_HINT = "today | tomorrow | 3days | thisweek | 7days"


class HelpCircuitBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())  # no message_content needed
        self.tree = app_commands.CommandTree(self)
        self.channel_session = {}  # channel_id -> session_id

    async def setup_hook(self):
        if config.DISCORD_GUILD_ID:
            guild = discord.Object(id=int(config.DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        print(f"HelpCircuit online as {self.user} | LLM: {store.LLM.status()}")

    def _names(self, ids):
        return ", ".join(
            (store.student(i).display_name if store.student(i) else str(i)) for i in ids
        )

    async def _channel(self, channel_id):
        return self.get_channel(channel_id) or await self.fetch_channel(channel_id)

    async def drive(self, sess):
        """Advance a session: post public updates and DM confirmation buttons."""
        channel = await self._channel(sess.channel_id)

        if sess.state == "AWAITING_CONFIRMATION":
            if sess.notified_for == sess.selected.key:
                return  # already asked for this slot
            sess.notified_for = sess.selected.key
            if channel:
                await channel.send(
                    f"🤖 Agents compared everyone's schedules — ruled out "
                    f"{sess.stats.get('ruled_out_hard', 0)} time(s) with hard conflicts. "
                    f"Proposed: **{sess.selected.label()}**. Sent DMs to confirm."
                )
            for pid in list(sess.pending_confirm):
                soft = coordinator.soft_violated_for(sess, pid)
                prompt = store.agent(pid).confirmation_prompt(sess.selected, soft)
                try:
                    user = self.get_user(pid) or await self.fetch_user(pid)
                    await user.send(prompt, view=ConfirmView(sess.id, pid))
                except Exception:
                    if channel:
                        await channel.send(f"⚠️ I couldn't DM <@{pid}> — please enable DMs.")

        elif sess.state == "CONFIRMED":
            if channel:
                await channel.send(
                    f"✅ Locked in: **{sess.selected.label()}** for {self._names(sess.participant_ids)}."
                )

        elif sess.state == "NO_SOLUTION":
            if channel:
                await channel.send(
                    "❌ No time works for everyone's fixed commitments in this window. "
                    "Try a wider window, e.g. `window: 7days`."
                )


bot = HelpCircuitBot()


# ---------------------------------------------------------------------------
# Confirmation buttons
# ---------------------------------------------------------------------------

class ConfirmView(discord.ui.View):
    def __init__(self, session_id, user_id):
        super().__init__(timeout=None)
        self.session_id = session_id
        self.user_id = user_id

    async def _respond(self, interaction, accept):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This confirmation isn't for you.", ephemeral=True)
            return
        sess, detail = coordinator.record_confirmation(self.session_id, self.user_id, accept)
        await interaction.response.edit_message(
            content=("Recorded: **yes** ✅" if accept else "Recorded: **no** ❌ — I'll look for another time."),
            view=None,
        )
        if sess:
            await bot.drive(sess)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._respond(interaction, True)

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._respond(interaction, False)


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@bot.tree.command(name="register", description="Register yourself with HelpCircuit")
async def register_cmd(interaction: discord.Interaction):
    _, created = store.register(interaction.user.id, interaction.user.display_name)
    msg = ("Registered! Now set your schedule with `/setschedule`."
           if created else "You're already registered.")
    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="setschedule", description="Set (replace) your whole schedule in plain language")
@app_commands.describe(text="e.g. busy Mon/Wed 9-5 for class, no evenings, I dislike mornings")
async def setschedule_cmd(interaction: discord.Interaction, text: str):
    st = store.student(interaction.user.id)
    if not st:
        await interaction.response.send_message("Use `/register` first.", ephemeral=True)
        return
    if not store.LLM.enabled:
        await interaction.response.send_message(
            "Schedule parsing needs an LLM API key configured in .env.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    cs = await asyncio.to_thread(constraint_parser.parse_and_store, st, text)
    if cs is None:
        await interaction.followup.send(
            "I couldn't understand that. Try e.g. *busy Mon/Wed 9-5, no evenings*.", ephemeral=True)
    else:
        await interaction.followup.send("Saved! Here's your schedule:\n" + cs.summary(), ephemeral=True)


@bot.tree.command(name="update", description="Change your schedule while keeping the rest")
@app_commands.describe(change="e.g. add a lab Friday 2-4pm  /  remove my Tuesday practice")
async def update_cmd(interaction: discord.Interaction, change: str):
    st = store.student(interaction.user.id)
    if not st:
        await interaction.response.send_message("Use `/register` first.", ephemeral=True)
        return
    if not store.LLM.enabled:
        await interaction.response.send_message(
            "Editing needs an LLM API key configured in .env.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    cs = await asyncio.to_thread(constraint_parser.apply_update, st, change)
    if cs is None:
        await interaction.followup.send(
            "I couldn't apply that change. Try e.g. *add class Mon 9-11* or *remove Friday lab*.",
            ephemeral=True)
    else:
        await interaction.followup.send("Updated! Your schedule now:\n" + cs.summary(), ephemeral=True)


@bot.tree.command(name="clear", description="Wipe your whole schedule")
async def clear_cmd(interaction: discord.Interaction):
    st = store.student(interaction.user.id)
    if not st:
        await interaction.response.send_message("Use `/register` first.", ephemeral=True)
        return
    st.constraints = ConstraintSet()
    store.persist_constraints(st)
    await interaction.response.send_message("Cleared your whole schedule.", ephemeral=True)


@bot.tree.command(name="mytimes", description="Show the constraints I parsed for you (private)")
async def mytimes_cmd(interaction: discord.Interaction):
    st = store.student(interaction.user.id)
    if not st:
        await interaction.response.send_message("Use `/register` first.", ephemeral=True)
        return
    await interaction.response.send_message(
        "Here's what I have for you (private):\n" + st.constraints.summary(), ephemeral=True)


@bot.tree.command(name="schedule", description="Find a meeting time for the people you pick")
@app_commands.describe(
    user1="Participant", user2="Participant",
    user3="(optional)", user4="(optional)", user5="(optional)",
    window=WINDOW_HINT,
)
async def schedule_cmd(
    interaction: discord.Interaction,
    user1: discord.Member, user2: discord.Member,
    user3: discord.Member = None, user4: discord.Member = None, user5: discord.Member = None,
    window: str = "7days",
):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/schedule` in a server channel.", ephemeral=True)
        return
    members = [m for m in (user1, user2, user3, user4, user5) if m and not m.bot]
    ids = list(dict.fromkeys(m.id for m in members))

    ok, err = coordinator.validate_participants(ids)
    if not ok:
        if err.startswith("unregistered:"):
            mentions = " ".join(f"<@{i}>" for i in err.split(":", 1)[1].split(","))
            await interaction.response.send_message(
                f"Not registered yet: {mentions}. Each should run `/register` and `/setschedule`.",
                ephemeral=True)
        else:
            await interaction.response.send_message(err, ephemeral=True)
        return

    sess = coordinator.start_session(interaction.channel_id, interaction.user.id, ids, window)
    bot.channel_session[interaction.channel_id] = sess.id
    await interaction.response.send_message("On it — the agents are comparing schedules…", ephemeral=True)
    await bot.drive(sess)


@bot.tree.command(name="status", description="Show the current scheduling session in this channel")
async def status_cmd(interaction: discord.Interaction):
    sid = bot.channel_session.get(interaction.channel_id)
    sess = store.session(sid) if sid else None
    if not sess:
        await interaction.response.send_message("No active session in this channel.", ephemeral=True)
        return
    sel = sess.selected.label() if sess.selected else "—"
    await interaction.response.send_message(
        f"Session **{sess.state}** | proposed: {sel} | "
        f"waiting on {len(sess.pending_confirm)} confirmation(s).", ephemeral=True)


@bot.tree.command(name="help", description="How to use HelpCircuit")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**HelpCircuit** — scheduling agents.\n"
        "`/register` then `/setschedule text:<your schedule>`.\n"
        "`/update change:<...>` edits while keeping the rest; `/clear` wipes it.\n"
        "`/schedule user1 user2 [user3..5] [window]` — only the people you pick are included.\n"
        "Confirm via the Yes/No buttons I DM you. `/mytimes` shows your parsed schedule.",
        ephemeral=True)


def main():
    if not config.DISCORD_BOT_TOKEN:
        print("DISCORD_BOT_TOKEN is not set. Add it to your .env file.")
        sys.exit(1)
    bot.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
