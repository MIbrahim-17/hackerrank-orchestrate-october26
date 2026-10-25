# Evaluation Report: Ghost Data Still Exists

This report evaluates the deletion-audit pipeline in `code/`. Every number here comes from a recorded run of `code/evaluation/score.py`, the per-case agent logs, or a measurement recorded in `docs/DECISIONS.md`. Nothing is estimated unless marked as such.

**Pipeline in one line:** Haiku 5.5 intent → deterministic evidence index (gates on `captured_at`, record time and the request lifecycle) → identity and activity-row ownership linking → Sonnet 5.5 agent, only for support/analytics records with no explicit category label → deterministic validator that applies `deletion_rules.csv` and builds `steps_json` (the model never writes steps).

## 1. How to reproduce

```bash
.venv/bin/python code/main.py --sample --no-llm --out .cache/sample_pred.csv   # deterministic baseline (no API calls)
.venv/bin/python code/main.py --sample --out .cache/sample_full.csv            # full system (agent where routed)
.venv/bin/python code/evaluation/score.py .cache/sample_pred.csv               # score against dataset/sample_output.csv
.venv/bin/python code/evaluation/score.py .cache/sample_full.csv
.venv/bin/python code/evaluation/score.py --custom                             # 6 synthetic custom cases
.venv/bin/python code/evaluation/intent_eval.py                                # intent: 32 samples + 6 sentences
.venv/bin/python -m unittest discover -s code/tests                            # 26 tests incl. determinism
```

**Metric definitions (`score.py`):**
- **Status accuracy:** `deletion_status` matches.
- **Step exact match:** whole step objects compared as a multiset, ignoring `step_no`, reported as precision, recall and F1.
- **Per-field accuracy:** positional; a missing or extra step counts as wrong on every field.
- **Sequence accuracy:** the whole `steps_json` array is identical.

`steps_json` is parsed as JSON, so key order and whitespace are ignored.

## 2. Results on the 32 public samples

| Metric | `--no-llm` baseline | Full system (agent where routed) |
|---|---|---|
| Case-level status accuracy | **100.00%** (32/32) | **100.00%** (32/32) |
| Step precision | **100.00%** | **100.00%** |
| Step recall | 93.78% (181/193) | 93.78% (181/193) |
| Step F1 | 96.79% | 96.79% |
| Sequence accuracy | 65.62% (21/32) | 65.62% (21/32) |
| Field: phase | 93.78% | 93.78% |
| Field: system_id | 82.90% | 82.90% |
| Field: resource_id | 82.90% | 82.90% |
| Field: operation | 84.46% | 84.46% |
| Field: state | 84.46% | 84.46% |
| Field: evidence_id | 93.26% | 93.26% |
| Extra (wrong) steps | **0** | **0** |

- The two output files are **byte-identical**. Four sample cases route to the agent (case_10, case_12, case_18, case_19), and it changed none of them.
- Precision is 100%: every step the system emits is in the gold answer. All remaining error is missing steps.
- Per-field accuracy is positional, so each missing step shifts the later steps of that case and costs field points even though no field value is wrong (see section 3).

## 3. Why sequence accuracy is 65.62%

11 of 32 cases do not match the gold array exactly. For each one, **removing the gold steps of the resources the prediction lacks leaves an array identical to the prediction** in content, order, state and evidence_id. So every sequence miss is a missing resource; none is an ordering, state or citation error.

| Case | Missing resource(s) | Identical after removing them |
|---|---|---|
| case_03 | analytics_9406 | yes |
| case_04 | account_004 | yes |
| case_18 | audit_record_6645 | yes |
| case_20 | audit_record_5569 | yes |
| case_21 | analytics_5335 | yes |
| case_23 | account_410 | yes |
| case_25 | analytics_1895 | yes |
| case_26 | analytics_4566 | yes |
| case_27 | analytics_4574 | yes |
| case_28 | account_5482, analytics_6077 | yes |
| case_29 | account_7012 | yes |

## 4. The 12 unrecovered sample resources and the 108/111 ceiling

The gold answers involve 111 distinct (case, resource) pairs; the system finds **99**. Each missing resource costs exactly one verification step (193 − 181 = 12).

| Reason | Count | Resources | Why |
|---|---|---|---|
| Ambiguous ownership | 9 | analytics_9406 (case_03), analytics_5335 (case_21), account_410 (case_23), analytics_1895 (case_25), analytics_4566 (case_26), analytics_4574 (case_27), account_5482 + analytics_6077 (case_28), account_7012 (case_29) | No evidence record ties the resource to the subject (an account seen only as a bare 404, an analytics record with every identifier nulled). The only link is a deletion-worker activity row, and several cases share the same `reported_at`, so the row's owner cannot be decided. They are kept as ambiguous sets and never guessed. |
| No grounding anywhere | 3 | account_004 (case_04), audit_record_6645 (case_18), audit_record_5569 (case_20) | These IDs appear in no participant file except `sample_output.csv`, so no system can derive them. |

**Ceiling:** 111 − 3 ungrounded = **108/111**. The system reaches 99/111 (89.2% of all, 91.7% of the reachable 108). The 9 ambiguous resources are the gap between the current result and the ceiling.

## 5. Additional evaluation cases (created by us)

### 5.1 Six synthetic end-to-end cases

They live in `code/evaluation/custom_cases/` (one folder per case, with its input CSVs, evidence files and `expected_output.csv`). All people, emails, phones and records are synthetic (`example.test`); no dataset personal data is reused. `score.py --custom` merges them into a temporary dataset, runs the **unchanged** pipeline on it, and scores each case.

| # | Case | What it tests | Result |
|---|---|---|---|
| 1 | case_9001 | 3-hop email change; the request uses the oldest email | **PASS** |
| 2 | case_9002 | a sync recreates the deleted account before audit_at | **PASS** |
| 3 | case_9003 | evidence after audit_at (record gate and file gate) must not change state or be cited | **PASS** |
| 4 | case_9004 | a record found only through an old email_hash | **PASS** |
| 5 | case_9005 | a non-deletion request in Spanish → NOT_APPLICABLE | **PASS** |
| 6 | case_9006 | a French deletion with retained legal-hold and audit records | **PASS** |

Aggregate (`score.py --custom`): status 100% (6/6); step P/R/F1 100% (20/20); sequence 100% (6/6); all six fields 100%.

### 5.2 Intent classification (32 samples + 6 hand-written sentences in 4 languages)

| Setting (Haiku 5.5) | Correct | Miss |
|---|---|---|
| thinking disabled, effort low | 37/38 | case_27 ("audit the deletion as it stood…", labelled OTHER) |
| adaptive, low | 37/38 | case_27 |
| **adaptive, medium (used)** | **38/38** | — |
| adaptive, high | 38/38 | — |

The 6 sentences, all classified correctly at every setting:
- "Please export all of my personal data…" → DATA_EXPORT (en)
- "Unsubscribe me from your marketing emails…" → MARKETING_OPT_OUT (en)
- "Close my account, but keep my order history…" → DELETION (en)
- "Je voudrais savoir quelles données…" → DATA_ACCESS (fr)
- "He cambiado de dirección de correo…" → CORRECTION (es)
- "メールマガジンの配信を停止してください。アカウントは削除しないでください。" → MARKETING_OPT_OUT (ja)

On the 518 evaluation requests, 10 are classified as non-deletion. That matches the 10 `CLASSIFY_REQUEST … as non-deletion` activity rows, and all 10 texts were read and confirmed.

### 5.3 Every custom case in full

### Custom case 1: 01_three_hop_oldest_email (`case_9001`): **PASS**

User changed email three times (q0→q1→q2→q3). The request arrives from the oldest address q0. The account is checked under the current address, a search document still exists under the middle address q1, and a retained audit record is keyed by user_id. Identity resolution must follow all three hops.

**Input: request**

| email | requested_at | reported_status | reported_at | audit_at |
|---|---|---|---|---|
| avery.q0@example.test | 2026-05-01T10:00:00Z | COMPLETE | 2026-05-03T10:00:00Z | 2026-05-20T10:00:00Z |

> Please delete my account and every personal record linked to it, including under my previous email addresses.

**Input: identity snapshot**

| user_id | name | email | email_hash |
|---|---|---|---|
| user_9001 | Avery Quill | avery.q3@example.test | 28add223f16c8514… |

**Input: identity history (user_audit_log)**

| audit_id | event_time | field | old → new |
|---|---|---|---|
| audit_9001 | 2025-01-10T10:00:00Z | email | avery.q0@example.test → avery.q1@example.test |
| audit_9003 | 2025-06-10T10:00:00Z | email | avery.q1@example.test → avery.q2@example.test |
| audit_9005 | 2025-11-10T10:00:00Z | email | avery.q2@example.test → avery.q3@example.test |
| audit_9002 | 2025-01-10T10:00:00Z | email_hash | a7109bd5c61b61de… → 298dbc302f5130c0… |
| audit_9004 | 2025-06-10T10:00:00Z | email_hash | 298dbc302f5130c0… → 1e67ecab11040147… |
| audit_9006 | 2025-11-10T10:00:00Z | email_hash | 1e67ecab11040147… → 28add223f16c8514… |

**Input: evidence**

- `evidence_9001` (custom_ledger_9001.json, captured 2026-05-15T10:00:00Z):
  - 2026-05-15T10:00:00Z · account_service · account_90011 · USER_PROFILE · **NOT_FOUND** · subject avery.q3@example.test
  - 2026-05-15T10:00:00Z · search_service · search_90012 · SEARCH_INDEX_ENTRY · **FOUND** · subject avery.q1@example.test
  - 2026-05-15T10:00:00Z · security_service · audit_record_90013 · SECURITY_AUDIT_LOG · **FOUND** · subject user_9001

**Expected:** INCOMPLETE

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | FINDING | search_service | search_90012 | REPORT_REMAINING_RECORD | PRESENT | evidence_9001 |
| 2 | REMEDIATION | search_service | search_90012 | DELETE_RECORD | ABSENT | "" |
| 3 | VERIFICATION | account_service | account_90011 | VERIFY_RECORD_ABSENT | ABSENT | "" |
| 4 | VERIFICATION | search_service | search_90012 | VERIFY_RECORD_ABSENT | ABSENT | "" |
| 5 | VERIFICATION | security_service | audit_record_90013 | VERIFY_RECORD_PRESENT | PRESENT | "" |

**Actual (pipeline output):** INCOMPLETE (identical to expected)

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | FINDING | search_service | search_90012 | REPORT_REMAINING_RECORD | PRESENT | evidence_9001 |
| 2 | REMEDIATION | search_service | search_90012 | DELETE_RECORD | ABSENT | "" |
| 3 | VERIFICATION | account_service | account_90011 | VERIFY_RECORD_ABSENT | ABSENT | "" |
| 4 | VERIFICATION | search_service | search_90012 | VERIFY_RECORD_ABSENT | ABSENT | "" |
| 5 | VERIFICATION | security_service | audit_record_90013 | VERIFY_RECORD_PRESENT | PRESENT | "" |

### Custom case 2: 02_sync_recreates_before_audit (`case_9002`): **PASS**

The account was NOT_FOUND on 06-05, but an active connector re-synced it and it is FOUND again on 06-08, before audit_at (06-10). The workflow claims COMPLETE. The latest eligible state wins: the account is a remaining record and the active flow must be disabled before the record is deleted.

**Input: request**

| email | requested_at | reported_status | reported_at | audit_at |
|---|---|---|---|---|
| blake.f@example.test | 2026-06-01T09:00:00Z | COMPLETE | 2026-06-03T09:00:00Z | 2026-06-10T09:00:00Z |

> Please erase my account and make sure no integration brings my data back.

**Input: identity snapshot**

| user_id | name | email | email_hash |
|---|---|---|---|
| user_9002 | Blake Ferrow | blake.f@example.test | f4651a207fe68891… |

**Input: activity (a claim, not proof)**

| activity_id | event_time | event_type | resource_id | result | details |
|---|---|---|---|---|---|
| activity_9001 | 2026-06-07T09:00:00Z | SYNC_RECORD | account_90021 | SUCCESS | Active connector repopulated downstream resource account_90021. |

**Input: evidence**

- `evidence_9002` (custom_ledger_9002.json, captured 2026-06-05T09:00:00Z):
  - 2026-06-05T09:00:00Z · account_service · account_90021 · USER_PROFILE · **NOT_FOUND** · subject blake.f@example.test
- `evidence_9003` (custom_ledger_9003.json, captured 2026-06-08T09:00:00Z):
  - 2026-06-08T09:00:00Z · account_service · account_90021 · USER_PROFILE · **FOUND** · subject blake.f@example.test
  - 2026-06-08T09:00:00Z · integration_service · data_flow_90022 · DATA_FLOW · **ACTIVE** · subject blake.f@example.test

**Expected:** INCOMPLETE

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | FINDING | account_service | account_90021 | REPORT_REMAINING_RECORD | PRESENT | evidence_9003 |
| 2 | FINDING | integration_service | data_flow_90022 | REPORT_ACTIVE_DATA_FLOW | ACTIVE | evidence_9003 |
| 3 | REMEDIATION | integration_service | data_flow_90022 | DISABLE_DATA_FLOW | DISABLED | "" |
| 4 | REMEDIATION | account_service | account_90021 | DELETE_RECORD | ABSENT | "" |
| 5 | VERIFICATION | account_service | account_90021 | VERIFY_RECORD_ABSENT | ABSENT | "" |
| 6 | VERIFICATION | integration_service | data_flow_90022 | VERIFY_DATA_FLOW_DISABLED | DISABLED | "" |

**Actual (pipeline output):** INCOMPLETE (identical to expected)

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | FINDING | account_service | account_90021 | REPORT_REMAINING_RECORD | PRESENT | evidence_9003 |
| 2 | FINDING | integration_service | data_flow_90022 | REPORT_ACTIVE_DATA_FLOW | ACTIVE | evidence_9003 |
| 3 | REMEDIATION | integration_service | data_flow_90022 | DISABLE_DATA_FLOW | DISABLED | "" |
| 4 | REMEDIATION | account_service | account_90021 | DELETE_RECORD | ABSENT | "" |
| 5 | VERIFICATION | account_service | account_90021 | VERIFY_RECORD_ABSENT | ABSENT | "" |
| 6 | VERIFICATION | integration_service | data_flow_90022 | VERIFY_DATA_FLOW_DISABLED | DISABLED | "" |

### Custom case 3: 03_post_audit_evidence_ignored (`case_9003`): **PASS**

At audit_at (07-10 12:00) the account is NOT_FOUND. Two later observations say FOUND: a record dated 07-12 inside a file captured exactly at audit_at (record gate), and a file captured on 07-20 (file gate). Neither may change the state or be cited, so the case is COMPLETE with citations to the eligible file only.

**Input: request**

| email | requested_at | reported_status | reported_at | audit_at |
|---|---|---|---|---|
| casey.m@example.test | 2026-07-01T08:00:00Z | COMPLETE | 2026-07-03T08:00:00Z | 2026-07-10T12:00:00Z |

> Please close my account permanently and confirm the deletion.

**Input: identity snapshot**

| user_id | name | email | email_hash |
|---|---|---|---|
| user_9003 | Casey Morrow | casey.m@example.test | 145a949318b01f5c… |

**Input: evidence**

- `evidence_9004` (custom_ledger_9004.json, captured 2026-07-10T12:00:00Z):
  - 2026-07-10T12:00:00Z · account_service · account_90031 · USER_PROFILE · **NOT_FOUND** · subject casey.m@example.test
  - 2026-07-10T12:00:00Z · security_service · audit_record_90032 · SECURITY_AUDIT_LOG · **FOUND** · subject user_9003
  - 2026-07-12T12:00:00Z · account_service · account_90031 · USER_PROFILE · **FOUND** · subject casey.m@example.test
- `evidence_9005` (custom_ledger_9005.json, captured 2026-07-20T12:00:00Z):
  - 2026-07-20T12:00:00Z · account_service · account_90031 · USER_PROFILE · **FOUND** · subject casey.m@example.test

**Expected:** COMPLETE

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | VERIFICATION | account_service | account_90031 | VERIFY_RECORD_ABSENT | ABSENT | evidence_9004 |
| 2 | VERIFICATION | security_service | audit_record_90032 | VERIFY_RECORD_PRESENT | PRESENT | evidence_9004 |

**Actual (pipeline output):** COMPLETE (identical to expected)

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | VERIFICATION | account_service | account_90031 | VERIFY_RECORD_ABSENT | ABSENT | evidence_9004 |
| 2 | VERIFICATION | security_service | audit_record_90032 | VERIFY_RECORD_PRESENT | PRESENT | evidence_9004 |

### Custom case 4: 04_old_email_hash_only (`case_9004`): **PASS**

A search document is visible only in a log trace keyed by the sha256 hash of the user's previous email. The email and its hash changed in 2025, and the request uses the current email. The old hash comes from user_audit_log; the lookup line and the result line are joined by trace_id.

**Input: request**

| email | requested_at | reported_status | reported_at | audit_at |
|---|---|---|---|---|
| dana.p2@example.test | 2026-08-01T10:00:00Z | COMPLETE | 2026-08-02T10:00:00Z | 2026-08-15T10:00:00Z |

> I want my account and all of my personal data deleted.

**Input: identity snapshot**

| user_id | name | email | email_hash |
|---|---|---|---|
| user_9004 | Dana Pell | dana.p2@example.test | b35c564a9b553275… |

**Input: identity history (user_audit_log)**

| audit_id | event_time | field | old → new |
|---|---|---|---|
| audit_9007 | 2025-03-01T10:00:00Z | email | dana.p1@example.test → dana.p2@example.test |
| audit_9008 | 2025-03-01T10:00:00Z | email_hash | de5a9ed7c602017b… → b35c564a9b553275… |

**Input: evidence**

- `evidence_9006` (custom_search_trace_9004.log, captured 2026-08-10T10:00:00Z):
  - `2026-08-10T09:00:00Z level=DEBUG service=search_service trace_id=tr-9004001 event=index_query_started match_key=de5a9ed7c602017b… attempt=1`
  - `2026-08-10T09:00:01Z level=INFO service=search_service trace_id=tr-9004001 resource_id=search_90041 event=index_query_completed result=hit index=customer_directory_v3`
- `evidence_9007` (custom_ledger_9007.json, captured 2026-08-10T10:00:00Z):
  - 2026-08-10T10:00:00Z · account_service · account_90042 · USER_PROFILE · **NOT_FOUND** · subject dana.p2@example.test

**Expected:** INCOMPLETE

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | FINDING | search_service | search_90041 | REPORT_REMAINING_RECORD | PRESENT | evidence_9006 |
| 2 | REMEDIATION | search_service | search_90041 | DELETE_RECORD | ABSENT | "" |
| 3 | VERIFICATION | account_service | account_90042 | VERIFY_RECORD_ABSENT | ABSENT | "" |
| 4 | VERIFICATION | search_service | search_90041 | VERIFY_RECORD_ABSENT | ABSENT | "" |

**Actual (pipeline output):** INCOMPLETE (identical to expected)

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | FINDING | search_service | search_90041 | REPORT_REMAINING_RECORD | PRESENT | evidence_9006 |
| 2 | REMEDIATION | search_service | search_90041 | DELETE_RECORD | ABSENT | "" |
| 3 | VERIFICATION | account_service | account_90042 | VERIFY_RECORD_ABSENT | ABSENT | "" |
| 4 | VERIFICATION | search_service | search_90041 | VERIFY_RECORD_ABSENT | ABSENT | "" |

### Custom case 5: 05_non_deletion_spanish (`case_9005`): **PASS**

A Spanish request to download a copy of the data, explicitly asking not to delete the account. Even though a live account record exists, the request does not authorize deletion, so the answer is NOT_APPLICABLE with [].

**Input: request**

| email | requested_at | reported_status | reported_at | audit_at |
|---|---|---|---|---|
| emilia.s@example.test | 2026-09-01T09:00:00Z | NOT_STARTED | 2026-09-02T09:00:00Z | 2026-09-10T09:00:00Z |

> Quisiera descargar una copia de todos mis datos personales. Por favor, no eliminen mi cuenta ni mi historial de pedidos.

**Input: identity snapshot**

| user_id | name | email | email_hash |
|---|---|---|---|
| user_9005 | Emilia Sarto | emilia.s@example.test | 76a10fcfb45099df… |

**Input: evidence**

- `evidence_9008` (custom_ledger_9008.json, captured 2026-09-05T09:00:00Z):
  - 2026-09-05T09:00:00Z · account_service · account_90051 · USER_PROFILE · **FOUND** · subject emilia.s@example.test

**Expected:** NOT_APPLICABLE

`[]` (no steps)

**Actual (pipeline output):** NOT_APPLICABLE (identical to expected)

`[]` (no steps)

### Custom case 6: 06_french_deletion_legal_hold (`case_9006`): **PASS**

A French deletion request that accepts legally required invoices being kept. The account is gone, a legal-hold order record and a security audit record must be retained (RETAIN policy), so the case is COMPLETE with PRESENT verifications for both.

**Input: request**

| email | requested_at | reported_status | reported_at | audit_at |
|---|---|---|---|---|
| felix.g@example.test | 2026-09-01T09:00:00Z | COMPLETE | 2026-09-02T09:00:00Z | 2026-09-12T09:00:00Z |

> Je souhaite supprimer définitivement mon compte. Vous pouvez conserver les factures exigées par la loi.

**Input: identity snapshot**

| user_id | name | email | email_hash |
|---|---|---|---|
| user_9006 | Félix Garnier | felix.g@example.test | 70cb3c8573d6356f… |

**Input: evidence**

- `evidence_9009` (custom_ledger_9009.json, captured 2026-09-10T09:00:00Z):
  - 2026-09-10T09:00:00Z · account_service · account_90061 · USER_PROFILE · **NOT_FOUND** · subject felix.g@example.test
  - 2026-09-10T09:00:00Z · legal_service · legal_hold_90062 · LEGAL_HOLD_RECORD · **FOUND** · subject user_9006
  - 2026-09-10T09:00:00Z · security_service · audit_record_90063 · SECURITY_AUDIT_LOG · **FOUND** · subject user_9006

**Expected:** COMPLETE

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | VERIFICATION | account_service | account_90061 | VERIFY_RECORD_ABSENT | ABSENT | evidence_9009 |
| 2 | VERIFICATION | legal_service | legal_hold_90062 | VERIFY_RECORD_PRESENT | PRESENT | evidence_9009 |
| 3 | VERIFICATION | security_service | audit_record_90063 | VERIFY_RECORD_PRESENT | PRESENT | evidence_9009 |

**Actual (pipeline output):** COMPLETE (identical to expected)

| # | phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|---|
| 1 | VERIFICATION | account_service | account_90061 | VERIFY_RECORD_ABSENT | ABSENT | evidence_9009 |
| 2 | VERIFICATION | legal_service | legal_hold_90062 | VERIFY_RECORD_PRESENT | PRESENT | evidence_9009 |
| 3 | VERIFICATION | security_service | audit_record_90063 | VERIFY_RECORD_PRESENT | PRESENT | evidence_9009 |

## 6. Failures found and improvements made

Each item lists the root cause, the fix, and the measured before/after. Full entries are in `docs/DECISIONS.md`.

### 6.1 case_17: backup restore flag not read
- **Root cause:** backup logs express restorability as `restore_candidate_evaluated eligible=true deletion_block=false`. The state parser knew only `restore_allowed`, so `backup_3245` read as PRESENT and was treated as compliant (verify-only). The `REPORT_RESTORE_RISK` / `BLOCK_RESTORE` steps were missing and the status was wrong.
- **Fix:** `deletion_block=false` with `eligible=true` → RESTORABLE; `deletion_block=true` → BLOCKED.
- **Before → after (samples, `--no-llm`):** status 96.88% → **100%**; step P 98.32% → **100%**, R 91.19% → **93.78%**, F1 94.62% → **96.79%**; sequence 62.50% → **65.62%**.

### 6.2 Output sorted as text instead of by number
- **Root cause:** `write_csv` sorted case IDs as strings, so `case_100` came before `case_33`. The zero-padded sample IDs (`case_01`…`case_32`) sort the same either way, which hid the bug until the 518 run.
- **Fix:** numeric sort key. The built-in output validation (which checks numeric order) caught it.
- **Before → after:** validation "rows not sorted by numeric case_id" → **validation OK**. Content unchanged; the re-run came from the cache at $0.

### 6.3 Random tie-break between category hints
- **Root cause:** `max(set(values), key=count)`. Python randomizes string hashing per process, so when two hints tie the winner changes between runs. It affected support_9309 (case_119: one attachment hint, one message hint), which showed up as a spurious "agent change".
- **Fix:**
  - An explicit, specific-beats-generic label rule: a record naming an attachment file (`ticket_attachments`, `attachment_scan`, `attachment_pii_scan`, `file="…pdf"`) is a SUPPORT_ATTACHMENT label from any time; generic views such as `support_records` are not labels.
  - A fixed `LABEL_PRIORITY` for conflicts (0 conflicts measured).
  - `most_common()` with an alphabetical tie-break, and an audit of every set and dict use.
- **Before → after:** output could differ between runs → **byte-identical across `PYTHONHASHSEED` 1 and 2** and equal to `output.csv` (`test_determinism.py`). case_71 and case_119 now resolve to SUPPORT_ATTACHMENT → DELETE.

### 6.4 operations_stream logs not parsed (found through the agent on case_515)
- **Root cause:** in operations_stream logs the text after the timestamp starts with "| ", so the `LEVEL | service | trace | event | k=v` branch never matched. Events were lost and lines were not grouped by trace, so a lookup key and a resource_id on different lines were never joined.
- **How it was found:** on case_515 the agent read `attachment_pii_scan … file="delivery_confirmation_71.pdf"` and classified support_4533 as an attachment, while the baseline said message. Investigating that disagreement exposed the parser gap. No sample uses this log family for a support record, so no sample-based check could have caught it.
- **Fix:** strip the leading "| " before format detection.
- **Before → after (518 run):** **+25 owned resources in 16 cases, 0 removed** (audit records, accounts, searches, data flows, a backup, a legal hold). case_517 and case_519 flipped COMPLETE → INCOMPLETE. Samples unchanged.

### 6.5 Activity-row ownership: 7 → 14 of the 23 activity-only sample resources
23 sample resources (accounts seen only as a 404 or not at all, anonymized analytics) are tied to their case only by a deletion-worker activity row. Each step was measured on the samples (extras must stay 0) and on the 518:

| Step | Recovered / 23 | Sample extras | Samples found / 111 | Accounts on the 518 (one / ambiguous) |
|---|---|---|---|---|
| Evidence + post-audit ownership only (no activity rows) | 0 | 0 | 85 | — |
| Per-template time windows, emit only unique | 7 | 0 | 92 | 30 / 243 |
| + constraint propagation (each row serves one request) | 7 | 0 | 92 | 50 / 223 |
| + non-deletion requests excluded | 7 | 0 | 92 | 50 / 223 |
| **+ account result must match `reported_status`** | **14** | **0** | **99** | **158 / 115** |
| Rejected: case singletons | 8 | 3 | — | — |
| Rejected: one-to-one min-cost matching | +0 | 0 | — | every ambiguous group shares one `reported_at`, so all assignments tie |

The decisive fact was found by cross-tabulating case fields against candidate rows: the workflow's `reported_status` summarizes the primary-profile delete row (COMPLETE ↔ SUCCESS 20/20, NOT_STARTED ↔ FAILED 12/12, PARTIALLY_COMPLETE ↔ PARTIAL 3 / SUCCESS 2).

### 6.6 Other fixes (each verified on the samples or the evidence)
- **Ownership from post-audit files:** 8 sample resources (case_09/23/24/26/27/29/30) are tied to the subject only by a file captured after audit_at. They are used for ownership only, never for state or citation; samples went from 77 to 85 found with 0 extras.
- **Category hints:** `contact_` lookups → SECONDARY_IDENTIFIER (analytics_9914, support_002, both gold DELETE); `message_` scans → SUPPORT_MESSAGE; a PDF's file name carries "attachment" (support_001).
- **Snapshot absence per system:** an empty in-scope snapshot proves ABSENT (case_31 cites evidence_51; case_01/02 cite evidence_54).
- **`exposes_pii` contradiction:** handover records marked IDENTIFIABLE read as not exposed. An explicit state now decides the flag.
- **Screenshot parsing:** records keyed by a user or ticket now fall back to the resource IDs in their fields (recovers analytics_7438 and support_1034); page headers count toward PII; connector status words give ACTIVE/DISABLED.
- **Intent provider:** the Gemini key is free tier (20 requests/day, about 80 s per call) and ran out mid-evaluation. Intent moved to Haiku 5.5 (about 3 s per call); tuning took accuracy from 37/38 to 38/38.

## 7. The agent's measured contribution

| Measurement | Result |
|---|---|
| Samples, first agent run (all 32 deletion cases) | **0 of 32** changed vs the deterministic baseline |
| Samples, current routing (4 cases) | 0 of 4 changed; output byte-identical to the baseline |
| Ambiguous ownership sets answered | **46 of 46 "none"** (9 sample + 37 pilot); 0 grounded picks |
| 40-case eval pilot | 1 change (case_431). A later explicit-label rule overrides it, so it does not reach the output. |
| First 518 run (84 routed) | 3 changes: case_515 right, case_71 likely wrong, case_119 a random tie |
| **Final 518 run (77 routed)** | **0 of 77 changed** vs the baseline |
| Discovery | case_515 exposed the operations_stream parser bug (+25 resources in 16 cases) |

The agent's direct effect on the final output is zero. Its value so far is diagnostic: on case_515 it read raw evidence correctly where the deterministic path had a blind spot, which led to a fix that now applies to every case. Because it can only (a) choose from an ambiguous ownership set with a cited grounding record and (b) categorize support/analytics records with no explicit label, it also cannot introduce unsupported resources. The validator rejects ungrounded choices, and 0 rejections were needed.

## 8. Known limitations
- **Ambiguous ownership on the 518:** 115 account sets and 200 analytics sets have no record tying a candidate to the subject, so they stay unresolved by design. On the samples this costs 9 of 111 resources. An analytics set may also belong to a case that has no anonymized analytics at all.
- **Unreachable sample resources:** 3 (account_004, audit_record_6645, audit_record_5569), giving a ceiling of 108/111.
- **Rules reasoned but not proven by a sample:**
  - "Lookup keys are not exposed data" (it affects 3 eval records).
  - Categories may come from evidence of any time ("what a resource is is stable").
  - Attachment-file records are explicit SUPPORT_ATTACHMENT labels.
  All three are consistent with proven rules (ownership-only post-audit evidence) and leave the samples unchanged.
- **Sample coverage:** every sample `audit_at` falls in Sep–Oct 2026 while the eval spans Jan–Oct. No sample is NOT_APPLICABLE. Several evidence families (inventory SQL, regional and reporting replicas, most screenshots, operations_stream logs) are never cited by a sample.
- **Screenshot states:** screenshots without explicit flags (e.g. backup consoles) read as PRESENT. Restore risk is only detected from flags in logs, snapshots and inventories.
- **Images:** the 11 PNGs were transcribed once by gemini-3.8-flash (free tier) and cached. Re-transcription needs a Gemini key; the cached transcriptions are used as is.
- **Model output determinism:** model calls are deterministic only through the disk cache. A fresh, uncached run could produce different agent or intent answers, although every agent output is constrained by the validator.
