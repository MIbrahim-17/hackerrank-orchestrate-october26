# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Phase 5b done: option 1 routing, time principle in the validator, full 518 run → valid output.csv.
Phase 5c next: user decision on two defect fixes (≈$0.11), then re-run, reports, README, code.zip.

## Done
- Phases 0–5a: setup; analysis; evidence foundation; activity-row ownership linking; Haiku intent (38/38);
  validator + --no-llm baseline; tools.py + agent.py (frozen); budget guard; output validation; 40-case pilot.
- Phase 5b:
  - main.route_to_agent: agent only for an owned support_/analytics_ resource with no explicit label anywhere
    (84 of 508 deletion cases); ambiguous sets go to the validator alone (46/46 "none").
  - validator.explicit_label/final_category: explicit label (record_type or structural collection name, any time)
    > agent > hint > prefix default; category_of untouched (feeds the frozen brief). Reasoned, not sample-proven.
  - main.py numeric case_id sort (validation caught a text sort hidden by zero-padded sample ids).
  - Full run: output.csv, 518 rows, validation OK; 0 budget fallbacks. 24 tests pass.

## Next step
User decides whether to apply both defect fixes and re-run (python code/main.py):
1. Deterministic tie-break in category_of (sorted before max) — affects support_9309 / case_119.
2. Pipe-format log parsing ("| LEVEL | svc | trace | event | kv") in evidence.parse_log_line — +25 owned
   resources in 16 eval cases, samples unchanged. Both re-bill 9 routed briefs (~$0.11) → total ≈ $1.85.
Then: re-validate output.csv; add validator regression tests; write code/evaluation/evaluation_report.md
(sample metrics, ≥3 custom cases, failures/fixes) and usage_report.md (final run tokens/cost per model);
README run instructions; package code.zip.

## Confirmed rules
Details: [docs/inferred_rules.md](inferred_rules.md); revisions in [docs/DECISIONS.md](DECISIONS.md) (authoritative).
- Steps sorted by (operation-table index, system_id, resource_id); FINDING → REMEDIATION → VERIFICATION.
- Policy by data_category; explicit label (any time) > agent judgement > hint.
- Identity/category may come from any time; state only from evidence ≤ audit_at; post-audit never cited.
- Eligibility: manifest captured_at and record ts ≤ audit_at; record ts ≥ requested_at.
- Agent picks ownership only with a cited grounding record; otherwise "none".

## Open questions
- The two defect fixes above (user approval needed: they touch brief-building code).
- case_71 / support_1370: agent chose SUPPORT_MESSAGE from a generic support_records row; the only specific
  signal (attachment_scan) is a post-audit log hint. Likely wrong; no rule lets a hint override the agent.
- 3 sample resources unreachable (max 108/111); "lookup keys are not exposed data" unproven.

## Latest scores
- Samples (unchanged): status 100%; steps P 100% / R 93.78% / F1 96.79%; sequence 65.62%; 0 extras.
- Full run: INCOMPLETE 352 / COMPLETE 156 / NOT_APPLICABLE 10; 3,043 steps; agent changed 3/84
  (case_515 right, case_71 likely wrong, case_119 spurious tie).
- Spend: $1.7270 priced (Haiku $0.1030, Sonnet $1.5774, Flash $0.0465 free tier); cap $4.50.

## Known issues
- Nondeterministic tie-break in validator.category_of (max over a set of strings).
- operations_stream logs (pipe format) not parsed: events lost, lines not grouped by trace.
- No validator regression tests yet; docs/inferred_rules.md predates the 2026-10-25 decisions.
