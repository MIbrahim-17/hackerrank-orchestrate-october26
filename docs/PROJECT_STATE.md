# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Phase 5c done: both defects fixed, explicit label rule, determinism proven, final 518 run, re-frozen.
Phase 6 next: evaluation_report.md, usage_report.md, README, validator tests, code.zip, submission checks.

## Done
- Phases 0–5b: setup; analysis; evidence foundation; activity-row ownership linking; Haiku intent (38/38);
  validator + --no-llm baseline; tools/agent (Sonnet 5.5); budget guard; output validation; pilot; routing
  option 1; time principle (identity/category any time, state ≤ audit_at).
- Phase 5c:
  - evidence.parse_log_line handles operations_stream "| LEVEL | svc | trace | event | kv" (+25 resources, 16 cases).
  - validator.observation_label/explicit_label: record_type > attachment-file records > structural collections;
    generic views are not labels; LABEL_PRIORITY for conflicts (0 measured); most_common() tie-break.
  - No set/dict-order or hash dependence; test_determinism.py: byte-identical across PYTHONHASHSEED 1/2.
  - main.py --offline (full pipeline from cache, miss = error); label conflicts logged.
  - Final run: output.csv 518 rows, validation OK, 0 budget fallbacks; agent routed 77, changed 0.
  - Freeze extended: prompts, tools, agent, evidence, identity, activity_links + validator brief functions.
  - 26 tests pass (incl. determinism and freeze).

## Next step
Exact next action: write code/evaluation/evaluation_report.md from measured results — sample status/step/field/
sequence accuracy (score.py on --no-llm and agent runs), ≥3 custom evaluation cases (e.g. the 6 intent sentences,
the D3 record-gate traps case_135/case_383, the case_515 attachment catch), failures found and fixes made
(from DECISIONS.md). Then usage_report.md (final full run: per-model calls/tokens/cost incl. cached replays,
totals, per-request averages), README setup/run instructions, validator regression tests, package code.zip
(README.md + code/, no .cache/.env/dataset), final checks against AGENTS.md §6.

## Confirmed rules
Details: [docs/inferred_rules.md](inferred_rules.md); revisions in [docs/DECISIONS.md](DECISIONS.md) (authoritative).
- Steps sorted by (operation-table index, system_id, resource_id); FINDING → REMEDIATION → VERIFICATION.
- Policy by data_category; explicit label (any time; specific beats generic) > agent judgement > hint.
- Identity/category may come from any time; state only from evidence ≤ audit_at; post-audit never cited.
- Eligibility: manifest captured_at and record ts ≤ audit_at; record ts ≥ requested_at.
- Agent picks ownership only with a cited grounding record; otherwise "none".

## Open questions
- 3 sample resources unreachable (account_004, audit_record_6645, audit_record_5569): max 108/111.
- "Lookup keys are not exposed data" and the time principle for categories: reasoned, not sample-proven.
- 115 ambiguous account / 200 ambiguous analytics ownership sets on the 518 remain unresolved by design.

## Latest scores
- Samples (unchanged): status 100%; steps P 100% / R 93.78% / F1 96.79%; sequence 65.62%; 0 extras.
- Final run: INCOMPLETE 354 / COMPLETE 154 / NOT_APPLICABLE 10; vs previous run 18 cases changed,
  +25 resources, 0 removed (case_517/519 COMPLETE→INCOMPLETE; case_71/119 REDACT→DELETE).
- Spend: $1.8604 priced (Haiku $0.1030, Sonnet $1.7108, Flash $0.0465 free tier); cap $4.50.

## Known issues
- No validator regression tests yet (determinism and freeze tests exist).
- docs/inferred_rules.md predates the 2026-10-25 decisions; DECISIONS.md wins where they differ.
