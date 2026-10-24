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

## 2026-10-24 — Two providers, each for the job it fits (supersedes the Opus-only proposal)
- **What:** `claude-sonnet-5-5` (anthropic SDK) runs the investigation tool loop, starting at effort `medium`. `gemini-3.8-flash` (google-genai SDK) does single-shot calls only: intent classification and one-time PNG transcription, with structured JSON output and the lowest thinking level that keeps intent accuracy at 100% on the samples. `llm.py` has two plain functions, `call_claude` and `call_gemini`, sharing one disk cache and one ledger format (provider, model, purpose, case_id, input, output, cached, from_disk). Keys: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` from `.env`.
- **Why:** The tool loop needs strong multi-turn tool use. Classification and transcription are single-shot and cheap on Flash. Two small functions are simpler than a provider abstraction.
- **Rejected:** Opus 5.5 everywhere (user decision: cost); a generic multi-provider client layer (YAGNI).
- **Pricing (in config.py, with dates):** Sonnet 5.5 $2.00 in / $10.00 out / $0.20 cache read / $2.50 cache write (5-min TTL = 1.25x input), from the claude-api skill model table cached 2026-10-06. Gemini 3.8 Flash $0.75 in / $3.75 out / $0.075 cached input, promotional rate valid to 2026-12-31 (user-supplied).
- **Note:** Sonnet 5.5 requests carry the server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`), per the SDK guidance. The ledger records the model that actually answered.

## 2026-10-24 — PDF text via pypdf, no poppler at runtime
- **What:** Extract PDF text with `pypdf` (pinned). Compare it once with `pdftotext` on all 4 PDFs. If pypdf loses a field, cache the better text for that file or transcribe it with Flash. poppler is never a runtime dependency.
- **Why:** Portability; code.zip must run without system binaries.
- **Rejected:** `pdftotext` at runtime.

## 2026-10-24 — PNGs transcribed at index build
- **What:** All 11 PNGs are transcribed once by gemini-3.8-flash when the evidence index is built, cached by file content hash, and parsed like text. Transcriptions are shown to the user for spot-checking.
- **Why:** `search_evidence` must find screenshots by identifier like any other source, and one call per file is cheap and cacheable.
- **Rejected:** Lazy, model-triggered image reads (the model can't know which image is relevant before it is indexed).

## 2026-10-24 — Post-audit linking rejected (Ambiguity 3)
- **What:** Evidence with manifest captured_at > audit_at, or a record timestamp > audit_at, is never used, not even only to learn a resource ID.
- **Why:** AGENTS.md §6.2: "Evidence created later must not change the answer for that case."
- **Rejected:** Using post-audit files to discover IDs for INCOMPLETE future checks.
- **Exception check (done 2026-10-24, not implemented):** 7 expected resources in 6 sample cases match sample_output.csv only through post-audit evidence. These are case_09 (account_3960, audit_record_4902 via evidence_06), case_23 (audit_record_4128), case_24 (audit_record_7095), case_29 (audit_record_3954) and case_30 (audit_record_1707), all via evidence_02, and case_26 (account_5684) and case_27 (account_3866), also via evidence_02. The 3 account IDs also appear in pre-audit deletion-worker activity rows (activity_3703, activity_3600, activity_3530); the 5 audit records appear nowhere else. Shown to the user; awaiting a decision.

## 2026-10-25 — Evidence model: one Observation per record, gates applied at search time
- **What:** evidence.py parses all 94 files plus the LINK_RESOURCE_IDENTITY activity rows into Observations: (source, captured_at, observed_at, system_id, resource_id, collection, record_type, category_hint, state, exposes_pii, identifiers, refs). The file gate, record gate and lifecycle bound are applied in `search()` / `for_resource()`, which return the eligible observations plus the excluded ones with a reason. Full collection snapshots (bundle snapshots, SQL tables) are kept as Coverage entries for absence proofs (D5).
- **Why:** Parsing once (0.7s) and gating per case keeps the agent tools deterministic, and lets the agent see why something was excluded.
- **Details that came from failures:**
  - **Own resource vs references:** only a record's own `resource_id` gets a state. Other IDs it mentions go to `refs`, as links only. The search_001 row names account_006 as its source, which doesn't prove account_006 exists.
  - **system_id comes from the resource prefix:** 300 log observations had `service=profile_service` acting on account records.
  - **category_hint precedence:** explicit record_type, then the leaf collection name, then a prefix with exactly one category. analytics_ and support_ are never decided by prefix, because the same prefix carries different categories.
  - **exposes_pii ignores lookup fields** (subject, lookup_key, query, correlation_key, ...) and is always False for ABSENT. The handover line `account_9335 | NOT_FOUND | <email>` holds no PII; the email is the lookup key.
  - **The record gate keeps the correct state:** evidence_13 has account_1417 NOT_FOUND at 08-12 (= case_135's audit_at) and FOUND at 08-14. Only the first is eligible, so the later recreation is correctly ignored.
- **Rejected:** Doc-level identifier sharing for screenshots (it would link decoy rows), and a phone-format-specific regex (digits-only normalization is enough).
- **Regression:** `code/tests/test_identity_evidence.py`, 16 tests. On the samples, identity linking finds 76 of 111 expected resources with 0 extras; the rest are activity-only, ungrounded or post-audit-only resources.

## 2026-10-25 — PDF comparison result
- **What:** pypdf and pdftotext give identical field sets and identical word sets on all 4 PDFs. Both drop the colon in times: pypdf splits "06:30" into "06" and "30 UTC" on separate lines, while pdftotext gives "06   30 UTC". That is the same information, so no cached override or Flash transcription is needed.

## 2026-10-25 — Post-audit evidence: ownership only (revises "Post-audit linking rejected")
- **What:** A file or record observed after audit_at may be used only to learn that a resource_id belongs to the subject: the record must match a resolved identifier, and the lifecycle lower bound still applies. It never establishes state and is never cited. State and citations come only from evidence at or before audit_at. Otherwise the step stays uncited where an empty evidence_id is allowed (INCOMPLETE future checks). Activity timing is never used to infer ownership. Implemented as `EvidenceIndex.owned_after_audit()`.
- **Why:** AGENTS.md §6.2: later evidence must not change the *answer* (state). Knowing which IDs are the subject's is identity knowledge, and the gold answers depend on it.
- **Correction:** the earlier entry said "7 resources in 6 sample cases"; the correct count is **8 resources in 7 cases** (case_09 has two). Verified one by one:
  - case_09 account_3960 and audit_record_4902 (owner: evidence_06) → uncited (gold `""`);
  - case_23 audit_record_4128, case_24 audit_record_7095, case_29 audit_record_3954, case_30 audit_record_1707 (owner: evidence_02) → uncited;
  - case_26 account_5684 and case_27 account_3866 (owner: evidence_02) → state ABSENT from evidence_92, cited evidence_92 (gold matches).
- **Result on samples:** 85/111 expected resources found, 0 extras.
- **Rejected:** Activity timing for ownership (user decision); using post-audit state.

## 2026-10-25 — Proving cases for two evidence rules
- **Lifecycle lower bound (observed_at ≥ requested_at): proven.** Removing it adds 3 extras: case_17 gains account_6523 and tombstone_17 (eval case_46's March lifecycle), and case_07 gains object_19 (activity_4007, eval case_61's February lifecycle). Kept.
- **"Lookup keys are not exposed data": no proving sample case.** Removing it changes no sample answer. It flips only case_11's analytics_2034 and support_864, which an explicit IDENTIFIABLE result already settles. On eval data it affects only 3 support_replica observations in evidence_61 (lookup by email, `rows=1`, no data fields). Kept as the safer default, because a lookup key is the auditor's query, not data the record holds. This is noted as unproven.
- **Bug found by the ablation:** with the rule on, handover IDENTIFIABLE records read `exposes_pii=False`. Fixed: an explicit state now decides the flag (IDENTIFIABLE → True; REDACTED, ANONYMIZED, ABSENT → False), and field inspection applies only when the source gives no explicit state. Covered by a test.

## 2026-10-25 — Refusal fallback off
- **What:** call_claude uses plain `messages.create` with no `fallbacks` parameter and no beta header.
- **Why:** One fixed model per job gives reproducibility and a clean usage report (every row names the model it was priced at).
- **Rejected:** Server-side fallback (`fallbacks: "default"`): a refusal would silently switch models and pricing.
- **Note:** llm.py reads GEMINI_API_KEY and falls back to GOOGLE_API_KEY, the google-genai SDK's other standard name, which is what the local .env uses.

## 2026-10-25 — PNG transcription results and parser fixes
- **What:** All 11 PNGs were transcribed by gemini-3.8-flash (thinking LOW, JSON schema output), cached by image hash. Cost: 14.3K input and 8.7K output tokens, about $0.044 in total. Latency was about 2.5 minutes per call (slow; to watch). Spot-checked against the screenshots, every identifier, email, phone, order or ticket number and date matches, and empty "—" cells became null.
- **Parser fixes found by the spot check:**
  - A record whose own resource_id isn't a resource ID now falls back to the resource IDs in its fields, plus the subtitle for the page subject. Without this, analytics_7438 (evidence_19, page keyed by user_20) and support_1034 (evidence_28, page keyed by CS-5034) were dropped.
  - The page header (name, email, phone) now counts toward the page subject's exposes_pii. marketing_001 (evidence_60) had read pii=False.
  - DATA_FLOW records without an enabled flag take their state from status words (Healthy, Continuous → ACTIVE; disabled, paused, stopped → DISABLED). evidence_14's connectors had read PRESENT.
- **Result:** 2,934 observations; samples still 85/111 with 0 extras; 19 tests pass.

## 2026-10-25 — Screenshot records: keep row and detail-panel duplicates; ID-less screens stay text-only
- **What:** When a screenshot shows a resource as a table row and also in a detail panel (e.g. search_428, data_flow_1121, export_1260, backup_9287, audit_record_003), both become observations from the same file. Screens without resource IDs (evidence_42 user_17 reference registry, evidence_46 object listing) produce no observations, but their transcription stays readable via `index.documents` for `read_image_or_pdf`.
- **Why:** The detail panel carries more fields (paths, retention end, timestamps). Both observations come from the same file and capture time, so they never disagree on eligibility or citation.
- **Rejected:** Merging rows and panels (extra code, no gain); inventing resource IDs for ID-less screens.
