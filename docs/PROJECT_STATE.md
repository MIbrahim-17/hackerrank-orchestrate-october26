# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Phase 2 done: evidence foundation (identity resolution, evidence index, LLM wrapper, image transcription).
Phase 3 next: intent classifier, then tools / agent loop / validator.

## Done
- Phase 0: setup (uv venv, pinned deps, .env.example, .gitignore, docs, log.txt, CLAUDE.md import).
- Phase 1: analysis — docs/data_profile.md, docs/sample_trace.md, docs/inferred_rules.md; code/evaluation/score.py.
- Phase 2 (code/, 19 tests in code/tests pass):
  - config.py: models (claude-sonnet-5-5 loop, gemini-3.8-flash single-shot), dated price tables.
  - data.py: typed CSV loaders. identity.py: full-history resolution, 550/550 requests → 1 user (103 via old email).
  - evidence.py: 2,934 Observations from 94 files + LINK_RESOURCE_IDENTITY rows; file gate, record gate,
    lifecycle bound; refs (links only); Coverage snapshots; `owned_after_audit` (ownership only, never state/cite).
  - llm.py: call_claude (no fallback) / call_gemini, shared disk cache + ledger; GEMINI_API_KEY or GOOGLE_API_KEY.
  - 11 PNGs transcribed by Flash (cached, ~$0.044), spot-checked against images; 4 PDFs via pypdf (= pdftotext).

## Next step
Exact next action: write the intent classifier (prompts.py + a `classify_intent()` using call_gemini with a JSON
schema), run it on the 32 samples (all deletion requests) plus 6 custom sentences in ≥3 languages ("export my data",
"unsubscribe me from emails", "close my account but keep my order history", …), starting at thinking MINIMAL and
raising only until accuracy is 100%; record the chosen level in config.py and DECISIONS.md.
Then: close the 23 activity-only gaps without timing → tools.py → agent.py → validator.py → main.py → 32-sample run.

## Confirmed rules
Details: [docs/inferred_rules.md](inferred_rules.md); later revisions in [docs/DECISIONS.md](DECISIONS.md) (authoritative).
- Steps sorted by (operation-table index, system_id, resource_id); FINDING → REMEDIATION → VERIFICATION.
- Policy by data_category, never by system or ID prefix (analytics_/support_ carry several categories).
- Identity: full history, exact normalized match (email lower, phone digits, sha256 email hash, user_id).
- Eligibility: manifest captured_at ≤ audit_at AND record ts ≤ audit_at; lifecycle bound record ts ≥ requested_at.
- Post-audit evidence: ownership only (8 sample resources depend on it); never state, never cited.
- Verification = final-state inventory; account always verified ABSENT; INCOMPLETE remediation/verification uncited.
- Activity rows are claims; activity timing is never used to infer ownership.

## Open questions
- 23 unmatched sample resources linked only through deletion-worker activity rows (10 with pre-audit state
  evidence, e.g. analytics_1895 in evidence_92; 3 cited via a snapshot lacking them, e.g. account_001;
  10 with no state evidence, e.g. account_5521). How to own them without timing?
- 3 sample resources ungrounded anywhere: account_004, audit_record_6645, audit_record_5569.
- "Lookup keys are not exposed data": kept, but no proving sample case (affects 3 eval records in evidence_61).
- NOT_APPLICABLE detection untested by samples (0 of 32 are non-deletion).

## Latest scores
- Samples, resource discovery: 85/111 expected resources found, 0 extras (unchanged by images). No steps_json yet.
- Full run: n/a.
- Spend so far: ~$0.044 (11 Flash image calls); Sonnet unused.

## Known issues
- Flash latency ~2.5 min per image call; long batches must run unbuffered in the background.
- docs/inferred_rules.md ambiguity list predates the 2026-10-25 decisions (Ambiguity 3 now resolved:
  ownership-only); DECISIONS.md wins where they differ.
