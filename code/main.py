"""Ghost Data Still Exists — deletion-audit pipeline.

Usage:
  python code/main.py                 # 518 evaluation requests -> output.csv
  python code/main.py --sample        # 32 sample requests -> .cache/sample_pred.csv (score with evaluation/score.py)
  python code/main.py --no-llm        # deterministic baseline: no agent, no API calls (intent from the disk cache)
  python code/main.py --cases case_11,case_28 --sample

Pipeline: evidence index -> intent (Haiku, cached) -> activity links over all requests -> per case: agent (Sonnet,
optional) -> deterministic validator -> steps_json.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import llm
from activity_links import build_activity_links
from config import CACHE_DIR, OUTPUT_CSV
from data import load_requests
from evidence import build_index
from intent import classify_many
from validator import CaseResult, validate_case


def write_csv(path: Path, results: list[CaseResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for res in sorted(results, key=lambda x: x.case_id):
            w.writerow([res.case_id, res.status, res.steps_json()])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ghost Data deletion-audit pipeline")
    ap.add_argument("--sample", action="store_true", help="run the 32 sample requests")
    ap.add_argument("--no-llm", action="store_true", help="deterministic baseline: no agent, no API calls")
    ap.add_argument("--cases", default="", help="comma-separated case_ids to run")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    llm.OFFLINE = args.no_llm

    samples, evals = load_requests("sample_deletion_requests.csv"), load_requests()
    targets = samples if args.sample else evals
    if args.cases:
        wanted = set(args.cases.split(","))
        targets = [r for r in targets if r.case_id in wanted]
    out = args.out or (CACHE_DIR / "sample_pred.csv" if args.sample else OUTPUT_CSV)

    index = build_index()
    everyone = samples + evals
    intents = classify_many([(r.case_id, r.request_text) for r in everyone], workers=args.workers)
    non_deletion = frozenset(cid for cid, v in intents.items() if not v["authorizes_deletion"])
    links = build_activity_links(index, everyone, non_deletion)

    agent_log: list[dict] = []

    def run(r):
        deletion = r.case_id not in non_deletion
        baseline = validate_case(r, index, links[r.case_id], deletion)
        if args.no_llm or not deletion:
            return baseline
        from agent import investigate  # imported lazily: --no-llm never needs it
        agent_result = investigate(r, index, links[r.case_id])
        final = validate_case(r, index, links[r.case_id], deletion, agent_result)
        agent_log.append({"case_id": r.case_id, **agent_result["_stats"],
                          "changed": final.steps != baseline.steps or final.status != baseline.status,
                          "choices": agent_result["choices"], "categories": agent_result["categories"],
                          "rejected": final.errors})
        return final

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, targets))
    write_csv(out, results)
    print(f"wrote {len(results)} rows to {out}")
    if agent_log:
        log_path = out.with_suffix(".agent_log.json")
        log_path.write_text(json.dumps(sorted(agent_log, key=lambda x: x["case_id"]), indent=1, ensure_ascii=False))
        print(f"agent log: {log_path}")
    for res in results:
        if res.errors:
            print(f"  {res.case_id}: rejected agent items: {json.dumps(res.errors)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
