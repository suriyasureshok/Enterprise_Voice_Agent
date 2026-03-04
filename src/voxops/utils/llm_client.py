"""
VOXOPS AI Gateway — OpenRouter LLM Client

Provides synchronous and asynchronous helpers for calling free LLMs via
the OpenRouter API (https://openrouter.ai).

OpenRouter is fully compatible with the OpenAI Chat Completions API format.
We use `httpx` (already a project dependency) instead of the openai SDK to
avoid an extra dependency.

Free models used (configurable via LLM_MODEL_NAME in .env):
  - mistralai/mistral-7b-instruct:free   (default)
  - meta-llama/llama-3.1-8b-instruct:free
  - google/gemma-3-12b-it:free
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_SITE_URL = "https://voxops.ai"
_SITE_NAME = "VOXOPS AI Gateway"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": _SITE_URL,
        "X-Title": _SITE_NAME,
    }


def _payload(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


# ---------------------------------------------------------------------------
# Synchronous call (used by intent_parser, response_generator)
# ---------------------------------------------------------------------------

def chat_complete_sync(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 25.0,
) -> str:
    """
    Synchronous wrapper around the OpenRouter chat completions endpoint.

    Returns the assistant's text content, or raises an exception on failure.
    """
    from configs.settings import settings  # local import to avoid circular

    api_key = settings.openrouter_api_key
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not configured.")

    _model = model or settings.llm_model_name
    _temperature = temperature if temperature is not None else settings.llm_temperature
    _max_tokens = max_tokens or settings.llm_max_tokens

    logger.debug("OpenRouter [{model}] → {n} messages", model=_model, n=len(messages))

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{OPENROUTER_BASE}/chat/completions",
            json=_payload(messages, _model, _temperature, _max_tokens),
            headers=_headers(api_key),
        )

    if resp.status_code != 200:
        logger.warning("OpenRouter error {}: {}", resp.status_code, resp.text[:300])
        resp.raise_for_status()

    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()
    logger.debug("OpenRouter response: {}", content[:200])
    return content


# ---------------------------------------------------------------------------
# Asynchronous call (used by async FastAPI endpoints if needed)
# ---------------------------------------------------------------------------

async def chat_complete_async(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 25.0,
) -> str:
    """
    Async wrapper around the OpenRouter chat completions endpoint.
    """
    from configs.settings import settings

    api_key = settings.openrouter_api_key
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not configured.")

    _model = model or settings.llm_model_name
    _temperature = temperature if temperature is not None else settings.llm_temperature
    _max_tokens = max_tokens or settings.llm_max_tokens

    logger.debug("OpenRouter async [{model}] → {n} messages", model=_model, n=len(messages))

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE}/chat/completions",
            json=_payload(messages, _model, _temperature, _max_tokens),
            headers=_headers(api_key),
        )

    if resp.status_code != 200:
        logger.warning("OpenRouter async error {}: {}", resp.status_code, resp.text[:300])
        resp.raise_for_status()

    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()
    logger.debug("OpenRouter async response: {}", content[:200])
    return content


# ---------------------------------------------------------------------------
# Convenience: single-turn completion (system + user)
# ---------------------------------------------------------------------------

def complete(
    system_prompt: str,
    user_message: str,
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Shorthand: one system message + one user message."""
    return chat_complete_sync(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def available() -> bool:
    """Return True if the OpenRouter key is configured."""
    try:
        from configs.settings import settings
        return bool(settings.openrouter_api_key)
    except Exception:
        return False
