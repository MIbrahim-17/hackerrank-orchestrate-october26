"""Token and cost figures for usage_report.md.

View 1, final run: replays the final full run from the disk cache (main.py --offline reproduces output.csv byte for
byte, see tests/test_determinism.py) and sums the ledger. Every call keeps its original token counts, whether served
from cache or not.
View 2, billed development spend: every billed call wrote exactly one disk-cache file, so the cache is the bill.

Usage: python code/evaluation/usage_ledger.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))

import llm  # noqa: E402
import main  # noqa: E402
from config import LLM_CACHE_DIR, PRICES, REPO_ROOT  # noqa: E402

TOKENS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")


def summarize(rows: list[dict]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        t = out[r["model"]]
        t["calls"] += 1
        for k in TOKENS:
            t[k] += r[k]
        t["cost"] += llm.usage_cost(r)
    return out


def table(summary: dict[str, dict[str, float]], requests: int | None) -> str:
    lines = ["| provider | model | calls | input | output | cache read | cache write | total tokens | cost (USD) |"
             + (" tokens/request | cost/request |" if requests else ""),
             "|---|---|---|---|---|---|---|---|---|" + ("---|---|" if requests else "")]
    grand: dict[str, float] = defaultdict(float)
    for model in sorted(summary):
        t = summary[model]
        total = sum(t[k] for k in TOKENS)
        for k in (*TOKENS, "calls", "cost"):
            grand[k] += t[k]
        row = (f"| {PRICES[model]['provider']} | {model} | {int(t['calls'])} | {int(t['input_tokens']):,} | "
               f"{int(t['output_tokens']):,} | {int(t['cache_read_tokens']):,} | {int(t['cache_write_tokens']):,} | "
               f"{int(total):,} | ${t['cost']:.4f} |")
        if requests:
            row += f" {total / requests:,.0f} | ${t['cost'] / requests:.6f} |"
        lines.append(row)
    total = sum(grand[k] for k in TOKENS)
    row = (f"| **all** | **overall** | **{int(grand['calls'])}** | **{int(grand['input_tokens']):,}** | "
           f"**{int(grand['output_tokens']):,}** | **{int(grand['cache_read_tokens']):,}** | "
           f"**{int(grand['cache_write_tokens']):,}** | **{int(total):,}** | **${grand['cost']:.4f}** |")
    if requests:
        row += f" **{total / requests:,.0f}** | **${grand['cost'] / requests:.6f}** |"
    lines.append(row)
    return "\n".join(lines)


def main_() -> None:
    llm.LEDGER.clear()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "replay.csv"
        assert main.main(["--offline", "--out", str(out)]) == 0
        identical = out.read_bytes() == (REPO_ROOT / "output.csv").read_bytes()
    final = list(llm.LEDGER)
    by_purpose: dict[tuple[str, str], int] = defaultdict(int)
    for r in final:
        by_purpose[(r["model"], r["purpose"])] += 1
    print(f"## View 1: final run (replay identical to output.csv: {identical})\n")
    print(table(summarize(final), requests=518))
    print("\ncalls by purpose:", dict(sorted(by_purpose.items())))
    print(f"agent cases: {len({r['case_id'] for r in final if r['purpose'] == 'agent'})}")
    billed = [json.loads(f.read_text(encoding="utf-8"))["usage"] for f in sorted(LLM_CACHE_DIR.glob("*.json"))]
    print("\n## View 2: billed development spend (one disk-cache file per billed call)\n")
    print(table(summarize(billed), requests=None))


if __name__ == "__main__":
    main_()
