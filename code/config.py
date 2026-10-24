"""Paths, models and prices. Secrets come from the environment (.env), never from this file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

DATASET_DIR = REPO_ROOT / "dataset"
CACHE_DIR = REPO_ROOT / ".cache"
LLM_CACHE_DIR = CACHE_DIR / "llm"
OUTPUT_CSV = REPO_ROOT / "output.csv"

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "medium")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_INTENT_THINKING = os.getenv("GEMINI_INTENT_THINKING", "MINIMAL")  # lowest level that keeps intent at 100% on samples
GEMINI_IMAGE_THINKING = os.getenv("GEMINI_IMAGE_THINKING", "LOW")

# USD per 1M tokens. "cache_read" = cached input; "cache_write" = Anthropic 5-minute cache write (1.25x input).
PRICES: dict[str, dict[str, float | str | None]] = {
    "claude-sonnet-5-5": {
        "provider": "anthropic", "input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50,
        "source": "claude-api skill model table (cached 2026-10-06); looked up 2026-10-24",
    },
    "gemini-3.8-flash": {
        "provider": "google", "input": 0.75, "output": 3.75, "cache_read": 0.075, "cache_write": None,
        "source": "promotional rate valid to 2026-12-31 (user-supplied 2026-10-24); thinking tokens bill as output",
    },
}
