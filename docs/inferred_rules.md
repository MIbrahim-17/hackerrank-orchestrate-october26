# Inferred Rules

Rules derived from the 32 public samples. Each rule names the case(s) that prove it.
Per-step evidence: [sample_trace.md](sample_trace.md). Verdicts on the five hypotheses are at the end.

## A. Output shape (checked programmatically on all 32 cases, 0 violations)

- **A1. Global sort.** Steps are sorted by (operation index in the problem-statement table, `system_id`, `resource_id`). This yields FINDING → REMEDIATION → VERIFICATION. Shown by all 32, e.g. case_11, case_26.
  - Findings: REMAINING_RECORD, EXPOSED_PII, ACTIVE_DATA_FLOW, RESTORE_RISK.
  - Remediation: DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE, REDACT, ANONYMIZE.
  - Verification: ABSENT, PRESENT, REDACTED, ANONYMIZED, DATA_FLOW_DISABLED, RESTORE_BLOCKED.
- **A2. COMPLETE = verification steps only**, each with an `evidence_id`. Shown by case_01–04, 21, 25–28, 31.
- **A3. INCOMPLETE = findings + remediation + verification.** Findings carry an `evidence_id`. Every remediation step and every verification step has `evidence_id=""`, including the verification of an already compliant retained audit record. Shown by case_11 (audit_record_9394) and case_14.
- **A4. One remediation per finding is the default, not an invariant.** In the samples, the finding set equals the remediation set (case_05–20, 22–24, 29, 30, 32). Default mapping:
  - REMAINING_RECORD → DELETE_RECORD
  - EXPOSED_PII → REDACT_RECORD or ANONYMIZE_RECORD (by category)
  - ACTIVE_DATA_FLOW → DISABLE_DATA_FLOW
  - RESTORE_RISK → BLOCK_RESTORE

  Compound check on the full dataset: no `resource_id` carries more than one category label in any labelled source (TXT handover, lookup ledgers, inventory, readback logs). Every prefix maps to a single category. Unlabelled sources (raw logs, PNGs) could not be checked this way.

  The pipeline therefore treats one finding as one remediation unit, but models a finding as (resource, violation) rather than (resource). If a resource ever shows two independent violations, both are kept, and a mismatch warning is logged instead of silently merging them.
- **A5. Every remediation has its matching verification** (DELETE → ABSENT, REDACT → REDACTED, ANONYMIZE → ANONYMIZED, DISABLE → DATA_FLOW_DISABLED, BLOCK → RESTORE_BLOCKED). Shown by all INCOMPLETE samples.
- **A6. Prefix → system_id is fixed.** account → account_service, search → search_service, analytics → analytics_platform, support → support_platform, export → export_service, data_flow → integration_service, backup → backup_service, audit_record → security_service, tombstone → identity_service. Shown by all 32.
- **A7. No NOT_APPLICABLE in the samples.** The behaviour for non-deletion requests comes only from the spec.

## B. Verification scope (H1)

- **B1. The primary account is always verified ABSENT,** even when it was never a finding. Shown in 32/32 cases, e.g. case_06 (account_006 is not a finding but is verified) and case_13 (account_9335: activity says DELETE FAILED, evidence_03 says NOT_FOUND, so it is verify-only).
- **B2. Retained records: the policy requirement is separate from discoverability.**
  - *Policy:* a SECURITY_AUDIT_LOG record within retention (rule_12), or a LEGAL_HOLD_RECORD with an active hold (rule_13), must stay available. It is never a finding while it is present.
  - *Discoverability:* we emit a step for a retained record only if we can find it, and what we may claim depends on the case status:
    - **COMPLETE:** VERIFY_RECORD_PRESENT must cite evidence that is eligible at `audit_at` (D3). Every COMPLETE sample does (case_03, 21, 25–28, 31). If the record is visible only after `audit_at`, we cannot claim it was present at `audit_at`, so we don't emit an evidence-backed step for it.
    - **INCOMPLETE:** VERIFY_RECORD_PRESENT is a post-remediation check with `evidence_id=""`, so it makes no claim about the past. The samples include such checks even when the record is only visible in post-audit files: audit_record_4128 (case_23), 7095 (case_24), 3954 (case_29) and 1707 (case_30) appear only in evidence_02, and audit_record_4902 (case_09) only in evidence_06. Using a later file just to learn the record's ID (never as a citation or as proof of state) is the open decision in Ambiguity 3.
  - Samples: 24/32 cases verify an audit record. Cases 01, 02 and 04–08 have no audit record linked to the user anywhere, so none is emitted. case_18 and case_20 verify records that are not discoverable in participant data at all (Ambiguity 2).
- **B3. COMPLETE verification lists every relevant record in its compliant state:** account ABSENT, audit PRESENT, tombstone or support REDACTED, analytics ANONYMIZED, data_flow DISABLED, backup BLOCKED, each with eligible evidence. Shown by case_26, 27, 28 (6 steps each) and case_31 (tombstone).
- **B4. Verification set = the required final-state inventory, for both COMPLETE and INCOMPLETE.** The steps are derived from the inventory, not from the finding list:
  1. The primary account is verified ABSENT (B1).
  2. Each remediated resource gets its matching verification (A5).
  3. Every other relevant resource whose compliant state the spec requires is also checked, even if it is already compliant: anonymized analytics, redacted messages or tombstones, disabled flows, blocked backups.
  4. Retained records are verified PRESENT where policy requires it and B2's discoverability rules allow.

  Sample status: items 1, 2 and 4 are proven for INCOMPLETE (all INCOMPLETE samples). Item 3 is proven for COMPLETE (case_26–28) but untested for INCOMPLETE, because no INCOMPLETE sample has an already compliant non-retained resource. We apply it anyway, since the spec says a deletion is complete only when "every relevant copy has the required treatment".

## C. Policy by data category, not system (H2)

The category comes from what the record is (`record_type`, collection, log event), never from `system_id` or the ID prefix.
- **C1. Support message vs attachment.**
  - support_864 is `SUPPORT_MESSAGE` → EXPOSED_PII / REDACT (rule_05). Proof: case_11, evidence_03 line "support_864 | SUPPORT_MESSAGE | IDENTIFIABLE".
  - support_4218 is `SUPPORT_ATTACHMENT` → REMAINING / DELETE (rule_06). Proof: case_13, evidence_03 line "support_4218 | SUPPORT_ATTACHMENT | FOUND".
  - The PDF attachment support_001 → DELETE (case_07).
- **C2. analytics_2034 (case_11) is an `ANALYTICS_PROFILE`** → EXPOSED_PII / ANONYMIZE (rule_07). **analytics_9914 (case_12) uses the same system but gets REMAINING / DELETE.** Its evidence_01 line is `event=contact_lookup_completed ... email_opt_in=true correlation_key=<old email hash>`, which is a contact/marketing-style record, not an analytics profile.
- **C3. Other mappings:**
  - search → SEARCH_INDEX_ENTRY → DELETE (rule_03): case_06, 11, 13, 16, 18–20, 22–24, 29, 30.
  - export → USER_EXPORT → DELETE (rule_09): case_08, 23.
  - backup with restore allowed → RESTORE_RISK / BLOCK (rule_14): case_09, 14, 17.
  - audit → RETAIN (rule_12).
- **C4. Tombstone (rule_15).** A tombstone with null name/email/phone/hash → VERIFY REDACTED (case_31, tombstone_440). A tombstone still holding PII → EXPOSED_PII / REDACT, never DELETE (case_32, tombstone_9178).
- **C5. Active connector selecting the user → REPORT_ACTIVE_DATA_FLOW** (case_11, 15, 18, 20, 29, 30). A disabled one → VERIFY_DATA_FLOW_DISABLED in COMPLETE (case_26–28).

## D. State and evidence

- **D1. Evidence beats activity claims.**
  - case_13 account_9335: activity DELETE FAILED, evidence NOT_FOUND → verify-only.
  - case_05 account_005: activity DELETE SUCCESS, but the failover replica still holds it → REMAINING.
  - case_25 account_3136: activity FAILED, evidence_92 lookup 404 → COMPLETE.
- **D2. A copy in any replica counts.** account_005 is present only in `customer_profiles_failover_replica`, not primary (case_05, evidence_54). account_994 is present only in `customer_data_read_replica` (case_16, evidence_05).
- **D3. Eligibility has two gates: the file, then each record.**
  1. **File gate (where the manifest defines one):** manifest `captured_at` ≤ `audit_at`. A file captured after `audit_at` never proves the state at `audit_at`, even if it contains older timestamps.
     - evidence_02 (manifest 09-17, inner snapshots dated 09-15) is never cited for 09-15 audits; evidence_92 is cited instead (case_23–30).
     - evidence_06 (manifest 09-18, lines from 09-10) is not cited for case_09 (audit 09-16); evidence_93 is.
  2. **Record gate (interpreted per format):** within an eligible file, a record's own timestamp must also be ≤ `audit_at`, and the record shows state as of that timestamp, not as of the capture.
     - Formats: logs use the line or trace time; snapshot bundles use the per-snapshot `captured_at`; ledgers use `recorded_at`; service exports use `observed_at`; SQL uses the header "Captured at" plus each row's `updated_at`; the TXT handover uses each line's time.
     - Proven traps: evidence_13 (captured 08-12T09:00) contains account_1417 USER_PROFILE FOUND `recorded_at` 08-14. eval case_135 (o.morgan56) has `audit_at` = 08-12T09:00, so the file passes the file gate, but this record must be ignored. Likewise evidence_36 (captured 04-09T12:00) contains account_5043 FOUND at 04-11, and eval case_383 has `audit_at` = 04-09T12:00. A file-only gate would wrongly report both accounts as remaining.
  - **Stale records:** snapshot bundles and logs contain records up to about 12 days older than their capture (e.g. evidence_22 spans 06-17 to 06-30, and evidence_44 spans 02-22 to 03-02). When several eligible records describe one resource, the latest record timestamp ≤ `audit_at` wins, not the latest file. A record older than the request is not proof of post-request state. Whether a stale record can outrank a newer file with no mention of the resource is untested (Ambiguity 9).
- **D4. Citation (H3).** Each finding, and each COMPLETE verification, cites the latest eligible file that shows the resource's state. Usually a single file covers the whole case. Shown by case_11 (4 findings → evidence_03), case_18 (evidence_94) and case_26 (6 verifications → evidence_92).
  - Not always one file: case_04 cites evidence_54 for the account and evidence_56 for the analytics record.
- **D5. Absence can be proven by a snapshot of the collection that lacks the record.**
  - case_01, 02, 04 cite evidence_54 (a profiles snapshot without account_001/002/004).
  - case_31 cites evidence_51 (its `account_service/customer_profiles` snapshot has 0 records).
  - case_21, 25, 27, 28 cite evidence_92, where the account lookup returns 404.
- **D6. Identity resolution and resource eligibility are separate steps.**
  1. **Identity resolution is time-unbounded and uses the full history.** Map the request email to a user_id via the current snapshot or *any* `old_value`/`new_value` in `user_audit_log.csv`, then collect every email, hash and phone the user ever held. No lifecycle window applies here.
     - Proof: all 306 identity changes in the dataset predate the request they belong to, and 103 of the 550 requests use a historical email. A window on identity would leave every one of them unresolved (case_10, 29, 30; case_12's old hash is from 05-18, the request from 08-24).
     - Changes after `audit_at`: none exist in this dataset. If one ever did, it would not be used.
  2. **Resource eligibility is time-bounded.** A record, line or activity row is associated with *this* request only if it matches a resolved identifier, passes D3 (≤ `audit_at`), and its record timestamp is ≥ `requested_at`. The lower bound separates the current lifecycle from an earlier request by the same person:
     - case_17: the same email has a March lifecycle (eval case_46: account_6523 404 in evidence_67, tombstone_17 via activity_4011). Neither appears in case_17's answer.
     - case_07: object_19 (activity_4007, Feb, eval case_61) is excluded.
     - With this bound, record-level linking reproduces 77 expected resources with **0 extras** across the samples.
  - Caveat: the lower bound is proven only for event/state records. A record created before the request that still exists afterwards (e.g. an old export) would show up in a later snapshot with an in-window timestamp, so the bound applies to the *observation* time, not the record's creation time.

## E. Identity (H4, H5)

- **E1. Matching is exact on the full identifier (case-insensitive for emails assumed, see ambiguities).** Near-miss decoys sit in cited, eligible files and are excluded:
  - jonas.berglund / search_8814 next to jonas.berg / search_001 (case_06, evidence_57);
  - Karim El-Masri, "Mateo Rios Gil", "Priya Ramanathan" in evidence_54 (case_01, 02, 07);
  - support_5914 keyed by nadia.popescu next to nadia.ionescu (case_10, evidence_61);
  - smartinez6461.jr / search_8168 (case_28, but only in post-audit evidence_02).
- **E2. Resolve the full chain:** request email → user_id (current snapshot or any `old_value`/`new_value`) → all emails, hashes and phones ever held.
  - case_10: the request uses the oldest of 3 emails for user_10 (2 hops). evidence_61 matches only that oldest email.
  - case_29, 30: the request email is historical, and eligible evidence_92 contains only the old email.
- **E3. Old email hashes appear in evidence.** case_12: analytics_9914 is linked only by the pre-change hash `44a65154…` (audit_283 old_value) in evidence_01.
- **E4. A log trace links through `trace_id`.** The lookup key is on `*_started`, the resource and result on `*_completed` (case_10, case_12, case_03). A `*_completed` line with its own `lookup_key` and no shared trace is a separate record (support_5914, a decoy).
- **E5. Retained records link by `user_id`** (audit `subject_reference`, `customer_reference`, `correlation_key`). Shown by case_03, 11–16, 26–28.

## Hypothesis verdicts

| # | Hypothesis | Verdict |
|---|---|---|
| 1 | Verification lists every relevant record in its final state, account included | **Holds** (B1–B3). The account is in 32/32. The audit record appears only when one exists (24/32). |
| 2 | Policy by data_category, not system_id | **Holds** (C1, C2): support_864 REDACT vs support_4218 DELETE, analytics_2034 ANONYMIZE vs analytics_9914 DELETE. |
| 3 | Findings cite one evidence_id: the latest at or before audit_at | **Holds per resource** (D3–D5). It is usually one file per case, but case_04 cites two. "At or before" has two gates: manifest `captured_at` and the record's own timestamp (traps in evidence_13 and evidence_36). |
| 4 | Exact identity matching (case_28 decoy) | **Holds** (E1). case_28's decoy is only in post-audit evidence, but case_06 and case_10 prove it with eligible files. |
| 5 | Multi-hop chains; old hashes appear | **Holds** (E2, E3) for user_10 (2 hops) and the case_12 hash. user_35 is not a sample (it is eval case_37), but its 2-hop chain is visible in evidence_03 using the oldest email. |

## Ambiguous / unresolved

1. **Linking accounts and anonymized analytics records.** In 15+ samples the account (often a bare 404) or the anonymized analytics record never appears next to an identifier in eligible evidence. The only tie is the deletion-worker activity batch:
   - the account submit lands at `reported_at` −0.8h to −1.2h (or ±0.1h for the "reported the requested operation" style in case_01–10);
   - anonymize/redact/disable/block land at −0.5h to −0.1h, and failures at +0.6h to +1.9h.
   - Cases sharing a `reported_at` overlap: 472/518 eval cases have more than one account candidate in the window. Disambiguation by eliminating resources claimed by other identities looks feasible (case_18 window: account_3610, 9335 and 5193 are each claimed elsewhere) but is unproven.
2. **Ungrounded expected resources.** account_004 (case_04), audit_record_6645 (case_18) and audit_record_5569 (case_20) appear nowhere in participant data except `sample_output.csv`. Treat them as unreachable.
3. **Retained audit records visible only in post-audit files (see B2).** audit_record_4128/7095/3954/1707 appear only in evidence_02 (manifest 09-17), and audit_record_4902 only in evidence_06. The answers still verify them (with `evidence_id=""`). So linking may use later evidence when nothing is cited; this needs a decision.
4. **analytics_9914's category.** It could be MARKETING_PROFILE (rule_10) or SECONDARY_IDENTIFIER (rule_02); both give DELETE, so the output is the same. support_002 (legacy contact index) could be SUPPORT_ATTACHMENT or SECONDARY_IDENTIFIER, also DELETE either way.
5. **Tie-break on `resource_id`.** No sample has two steps with the same operation and system, so lexicographic vs numeric ordering is untested.
6. **Case-insensitive email match.** Uppercase emails exist in evidence (e.g. evidence_03, inventory SQL) but no sample depends on one.
7. **NOT_APPLICABLE detection.** It is untested by the samples. Signals in the data: `CLASSIFY_REQUEST ... as non-deletion` activity rows (10) and the `request_text` itself.
8. **Sample coverage.** Sample `audit_at` values are all Sep–Oct 2026, while eval spans Jan–Oct, and some evidence families (inventory SQL, regional and reporting replicas, PNGs, PDFs other than evidence_58) are never cited by a sample.
9. **Stale record vs silent newer file.** If an older eligible record shows a resource and a newer eligible file covering the same collection doesn't mention it, it is unclear whether that absence counts (D5 says absence from a snapshot can prove ABSENT for accounts). The answer probably depends on whether the newer file is a full snapshot of that collection or a partial log.
