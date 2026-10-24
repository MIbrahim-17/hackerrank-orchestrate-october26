"""The only place that talks to model APIs: call_claude and call_gemini.

Both share one disk cache (.cache/llm/<sha256 of the request>.json) and one usage ledger. A cache hit
returns the stored response with zero API calls, and its ledger row keeps the original token counts
(from_disk=True), so usage reports always describe the full run. Because the tools are deterministic, an
unchanged case replays its whole tool loop from disk for free.

Ledger token fields (normalized across providers):
  input_tokens       uncached input billed at the full input rate
  cache_read_tokens  input served from the provider's prompt cache
  cache_write_tokens input written to the prompt cache (Anthropic only)
  output_tokens      visible output plus thinking tokens (both bill as output)
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from config import CLAUDE_EFFORT, CLAUDE_MODEL, GEMINI_MODEL, LLM_CACHE_DIR, MAX_SPEND_USD, PRICES

LEDGER: list[dict[str, Any]] = []
_budget = {"spent": None, "reserved": 0.0}  # spent: priced total of every billed call (one disk-cache file each)
OFFLINE = False  # True: serve only from the disk cache and raise on a miss (used by --no-llm)
_LOCK = threading.Lock()
_clients: dict[str, Any] = {}


class BudgetExceeded(RuntimeError):
    """Raised instead of making a live call that could push total spend over MAX_SPEND_USD."""


def usage_cost(usage: dict[str, Any]) -> float:
    p = PRICES[usage["model"]]
    return (usage["input_tokens"] * p["input"] + usage["output_tokens"] * p["output"]
            + usage["cache_read_tokens"] * p["cache_read"] + usage["cache_write_tokens"] * (p["cache_write"] or 0)) / 1e6


def spent_so_far() -> float:
    """Priced total of every billed call. Each live call writes exactly one cache file, so the cache is the ledger."""
    with _LOCK:
        if _budget["spent"] is None:
            _budget["spent"] = sum(usage_cost(json.loads(f.read_text(encoding="utf-8"))["usage"])
                                   for f in LLM_CACHE_DIR.glob("*.json")) if LLM_CACHE_DIR.exists() else 0.0
        return _budget["spent"]


def _reserve(model: str, request: dict[str, Any], max_output: int) -> float:
    """Conservative pre-call estimate (all input at full price, a capped output) checked against the budget."""
    p = PRICES[model]
    estimate = (len(json.dumps(request, default=str)) / 3 * p["input"] + min(max_output, 4000) * p["output"]) / 1e6
    spent = spent_so_far()
    with _LOCK:
        if spent + _budget["reserved"] + estimate > MAX_SPEND_USD:
            raise BudgetExceeded(f"spent ${spent:.4f} + in-flight ${_budget['reserved']:.4f} + next call "
                                 f"~${estimate:.4f} would exceed MAX_SPEND_USD ${MAX_SPEND_USD:.2f}")
        _budget["reserved"] += estimate
    return estimate


def _settle(estimate: float, usage: dict[str, Any]) -> None:
    with _LOCK:
        _budget["reserved"] -= estimate
        _budget["spent"] += usage_cost(usage)


def _cache_file(provider: str, request: dict[str, Any]) -> Path:
    blob = json.dumps({"provider": provider, **request}, sort_keys=True, ensure_ascii=False, default=str)
    return LLM_CACHE_DIR / f"{hashlib.sha256(blob.encode()).hexdigest()}.json"


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _save(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _record(provider: str, purpose: str, case_id: str, usage: dict[str, Any], from_disk: bool) -> None:
    with _LOCK:
        LEDGER.append({"provider": provider, "purpose": purpose, "case_id": case_id, "from_disk": from_disk, **usage})


def _client(provider: str) -> Any:
    with _LOCK:
        if provider not in _clients:
            if provider == "anthropic":
                import anthropic
                if not os.getenv("ANTHROPIC_API_KEY"):
                    raise RuntimeError("ANTHROPIC_API_KEY is not set (add it to .env)")
                _clients[provider] = anthropic.Anthropic(max_retries=5)
            else:
                from google import genai
                key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")  # the SDK's two standard names
                if not key:
                    raise RuntimeError("GEMINI_API_KEY is not set (add it to .env)")
                _clients[provider] = genai.Client(api_key=key)
        return _clients[provider]


def call_claude(*, purpose: str, case_id: str, system: list[dict] | str, messages: list[dict],
                tools: list[dict] | None = None, max_tokens: int = 16000, effort: str = CLAUDE_EFFORT,
                model: str = CLAUDE_MODEL, thinking: dict | None = None,
                output_format: dict | None = None, prompt_cache: bool = True) -> dict[str, Any]:
    """One Messages API turn. Returns the response as a plain dict (content blocks can be appended to messages as-is).

    `output_format` is a JSON schema for structured output (the reply's text block is then valid JSON).
    `prompt_cache=False` drops the API prompt-cache marker (single-shot calls never reuse a prefix); the disk cache
    is unaffected.
    """
    output_config: dict[str, Any] = {"effort": effort}
    if output_format:
        output_config["format"] = {"type": "json_schema", "schema": output_format}
    request: dict[str, Any] = {
        "model": model, "max_tokens": max_tokens, "system": system, "messages": messages,
        "output_config": output_config,
    }
    if prompt_cache:
        request["cache_control"] = {"type": "ephemeral"}
    if tools:
        request["tools"] = tools
    if thinking:
        request["thinking"] = thinking
    path = _cache_file("anthropic", request)
    cached = _load(path)
    if cached is None and OFFLINE:
        raise RuntimeError(f"offline mode: no cached Claude response for {purpose} {case_id}")
    if cached is None:
        estimate = _reserve(model, request, max_tokens)
        try:
            response = _client("anthropic").messages.create(**request)  # one fixed model, no refusal fallback
        except Exception:
            with _LOCK:
                _budget["reserved"] -= estimate
            raise
        u = response.usage
        cached = {"response": response.to_dict(), "usage": {
            "model": response.model,
            "input_tokens": u.input_tokens or 0,
            "cache_read_tokens": u.cache_read_input_tokens or 0,
            "cache_write_tokens": u.cache_creation_input_tokens or 0,
            "output_tokens": u.output_tokens or 0,
        }}
        _save(path, cached)
        _settle(estimate, cached["usage"])
        _record("anthropic", purpose, case_id, cached["usage"], from_disk=False)
    else:
        _record("anthropic", purpose, case_id, cached["usage"], from_disk=True)
    return cached["response"]


def call_gemini(*, purpose: str, case_id: str, system: str, parts: list[str | Path], schema: dict[str, Any],
                thinking_level: str, model: str = GEMINI_MODEL) -> dict[str, Any]:
    """One single-shot generate_content call with structured JSON output. `parts` are text or image file paths."""
    keyed_parts = [p if isinstance(p, str) else {"image_sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
                   for p in parts]
    request = {"model": model, "system": system, "parts": keyed_parts, "schema": schema, "thinking": thinking_level}
    path = _cache_file("google", request)
    cached = _load(path)
    if cached is None and OFFLINE:
        raise RuntimeError(f"offline mode: no cached Gemini response for {purpose} {case_id}")
    if cached is None:
        from google.genai import types
        estimate = _reserve(model, request, 4000)
        contents = [p if isinstance(p, str) else types.Part.from_bytes(data=Path(p).read_bytes(), mime_type="image/png")
                    for p in parts]
        response = _client("google").models.generate_content(
            model=model, contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
                thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
            ),
        )
        u = response.usage_metadata
        prompt, cached_in = u.prompt_token_count or 0, u.cached_content_token_count or 0
        cached = {"response": json.loads(response.text), "usage": {
            "model": model,
            "input_tokens": prompt - cached_in,
            "cache_read_tokens": cached_in,
            "cache_write_tokens": 0,
            "output_tokens": (u.candidates_token_count or 0) + (u.thoughts_token_count or 0),
        }}
        _save(path, cached)
        _settle(estimate, cached["usage"])
        _record("google", purpose, case_id, cached["usage"], from_disk=False)
    else:
        _record("google", purpose, case_id, cached["usage"], from_disk=True)
    return cached["response"]
