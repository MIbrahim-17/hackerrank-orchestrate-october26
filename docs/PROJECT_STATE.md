# Project State

Rewrite this file on every CHECKPOINT; keep it under 80 lines.

## Current phase
Analysis: samples traced, rules inferred. No pipeline code yet.

## Done
- Read AGENTS.md, README.md, problem_statement.md.
- `uv venv` at repo root; deps pinned in `code/requirements.txt` (anthropic, python-dotenv).
- `.env.example`, `.gitignore`, `docs/DECISIONS.md`, this file, CLAUDE.md import.
- log.txt started (SESSION START + per-turn entries).
- docs/data_profile.md (data profile), docs/sample_trace.md (32-case trace), docs/inferred_rules.md.

## Next step
Decide how to handle the ambiguities in inferred_rules.md (account/analytics linking via activity batch, post-audit linking for verify-only records), then design the pipeline.

## Confirmed rules
H1–H5 all hold; details in [docs/inferred_rules.md](inferred_rules.md).
Key: sort by (op index, system_id, resource_id); policy by category not system; eligibility = manifest captured_at ≤ audit_at;
identity resolved from full history (no window); records linked only if ts in [requested_at, audit_at];
two-gate eligibility (manifest captured_at, then record ts); verification = final-state inventory; exact match; account always verified ABSENT.
Contract reminders: output `case_id,deletion_status,steps_json`, 518 rows sorted by case_id;
phase order FINDING → REMEDIATION → VERIFICATION, within phase by operation-table order, then system_id, resource_id;
remediation and INCOMPLETE verification use `evidence_id=""`; only evidence at or before `audit_at`.

## Open questions
- Accounts / anonymized analytics often link only via deletion-worker activity timing (ambiguous when reported_at collides).
- 3 sample resources are ungrounded; 5 retained audit records are visible only in post-audit files.
- NOT_APPLICABLE detection is untested by samples.

## Latest scores
- Samples: n/a
- Full run: n/a

## Known issues
None yet.
