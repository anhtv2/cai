"""
Discord bot wrapper for CAI agents
----------------------------------

This bot exposes your CAI agents via Discord slash commands.
It keeps per-channel sessions (separate agent + history per channel),
streams safely (optionally), and mirrors key ENV behavior from the CLI.

Requirements (install in the same venv where CAI is available):
  pip install -U discord.py python-dotenv

Env vars (examples):
  DISCORD_TOKEN=...                 # required
  ALLOWED_GUILD_ID=1234567890123456 # optional, limits commands to one guild
  CAI_AGENT_TYPE=one_tool_agent     # default agent, same as CLI
  CAI_MODEL=alias0                  # default model
  CAI_MAX_TURNS=inf                 # e.g. "50" to cap turns per channel
  CAI_STREAM=false                  # set true to enable streamed edits

Run:
  python discord_cai_bot.py
"""
from __future__ import annotations

import os
import asyncio
import logging
import warnings
import json
from io import BytesIO
from typing import Dict, Optional, List, Any, Tuple

from dotenv import load_dotenv
load_dotenv()

# ---- Noise suppression (adapted from your CLI module) ----------------------
class ComprehensiveErrorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage().lower()
        suppress_patterns = [
            "asynchronous generator", "asyncgen", "closedresourceerror",
            "didn't stop after athrow", "didnt stop after athrow",
            "generator didn't stop", "cancel scope",
            "unhandled errors in a taskgroup", "error in post_writer",
            "was never awaited", "connection error while setting up",
            "error closing", "httpx_sse", "connection reset by peer",
            "broken pipe", "connection aborted", "runtime warning",
            "runtimewarning", "coroutine", "task was destroyed",
            "event loop is closed", "unclosed client session",
            "unclosed connector", "client_session:", "connector:",
            "connections:",
        ]
        for pat in suppress_patterns:
            if pat in msg:
                return False
        if "sse" in msg and any(w in msg for w in ["cleanup","closing","shutdown","closed"]):
            return False
        if "error invoking mcp tool" in msg and "closedresourceerror" in msg:
            return False
        if "mcp server session not found" in msg or "successfully reconnected to mcp server" in msg:
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        return True

for name in [
    "openai.agents","mcp.client.sse","httpx","httpx_sse","mcp",
    "asyncio","anyio","anyio._backends._asyncio","cai.sdk.agents","aiohttp",
]:
    lg = logging.getLogger(name)
    lg.addFilter(ComprehensiveErrorFilter())
    if name in ["asyncio","anyio","anyio._backends._asyncio"]:
        lg.setLevel(logging.ERROR)
    else:
        lg.setLevel(logging.WARNING)

warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", message=r".*asynchronous generator.*")
warnings.filterwarnings("ignore", message=r".*was never awaited.*")
warnings.filterwarnings("ignore", message=r".*didn't stop after athrow.*")
warnings.filterwarnings("ignore", message=r".*cancel scope.*")
warnings.filterwarnings("ignore", message=r".*coroutine.*was never awaited.*")
warnings.filterwarnings("ignore", message=r".*generator.*didn't stop.*")
warnings.filterwarnings("ignore", message=r".*Task was destroyed.*")
warnings.filterwarnings("ignore", message=r".*Event loop is closed.*")
warnings.filterwarnings("ignore", message=r".*Unclosed client session.*")
warnings.filterwarnings("ignore", message=r".*Unclosed connector.*")
warnings.filterwarnings("ignore", message=r".*client_session:.*")
warnings.filterwarnings("ignore", message=r".*connector:.*")
warnings.filterwarnings("ignore", message=r".*connections:.*")

# ---- CAI imports -----------------------------------------------------------
from cai import is_pentestperf_available  # noqa: F401 (not used here, kept for parity)
from cai.agents import get_agent_by_name
from cai.sdk.agents import Runner, set_tracing_disabled
from cai.sdk.agents.items import ToolCallOutputItem
from cai.util import fix_message_list, fix_litellm_transcription_annotations

# Some models/agents use internal tracing; match CLI behavior
set_tracing_disabled(True)
fix_litellm_transcription_annotations()

# ---- Discord imports -------------------------------------------------------
import discord
from discord import app_commands

# ---- Helper: recursively update model on agent & its handoffs --------------

def update_agent_models_recursively(agent, new_model, visited: Optional[set] = None):
    if visited is None:
        visited = set()
    if getattr(agent, "name", None) in visited:
        return
    visited.add(getattr(agent, "name", id(agent)))

    if hasattr(agent, "model") and hasattr(agent.model, "model"):
        agent.model.model = new_model
        if hasattr(agent.model, "agent_name"):
            agent.model.agent_name = getattr(agent, "name", "Agent")
        if hasattr(agent.model, "_client"):
            agent.model._client = None
        if hasattr(agent.model, "_converter"):
            conv = agent.model._converter
            if hasattr(conv, "recent_tool_calls"):
                conv.recent_tool_calls.clear()
            if hasattr(conv, "tool_outputs"):
                conv.tool_outputs.clear()

    if hasattr(agent, "handoffs"):
        for handoff_item in agent.handoffs:
            try:
                if hasattr(handoff_item, "on_invoke_handoff") and getattr(handoff_item.on_invoke_handoff, "__closure__", None):
                    for cell in handoff_item.on_invoke_handoff.__closure__:
                        obj = getattr(cell, "cell_contents", None)
                        if hasattr(obj, "model") and hasattr(obj, "name"):
                            update_agent_models_recursively(obj, new_model, visited)
                            break
                elif hasattr(handoff_item, "model"):
                    update_agent_models_recursively(handoff_item, new_model, visited)
            except Exception:
                continue

# ---- Per-channel agent session --------------------------------------------
class AgentSession:
    def __init__(self, channel_id: int, agent_type: str, model: str):
        self.channel_id = channel_id
        self.agent_type = agent_type
        self.model = model
        self.turns = 0
        self.lock = asyncio.Lock()
        self.agent = get_agent_by_name(agent_type, agent_id=f"C{channel_id}")
        # Configure model flags for server context
        if hasattr(self.agent, "model"):
            if hasattr(self.agent.model, "disable_rich_streaming"):
                self.agent.model.disable_rich_streaming = True
            if hasattr(self.agent.model, "suppress_final_output"):
                self.agent.model.suppress_final_output = False
        update_agent_models_recursively(self.agent, model)

    def reset(self):
        self.turns = 0
        if hasattr(self.agent, "model") and hasattr(self.agent.model, "message_history"):
            self.agent.model.message_history.clear()

    def build_history_context(self, user_text: str) -> List[dict] | str:
        mh = getattr(getattr(self.agent, "model", object()), "message_history", [])
        if not mh:
            return user_text
        history = []
        for msg in mh:
            role = msg.get("role")
            if role in ("user", "system"):
                history.append({"role": role, "content": msg.get("content") or ""})
            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    history.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
                else:
                    history.append({"role": "assistant", "content": msg.get("content")})
            elif role == "tool":
                history.append({"role": "tool", "tool_call_id": msg.get("tool_call_id"), "content": msg.get("content")})
        try:
            history = fix_message_list(history)
        except Exception:
            pass
        history.append({"role": "user", "content": user_text})
        return history

# Global sessions per channel
SESSIONS: Dict[int, AgentSession] = {}

async def get_session(channel_id: int) -> AgentSession:
    agent_type = os.getenv("CAI_AGENT_TYPE", "one_tool_agent")
    model = os.getenv("CAI_MODEL", "alias0")
    sess = SESSIONS.get(channel_id)
    if not sess or sess.agent_type != agent_type:
        sess = AgentSession(channel_id, agent_type, model)
        SESSIONS[channel_id] = sess
    else:
        if sess.model != model:
            update_agent_models_recursively(sess.agent, model)
            sess.model = model
    return sess

# ---- Messaging helpers -----------------------------------------------------
def _chunk_text(text: str, limit: int = 1900) -> List[str]:
    if not text:
        return [""]
    chunks: List[str] = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks

def _maybe_pretty_json(s: str) -> Tuple[str, Optional[str]]:
    """Return (formatted, ext) if JSON; else (original, None)."""
    try:
        obj = json.loads(s)
        return json.dumps(obj, ensure_ascii=False, indent=2), "json"
    except Exception:
        return s, None

def _build_tool_outputs(tool_outputs: List[Tuple[str, str]], small_limit: int = 1800) -> Tuple[str, List[discord.File]]:
    """
    tool_outputs: list of (label, content)
    Returns a tuple of (inline_snippets_md, files) where long outputs are attached as files.
    """
    inline_parts: List[str] = []
    files: List[discord.File] = []
    for idx, (label, content) in enumerate(tool_outputs, start=1):
        formatted, ext = _maybe_pretty_json(content or "")
        if len(formatted) > small_limit:
            fname = f"tool_output_{idx}.{ext or 'txt'}"
            bio = BytesIO(formatted.encode("utf-8"))
            files.append(discord.File(bio, filename=fname))
            inline_parts.append(f"\n\n**{label}** → attached `{fname}`")
        else:
            inline_parts.append(f"\n\n**{label}**\n```\n{formatted}\n```")
    return "".join(inline_parts), files

# ---- Discord bot setup -----------------------------------------------------
INTENTS = discord.Intents.default()
# Enable message content so the bot can respond to @mentions
INTENTS.message_content = True

class CAIBot(discord.Client):
    def __init__(self):
        super().__init__(intents=INTENTS)
        self.tree = app_commands.CommandTree(self)
        self.allowed_guild = int(os.getenv("ALLOWED_GUILD_ID", "0")) or None

    async def setup_hook(self) -> None:
        if self.allowed_guild:
            guild = discord.Object(id=self.allowed_guild)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (id={getattr(self.user, 'id', '?')}) | guilds={len(self.guilds)}")
        # If no allowed_guild configured, register commands per guild for instant availability
        if not self.allowed_guild:
            for g in self.guilds:
                try:
                    # Purge stale: clear then push empty to delete remote commands
                    self.tree.clear_commands(guild=g)
                    await self.tree.sync(guild=g)
                    # Reinstall current global set into guild
                    self.tree.copy_global_to(guild=g)
                    await self.tree.sync(guild=g)
                    logging.info(f"Slash commands synced to guild {g.name} ({g.id})")
                except Exception as e:
                    logging.warning(f"Guild sync failed for {getattr(g, 'id', '?')}: {e}")

    async def on_guild_join(self, guild: discord.Guild):
        # Sync commands immediately when the bot joins a new guild
        try:
            # Purge stale then reinstall
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logging.info(f"Slash commands synced on join: {guild.name} ({guild.id})")
        except Exception as e:
            logging.warning(f"Guild join sync failed for {getattr(guild, 'id', '?')}: {e}")

    async def on_message(self, message: discord.Message):
        # Ignore our own messages and non-mention messages
        if message.author.bot:
            return
        if not self.user or self.user not in getattr(message, "mentions", []):
            return

        channel_id = message.channel.id
        session = await get_session(channel_id)

        # Extract prompt by removing mentions
        content = message.content or ""
        for m in message.mentions:
            content = content.replace(f"<@{m.id}>", " ")
            content = content.replace(f"<@!{m.id}>", " ")
        prompt = content.strip()
        if not prompt:
            await message.reply("Provide a prompt after the mention.")
            return

        # Enforce turn cap
        max_turns_raw = os.getenv("CAI_MAX_TURNS", "inf")
        max_turns = float("inf") if max_turns_raw == "inf" else float(max_turns_raw)
        if session.turns >= max_turns:
            await message.reply(f"Turn limit reached ({int(max_turns) if max_turns!=float('inf') else '∞'}). Use /config to increase CAI_MAX_TURNS.")
            return

        async with session.lock:
            try:
                payload = session.build_history_context(prompt)
                stream_env = (os.getenv("CAI_STREAM", "false") or "false").lower() == "true"

                if stream_env:
                    typing = message.channel.typing()
                    await typing.__aenter__()
                    msg = await message.reply("Thinking…")
                    last_edit = 0.0

                    async def run_stream():
                        nonlocal last_edit
                        result = Runner.run_streamed(session.agent, payload)
                        stream = result.stream_events()
                        final_text = ""
                        tool_pairs: List[Tuple[str, str]] = []
                        try:
                            async for event in stream:
                                name = getattr(event, "name", "")
                                if name == "assistant_message_delta":
                                    delta = getattr(event.item, "delta", "") or ""
                                    final_text += delta
                                    now = asyncio.get_event_loop().time()
                                    if now - last_edit > 1.0:
                                        chunks = _chunk_text(final_text)
                                        await msg.edit(content=(chunks[-1] or "…"))
                                        last_edit = now
                                elif name == "tool_output":
                                    item = event.item
                                    if isinstance(item, ToolCallOutputItem):
                                        tool_pairs.append(("Tool Output", item.output or ""))
                        finally:
                            try:
                                chunks = _chunk_text(final_text)
                                inline, files = _build_tool_outputs(tool_pairs)
                                content = (chunks[-1] if chunks else "(no content)") + inline
                                await msg.edit(content=content)
                                for prev in chunks[:-1]:
                                    await message.reply(prev)
                                if files:
                                    await message.reply(files=files)
                            except Exception:
                                pass
                            try:
                                await typing.__aexit__(None, None, None)
                            except Exception:
                                pass
                        return True

                    await run_stream()
                else:
                    async with message.channel.typing():
                        resp = await Runner.run(session.agent, payload)
                    text = getattr(resp, "final_output", None) or "(no content)"
                    tool_pairs: List[Tuple[str, str]] = []
                    for item in getattr(resp, "new_items", []) or []:
                        if isinstance(item, ToolCallOutputItem):
                            tool_pairs.append(("Tool Output", item.output or ""))
                    chunks = _chunk_text(text)
                    inline, files = _build_tool_outputs(tool_pairs)
                    await message.reply((chunks[0] if chunks else "(no content)") + inline)
                    for extra in chunks[1:]:
                        await message.reply(extra)
                    if files:
                        await message.reply(files=files)

                session.turns += 1
            except Exception as e:
                try:
                    await message.reply(f"⚠️ Error: {e}")
                except Exception:
                    pass

bot = CAIBot()

# ---- Slash commands --------------------------------------------------------
@bot.tree.command(description="Ask the CAI agent in this channel")
@app_commands.describe(prompt="Your question or command for the agent")
async def ask(interaction: discord.Interaction, prompt: str):
    logging.info(f"/ask invoked by {getattr(interaction.user, 'id', '?')} in {interaction.channel_id}")
    await interaction.response.defer(thinking=True, ephemeral=False)
    channel_id = interaction.channel_id
    session = await get_session(channel_id)

    # Enforce per-channel turn cap
    max_turns_raw = os.getenv("CAI_MAX_TURNS", "inf")
    max_turns = float("inf") if max_turns_raw == "inf" else float(max_turns_raw)
    if session.turns >= max_turns:
        await interaction.followup.send(f"Turn limit reached ({int(max_turns) if max_turns!=float('inf') else '∞'}). Use /config to increase CAI_MAX_TURNS.")
        return

    async with session.lock:
        try:
            # Build input (carry over history)
            payload = session.build_history_context(prompt)

            # Stream or not
            stream_env = (os.getenv("CAI_STREAM", "false") or "false").lower() == "true"

            if stream_env:
                # Basic streamed editing: update a single message as tokens arrive
                # using periodic edits to avoid rate limits
                msg = await interaction.followup.send("Thinking…")
                last_edit = 0.0

                async def run_stream():
                    nonlocal last_edit
                    result = Runner.run_streamed(session.agent, payload)
                    stream = result.stream_events()
                    final_text = ""
                    tool_pairs: List[Tuple[str, str]] = []
                    try:
                        async for event in stream:
                            name = getattr(event, "name", "")
                            if name == "assistant_message_delta":
                                # accumulate text; edit at most ~1/sec
                                delta = getattr(event.item, "delta", "") or ""
                                final_text += delta
                                now = asyncio.get_event_loop().time()
                                if now - last_edit > 1.0:
                                    # Edit only the last chunk to keep under limits
                                    chunks = _chunk_text(final_text)
                                    await msg.edit(content=(chunks[-1] or "…"))
                                    last_edit = now
                            elif name == "tool_output":
                                item = event.item
                                if isinstance(item, ToolCallOutputItem):
                                    tool_pairs.append(("Tool Output", item.output or ""))
                    finally:
                        try:
                            chunks = _chunk_text(final_text)
                            inline, files = _build_tool_outputs(tool_pairs)
                            content = (chunks[-1] if chunks else "(no content)") + inline
                            await msg.edit(content=content)
                            # Send earlier chunks and files separately if needed
                            for prev in chunks[:-1]:
                                await interaction.followup.send(prev)
                            if files:
                                await interaction.followup.send(files=files)
                        except Exception:
                            pass
                    return True

                await run_stream()
            else:
                # Non-streaming path (simpler & robust)
                resp = await Runner.run(session.agent, payload)
                text = getattr(resp, "final_output", None) or "(no content)"
                tool_pairs: List[Tuple[str, str]] = []
                for item in getattr(resp, "new_items", []) or []:
                    if isinstance(item, ToolCallOutputItem):
                        tool_pairs.append(("Tool Output", item.output or ""))

                chunks = _chunk_text(text)
                inline, files = _build_tool_outputs(tool_pairs)
                # Send primary content
                await interaction.followup.send((chunks[0] if chunks else "(no content)") + inline)
                # Send remainder chunks
                for extra in chunks[1:]:
                    await interaction.followup.send(extra)
                # Attach files if any
                if files:
                    await interaction.followup.send(files=files)

            session.turns += 1
        except Exception as e:
            await interaction.followup.send(f"⚠️ Error: {e}")


@bot.tree.command(description="Switch the agent type for this channel")
@app_commands.describe(agent_name="Name returned by /agents (e.g. one_tool_agent)")
async def agent(interaction: discord.Interaction, agent_name: str):
    logging.info(f"/agent invoked: agent={agent_name} by {getattr(interaction.user, 'id', '?')} in {interaction.channel_id}")
    await interaction.response.defer(thinking=True, ephemeral=True)
    channel_id = interaction.channel_id
    # Force new session with requested agent
    model = os.getenv("CAI_MODEL", "alias0")
    SESSIONS[channel_id] = AgentSession(channel_id, agent_name, model)
    await interaction.followup.send(f"Agent switched to `{agent_name}` for this channel.")


@bot.tree.command(description="Set a CAI_* or CTF_* environment variable for this bot process")
@app_commands.describe(key="Env var (e.g. CAI_MAX_TURNS)", value="Value (e.g. 50)")
async def config(interaction: discord.Interaction, key: str, value: str):
    logging.info(f"/config invoked: {key} set by {getattr(interaction.user, 'id', '?')} in {interaction.channel_id}")
    await interaction.response.defer(thinking=True, ephemeral=True)
    key_upper = key.strip().upper()
    if not (key_upper.startswith("CAI_") or key_upper.startswith("CTF_")):
        await interaction.followup.send("Only CAI_* or CTF_* keys are allowed.")
        return
    os.environ[key_upper] = value
    # Apply model change to current session if relevant
    if key_upper in ("CAI_MODEL",):
        sess = await get_session(interaction.channel_id)
        update_agent_models_recursively(sess.agent, os.getenv("CAI_MODEL", "alias0"))
        sess.model = os.getenv("CAI_MODEL", "alias0")
    await interaction.followup.send(f"Set `{key_upper}={value}`")


@bot.tree.command(description="Reset the conversation (clears history) for this channel")
async def reset(interaction: discord.Interaction):
    logging.info(f"/reset invoked by {getattr(interaction.user, 'id', '?')} in {interaction.channel_id}")
    await interaction.response.defer(thinking=False, ephemeral=True)
    sess = await get_session(interaction.channel_id)
    sess.reset()
    await interaction.followup.send("History cleared for this channel.")


@bot.tree.command(description="Show basic info about the current session")
async def session(interaction: discord.Interaction):
    logging.info(f"/session invoked by {getattr(interaction.user, 'id', '?')} in {interaction.channel_id}")
    await interaction.response.defer(thinking=False, ephemeral=True)
    sess = await get_session(interaction.channel_id)
    max_turns_raw = os.getenv("CAI_MAX_TURNS", "inf")
    await interaction.followup.send(
        f"Agent: `{sess.agent_type}`\nModel: `{sess.model}`\nTurns: {sess.turns}/{max_turns_raw}"
    )


@bot.tree.command(description="List a few available agents by key (best-effort)")
async def agents(interaction: discord.Interaction):
    logging.info(f"/agents invoked by {getattr(interaction.user, 'id', '?')} in {interaction.channel_id}")
    from cai.agents import get_available_agents
    await interaction.response.defer(thinking=False, ephemeral=True)
    names = sorted(list(get_available_agents().keys()))[:25]
    if not names:
        await interaction.followup.send("No agents found in registry.")
        return
    await interaction.followup.send("Available agent keys:\n``" + ", ".join(names) + "```")


@bot.tree.command(description="Force-resync slash commands (admin-only)")
@app_commands.describe(purge="If true, removes old guild commands before re-adding")
async def sync(interaction: discord.Interaction, purge: bool = True):
    # Only allow server managers to sync
    perms_ok = False
    try:
        member = interaction.user  # discord.Member in guild context
        if isinstance(member, discord.Member):
            perms_ok = bool(member.guild_permissions.manage_guild or member.guild_permissions.administrator)
    except Exception:
        perms_ok = False

    if not perms_ok:
        await interaction.response.send_message("You need Manage Server permission to sync commands.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        if bot.allowed_guild:
            guild = discord.Object(id=bot.allowed_guild)
            if purge:
                bot.tree.clear_commands(guild=guild)
                await bot.tree.sync(guild=guild)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            await interaction.followup.send(f"Synced {len(synced)} commands to configured guild.")
        else:
            # If invoked in a guild, prefer per-guild purge/sync for instant results
            if interaction.guild_id:
                g = discord.Object(id=interaction.guild_id)
                if purge:
                    bot.tree.clear_commands(guild=g)
                    await bot.tree.sync(guild=g)
                bot.tree.copy_global_to(guild=g)
                synced = await bot.tree.sync(guild=g)
                await interaction.followup.send(f"Synced {len(synced)} commands to this guild.")
            else:
                # DM/global context – do a global sync (may take time to propagate; purge not supported here)
                synced = await bot.tree.sync()
                await interaction.followup.send(f"Synced {len(synced)} global commands (propagation can take up to ~1 hour).")
    except Exception as e:
        await interaction.followup.send(f"Sync failed: {e}")


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is required")
    logging.getLogger("discord").setLevel(logging.WARNING)
    bot.run(token)


if __name__ == "__main__":
    main()
