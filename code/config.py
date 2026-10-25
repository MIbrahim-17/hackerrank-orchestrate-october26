"""Paths, models and prices. Secrets come from the environment (.env), never from this file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

DATASET_DIR = REPO_ROOT / "dataset"
CACHE_DIR = REPO_ROOT / ".cache"
LLM_CACHE_DIR = Path(__file__).resolve().parent / "cache" / "llm"  # shipped in code.zip so the run replays offline at $0
OUTPUT_CSV = REPO_ROOT / "output.csv"

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "medium")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_SPEND_USD = float(os.getenv("MAX_SPEND_USD", "4.50"))  # hard cap on total priced spend, past calls included
INTENT_MODEL = os.getenv("INTENT_MODEL", "claude-haiku-5-5")
INTENT_THINKING = os.getenv("INTENT_THINKING", "adaptive")  # disabled/low and adaptive/low miss case_27
INTENT_EFFORT = os.getenv("INTENT_EFFORT", "medium")  # lowest effort with 38/38 on samples + custom
GEMINI_IMAGE_THINKING = os.getenv("GEMINI_IMAGE_THINKING", "LOW")

# USD per 1M tokens. "cache_read" = cached input; "cache_write" = Anthropic 5-minute cache write (1.25x input).
PRICES: dict[str, dict[str, float | str | None]] = {
    "claude-sonnet-5-5": {
        "provider": "anthropic", "input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50,
        "source": "claude-api skill model table (cached 2026-10-06); looked up 2026-10-24",
    },
    "claude-haiku-5-5": {
        "provider": "anthropic", "input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125,
        "source": "claude-api skill migration guide (prompts <=100K tokens; $0.50/$2.50 above), looked up 2026-10-25",
    },
    "gemini-3.8-flash": {
        "provider": "google", "input": 0.75, "output": 3.75, "cache_read": 0.075, "cache_write": None,
        "source": "promotional rate valid to 2026-12-31 (user-supplied 2026-10-24); thinking tokens bill as output",
    },
}
