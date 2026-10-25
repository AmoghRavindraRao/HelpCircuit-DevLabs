"""Configuration and environment loading.

Reads a .env file (repo root and/or backend/) and resolves which LLM provider to
use. Whatever key the user supplies is auto-detected:

    OPENAI_API_KEY      -> OpenAI (or any OpenAI-compatible endpoint via LLM_BASE_URL)
    ANTHROPIC_API_KEY   -> Anthropic

Optional overrides:
    LLM_PROVIDER  = auto | openai | anthropic | none   (default: auto)
    LLM_MODEL     = model name (sensible per-provider default otherwise)
    LLM_BASE_URL  = custom OpenAI-compatible base URL (Groq, Together, local, ...)
    LLM_TIMEOUT   = seconds (default 30)
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # dotenv not installed yet
    def load_dotenv(*_args, **_kwargs):
        return False

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = Path(__file__).resolve().parent

# Load repo-root .env first, then backend/.env (backend overrides root).
load_dotenv(_ROOT / ".env")
load_dotenv(_BACKEND / ".env")


def _get(*names, default=None):
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return default


OPENAI_API_KEY = _get("OPENAI_API_KEY", "LLM_API_KEY")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")

# Discord bot settings
DISCORD_BOT_TOKEN = _get("DISCORD_BOT_TOKEN")
# Optional: a server (guild) id for INSTANT slash-command sync during development.
# Without it, global commands are used (can take up to ~1 hour to appear).
DISCORD_GUILD_ID = _get("DISCORD_GUILD_ID")
LLM_BASE_URL = _get("LLM_BASE_URL", "OPENAI_BASE_URL")
LLM_MODEL = _get("LLM_MODEL")
LLM_TIMEOUT = float(_get("LLM_TIMEOUT", default="30"))
_PROVIDER_PREF = (_get("LLM_PROVIDER", default="auto") or "auto").lower()

_DEFAULT_MODELS = {"openai": "gpt-4o-mini", "anthropic": "claude-3-5-haiku-latest"}


def resolve_provider():
    """Return (provider, model) where provider is 'openai' | 'anthropic' | 'none'."""
    if _PROVIDER_PREF == "none":
        return "none", None

    if _PROVIDER_PREF == "openai":
        provider = "openai" if OPENAI_API_KEY else "none"
    elif _PROVIDER_PREF == "anthropic":
        provider = "anthropic" if ANTHROPIC_API_KEY else "none"
    else:  # auto
        if OPENAI_API_KEY:
            provider = "openai"
        elif ANTHROPIC_API_KEY:
            provider = "anthropic"
        else:
            provider = "none"

    model = LLM_MODEL or _DEFAULT_MODELS.get(provider)
    return provider, model
