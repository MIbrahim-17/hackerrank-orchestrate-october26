"""Classify whether a request authorizes deletion (claude-haiku-5-5, single shot, structured JSON, cached).

Moved from gemini-3.8-flash on 2026-10-25: the Gemini key is free tier (20 requests/day). See DECISIONS.md.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from config import INTENT_EFFORT, INTENT_MODEL, INTENT_THINKING
from llm import call_claude
from prompts import INTENT_SCHEMA, INTENT_SYSTEM


def classify_intent(case_id: str, request_text: str, thinking: str = INTENT_THINKING,
                    effort: str = INTENT_EFFORT) -> dict[str, Any]:
    response = call_claude(purpose="intent", case_id=case_id, model=INTENT_MODEL, max_tokens=2000,
                           system=INTENT_SYSTEM, messages=[{"role": "user", "content": request_text}],
                           thinking={"type": thinking}, effort=effort, output_format=INTENT_SCHEMA,
                           prompt_cache=False)
    text = next((b["text"] for b in response["content"] if b["type"] == "text"), None)
    try:
        if response.get("stop_reason") not in ("end_turn", None) or text is None:
            raise ValueError(f"stop_reason={response.get('stop_reason')}")
        result = json.loads(text)
        intent = result["intent"]
    except (ValueError, KeyError, TypeError) as e:
        # Refusal, truncation or bad JSON: audit it as a deletion (the conservative choice; NOT_APPLICABLE would
        # drop every finding) and flag it so main.py reports it.
        return {"intent": "UNPARSEABLE", "authorizes_deletion": True, "language": "", "reason": str(e), "fallback": True}
    # The decision is the intent label; authorizes_deletion must agree with it.
    result["authorizes_deletion"] = intent == "DELETION"
    return result


def classify_many(items: list[tuple[str, str]], thinking: str = INTENT_THINKING, effort: str = INTENT_EFFORT,
                  workers: int = 8) -> dict[str, dict[str, Any]]:
    """{case_id: result} for [(case_id, request_text)], run in a thread pool (calls are cached on disk)."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(lambda item: classify_intent(item[0], item[1], thinking, effort), items)
        return dict(zip((cid for cid, _ in items), results))
