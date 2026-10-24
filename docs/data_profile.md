# Data Profile

Descriptive only, no design. Profiled 2026-10-24.

## CSVs

| File | Rows | Columns |
|---|---|---|
| deletion_requests.csv | 518 | case_id, email, requested_at, reported_status, reported_at, audit_at, request_text |
| sample_deletion_requests.csv | 32 | same as above |
| sample_output.csv | 32 | case_id, deletion_status, steps_json |
| user_identities.csv | 850 | user_id, name, email, phone, email_hash, updated_at |
| user_audit_log.csv | 306 | audit_id, user_id, event_time, field_name, old_value, new_value |
| system_activity.csv | 4011 | activity_id, event_time, event_type, source_system, target_system, resource_id, reported_result, details |
| deletion_rules.csv | 15 | rule_id, data_category, condition, required_action |
| evidence_files.csv | 94 | file_id, file_path, origin, captured_at |
| output.csv | 0 | template header only |

- Eval `reported_status`: COMPLETE 254, PARTIALLY_COMPLETE 152, NOT_STARTED 112. `audit_at` runs from 2026-01-29 to 2026-10-01.
- Sample `reported_status`: COMPLETE 17, NOT_STARTED 10, PARTIALLY 5. Sample answers: INCOMPLETE 22, COMPLETE 10, **NOT_APPLICABLE 0**. All sample `audit_at` values fall in Sep–Oct 2026, so the samples under-cover the eval time range.
- Audit-log fields changed: email 107, email_hash 107, phone 92. Names never change.
- Activity time span: 2026-01-04 → 2026-10-01. Resource-ID prefixes: account, search, analytics, support, email_delivery, cache, audit_record, export, data_flow, backup, tombstone, legal_hold, plus one each of object and marketing.

## Rules (deletion_rules.csv)
DELETE: USER_PROFILE, SECONDARY_IDENTIFIER, SEARCH_INDEX_ENTRY, CACHE_ENTRY, SUPPORT_ATTACHMENT (subject-only), USER_EXPORT, MARKETING_PROFILE.
REDACT: SUPPORT_MESSAGE (shared context), EMAIL_DELIVERY_LOG, ACCOUNT_TOMBSTONE.
ANONYMIZE: ANALYTICS_PROFILE, PRODUCT_TELEMETRY. RETAIN: SECURITY_AUDIT_LOG (within retention), LEGAL_HOLD_RECORD (active hold), BACKUP_ARCHIVE (if restore can be blocked).

## system_activity: event_type × reported_result
| event_type | SUCCESS | PARTIAL | FAILED |
|---|---|---|---|
| UPDATE_RECORD | 587 | 32 | 53 |
| DELETE_RECORD | 302 | 220 | 368 |
| SYNC_RECORD | 381 | 46 | 20 |
| INDEX_RECORD | 348 | 20 | 32 |
| SEND_EMAIL | 333 | 14 | 21 |
| REFRESH_CACHE | 246 | 16 | 22 |
| RETAIN_RECORD | 185 | 6 | 15 |
| ANONYMIZE_RECORD | 132 | 8 | 64 |
| REDACT_RECORD | 47 | 9 | 117 |
| CREATE_EXPORT | 141 | 5 | 9 |
| CHECK_DATA_FLOW | 89 | – | – |
| DISABLE_DATA_FLOW | 36 | – | – |
| BLOCK_RESTORE | 36 | – | – |
| CHECK_RESTORE_ACCESS | 28 | – | – |
| LINK_RESOURCE_IDENTITY | 12 | – | – |
| CLASSIFY_REQUEST | 10 | – | – |
| RESTORE_BACKUP | 1 | – | – |

Most `details` text names only resource IDs, not people. The exceptions are `LINK_RESOURCE_IDENTITY` (links a resource to an email and a user_id), `CLASSIFY_REQUEST` (says "non-deletion"), `RESTORE_BACKUP` (says a restore repopulated a named downstream resource), and the CHECK_* rows (state the flow is still enabled or the backup is still restorable).

## Evidence (94 files: 24 sql, 28 json, 26 log, 1 txt, 11 png, 4 pdf)
`captured_at` runs from 2026-01-29 to 2026-10-01. Some manifest captures postdate some audits. Individual log lines and JSON snapshots carry their own earlier timestamps.

### SQL (all 24 load in sqlite3 `:memory:` via executescript)
- **Replica pairs** (`read_replica` ×5, `reporting_replica` ×2, `failover_replica` ×1, `regional_replicas` ×3 with ap_south and eu_west copies): `customer_data_primary` + `customer_data_<replica>`, each with `(resource_id, origin_system, collection_name, record_json, updated_at)`. `record_json` is a full JSON document. Collections seen: security_audit_events, customer_analytics_reports, connector_configurations, customer_search_documents, support_conversations, backup_catalog. Replica row counts differ from primary by 1–2 rows, which is the replication drift.
- **Inventory** (×12, `customer_data_inventory_*`): `snapshot_scope(origin_system, captured_at)` plus typed tables: customer_profiles, customer_search_documents, customer_analytics_profiles, support_records, customer_exports, connector_subscriptions (enabled 0/1), backup_restore_entries (restore_allowed 0/1), security_audit_records (retention_until). Rows identify the person via `customer_reference` (user_id) **or** an email column, rarely both. Emails sometimes appear in UPPERCASE.
- **customer_accounts_failover_replica**: `customer_profiles_primary` / `_failover_replica(resource_id, user_id, full_name, email, phone, account_status, updated_at)`.
- **customer_search_primary**: `search_documents_primary(resource_id, display_name, email, source_resource_id, indexed_at)`.

### JSON
- **snapshot_bundle** (×13): `{exported_at, source, snapshots:[{captured_at, data_store, collection, records:[...]}]}`. Store/collection pairs include account_service/customer_profiles, identity_service/deleted_customer_references (tombstones with null PII), security audit events, analytics reports, backup_catalog (restore_allowed), export jobs, connector_configurations (enabled, subject_selector), search documents (nested `document`), support ticket_attachments / support_conversations (PII inside `message_text`), legal_service/retained_order_records, and `operational_record_history` lookups.
- **Lookup ledgers** (connector_configurations, customer_export_manifest, security_audit_ledger): `{exported_at, origin, record_count, records:[{recorded_at, system, resource_id, record_type, result, subject_reference}]}`. `result` ∈ FOUND/NOT_FOUND/IDENTIFIABLE/ANONYMIZED/REDACTED/ACTIVE/DISABLED/BLOCKED. `subject_reference` is an email or a user_id.
- **service_resource_export** (×12): `{exported_at, region, source, service_exports:{account_service.profile_lookups (status_code 200/404), analytics_platform.profiles, backup_service.restore_entries, export_service.exports, integration_service.connectors, search_service.index_queries (hits.documents), security_service.audit_records, support_platform.tickets}}`, each item with `observed_at`.
- **Single-collection** files (analytics_report, export_jobs): `{captured_at, source, collection, records:[...]}`.

### Logs (6+ line syntaxes)
- `ts level=.. service=.. trace_id=.. event=.. key=value` (service_events, support_replica, resource_lookup_trace)
- `ts {json}` (structured_service_events)
- RFC5424 syslog `ts <15>1 node svc trace - - k="v"` (syslog_archive)
- `ts [LEVEL] [svc] [trace] event: k="v"` (application_trace)
- `ts | LEVEL | svc | trace | event | k="v"` (operations_stream)
- `ts requestId=.. function=svc message="k=\"v\" ..."` (cloud_runtime_export)
- `ts INFO service=.. event=record_lookup system= resource_id= record_type= result= subject_reference=` (search_index_diagnostic, notification_delivery)

Lookups are split across lines that share a `trace_id`: `*_started` carries `lookup_key`/`match_key` (an email), and `*_completed` carries `resource_id`, `rows`, `http_status`/`result`. The logs contain a lot of noise (dns, vault, retries).

### TXT
`customer_account_handover_20261001.txt`: a header plus lines of the form `- ts | system | resource_id | RECORD_TYPE | RESULT | subject (email, user_id, or "no direct identifier")`.

### PDFs (4) and PNGs (11)
- PDFs: customer statement (user_id, email, order), delivery-correction attachment (support ref, name, email, phone), legal retention register (order | user_id | retain-until), security retention extract (audit_record, subject user_id, retain-until).
- PNGs: 1500–1800px rendered admin consoles (connectors, search inspector, backup restore, export, analytics, support, object storage, security audit, marketing, deleted-account reference, account admin). They show clean tables of resource_id, selector/email, status, and timestamps.

## Tooling for PDF/PNG
| Option | Available | Notes |
|---|---|---|
| `pdftotext -layout` (poppler) | yes | Clean text from all 4 PDFs, so no LLM is needed for them. |
| `mutool`, `pdftoppm` | yes | Render PDF pages to PNG if needed. |
| pypdf, PIL | system python only | Not in `.venv`; would need adding to requirements. |
| tesseract / pytesseract | no | No local OCR. |
| Claude vision | yes (API) | Only practical way to read the 11 PNGs. It's a fixed set, so extract once and cache. |
