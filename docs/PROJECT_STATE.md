# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Setup complete. No solution code yet.

## Done
- Read AGENTS.md, README.md, problem_statement.md.
- `uv venv` at repo root; deps pinned in `code/requirements.txt` (anthropic, python-dotenv).
- `.env.example`, `.gitignore`, `docs/DECISIONS.md`, this file, CLAUDE.md import.
- log.txt started (SESSION START + per-turn entries).

## Next step
Explore `dataset/` (CSVs, evidence formats, samples) and derive rules from the 32 samples into `docs/inferred_rules.md`.

## Confirmed rules
None yet. Details will live in [docs/inferred_rules.md](inferred_rules.md).
Contract reminders: output `case_id,deletion_status,steps_json`, 518 rows sorted by case_id;
phase order FINDING → REMEDIATION → VERIFICATION, within phase by operation-table order, then system_id, resource_id;
remediation and INCOMPLETE verification use `evidence_id=""`; only evidence at or before `audit_at`.

## Open questions
- How deterministic can the pipeline be vs. where an LLM is actually needed (request-text intent, PDFs/images)?
- Evidence linking: which identifiers (hash, historical email, resource IDs) connect files to users?

## Latest scores
- Samples: n/a
- Full run: n/a

## Known issues
None yet.
