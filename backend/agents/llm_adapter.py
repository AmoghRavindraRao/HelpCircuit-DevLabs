"""Provider-agnostic LLM client.

Supports OpenAI (and any OpenAI-compatible endpoint via LLM_BASE_URL) and
Anthropic. Clients are imported lazily so a missing SDK never breaks startup.
All calls return a parsed JSON dict, or None on any failure, so callers can fall
back to deterministic behavior.
"""

import json
import logging

import config

log = logging.getLogger("helpcircuit.llm")


class LLMAdapter:
    def __init__(self):
        self.provider, self.model = config.resolve_provider()
        self._client = None
        self._init_error = None
        self.enabled = self.provider != "none"
        if self.enabled:
            try:
                self._client = self._build_client()
            except Exception as exc:  # pragma: no cover - depends on env
                self._init_error = str(exc)
                self.enabled = False
                log.warning("LLM disabled (%s): %s", self.provider, exc)

    # -- client construction -------------------------------------------------

    def _build_client(self):
        if self.provider == "openai":
            from openai import OpenAI
            kwargs = {"api_key": config.OPENAI_API_KEY, "timeout": config.LLM_TIMEOUT}
            if config.LLM_BASE_URL:
                kwargs["base_url"] = config.LLM_BASE_URL
            return OpenAI(**kwargs)
        if self.provider == "anthropic":
            from anthropic import Anthropic
            return Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=config.LLM_TIMEOUT)
        raise RuntimeError(f"Unknown provider {self.provider!r}")

    # -- public API ----------------------------------------------------------

    def status(self):
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "error": self._init_error,
        }

    def chat_json(self, system_prompt, user_prompt, retries=1):
        """Return a parsed JSON object from the model, or None on failure."""
        if not self.enabled:
            return None
        for attempt in range(retries + 1):
            try:
                raw = self._raw_call(system_prompt, user_prompt)
                return self._parse_json(raw)
            except Exception as exc:  # pragma: no cover - network dependent
                log.warning("LLM call failed (attempt %d): %s", attempt + 1, exc)
        return None

    # -- provider calls ------------------------------------------------------

    def _raw_call(self, system_prompt, user_prompt):
        if self.provider == "openai":
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content
        if self.provider == "anthropic":
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=400,
                temperature=0.2,
                system=system_prompt + "\nRespond with a single JSON object only.",
                messages=[{"role": "user", "content": user_prompt}],
            )
            return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        raise RuntimeError(f"Unknown provider {self.provider!r}")

    @staticmethod
    def _parse_json(raw):
        if not raw:
            return None
        text = raw.strip()
        # Tolerate code fences or surrounding prose.
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        return json.loads(text)
