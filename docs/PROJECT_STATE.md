# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Phase 6 done: submission ready (README, shipped cache, code.zip, clean-room replay) and code-judge review fixes.
Remaining: user uploads code.zip, output.csv and log.txt; optional: final read-through before submitting.

## Done
- Phases 0–5c: setup; analysis; evidence foundation; ownership linking; Haiku intent (38/38); validator +
  --no-llm baseline; tools/agent (Sonnet 5.5); budget guard; output validation; routing (77 agent cases);
  time principle; explicit label rule; determinism test; final 518 run → output.csv (validated); freeze.
- Phase 6:
  - evaluation_report.md (6 custom cases 6/6, failures/fixes, agent contribution, limitations incl. frozen
    weaknesses) and usage_report.md (final run $0.9465; billed $1.9184 priced / $1.8719 charged).
  - README.md rewritten for submission (setup, run, architecture, models, links).
  - Disk cache (5.1 MB, responses + usage only) moved to code/cache/llm; config path updated.
  - Secrets: exact key values absent from 1,482 tree files and 519 history objects; .env never tracked.
  - code.zip: 1,365 entries (README, code/ incl. cache + custom cases, DECISIONS.md, inferred_rules.md);
    no dataset/.env/log.txt/__pycache__/.venv/nested archives.
  - Clean-room keyless run in a fresh venv: output.csv byte-identical, 0 live calls (rechecked after review).
  - Review: main.py per-case agent fallback; intent.py guarded parse; tests/test_validator.py (9 tests).
  - 35 tests pass (incl. determinism and freeze).

## Next step
Exact next action (user): submit at
https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists
with code.zip (repo root), output.csv (repo root) and log.txt (chat_transcript). If any code changes later:
run the tests, `main.py --offline` + cmp output.csv, rebuild code.zip, and repeat the clean-room check.

## Confirmed rules
Details: [docs/inferred_rules.md](inferred_rules.md); revisions in [docs/DECISIONS.md](DECISIONS.md) (authoritative).
- Steps sorted by (operation-table index, system_id, resource_id); FINDING → REMEDIATION → VERIFICATION.
- Policy by data_category; explicit label (any time; specific beats generic) > agent judgement > hint.
- Identity/category may come from any time; state only from evidence ≤ audit_at; post-audit never cited.
- Eligibility: manifest captured_at and record ts ≤ audit_at; record ts ≥ requested_at.
- Agent picks ownership only with a cited grounding record; otherwise "none".

## Open questions
- None blocking submission.
- Unfixed by choice (frozen files, would re-bill): agent.py stop_reason handling and dead needs_agent;
  tools.get_activity substring matching; 600-char name-grounding window; RETAIN ignores rule conditions
  (0/437 affected). All listed in the evaluation report's limitations.
- 3 sample resources unreachable (max 108/111); 115/200 ambiguous ownership sets unresolved by design.
- Reasoned, not sample-proven: lookup keys not exposed data; categories from any time; attachment labels.

## Latest scores
- Samples (unchanged): status 100%; steps P 100% / R 93.78% / F1 96.79%; sequence 65.62%; 0 extras.
- Custom cases 6/6; intent 38/38; final run INCOMPLETE 354 / COMPLETE 154 / NOT_APPLICABLE 10.
- output.csv sha256 d0197918…; spend $1.9184 priced, $1.8719 charged; cap $4.50.

## Known issues
- docs/inferred_rules.md predates the 2026-10-25 decisions; DECISIONS.md wins where they differ.
