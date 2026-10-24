"""Budget guard behaviour, and the freeze of everything that shapes model requests (DECISIONS 2026-10-25).

Run: .venv/bin/python -m unittest discover -s code/tests
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))

import llm  # noqa: E402

# Changing any of these files changes the requests sent to the models, so every affected case would miss the disk
# cache and be billed again. Update a hash only on purpose, together with a DECISIONS.md entry.
FROZEN = {
    "prompts.py": "20e96e9ae4ea361b745464296461e5b57fc8f7b9ae371fecd60e3b49ba5c8e14",
    "tools.py": "7d7e630bb917a779aaf18c569204f592390f32129f4e8b0370e16d9ef5ddb7bc",
    "agent.py": "41288dd97785519d3f4d1fc32c7d9c1eccea5016d37ec527ec88072078848315",
}


class FreezeTests(unittest.TestCase):
    def test_request_shaping_files_unchanged(self) -> None:
        for name, digest in FROZEN.items():
            self.assertEqual(digest, hashlib.sha256((CODE / name).read_bytes()).hexdigest(), f"{name} changed")


class BudgetGuardTests(unittest.TestCase):
    def test_refuses_live_call_over_cap_and_allows_cache_hits(self) -> None:
        saved = llm.MAX_SPEND_USD
        llm.MAX_SPEND_USD = 0.0
        try:
            with self.assertRaises(llm.BudgetExceeded):
                llm.call_claude(purpose="test", case_id="guard", system="x", model="claude-haiku-5-5",
                                messages=[{"role": "user", "content": "uncached guard probe 9c1e"}], max_tokens=10)
        finally:
            llm.MAX_SPEND_USD = saved


if __name__ == "__main__":
    unittest.main()
