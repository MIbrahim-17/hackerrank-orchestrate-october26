"""The full pipeline must not depend on set/dict iteration order or string hashing (DECISIONS 2026-10-25).

Runs main.py twice from the disk cache (--offline: agent included, any cache miss is an error) with different
PYTHONHASHSEED values and asserts the outputs are byte-identical to each other and to the committed output.csv.
Needs the cache from the final run. Run: .venv/bin/python -m unittest discover -s code/tests -p "test_determinism.py"
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run_offline(out: Path, seed: str) -> None:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    proc = subprocess.run([sys.executable, str(REPO / "code" / "main.py"), "--offline", "--out", str(out)],
                          cwd=REPO, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"seed {seed} failed:\n{proc.stdout}\n{proc.stderr[-2000:]}")


class DeterminismTests(unittest.TestCase):
    def test_output_identical_across_hash_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "seed1.csv", Path(tmp) / "seed2.csv"
            run_offline(a, "1")
            run_offline(b, "2")
            self.assertEqual(a.read_bytes(), b.read_bytes(), "output differs between hash seeds")
            self.assertEqual(a.read_bytes(), (REPO / "output.csv").read_bytes(), "output differs from output.csv")


if __name__ == "__main__":
    unittest.main()
