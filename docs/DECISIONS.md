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
