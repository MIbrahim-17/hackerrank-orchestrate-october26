# 02_sync_recreates_before_audit

The account was NOT_FOUND on 06-05, but an active connector re-synced it and it is FOUND again on 06-08, before audit_at (06-10). The workflow claims COMPLETE. The latest eligible state wins: the account is a remaining record and the active flow must be disabled before the record is deleted.

All people, emails, phones and records are synthetic (example.test).
