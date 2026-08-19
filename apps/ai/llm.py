"""
LLM integration via OpenRouter's OpenAI-compatible API.

Primary:  nvidia/nemotron-3.5-lightning:free  (OPENROUTER_API_KEY)
Fallback: z-ai/glm-5.2:free                  (OPENROUTER_API_KEY_2)

If the primary model returns an error or times out, call_llm()
automatically retries with the fallback model and second API key.
"""

import logging

from django.conf import settings

from openai import OpenAI

log = logging.getLogger(__name__)


class LLMAvailabilityError(Exception):
    """Raised when all LLM clients fail."""


_client = None
_fallback_client = None

# ── Model configuration ─────────────────────────────────────────────

LLM_MODEL = getattr(settings, "LLM_MODEL", "nvidia/nemotron-3.5-lightning:free")
FALLBACK_LLM_MODEL = getattr(settings, "FALLBACK_LLM_MODEL", "z-ai/glm-5.2:free")


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = getattr(settings, "OPENROUTER_API_KEY", None)
        if not api_key:
            raise LLMAvailabilityError(
                "OPENROUTER_API_KEY is not configured. "
                "Set it in your .env file or Django settings."
            )
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    return _client


def _get_fallback_client() -> OpenAI | None:
    global _fallback_client
    api_key = getattr(settings, "OPENROUTER_API_KEY_2", None)
    if not api_key:
        return None
    if _fallback_client is None:
        _fallback_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    return _fallback_client


def _try_call(client: OpenAI, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        timeout=60,
    )
    content = response.choices[0].message.content
    if not content:
        raise LLMAvailabilityError("LLM returned an empty response.")
    return content


def call_llm(prompt: str, *, model: str | None = None) -> str:
    """
    Send a prompt to the primary LLM, falling back to the secondary
    model + key if the primary fails.

    Raises LLMAvailabilityError only when BOTH models fail.
    """
    if not prompt or not prompt.strip():
        raise LLMAvailabilityError("Cannot call LLM with an empty prompt.")

    primary_model = model or LLM_MODEL

    # ── Primary ──
    try:
        client = _get_client()
        return _try_call(client, primary_model, prompt)
    except Exception as exc:
        log.warning("Primary LLM (%s) failed: %s", primary_model, exc)

    # ── Fallback ──
    fallback_model = getattr(settings, "FALLBACK_LLM_MODEL", FALLBACK_LLM_MODEL)
    if model:
        raise LLMAvailabilityError(
            f"Explicit model '{model}' failed."
        )
    try:
        client = _get_fallback_client()
        if client is None:
            raise LLMAvailabilityError("No fallback API key configured.")
        return _try_call(client, fallback_model, prompt)
    except LLMAvailabilityError:
        raise
    except Exception as exc:
        log.warning("Fallback LLM (%s) failed: %s", fallback_model, exc)
        raise LLMAvailabilityError(
            f"Both LLMs failed. Primary and fallback both unavailable."
        ) from exc
