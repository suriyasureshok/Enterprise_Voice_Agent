"""
VOXOPS AI Gateway — LLM Client

Primary:  Google Gemini (via google-genai SDK)
Fallback: OpenRouter free-tier models (httpx → OpenAI-compatible API)

The rest of the codebase calls ``complete()`` and ``available()`` — those
signatures are unchanged.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

# ═══════════════════════════════════════════════════════════════════════════
#  GEMINI (primary) — uses new google-genai SDK
# ═══════════════════════════════════════════════════════════════════════════

_gemini_client = None

# Models to try in order — each has independent daily quota on free tier
_GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

# Track per-model daily exhaustion so we skip models known to be empty
_gemini_daily_exhausted: Dict[str, float] = {}  # model → timestamp
_DAILY_EXHAUSTION_RESET_SEC = 3600  # re-check after 1 hour


def _get_gemini_client():
    """Lazily initialise and cache the Gemini Client."""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    from google import genai
    from configs.settings import settings

    key = settings.gemini_api_key
    if not key:
        return None

    _gemini_client = genai.Client(api_key=key)
    return _gemini_client


def _strip_think(text: str) -> str:
    """Remove <think> tags from LLM output."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'<think>.*', '', text, flags=re.DOTALL).strip()
    return text


def _is_daily_exhausted(model_name: str) -> bool:
    """Check if a model's daily quota is known to be exhausted."""
    ts = _gemini_daily_exhausted.get(model_name)
    if ts is None:
        return False
    if time.time() - ts > _DAILY_EXHAUSTION_RESET_SEC:
        del _gemini_daily_exhausted[model_name]
        return False
    return True


def _parse_gemini_429(exc: Exception) -> tuple:
    """Parse a Gemini 429 error. Returns (is_daily, retry_seconds)."""
    msg = str(exc)
    is_daily = "PerDay" in msg
    retry_sec = 0.0
    # Extract retryDelay from error message
    import re as _re
    m = _re.search(r"retryDelay.*?'(\d+(?:\.\d+)?)s'", msg)
    if m:
        retry_sec = float(m.group(1))
    return is_daily, retry_sec


def _gemini_generate(
    contents,
    config,
) -> Optional[str]:
    """Try each Gemini model with smart rate-limit handling."""
    client = _get_gemini_client()
    if client is None:
        return None

    now = time.time()
    for model_name in _GEMINI_MODELS:
        if _is_daily_exhausted(model_name):
            logger.debug("Gemini [{}] — skipped (daily quota exhausted)", model_name)
            continue

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            text = _strip_think(response.text.strip()) if response.text else ""
            if text:
                logger.debug("Gemini [{}] response: {}", model_name, text[:200])
                return text
            logger.warning("Gemini [{}] returned empty content", model_name)
        except Exception as exc:
            is_daily, retry_sec = _parse_gemini_429(exc)
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                if is_daily:
                    _gemini_daily_exhausted[model_name] = now
                    logger.info("Gemini [{}] daily quota exhausted — skipping", model_name)
                elif retry_sec > 0 and retry_sec <= 45:
                    # Per-minute limit — wait and retry once
                    logger.info("Gemini [{}] per-minute limit — waiting {:.0f}s", model_name, retry_sec)
                    time.sleep(min(retry_sec + 1, 46))
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=config,
                        )
                        text = _strip_think(response.text.strip()) if response.text else ""
                        if text:
                            logger.debug("Gemini [{}] retry OK: {}", model_name, text[:200])
                            return text
                    except Exception:
                        _gemini_daily_exhausted[model_name] = now
                else:
                    logger.warning("Gemini [{}] rate limited: {}", model_name, str(exc)[:200])
            else:
                logger.warning("Gemini [{}] failed: {}", model_name, str(exc)[:200])
            continue

    return None


def _gemini_complete(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> Optional[str]:
    """Call Google Gemini (single-turn).  Returns text or None on failure."""
    from google.genai import types

    prompt = f"{system_prompt}\n\n---\n\n{user_message}"
    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    return _gemini_generate(prompt, config)


def _gemini_chat(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> Optional[str]:
    """Multi-turn chat via Gemini."""
    from google.genai import types

    client = _get_gemini_client()
    if client is None:
        return None

    # Build contents list for Gemini
    contents = []
    system_parts = []
    for m in messages:
        if m["role"] == "system":
            system_parts.append(m["content"])
        elif m["role"] == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=m["content"])]))
        else:  # assistant / model
            contents.append(types.Content(role="model", parts=[types.Part(text=m["content"])]))

    # Prepend system instructions into the first user message
    if system_parts and contents:
        prefix = "\n".join(system_parts)
        first = contents[0]
        first.parts[0] = types.Part(text=f"[System instructions]\n{prefix}\n\n{first.parts[0].text}")

    if not contents:
        return None

    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    return _gemini_generate(contents, config)


# ═══════════════════════════════════════════════════════════════════════════
#  OPENROUTER (fallback)
# ═══════════════════════════════════════════════════════════════════════════

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_SITE_URL = "https://voxops.ai"
_SITE_NAME = "VOXOPS AI Gateway"

_RATE_LIMIT_COOLDOWN_SEC = 15
_all_models_exhausted_at: float = 0.0

_FALLBACK_MODELS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "google/gemma-3-12b-it:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "qwen/qwen3-4b:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
]


def _or_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": _SITE_URL,
        "X-Title": _SITE_NAME,
    }


def _or_payload(messages, model, temperature, max_tokens):
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def _merge_system_to_user(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
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


def _openrouter_sync(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 25.0,
) -> str:
    """OpenRouter chat completion with fallback chain."""
    from configs.settings import settings

    api_key = settings.openrouter_api_key
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not configured.")

    global _all_models_exhausted_at
    if _all_models_exhausted_at and (time.time() - _all_models_exhausted_at) < _RATE_LIMIT_COOLDOWN_SEC:
        remaining = int(_RATE_LIMIT_COOLDOWN_SEC - (time.time() - _all_models_exhausted_at))
        raise RuntimeError(f"All LLM models rate-limited — cooldown {remaining}s remaining")

    _model = model or settings.llm_model_name
    _temperature = temperature if temperature is not None else settings.llm_temperature
    _max_tokens = max_tokens or settings.llm_max_tokens

    models_to_try = [_model] + [m for m in _FALLBACK_MODELS if m != _model]
    last_error = None

    for attempt_model in models_to_try:
        for retry in range(2):
            logger.debug("OpenRouter [{}] → {} messages (attempt {})", attempt_model, len(messages), retry + 1)
            try:
                adjusted_messages = messages
                if "gemma" in attempt_model.lower() and any(m["role"] == "system" for m in messages):
                    adjusted_messages = _merge_system_to_user(messages)

                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(
                        f"{OPENROUTER_BASE}/chat/completions",
                        json=_or_payload(adjusted_messages, attempt_model, _temperature, _max_tokens),
                        headers=_or_headers(api_key),
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    choice = data.get("choices", [{}])[0]
                    msg = choice.get("message", {})
                    content = (msg.get("content") or "").strip()
                    if not content:
                        break
                    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                    content = re.sub(r'<think>.*', '', content, flags=re.DOTALL).strip()
                    logger.debug("OpenRouter [{}] response: {}", attempt_model, content[:200])
                    return content

                if resp.status_code == 429:
                    logger.info("OpenRouter 429 on {} — trying next", attempt_model)
                    last_error = RuntimeError(f"429 for {attempt_model}")
                    if retry == 0:
                        time.sleep(1.5)
                        continue
                    break

                logger.warning("OpenRouter error {}: {}", resp.status_code, resp.text[:300])
                last_error = RuntimeError(f"{resp.status_code} for {attempt_model}")
                break

            except httpx.TimeoutException as exc:
                logger.warning("OpenRouter timeout on {}: {}", attempt_model, exc)
                last_error = exc
                break

    if last_error:
        _all_models_exhausted_at = time.time()
        raise last_error
    raise RuntimeError("All OpenRouter models exhausted")


# ═══════════════════════════════════════════════════════════════════════════
#  PUBLIC API  (unchanged signatures)
# ═══════════════════════════════════════════════════════════════════════════

def complete(
    system_prompt: str,
    user_message: str,
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Single-turn completion: system + user message.

    Tries Gemini first, then falls back to OpenRouter.
    """
    from configs.settings import settings
    _temp = temperature if temperature is not None else settings.llm_temperature
    _tokens = max_tokens or settings.llm_max_tokens

    # 1. Try Gemini
    result = _gemini_complete(system_prompt, user_message, temperature=_temp, max_tokens=_tokens)
    if result:
        return result

    # 2. Fallback → OpenRouter
    logger.info("Gemini unavailable — falling back to OpenRouter")
    return _openrouter_sync(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def chat_complete_sync(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 25.0,
) -> str:
    """Multi-turn chat completion.

    Tries Gemini first, then falls back to OpenRouter.
    """
    from configs.settings import settings
    _temp = temperature if temperature is not None else settings.llm_temperature
    _tokens = max_tokens or settings.llm_max_tokens

    # 1. Try Gemini
    result = _gemini_chat(messages, temperature=_temp, max_tokens=_tokens)
    if result:
        return result

    # 2. Fallback → OpenRouter
    logger.info("Gemini chat unavailable — falling back to OpenRouter")
    return _openrouter_sync(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def available() -> bool:
    """Return True if at least one LLM backend is configured."""
    try:
        from configs.settings import settings
        return bool(settings.gemini_api_key) or bool(settings.openrouter_api_key)
    except Exception:
        return False
