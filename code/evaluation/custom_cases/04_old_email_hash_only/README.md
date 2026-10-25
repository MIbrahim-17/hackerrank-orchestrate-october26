# 04_old_email_hash_only

A search document is visible only in a log trace keyed by the sha256 hash of the user's previous email. The email and its hash changed in 2025, and the request uses the current email. The old hash comes from user_audit_log; the lookup line and the result line are joined by trace_id.

All people, emails, phones and records are synthetic (example.test).
