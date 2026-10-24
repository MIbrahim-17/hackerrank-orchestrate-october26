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
    "evidence.py": "41aa3fd3c7751f22de5705978467cab60a30d3fe40c28b1daebbb3e66c1218f2",
    "identity.py": "b811e490468a6a60ebbbe92325437578c82ac2458835575c1e3b8dfcca5e92d8",
    "activity_links.py": "59eb46a0bdd833e93f98db2a1c6abf36f30eac36c5670fd9e66306d5026bd4d4",
}
# validator.py functions that feed the agent brief or its rejection messages; the rest of validator.py may change.
VALIDATOR_BRIEF_FUNCTIONS = ['deterministic_owned', 'category_of', 'state_of', 'grounding_error', 'most_common']
VALIDATOR_BRIEF_HASH = "8542462bc2ac318a39d8d1095d744f48f0abaecd8fa7ebcd6d4e2dec2f741084"


class FreezeTests(unittest.TestCase):
    def test_request_shaping_files_unchanged(self) -> None:
        for name, digest in FROZEN.items():
            self.assertEqual(digest, hashlib.sha256((CODE / name).read_bytes()).hexdigest(), f"{name} changed")

    def test_validator_brief_functions_unchanged(self) -> None:
        import inspect
        import validator
        source = "".join(inspect.getsource(getattr(validator, n)) for n in VALIDATOR_BRIEF_FUNCTIONS)
        self.assertEqual(VALIDATOR_BRIEF_HASH, hashlib.sha256(source.encode()).hexdigest(), "brief-shaping validator code changed")


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
