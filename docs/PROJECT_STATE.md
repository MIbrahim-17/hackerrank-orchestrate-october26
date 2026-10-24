# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Phase 5a done: routing (option A), budget guard, freeze, output validation, 40-case agent pilot.
Phase 5b blocked on two user decisions (budget routing, post-audit categories); then full 518 run and reports.

## Done
- Phases 0–4: setup; analysis; evidence foundation; activity-row ownership linking; Haiku intent (38/38);
  validator + --no-llm baseline; tools.py + agent.py (Sonnet 5.5).
- Phase 5a:
  - Routing: agent only when an ambiguous set or an unlabeled support_/analytics_ resource exists (352 of 508);
    brief offers only support_/analytics_ resources for category judgement.
  - Sample sequence mismatches (11) confirmed to be missing resources only; ordering is correct.
  - llm.py hard budget guard: MAX_SPEND_USD (default 4.50) vs spend from the disk cache + in-flight + estimate;
    BudgetExceeded → deterministic fallback, counted in main.py. Cache hits always allowed.
  - Freeze: prompts.py, tools.py, agent.py pinned by SHA-256 in tests (changes re-bill cases).
  - main.py validate_output(): full output contract; passes on baseline and on gold sample_output.csv.
  - Pilot (40 routed eval cases): $0.0118/case, 2.02 turns, 0 retries, 37/37 ambiguous → "none", 1 change.
  - 24 tests pass.

## Next step
Waiting for the user on:
a) Budget: remaining 312 routed cases ≈ $3.68 → total ≈ $4.62 > $4.50 cap. Options: (1, recommended) route only
   the ~182 cases with an unlabeled support_/analytics_ resource (ambiguous sets gave 46/46 "none"); (2) keep 352
   and accept ~10 guard fallbacks; (3) lower Sonnet effort (re-bills the pilot).
b) Categories: should category evidence, like state, come only from records at or before audit_at? (case_431)
Then: python code/main.py → output.csv (518 rows, validated); report status distribution, cost/tokens per model,
fallbacks, changes by type, evidence trails for ≤5 changed cases; then evaluation_report.md, usage_report.md, README, code.zip.

## Confirmed rules
Details: [docs/inferred_rules.md](inferred_rules.md); revisions in [docs/DECISIONS.md](DECISIONS.md) (authoritative).
- Steps sorted by (operation-table index, system_id, resource_id); FINDING → REMEDIATION → VERIFICATION.
- Policy by data_category, never by system or ID prefix; explicit source label wins over hint or agent choice.
- Identity: full history, exact normalized match. Eligibility: manifest captured_at and record ts ≤ audit_at;
  record ts ≥ requested_at. Post-audit and activity rows: ownership only, never state.
- State: direct observation beats snapshot absence; no state evidence → uncited step.
- Agent picks from an ambiguous set only with a cited grounding record; otherwise "none".

## Open questions
- (a) and (b) above.
- case_431 / support_3615: attachment (post-audit evidence_40) vs generic ticket row (eligible evidence_68);
  samples cannot settle it.
- 3 sample resources unreachable (account_004, audit_record_6645, audit_record_5569): max 108/111.
- "Lookup keys are not exposed data": kept, no proving sample case.

## Latest scores
- Samples (unchanged): status 100%; steps P 100% / R 93.78% / F1 96.79%; sequence 65.62%; 0 extras.
- Pilot (40 eval cases): agent changed 1/40 vs baseline (uncertain).
- Spend: $0.9347 priced total (Haiku $0.1030, Sonnet $0.7852, Flash $0.0465 free tier); cap $4.50.

## Known issues
- No validator regression tests yet (baseline P=100% on samples, case_17 restore risk, case_31 snapshot absence).
- validator.category_of reads evidence of any time (gap vs the ownership-only rule; see b).
- docs/inferred_rules.md predates the 2026-10-25 decisions; DECISIONS.md wins where they differ.
