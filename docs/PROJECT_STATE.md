# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Phase 3 done: ownership linking (activity rows) and intent classification.
Phase 4 next: agent tools, Sonnet tool loop, deterministic validator, main.py; first scored 32-sample run.

## Done
- Phase 0: setup (uv venv, pinned deps, .env.example, .gitignore, docs, log.txt, CLAUDE.md import).
- Phase 1: analysis — docs/data_profile.md, docs/sample_trace.md, docs/inferred_rules.md; code/evaluation/score.py.
- Phase 2: evidence foundation — config, data, identity (550/550 → 1 user), evidence (2,934 Observations,
  file + record gates, lifecycle bound, refs, Coverage, ownership-only post-audit), llm (disk cache + ledger),
  11 PNGs transcribed by Flash (cached), PDFs via pypdf.
- Phase 3 (22 tests pass):
  - activity_links.py: per-template windows, evidence elimination, skip-if-linked, NOT_APPLICABLE excluded,
    account result must match reported_status, constraint propagation; leftovers marked ambiguous.
  - intent.py on claude-haiku-5-5 (json_schema, adaptive/medium); evaluation/intent_eval.py: 38/38.
    518 run: 508 deletion, 10 not (matches the 10 CLASSIFY_REQUEST rows); results cached.
  - Gemini key is free tier → Flash used only for the 11 cached image transcriptions.

## Next step
Exact next action: write code/tools.py — six deterministic tools over EvidenceIndex + activity links
(resolve_identity, search_evidence with excluded-and-why, query_sql_snapshot read-only, get_activity returning the
case's link status and ambiguous candidates, read_image_or_pdf, lookup_policy) plus a strict submit_findings schema
that allows "none" for ambiguous analytics. Then agent.py (Sonnet 5.5 loop, 12-turn cap, ≤2 validator retries),
validator.py (gates, policy by category, steps_json order), main.py (intent → links → agent → validator → CSV);
run the 32 samples and report score.py metrics, tokens and cost.

## Confirmed rules
Details: [docs/inferred_rules.md](inferred_rules.md); later revisions in [docs/DECISIONS.md](DECISIONS.md) (authoritative).
- Steps sorted by (operation-table index, system_id, resource_id); FINDING → REMEDIATION → VERIFICATION.
- Policy by data_category, never by system or ID prefix (analytics_/support_ carry several categories).
- Identity: full history, exact normalized match (email lower, phone digits, sha256 email hash, user_id).
- Eligibility: manifest captured_at ≤ audit_at AND record ts ≤ audit_at; lifecycle bound record ts ≥ requested_at.
- Post-audit evidence: ownership only; never state, never cited.
- Activity rows: ownership only, via the proven window + status + propagation rule; never state.
- Verification = final-state inventory; account always verified ABSENT; INCOMPLETE remediation/verification uncited.

## Open questions
- Ambiguous ownership on the 518: accounts 115, analytics 200 (same reported_at; time cannot split them).
  The agent may pick or answer none; the validator must check the pick. How should the validator judge it?
- An ambiguous analytics set can belong to a case with no anonymized analytics (samples case_09/19/20/23).
- 3 sample resources unreachable (account_004, audit_record_6645, audit_record_5569): max 108/111.
- "Lookup keys are not exposed data": kept, no proving sample case.

## Latest scores
- Samples, resource discovery: 99/111 found, 0 extras (was 92): 14/23 activity-only resources recovered,
  9 inside ambiguous sets, 3 unreachable. No steps_json yet.
- Intent: 38/38 (32 samples + 6 custom, 4 languages) at Haiku adaptive/medium.
- Spend so far: Flash ≈ $0.047 (20 calls), Haiku ≈ $0.08 (≈670 calls); Sonnet unused.

## Known issues
- Intent calls write ~700 cache tokens each that are never read (~$0.05 per 518 run).
- docs/inferred_rules.md predates the 2026-10-25 decisions; DECISIONS.md wins where they differ.
