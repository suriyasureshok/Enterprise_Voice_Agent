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

import time

import httpx
from loguru import logger

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_SITE_URL = "https://voxops.ai"
_SITE_NAME = "VOXOPS AI Gateway"

# Rate-limit cooldown: when ALL models get 429, skip LLM calls for this period
_RATE_LIMIT_COOLDOWN_SEC = 60  # seconds
_all_models_exhausted_at: float = 0.0  # timestamp of last exhaustion

# Fallback chain: if primary model is rate-limited, try these in order
# Prefer instruction-following models that output JSON directly
_FALLBACK_MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "google/gemma-3-12b-it:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "qwen/qwen3-4b:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
]


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

    Includes automatic retry with exponential backoff and fallback to
    alternative free models if the primary model is rate-limited (429).

    Returns the assistant's text content, or raises an exception on failure.
    """
    from configs.settings import settings  # local import to avoid circular

    api_key = settings.openrouter_api_key
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not configured.")

    # Fast-fail if all models were recently rate-limited
    global _all_models_exhausted_at
    if _all_models_exhausted_at and (time.time() - _all_models_exhausted_at) < _RATE_LIMIT_COOLDOWN_SEC:
        remaining = int(_RATE_LIMIT_COOLDOWN_SEC - (time.time() - _all_models_exhausted_at))
        raise RuntimeError(f"All LLM models rate-limited — cooldown {remaining}s remaining")

    _model = model or settings.llm_model_name
    _temperature = temperature if temperature is not None else settings.llm_temperature
    _max_tokens = max_tokens or settings.llm_max_tokens

    # Build ordered list of models to try: primary first, then fallbacks
    models_to_try = [_model] + [m for m in _FALLBACK_MODELS if m != _model]

    last_error = None
    for attempt_model in models_to_try:
        for retry in range(2):  # up to 1 retry per model
            logger.debug(
                "OpenRouter [{model}] → {n} messages (attempt {r})",
                model=attempt_model, n=len(messages), r=retry + 1,
            )
            try:
                # Some models (Gemma) don't support system role — convert if needed
                adjusted_messages = messages
                if "gemma" in attempt_model.lower() and any(m["role"] == "system" for m in messages):
                    adjusted_messages = _merge_system_to_user(messages)

                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(
                        f"{OPENROUTER_BASE}/chat/completions",
                        json=_payload(adjusted_messages, attempt_model, _temperature, _max_tokens),
                        headers=_headers(api_key),
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    choice = data.get("choices", [{}])[0]
                    msg = choice.get("message", {})
                    content = msg.get("content") or ""
                    # Some models put output in a "reasoning" or thinking field
                    if not content and msg.get("reasoning"):
                        content = msg["reasoning"]
                    content = content.strip()
                    if not content:
                        logger.warning("OpenRouter [{}] returned empty content, raw: {}", attempt_model, data)
                        break  # try next model
                    logger.debug("OpenRouter [{}] response: {}", attempt_model, content[:200])
                    return content

                if resp.status_code == 429:
                    logger.info("OpenRouter 429 rate-limit on {} — trying next", attempt_model)
                    last_error = httpx.HTTPStatusError(
                        f"429 for {attempt_model}", request=resp.request, response=resp
                    )
                    if retry == 0:
                        time.sleep(1.5)  # brief backoff before retry on same model
                        continue
                    break  # move to next model

                # Other error — don't retry, move on
                logger.warning("OpenRouter error {}: {}", resp.status_code, resp.text[:300])
                last_error = httpx.HTTPStatusError(
                    f"{resp.status_code} for {attempt_model}", request=resp.request, response=resp
                )
                break

            except httpx.TimeoutException as exc:
                logger.warning("OpenRouter timeout on {}: {}", attempt_model, exc)
                last_error = exc
                break

    # All models exhausted
    if last_error:
        _all_models_exhausted_at = time.time()
        logger.warning("All LLM models exhausted — entering {}s cooldown", _RATE_LIMIT_COOLDOWN_SEC)
        raise last_error
    raise RuntimeError("All OpenRouter models exhausted")


def _merge_system_to_user(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Merge system messages into the first user message for models that don't support system role."""
    system_parts = []
    other_msgs = []
    for m in messages:
        if m["role"] == "system":
            system_parts.append(m["content"])
        else:
            other_msgs.append(m)
    if system_parts and other_msgs:
        prefix = "\n".join(system_parts)
        other_msgs[0] = {
            "role": other_msgs[0]["role"],
            "content": f"[Instructions: {prefix}]\n\n{other_msgs[0]['content']}",
        }
    return other_msgs or messages


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
