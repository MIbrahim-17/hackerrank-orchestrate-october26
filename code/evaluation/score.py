"""Score a predicted output CSV against a gold CSV (default: dataset/sample_output.csv).

Usage:
    python code/evaluation/score.py PRED_CSV [--gold GOLD_CSV] [--no-diff]

Metrics:
- status accuracy: deletion_status matches, per gold case.
- step precision/recall/F1: steps compared as a multiset of whole objects (step_no ignored),
  so a correct step in the wrong position still counts here.
- field accuracy: steps aligned by position; a missing or extra step counts as wrong for every field.
- sequence accuracy: the whole steps array is identical, order included.
Cases missing from the prediction score zero everywhere.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD = REPO_ROOT / "dataset" / "sample_output.csv"
FIELDS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")

Step = dict
Row = tuple[str, list[Step]]  # (deletion_status, steps)


@dataclass
class Report:
    cases: int = 0
    status_ok: int = 0
    sequence_ok: int = 0
    gold_steps: int = 0
    pred_steps: int = 0
    matched_steps: int = 0
    field_slots: int = 0
    field_ok: Counter = field(default_factory=Counter)
    diffs: dict[str, list[str]] = field(default_factory=dict)

    @property
    def status_accuracy(self) -> float:
        return _ratio(self.status_ok, self.cases)

    @property
    def sequence_accuracy(self) -> float:
        return _ratio(self.sequence_ok, self.cases)

    @property
    def step_precision(self) -> float:
        return _ratio(self.matched_steps, self.pred_steps)

    @property
    def step_recall(self) -> float:
        return _ratio(self.matched_steps, self.gold_steps)

    @property
    def step_f1(self) -> float:
        p, r = self.step_precision, self.step_recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def field_accuracy(self, name: str) -> float:
        return _ratio(self.field_ok[name], self.field_slots)


def _ratio(n: int, d: int) -> float:
    return n / d if d else 1.0


def load(path: Path) -> dict[str, Row]:
    """Read case_id -> (status, steps). Invalid steps_json becomes a sentinel step so it scores as wrong."""
    rows: dict[str, Row] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                steps = json.loads(r["steps_json"])
                if not isinstance(steps, list):
                    raise ValueError("steps_json is not a JSON array")
            except (json.JSONDecodeError, ValueError):
                steps = [{"_invalid_json": r["steps_json"]}]
            rows[r["case_id"]] = (r["deletion_status"], steps)
    return rows


def _key(step: Step) -> str:
    return json.dumps({k: v for k, v in step.items() if k != "step_no"}, sort_keys=True)


def _show(step: Step | None) -> str:
    if step is None:
        return "-"
    if "_invalid_json" in step:
        return "INVALID JSON"
    return " ".join(str(step.get(k, "?")) for k in ("phase", "operation", "system_id", "resource_id", "state")) + f" ev={step.get('evidence_id', '?')!r}"


def score_case(gold: Row, pred: Row | None, report: Report, case_id: str) -> None:
    g_status, g_steps = gold
    p_status, p_steps = pred if pred else ("<missing>", [])
    report.cases += 1
    report.gold_steps += len(g_steps)
    report.pred_steps += len(p_steps)
    report.status_ok += g_status == p_status
    report.sequence_ok += pred is not None and g_steps == p_steps

    matched = Counter(map(_key, g_steps)) & Counter(map(_key, p_steps))
    report.matched_steps += sum(matched.values())

    lines: list[str] = []
    if g_status != p_status:
        lines.append(f"status: gold={g_status} pred={p_status}")
    for i in range(max(len(g_steps), len(p_steps))):
        g = g_steps[i] if i < len(g_steps) else None
        p = p_steps[i] if i < len(p_steps) else None
        report.field_slots += 1
        for name in FIELDS:
            report.field_ok[name] += g is not None and p is not None and g.get(name) == p.get(name)
        if g != p:
            lines.append(f"step {i + 1}: gold [{_show(g)}]\n{' ' * (9 + len(str(i + 1)))}pred [{_show(p)}]")
    if lines:
        report.diffs[case_id] = lines


def score(gold: dict[str, Row], pred: dict[str, Row]) -> Report:
    report = Report()
    for case_id in sorted(gold):
        score_case(gold[case_id], pred.get(case_id), report, case_id)
    extra = sorted(set(pred) - set(gold))
    if extra:
        report.diffs["_extra_cases"] = [f"prediction has cases not in gold: {', '.join(extra)}"]
    return report


def score_files(pred_path: Path, gold_path: Path = DEFAULT_GOLD) -> Report:
    return score(load(gold_path), load(pred_path))


def format_report(report: Report, show_diff: bool = True) -> str:
    out = [
        f"cases: {report.cases}",
        f"status accuracy:   {report.status_accuracy:.2%} ({report.status_ok}/{report.cases})",
        f"sequence accuracy: {report.sequence_accuracy:.2%} ({report.sequence_ok}/{report.cases})",
        f"step exact match:  P {report.step_precision:.2%}  R {report.step_recall:.2%}  F1 {report.step_f1:.2%}"
        f" ({report.matched_steps} matched; gold {report.gold_steps}, pred {report.pred_steps})",
        "field accuracy (positional, " + f"{report.field_slots} slots):",
    ]
    out += [f"  {name:<12} {report.field_accuracy(name):.2%}" for name in FIELDS]
    if show_diff and report.diffs:
        out.append(f"\nmismatched cases: {len(report.diffs)}")
        for case_id, lines in report.diffs.items():
            out.append(f"== {case_id}")
            out += [f"  {line}" for line in lines]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pred", type=Path)
    ap.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    ap.add_argument("--no-diff", action="store_true", help="hide the per-case diff")
    args = ap.parse_args(argv)
    print(format_report(score_files(args.pred, args.gold), show_diff=not args.no_diff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
