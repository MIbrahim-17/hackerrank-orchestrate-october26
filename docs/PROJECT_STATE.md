# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Phase 4 done: validator, deterministic baseline, agent tools and Sonnet loop, first scored sample runs.
Phase 5 next: user decision on agent scope, brief fix, full 518 run, evaluation and usage reports, packaging.

## Done
- Phases 0–2: setup; analysis docs; evidence foundation (identity, evidence index with gates, llm cache + ledger,
  11 cached Flash transcriptions, pypdf).
- Phase 3: activity_links.py (windows + status filter + propagation, NOT_APPLICABLE excluded);
  intent.py on Haiku 5.5 (adaptive/medium, 38/38; 518 → 508 deletion / 10 not).
- Phase 4:
  - llm.py: prompt cache optional (off for intent), OFFLINE mode for --no-llm.
  - validator.py: ownership → category → state (latest eligible obs > snapshot absence > UNKNOWN) → policy → steps.
  - evidence fixes: deletion_block/eligible restore state, contact_/message_ hints, PDF file-name collection,
    per-system snapshot coverage with snapshot_scope.
  - main.py CLI (--sample, --no-llm, --cases, --out, --workers; agent log JSON).
  - tools.py (6 read-only gated tools + strict submit_findings), agent.py (pre-fetched brief, 6 turns, 2 retries).
  - 22 tests pass (identity/evidence/ownership/activity links; no validator tests yet).

## Next step
1. User decides agent scope: A) only the 352 cases with something to decide (recommended), B) none, C) all 508.
2. Fix the brief: list only support_/analytics_ resources without a source label as category decisions.
3. Add validator regression tests (baseline P=100% on samples, case_17 restore risk, case_31 snapshot absence).
4. Full run: `python code/main.py` → output.csv (518 rows); then evaluation_report.md, usage_report.md, README, code.zip.

## Confirmed rules
Details: [docs/inferred_rules.md](inferred_rules.md); revisions in [docs/DECISIONS.md](DECISIONS.md) (authoritative).
- Steps sorted by (operation-table index, system_id, resource_id); FINDING → REMEDIATION → VERIFICATION.
- Policy by data_category, never by system or ID prefix; explicit source label wins over any hint or agent choice.
- Identity: full history, exact normalized match. Eligibility: manifest captured_at and record ts ≤ audit_at;
  record ts ≥ requested_at. Post-audit and activity rows: ownership only, never state.
- State: direct observation beats snapshot absence; no state evidence → uncited step.
- Agent may pick from an ambiguous set only with a cited grounding record (identifier or exact full name).

## Open questions
- Agent scope (above). On the 518: 156 deletion cases have nothing to decide; 352 have an ambiguous set and/or
  an unlabeled support/analytics resource.
- Ambiguous ownership on the 518 (accounts 115, analytics 200) has no grounding in the samples; expect mostly "none".
- 3 sample resources unreachable (account_004, audit_record_6645, audit_record_5569): max 108/111.
- "Lookup keys are not exposed data": kept, no proving sample case.

## Latest scores
- Samples, --no-llm baseline: status 100% (32/32); steps P 100% / R 93.78% / F1 96.79% (181/193);
  sequence 65.62% (21/32); 0 extras. With agent: identical (0/32 cases changed).
- Agent cost: $0.0098/case (1.53 turns, 2.59 tool calls, ~6.3K in / 365 out tokens); ~$5.00 projected for 508.
- Spend so far: Flash ≈ $0.047, Haiku ≈ $0.12, Sonnet ≈ $0.33.

## Known issues
- Agent brief lists hint-categorised accounts/searches/audits as "without source label" (wasted tokens).
- docs/inferred_rules.md predates the 2026-10-25 decisions; DECISIONS.md wins where they differ.
