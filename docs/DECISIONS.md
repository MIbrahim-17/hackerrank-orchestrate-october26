# Decisions

Append-only. Each entry: what, why, alternatives rejected.

## 2026-10-24 — Tooling and project layout
- **What:** Python 3.12 via `uv venv` at repo root; direct deps pinned in `code/requirements.txt`; official `anthropic` SDK with a hand-written tool-calling loop; secrets from env via `python-dotenv` (`.env`, template in `.env.example`).
- **Why:** `code.zip` only packages `README.md` and `code/`, so requirements must live under `code/`. KISS/YAGNI: stdlib first, flat modules, no frameworks.
- **Rejected:** `pyproject.toml` at root (not packaged in code.zip); agent frameworks (LangChain etc.) — extra abstraction, harder to explain and debug; pinning transitive deps (noise; direct pins are enough for reproducibility here).

## 2026-10-24 — Session memory
- **What:** `docs/PROJECT_STATE.md` (rewritten, <80 lines) imported from CLAUDE.md; `docs/DECISIONS.md` append-only; auto memory only for durable lessons on CHECKPOINT.
- **Why:** Keeps current state loaded every session without bloating context; decision history stays auditable.
- **Rejected:** Editing AGENTS.md (forbidden; organizer-owned).

## 2026-10-24 — Identity resolution vs resource eligibility (D6)
- **What:** Resolve identity from the full `user_audit_log` history with no time window. Associate records with the current request only when the record timestamp is in [requested_at, audit_at].
- **Why:** All 306 identity changes predate their requests, and 103/550 requests use a historical email, so windowing identity would leave them unresolved. The lower bound on records is still needed to exclude a repeat requester's earlier lifecycle (case_17, case_07).
- **Rejected:** A single lifecycle window for everything (breaks historical-email requests); no window at all (pulls in case_46/case_61 resources).

## 2026-10-24 — Two-gate evidence eligibility (D3)
- **What:** Gate 1 is the manifest captured_at ≤ audit_at. Gate 2 is the per-record timestamp ≤ audit_at, interpreted per format. When several eligible records describe a resource, the latest one wins.
- **Why:** evidence_13 and evidence_36 each contain one record dated after the file's capture. For eval case_135 and case_383 the file is eligible (captured_at = audit_at) but that record is not, and a file-only gate would mark a deleted account as remaining.
- **Rejected:** File-level gate only; record-level gate only (it would let a post-audit file prove historical state).

## 2026-10-24 — Verification from the final-state inventory (B4); retained-record discoverability (B2)
- **What:** Build verification from the inventory: account ABSENT, a check for each remediated resource, already-compliant relevant resources, and retained records. A retained record is verified only if discoverable. A COMPLETE case needs a citation eligible at audit_at; an INCOMPLETE case's future check uses an empty evidence_id.
- **Why:** This follows the spec's definition of complete instead of reproducing only what the samples happen to show. It also never fabricates an evidence-backed presence claim from post-audit evidence.
- **Rejected:** "Remediated + account + audit only" (misses compliant records that still need checking); always emitting an audit PRESENT step (it would invent records).

## 2026-10-24 — One remediation per (resource, violation) (A4)
- **What:** Keep 1:1 finding→remediation as the default, but key findings by (resource, violation) and log a warning on compound cases.
- **Why:** A full-dataset check found 0 resources with more than one category label, but unlabelled sources (raw logs, PNGs) can't be checked that way.
- **Rejected:** Hard-asserting 1:1 (silently drops a second violation); building multi-action support now (YAGNI).

## 2026-10-24 — Local scorer metric definitions (code/evaluation/score.py)
- **What:** Status accuracy per gold case. Step exact match is a multiset of whole step objects (step_no ignored) → precision/recall/F1. Per-field accuracy is positional (a missing or extra step is wrong on every field). Sequence accuracy means the whole array is identical. Missing cases score zero; invalid JSON becomes a sentinel step that never matches.
- **Why:** The multiset metric separates "found the right steps" from "ordered them right"; the positional field metric and sequence accuracy catch ordering errors. An order-only error (two steps swapped) leaves step F1 unchanged but drops field and sequence accuracy, which tells us which kind of bug we have.
- **Rejected:** Aligning steps by (system_id, resource_id) before field scoring (hides ordering errors and is ambiguous when one resource has several steps); counting step_no as a field (it is derived from position, so it would double-count order errors). The hidden grader's exact formula is unknown, so these are proxies.
