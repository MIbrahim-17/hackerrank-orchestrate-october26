# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Phase 6a done: evaluation_report.md (with 6 custom cases) and usage_report.md written from measured runs.
Phase 6b next: README, validator regression tests, code.zip packaging, final submission checks.

## Done
- Phases 0–5c: setup; analysis; evidence foundation; ownership linking; Haiku intent (38/38); validator +
  --no-llm baseline; tools/agent (Sonnet 5.5); budget guard; output validation; routing (77 agent cases);
  time principle; explicit label rule; determinism test; final 518 run → output.csv (validated); freeze.
- Phase 6a:
  - code/evaluation/custom_cases/: 6 synthetic cases (3-hop oldest email, sync recreation before audit_at,
    post-audit evidence ignored, old-hash-only record, Spanish non-deletion, French legal hold).
  - score.py --custom: runs the unchanged pipeline on a merged temp dataset; 6/6 PASS, 100% all metrics.
  - Full system on samples (4 routed, 0 changed) byte-identical to the --no-llm baseline.
  - code/evaluation/evaluation_report.md (465 lines): metrics, sequence-miss proof, 108/111 ceiling,
    generated custom-case details, failures/fixes with before/after, agent contribution, limitations.
  - code/evaluation/usage_ledger.py + usage_report.md: final run 721 calls, 1,122,288 tokens, $0.9465
    ($0.001827/request; $0.9301 counting identical intent texts once); billed dev spend.

## Next step
Exact next action: rewrite the root README.md for submission — what the system does, architecture in brief,
setup (uv venv, uv pip install -r code/requirements.txt, .env with ANTHROPIC_API_KEY and GEMINI_API_KEY or
GOOGLE_API_KEY), run commands (main.py full/--sample/--no-llm/--offline, score.py, --custom, intent_eval.py,
usage_ledger.py, tests), outputs, budget guard (MAX_SPEND_USD), note that the .cache is not shipped so a clean
run re-bills. Then validator regression tests (no pipeline change), package code.zip (README.md + code/;
exclude __pycache__, .venv, .cache, .env, dataset, nested archives) and verify its contents; final AGENTS.md §6 checks.

## Confirmed rules
Details: [docs/inferred_rules.md](inferred_rules.md); revisions in [docs/DECISIONS.md](DECISIONS.md) (authoritative).
- Steps sorted by (operation-table index, system_id, resource_id); FINDING → REMEDIATION → VERIFICATION.
- Policy by data_category; explicit label (any time; specific beats generic) > agent judgement > hint.
- Identity/category may come from any time; state only from evidence ≤ audit_at; post-audit never cited.
- Eligibility: manifest captured_at and record ts ≤ audit_at; record ts ≥ requested_at.
- Agent picks ownership only with a cited grounding record; otherwise "none".

## Open questions
- Should code.zip ship the 11 cached image transcriptions so a clean run does not need a Gemini key?
  (They are in .cache/llm, which is excluded; a clean run without GEMINI/GOOGLE key skips images with a warning.)
- 3 sample resources unreachable (max 108/111); 115/200 ambiguous ownership sets unresolved by design.
- Reasoned, not sample-proven: lookup keys not exposed data; categories from any time; attachment labels.

## Latest scores
- Samples (unchanged): status 100%; steps P 100% / R 93.78% / F1 96.79%; sequence 65.62%; 0 extras.
- Custom cases: 6/6 PASS. Intent: 38/38.
- Final run: INCOMPLETE 354 / COMPLETE 154 / NOT_APPLICABLE 10; agent 77 routed, 0 changed.
- Spend: $1.9184 priced, $1.8719 charged (Flash free tier); cap $4.50.

## Known issues
- No validator regression tests yet (determinism, freeze, identity/evidence/links tests exist; 26 pass).
- docs/inferred_rules.md predates the 2026-10-25 decisions; DECISIONS.md wins where they differ.
