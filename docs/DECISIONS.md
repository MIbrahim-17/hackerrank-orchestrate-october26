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

## 2026-10-25 — Activity-row linking for resources no evidence ties to the subject (revises "no activity timing")
- **Context:** 23 of 111 expected sample resources (accounts seen only as a 404 or not at all, and anonymized analytics with every identifier null) are tied to their case only by a deletion_worker activity row. The user revised the earlier ban on activity timing because the gold answers expect these resources, on condition that the rule is proven by the samples.
- **Exact links first (none found):** each of the 23 appears in exactly one activity row. No row shares a timestamp with requested_at, reported_at or audit_at, no row names a second resource, and the details never name the subject or the request. All 23 come from source_system `deletion_worker`, with three detail templates: "reported the requested operation as completed" or "completed some internal work" (case_01–10 style, reported_at ±0.1h); "submitted primary profile <account>" (reported_at −1.25h to −0.75h); "Policy action completed for <analytics>" (about −0.48h).
- **Rule (code/activity_links.py):**
  - **Windows per detail template, relative to reported_at:** completed ±15 min; submitted primary profile −1.5h to −0.5h; policy action −0.6h to −0.4h.
  - **Kinds:** account = DELETE_RECORD on account_service; analytics = ANONYMIZE_RECORD on analytics_platform.
  - **Skip** a kind that evidence already links to the subject.
  - **Exclude** a candidate whose evidence ties it to a different user.
  - **Emit** only when the window holds exactly one candidate and no other request's window (all 550 requests) contains it. Any other non-empty window is **ambiguous**: the candidates go to the agent and the validator checks its choice.
  - The rows prove ownership only, never state.
- **Proof (samples):** 7/23 recovered (account_001, 002, 007, 008, 010, 4163, analytics_901) with **0 extras**. The other 16 targets are all inside their case's ambiguous candidate set. Total: **92/111 found, 0 extras**.
- **Full dataset (518 cases):**
  - accounts: 241 already linked by evidence, 30 exactly one, 243 ambiguous, 4 none;
  - analytics: 73 linked, 17 one, 206 ambiguous, 222 none.
  - Caveat: an ambiguous analytics set can belong to a case that has no anonymized analytics at all (samples case_09, 19, 20, 23), so the agent must also be able to choose "none".
- **Rejected alternatives (all measured on the samples):**
  - **A** [requested_at, reported_at], or **B** with +10 min: misses the case_01–10 rows that land after reported_at. Under the emit rule, 0/23 recovered.
  - **D without global uniqueness:** 4–6 extras, all analytics (a neighbour case's anonymize row in the window, e.g. analytics_5335 of case_21 in case_23's window).
  - **D without skip-if-linked:** extras for case_11 and case_18 (another case's anonymize row next to the case's own evidence-linked analytics).
  - **C** [reported_at −1.5h, +10m]: same 7/23 and 0 extras, but more ambiguity on eval (30 vs 47 single-candidate cases), so D was chosen.
  - **Ordering heuristics** (row order vs requested_at or case_id) to break ties: inconsistent across case_18/20, case_31/32 and case_24/25/26, so rejected as guessing.

## 2026-10-25 — Accepted loss: 3 ungrounded sample resources
- **What:** account_004 (case_04), audit_record_6645 (case_18) and audit_record_5569 (case_20) are not reproduced.
- **Why:** None of them appears in any participant file except sample_output.csv. The only numeric matches are unrelated: support_5569 is case_18's own support record, and account_6645 is a February deletion (activity_561). case_04 has no deletion_worker DELETE_RECORD row in any window.
- **Effect:** at most 108/111 resources are reachable on the samples.

## 2026-10-25 — Intent classifier (Flash): thinking level LOW; blocked by free-tier quota
- **What:** `code/intent.py` makes a single-shot call to gemini-3.8-flash with a JSON schema (`intent` enum: DELETION, DATA_ACCESS, DATA_EXPORT, CORRECTION, MARKETING_OPT_OUT, OTHER) and runs batches in a thread pool. The decision is `intent == "DELETION"`; `authorizes_deletion` is forced to agree with it. The prompt encodes what the samples prove: verifying or finishing an earlier deletion (case_25, case_28) and deleting one copy (case_08 export) are deletion requests. `code/evaluation/intent_eval.py` runs the 32 samples plus 6 custom sentences (en, fr, es, ja): export, unsubscribe, close-but-keep-order-history, access, correction, and "unsubscribe but do not delete".
- **Thinking level:** MINIMAL is rejected by the model (400 "Thinking level MINIMAL is not supported for this model"), so LOW is the lowest available level and the default. Accuracy at LOW is not yet confirmed at 100%.
- **Measured:** one intent call at LOW took 82s for 257 input and 42 output tokens; image calls took 136–183s. The latency comes from the API, not from thinking.
- **Blocker:** the GOOGLE_API_KEY in `.env` is on the Gemini **free tier: 20 generate_content requests per day per model**. The quota was used by 11 image transcriptions and 9 intent calls (all 9 correct so far). The rest of the evaluation, and the 518-case run, need a paid tier or a different plan. This is waiting on a user decision.

## 2026-10-25 — Intent classification moved to claude-haiku-5-5 (supersedes the Flash intent entry)
- **What:** `intent.py` calls claude-haiku-5-5 through `call_claude` with structured output (`output_config.format` json_schema, `additionalProperties: false`), cached and run in a thread pool. The 11 cached Flash image transcriptions stay as they are; Flash is now used only for images. Haiku pricing was added to config.py: $0.10 in / $0.50 out / $0.01 cache read / $0.125 cache write per MTok (prompts ≤100K tokens), from the claude-api skill migration guide, looked up 2026-10-25.
- **Why:** The Gemini key is free tier (20 requests/day) and billing can't be enabled now (user decision). Haiku answers in about 3s against about 82s for Flash.
- **Tuning (32 samples + 6 custom sentences in en, fr, es, ja):**
  - thinking disabled, effort low: 37/38 (misses case_27, "audit the deletion as it stood…", labelled OTHER);
  - adaptive, low: 37/38 (same miss);
  - **adaptive, medium: 38/38**;
  - adaptive, high: 38/38.
  - The default is adaptive/medium, the lowest setting at 100%. All 6 custom sentences were right at every level.
- **518 run:** 508 DELETION and 10 non-deletion (3 CORRECTION, 3 DATA_ACCESS, 2 MARKETING_OPT_OUT, 1 DATA_EXPORT, 1 OTHER). The 10 match the 10 `CLASSIFY_REQUEST … non-deletion` activity rows by count, and all 10 texts were read and confirmed.
- **Rejected:** a prompt tweak for "audit" wording (raising effort fixed it without fitting the prompt to one sample); Sonnet for intent (more cost for a single-shot classification).
- **Known waste:** top-level cache_control writes about 700 tokens per intent call that are never read back (about $0.046 of the $0.06 the 518 run cost).

## 2026-10-25 — Activity linking: constraint propagation + workflow-status filter (supersedes the "emit only unique" rule)
- **Method (code/activity_links.py):**
  - per-template windows, evidence elimination and skip-if-linked, as before;
  - **NOT_APPLICABLE cases claim no rows** (Haiku intent);
  - **account rows must match the case's reported_status:** COMPLETE needs SUCCESS, NOT_STARTED needs FAILED, PARTIALLY_COMPLETE needs PARTIAL or SUCCESS;
  - **constraint propagation:** each deletion_worker row serves exactly one request. A row in exactly one open case's window goes to that case and leaves every other set, repeated until stable. What remains is ambiguous and goes to the agent, with the validator checking its choice.
- **Proof of the status filter:** across every sample account row, COMPLETE↔SUCCESS 20/20, NOT_STARTED↔FAILED 12/12, PARTIALLY_COMPLETE↔PARTIAL 3 / SUCCESS 2. It is a semantic link (the workflow's reported status summarizes that delete row), not a timing assumption. Analytics rows show no such relation (COMPLETE: FAILED 12, SUCCESS 4; NOT_STARTED: FAILED 3, SUCCESS 3), so the filter applies to accounts only.
- **Results (samples recovered / 23, sample extras; 518 one / ambiguous / none / linked):**

  | Approach | Recovered / 23 | Extras | Accounts on the 518 | Analytics on the 518 |
  |---|---|---|---|---|
  | Previous rule (emit only unique) | 7 | 0 | 30 / 243 / 4 / 241 | 17 / 206 / 222 / 73 |
  | Propagation (row singletons) | 7 | 0 | 50 / 223 / 4 / 241 | 19 / 204 / 222 / 73 |
  | + NOT_APPLICABLE excluded | 7 | 0 | 50 / 223 / 4 / 231 (+10 n/a) | 20 / 200 / 215 / 73 |
  | **+ status filter (chosen)** | **14** | **0** | **158 / 115 / 4 / 231** (+10 n/a) | **20 / 200 / 215 / 73** |

  Samples overall: **99/111 found, 0 extras.**
- **Rejected:**
  - **Case singletons** (a case with one remaining candidate takes it): 8/23 but 3 extras (case_09, case_19, case_20 analytics; cases with no analytics grab a neighbour's row).
  - **One-to-one min-cost bipartite matching** on |offset − expected offset per template|: settles **0** cases. Every remaining ambiguous component (90 for accounts, 80 for analytics before the status filter) shares a single identical reported_at, so the cost is the same for every case in a component and all optimal assignments tie.
  - **Ordering heuristics:** inconsistent on the samples.
- **Remaining ambiguity is irreducible from timing:** 115 account and 200 analytics cases on the 518. Sample examples: case_28/case_29 (both NOT_STARTED, same reported_at, {account_5482, account_7012}) and case_24/25/26 analytics {analytics_1895, analytics_4566}. An analytics set can belong to a case with no anonymized analytics at all (case_09, case_19, case_20, case_23), so the agent must be allowed to answer "none".

## 2026-10-25 — Pipeline order: intent for every request before activity linking
- **What:** main.py will classify intent for all requests first, then call `build_activity_links(index, all_requests, non_deletion=<NOT_APPLICABLE case_ids>)`, then run the per-case agent only for deletion requests. Sample requests are always included in the linking set, because uniqueness and propagation are global across the 550 requests in the shared activity stream.
- **Why:** NOT_APPLICABLE cases own no deletion_worker rows but their windows overlap neighbours'. Excluding them is grounded (10 Haiku non-deletion = 10 CLASSIFY_REQUEST rows). Linking is deterministic and cheap (≈2s), so it runs once per run.
- **Rejected:** Linking per case inside the agent (the constraints are global); excluding sample requests from the linking set (their rows would then look unclaimed to eval cases).

## 2026-10-25 — Prompt caching off for single-shot intent calls
- **What:** `call_claude(prompt_cache=False)` omits the top-level `cache_control` marker; intent.py uses it. The disk cache is unchanged. `llm.OFFLINE` makes any disk-cache miss raise instead of calling the API (used by `--no-llm`).
- **Why:** Each intent call wrote about 700 cache tokens that were never read (about $0.05 of $0.06 per 518 run). After the change: intent eval still 38/38; the 518 re-run cost 369 live calls, 282K input and 22K output tokens, 0 cache writes (149 hits from identical request texts).

## 2026-10-25 — Validator first; deterministic --no-llm baseline
- **What:** validator.py turns owned resources into steps.
  - **Ownership:** evidence, refs, post-audit ownership-only, activity "one" links, or a grounded agent choice.
  - **Category:** explicit source label > agent override (only without a label) > collection or prefix hint.
  - **State:** latest eligible direct observation > absence from the latest eligible full collection snapshot of that system > UNKNOWN (uncited).
  - **Policy:** deletion_rules.csv by category, with DATA_FLOW → disable and BACKUP_ARCHIVE → block restore.
  - **Steps:** violations give finding + remediation + verification; compliant resources give verification only. Status is INCOMPLETE if any finding. Steps are sorted by (operation index, system_id, resource_id).
  - **Citations:** findings and COMPLETE verifications are cited; INCOMPLETE remediation and verification stay "".
- **Evidence fixes it needed (each proven on a sample):**
  - **Restore state from `deletion_block` and `eligible`:** `restore_candidate_evaluated eligible=true deletion_block=false` means RESTORABLE (case_17, backup_3245 was wrongly verify-only).
  - **"contact_" lookups → SECONDARY_IDENTIFIER (DELETE):** analytics_9914 in case_12 and support_002 in case_10, both gold DELETE. **"message_" scans → SUPPORT_MESSAGE.**
  - **PDF collection carries the file name:** delivery_correction_attachment.pdf → SUPPORT_ATTACHMENT (case_07).
  - **Collection snapshots per system:** an inventory file counts only for systems in its `snapshot_scope`, and an empty in-scope table still proves absence. This yields evidence_51 (empty profiles, case_31) and evidence_54 (case_01, 02).
  - **Direct observations beat snapshot absence:** case_21 cites the evidence_92 404, not the later evidence_51 snapshot.
- **Baseline (`main.py --sample --no-llm`):** status 32/32 (100%); step P 100%, R 93.78%, F1 96.79% (181/193); sequence 65.62% (21/32); fields: phase 93.8%, system_id and resource_id 82.9%, operation and state 84.5%, evidence_id 93.3%. **0 extras.** The 12 missing steps are exactly the 9 resources in ambiguous sets plus the 3 unreachable ones.

## 2026-10-25 — Agent (Sonnet 5.5) as specified; result on the samples
- **What:** tools.py (6 read-only tools bound to the case's gates, plus a strict submit_findings) and agent.py (pre-fetched brief: identity, linked resources with category, state and evidence, ambiguous sets with every record of each candidate; cap of 6 turns; at most 2 validator retries). A choice from an ambiguous set needs a cited record containing the candidate plus a subject identifier or the exact full name, either eligible or ownership-only after audit_at. Otherwise the answer is "none", and the validator rejects ungrounded choices.
- **32-sample result:** identical to the baseline (every metric; 0 extras). The agent changed **0/32** cases: it answered "none" for every ambiguous set (no candidate has grounding in the data), and every category it submitted equalled the hint. 0 rejections, 0 retries, all submitted.
  - Averages: 1.53 turns, 2.59 tool calls, about 6.3K input (mostly cache reads) and 365 output tokens per case.
  - Cost: **$0.0098 per case, $0.31 total, about $5.00 projected for 508 deletion cases.**
- **Flaw found:** the brief listed every hint-categorised resource (accounts, searches, audits) as "without source label", so the agent restated obvious categories. Only support_ and analytics_ resources (the prefixes that carry several categories) need its judgement.

## 2026-10-25 — main.py CLI and run artefacts
- **What:** `python code/main.py [--sample] [--no-llm] [--cases ...] [--out PATH] [--workers N]`.
  - Defaults: the 518 requests → `output.csv` at the repo root; `--sample` → `.cache/sample_pred.csv`.
  - With the agent on, a per-case log (turns, tool calls, tokens, changed vs baseline, choices, rejected items) goes to `<out>.agent_log.json`.
  - Each case computes the deterministic baseline first, then the agent result, so "changed" is measured on every run.
- **Why:** One entry point for the baseline, the agent run and the final output. Sample predictions stay out of the repo root so they are never mistaken for the submission.
- **Rejected:** Separate scripts per mode (duplicated pipeline wiring).
