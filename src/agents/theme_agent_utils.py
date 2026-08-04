"""Shared helpers for bull/bear theme agents.

Default path is an explicit z-score heuristic (not LLM theater). Optional LLM
calls require ``BULL_BEAR_LLM_ENABLED=true``, a usable API key, and remaining
hourly/daily budget — otherwise agents stay heuristic and do not spend tokens.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Literal

from src.config import settings

logger = logging.getLogger(__name__)

ThemeSide = Literal["bull", "bear"]

HEURISTIC_SOURCE = "heuristic_stub"
LLM_SOURCE = "llm"
QUALITY_NON_LLM = "non_llm"
QUALITY_LLM = "llm"

_PLACEHOLDER_KEY_FRAGMENTS = (
    "",
    "your_",
    "changeme",
    "replace_me",
    "todo",
    "xxx",
    "placeholder",
)

# Process-local budget (shared by bull + bear). Not persisted across restarts.
_budget_lock = threading.Lock()
_budget_hour_bucket: int | None = None
_budget_day_bucket: int | None = None
_budget_hour_count = 0
_budget_day_count = 0


def reset_theme_llm_budget_for_tests() -> None:
    """Reset in-process LLM call counters (unit tests only)."""
    global _budget_hour_bucket, _budget_day_bucket, _budget_hour_count, _budget_day_count
    with _budget_lock:
        _budget_hour_bucket = None
        _budget_day_bucket = None
        _budget_hour_count = 0
        _budget_day_count = 0


def is_usable_llm_api_key(value: str | None) -> bool:
    key = str(value or "").strip()
    if not key:
        return False
    lowered = key.lower()
    if any(frag and frag in lowered for frag in _PLACEHOLDER_KEY_FRAGMENTS if frag):
        return False
    if lowered.startswith("your_") or lowered in {"test", "none", "null"}:
        return False
    return len(key) >= 12


def theme_llm_enabled() -> bool:
    return bool(getattr(settings, "BULL_BEAR_LLM_ENABLED", False))


def theme_llm_keys_available() -> bool:
    return is_usable_llm_api_key(getattr(settings, "GEMINI_API_KEY", "")) or is_usable_llm_api_key(
        getattr(settings, "OPENAI_API_KEY", "")
    )


def theme_llm_budget_status() -> dict[str, Any]:
    """Snapshot of remaining process-local LLM budget."""
    now = time.time()
    hour_bucket = int(now // 3600)
    day_bucket = int(now // 86400)
    max_hour = int(getattr(settings, "BULL_BEAR_LLM_MAX_CALLS_PER_HOUR", 4) or 0)
    max_day = int(getattr(settings, "BULL_BEAR_LLM_MAX_CALLS_PER_DAY", 20) or 0)

    with _budget_lock:
        hour_count = _budget_hour_count if _budget_hour_bucket == hour_bucket else 0
        day_count = _budget_day_count if _budget_day_bucket == day_bucket else 0

    return {
        "enabled": theme_llm_enabled(),
        "keys_available": theme_llm_keys_available(),
        "hour_count": hour_count,
        "day_count": day_count,
        "max_per_hour": max_hour,
        "max_per_day": max_day,
        "remaining_hour": max(0, max_hour - hour_count) if max_hour > 0 else 0,
        "remaining_day": max(0, max_day - day_count) if max_day > 0 else 0,
    }


def _try_consume_theme_llm_budget() -> tuple[bool, str]:
    """Atomically consume one LLM call slot. Returns (ok, reason)."""
    global _budget_hour_bucket, _budget_day_bucket, _budget_hour_count, _budget_day_count

    if not theme_llm_enabled():
        return False, "llm_disabled"
    if not theme_llm_keys_available():
        return False, "no_usable_api_key"

    max_hour = int(getattr(settings, "BULL_BEAR_LLM_MAX_CALLS_PER_HOUR", 4) or 0)
    max_day = int(getattr(settings, "BULL_BEAR_LLM_MAX_CALLS_PER_DAY", 20) or 0)
    if max_hour <= 0 or max_day <= 0:
        return False, "budget_caps_zero"

    now = time.time()
    hour_bucket = int(now // 3600)
    day_bucket = int(now // 86400)

    with _budget_lock:
        if _budget_hour_bucket != hour_bucket:
            _budget_hour_bucket = hour_bucket
            _budget_hour_count = 0
        if _budget_day_bucket != day_bucket:
            _budget_day_bucket = day_bucket
            _budget_day_count = 0

        if _budget_hour_count >= max_hour:
            return False, "hourly_budget_exhausted"
        if _budget_day_count >= max_day:
            return False, "daily_budget_exhausted"

        _budget_hour_count += 1
        _budget_day_count += 1
        return True, "ok"


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _signal_z(signal_context: dict | None) -> float:
    try:
        return abs(float((signal_context or {}).get("z_score", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def heuristic_confidence(side: ThemeSide, signal_context: dict | None) -> float:
    """Deterministic z-score heuristic — not fixed theater constants.

    Mean-reversion framing:
    - bull confidence rises with dislocation magnitude (entry support);
    - bear confidence rises once |z| exceeds a mild break risk floor.
    """
    z = _signal_z(signal_context)
    if side == "bull":
        # Formerly hardcoded 0.7; now context-sensitive and labeled non-LLM.
        return _clamp_confidence(0.40 + 0.10 * min(z, 4.0))
    # Formerly hardcoded 0.4; stronger when |z| looks structurally extreme.
    return _clamp_confidence(0.25 + 0.12 * min(max(z - 1.5, 0.0), 4.0))


def heuristic_argument(side: ThemeSide, signal_context: dict | None) -> str:
    z = _signal_z(signal_context)
    pair = (
        f"{(signal_context or {}).get('ticker_a', '?')}/"
        f"{(signal_context or {}).get('ticker_b', '?')}"
    )
    if side == "bull":
        return (
            f"Heuristic (non-LLM): |z|={z:.2f} on {pair} supports a mean-reversion "
            "entry thesis; confidence is z-scaled, not model-scored."
        )
    return (
        f"Heuristic (non-LLM): |z|={z:.2f} on {pair} may reflect structural break "
        "risk rather than clean reversion; confidence is z-scaled, not model-scored."
    )


def build_theme_result(
    *,
    side: ThemeSide,
    confidence: float,
    argument: str,
    source: str,
    quality: str,
    llm_used: bool,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "confidence": _clamp_confidence(confidence),
        "argument": argument,
        "reasoning": argument,
        "source": source,
        "quality": quality,
        "llm_used": bool(llm_used),
        "side": side,
        "active": True,
        "status": "heuristic" if source == HEURISTIC_SOURCE else "llm",
    }
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    return result


def is_heuristic_theme_verdict(verdict: dict | None) -> bool:
    """True when bull/bear output is explicitly non-LLM (or unlabeled legacy stub)."""
    if not isinstance(verdict, dict):
        return True
    if verdict.get("llm_used") is True and verdict.get("source") == LLM_SOURCE:
        return False
    source = verdict.get("source")
    quality = verdict.get("quality")
    if source == HEURISTIC_SOURCE or quality == QUALITY_NON_LLM:
        return True
    if source == LLM_SOURCE and quality == QUALITY_LLM:
        return False
    # Legacy unlabeled payloads (old 0.7/0.4 theater) are treated as non-LLM.
    return True


async def evaluate_theme(side: ThemeSide, signal_context: dict | None) -> dict[str, Any]:
    """Evaluate bull or bear theme with heuristic default and optional capped LLM."""
    heuristic = build_theme_result(
        side=side,
        confidence=heuristic_confidence(side, signal_context),
        argument=heuristic_argument(side, signal_context),
        source=HEURISTIC_SOURCE,
        quality=QUALITY_NON_LLM,
        llm_used=False,
    )

    allowed, reason = _try_consume_theme_llm_budget()
    if not allowed:
        if reason != "llm_disabled":
            heuristic["fallback_reason"] = reason
            logger.debug(
                "Theme %s agent staying heuristic (%s) signal_id=%s",
                side,
                reason,
                (signal_context or {}).get("signal_id", "N/A"),
            )
        return heuristic

    try:
        llm_result = await _call_theme_llm(side, signal_context)
        if llm_result is None:
            heuristic["fallback_reason"] = "llm_returned_empty"
            return heuristic
        return llm_result
    except Exception as exc:
        logger.warning("Theme %s LLM call failed; using heuristic: %s", side, exc)
        heuristic["fallback_reason"] = f"llm_error:{type(exc).__name__}"
        return heuristic


async def _call_theme_llm(side: ThemeSide, signal_context: dict | None) -> dict[str, Any] | None:
    """Best-effort Gemini (preferred) or OpenAI JSON theme score.

    Budget already consumed by the caller. Failures return None so the agent
    falls back to the heuristic without retry-spamming.
    """
    ctx = signal_context or {}
    z = _signal_z(ctx)
    prompt = (
        f"You are the {side} analyst for a statistical-arbitrage pair trade.\n"
        f"Pair: {ctx.get('ticker_a')}/{ctx.get('ticker_b')}\n"
        f"z_score: {ctx.get('z_score')}\n"
        f"|z|: {z:.3f}\n"
        f"sector: {ctx.get('sector', 'Unassigned')}\n"
        "Return ONLY compact JSON: "
        '{"confidence": <float 0..1>, "argument": "<one short sentence>"}'
    )

    gemini_key = str(getattr(settings, "GEMINI_API_KEY", "") or "")
    openai_key = str(getattr(settings, "OPENAI_API_KEY", "") or "")

    raw_text: str | None = None
    provider = None

    if is_usable_llm_api_key(gemini_key):
        provider = "gemini"
        raw_text = await _gemini_generate(gemini_key, prompt)
    elif is_usable_llm_api_key(openai_key):
        provider = "openai"
        raw_text = await _openai_generate(openai_key, prompt)

    if not raw_text:
        return None

    parsed = _parse_theme_llm_json(raw_text)
    if parsed is None:
        return None

    confidence = _clamp_confidence(float(parsed.get("confidence", 0.5)))
    argument = str(parsed.get("argument") or parsed.get("reasoning") or "").strip()
    if not argument:
        argument = f"LLM {side} theme score ({provider}) without free-text argument."

    return build_theme_result(
        side=side,
        confidence=confidence,
        argument=argument,
        source=LLM_SOURCE,
        quality=QUALITY_LLM,
        llm_used=True,
        fallback_reason=None,
    ) | {"llm_provider": provider}


def _parse_theme_llm_json(raw_text: str) -> dict[str, Any] | None:
    try:
        from src.utils import extract_json

        data = extract_json(raw_text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


async def _gemini_generate(api_key: str, prompt: str) -> str | None:
    import asyncio
    import warnings

    def _sync() -> str | None:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"\n\nAll support for the `google\.generativeai` package has ended\..*",
                category=FutureWarning,
            )
            import google.generativeai as genai

        genai.configure(api_key=api_key)
        model_name = str(
            getattr(settings, "BULL_BEAR_LLM_MODEL_GEMINI", "gemini-1.5-flash") or "gemini-1.5-flash"
        )
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        return getattr(response, "text", None) or str(response)

    return await asyncio.to_thread(_sync)


async def _openai_generate(api_key: str, prompt: str) -> str | None:
    import asyncio

    def _sync() -> str | None:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model_name = str(
            getattr(settings, "BULL_BEAR_LLM_MODEL_OPENAI", "gpt-4o-mini") or "gpt-4o-mini"
        )
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=120,
        )
        choice = completion.choices[0].message.content if completion.choices else None
        return choice

    return await asyncio.to_thread(_sync)
