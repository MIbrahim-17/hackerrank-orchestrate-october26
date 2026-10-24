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
from data import Request, load_activity, load_audit_log, load_manifest, load_requests
from evidence import build_index
from intent import classify_many
from validator import OPERATIONS, CaseResult, deterministic_owned, explicit_label, validate_case

STEP_KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
ALLOWED = {(phase, op, state) for phase, op, state in OPERATIONS}


def write_csv(path: Path, results: list[CaseResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for res in sorted(results, key=lambda x: int(x.case_id.split("_")[1])):  # numeric: case_33 before case_100
            w.writerow([res.case_id, res.status, res.steps_json()])


def route_to_agent(r: Request, index, links) -> bool:
    """Agent only for an owned support_/analytics_ resource with no explicit label anywhere (DECISIONS 2026-10-25,
    option 1). Ambiguous ownership sets alone go to the validator: the agent answered "none" on 46/46."""
    return any(rid.split("_", 1)[0] in ("support", "analytics") and explicit_label(index, rid) is None
               for rid in deterministic_owned(index, links, r))


def validate_output(path: Path, requests: list[Request]) -> list[str]:
    """Contract checks on the written CSV. Returns a list of problems (empty = valid)."""
    problems: list[str] = []
    evidence_time = {f.file_id: f.captured_at for f in load_manifest()}
    evidence_time |= {a.activity_id: a.event_time for a in load_activity()}
    evidence_time |= {a.audit_id: a.event_time for a in load_audit_log()}
    audit_at = {r.case_id: r.audit_at for r in requests}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        rows = list(reader)
    if header != ["case_id", "deletion_status", "steps_json"]:
        problems.append(f"bad header {header}")
    ids = [row[0] for row in rows]
    if len(rows) != len(requests):
        problems.append(f"{len(rows)} rows, expected {len(requests)}")
    if len(set(ids)) != len(ids):
        problems.append("duplicate case_id")
    if set(ids) != set(audit_at):
        problems.append(f"case_id set differs from requests: {sorted(set(ids) ^ set(audit_at))[:5]}")
    if ids != sorted(ids, key=lambda c: int(c.split("_")[1])):
        problems.append("rows not sorted by numeric case_id")
    for case_id, status, steps_json in rows:
        try:
            steps = json.loads(steps_json)
        except json.JSONDecodeError:
            problems.append(f"{case_id}: steps_json is not JSON")
            continue
        if not isinstance(steps, list):
            problems.append(f"{case_id}: steps_json is not an array")
            continue
        if status not in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
            problems.append(f"{case_id}: bad status {status}")
        if status == "NOT_APPLICABLE" and steps:
            problems.append(f"{case_id}: NOT_APPLICABLE with steps")
        if status != "NOT_APPLICABLE" and not steps:
            problems.append(f"{case_id}: {status} with no steps")
        if [s.get("step_no") for s in steps] != list(range(1, len(steps) + 1)):
            problems.append(f"{case_id}: step_no not consecutive from 1")
        for s in steps:
            if set(s) != STEP_KEYS:
                problems.append(f"{case_id}: step keys {sorted(s)}")
            if (s.get("phase"), s.get("operation"), s.get("state")) not in ALLOWED:
                problems.append(f"{case_id}: illegal phase/operation/state {s.get('phase')}/{s.get('operation')}/{s.get('state')}")
            ev = s.get("evidence_id", "")
            if ev and ev not in evidence_time:
                problems.append(f"{case_id}: unknown evidence_id {ev}")
            elif ev and evidence_time[ev] > audit_at.get(case_id, ""):
                problems.append(f"{case_id}: evidence {ev} captured after audit_at")
            if status == "COMPLETE" and s.get("phase") != "VERIFICATION":
                problems.append(f"{case_id}: COMPLETE with a {s.get('phase')} step")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ghost Data deletion-audit pipeline")
    ap.add_argument("--sample", action="store_true", help="run the 32 sample requests")
    ap.add_argument("--no-llm", action="store_true", help="deterministic baseline: no agent, no API calls")
    ap.add_argument("--offline", action="store_true", help="full pipeline from the disk cache only; a miss is an error")
    ap.add_argument("--cases", default="", help="comma-separated case_ids to run")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    llm.OFFLINE = args.no_llm or args.offline

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
    fallbacks: list[dict] = []

    def run(r):
        deletion = r.case_id not in non_deletion
        baseline = validate_case(r, index, links[r.case_id], deletion)
        if args.no_llm or not deletion:
            return baseline
        from agent import investigate  # imported lazily: --no-llm never needs it
        if not route_to_agent(r, index, links[r.case_id]):
            return baseline
        try:
            agent_result = investigate(r, index, links[r.case_id])
        except llm.BudgetExceeded as e:
            fallbacks.append({"case_id": r.case_id, "reason": str(e)})
            return baseline
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
    problems = validate_output(out, targets)
    print(f"output validation: {'OK' if not problems else f'{len(problems)} problems'}")
    for p in problems[:50]:
        print(f"  {p}", file=sys.stderr)
    print(f"budget fallbacks (deterministic result used): {len(fallbacks)}")
    for fb in fallbacks:
        print(f"  {fb['case_id']}: {fb['reason']}")
    if agent_log:
        log_path = out.with_suffix(".agent_log.json")
        log_path.write_text(json.dumps(sorted(agent_log, key=lambda x: x["case_id"]), indent=1, ensure_ascii=False))
        print(f"agent log: {log_path}")
    from validator import LABEL_CONFLICTS
    for rid, labels, chosen in sorted(set(LABEL_CONFLICTS)):
        print(f"  label conflict {rid}: {labels} -> {chosen}", file=sys.stderr)
    for res in results:
        if res.errors:
            print(f"  {res.case_id}: rejected agent items: {json.dumps(res.errors)}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
