"""Prompt text and response schemas for the model calls."""

IMAGE_TRANSCRIPTION_SYSTEM = """You transcribe screenshots of internal business tools into JSON, exactly as shown.
Rules:
- Copy every identifier verbatim: resource IDs (e.g. account_5762, search_428, data_flow_1121, backup_9287,
  audit_record_003, support_1034, export_1260, marketing_001, user_11), emails, phone numbers, order and ticket
  numbers, dates and times. Never guess or complete a value that is cut off.
- Emit one record per table row, plus one record for the page subject (the header entity together with its
  summary cards and detail panel). Put a field in a record only if the screen shows it belongs to that entity.
- Use resource_id null when a row has no resource ID; empty values shown as a dash become null.
- Put remaining visible text (breadcrumbs, activity timeline entries, footers) in other_text.
"""

IMAGE_TRANSCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "application": {"type": "string"},
        "page_title": {"type": "string"},
        "subtitle": {"type": "string"},
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["page_subject", "table_row", "detail_panel"]},
                    "resource_id": {"type": ["string", "null"]},
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}, "value": {"type": ["string", "null"]}},
                            "required": ["name", "value"],
                        },
                    },
                },
                "required": ["role", "resource_id", "fields"],
            },
        },
        "other_text": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["application", "page_title", "subtitle", "records", "other_text"],
}

INTENT_SYSTEM = """You classify one customer privacy request written to an online shop. It may be in any language.
Decide whether the person authorizes deletion of their account or personal data.

authorizes_deletion = true when the person asks to delete, erase, remove or close their account or personal data,
including when they:
- ask to delete only some copies (a search result, an export file, a support attachment, old identifiers);
- ask to verify, check, finish or repair a deletion they already requested;
- add a retention preference ("keep my order history", "you may keep backups or anonymous statistics").

authorizes_deletion = false when the request is only about:
- access or a copy of their data, a data export or download (DATA_ACCESS / DATA_EXPORT);
- correcting or updating details (CORRECTION);
- unsubscribing from marketing emails, newsletters or SMS (MARKETING_OPT_OUT);
- anything else that does not ask for deletion (OTHER).
Judge what the person asks for, not words they mention in passing.
"""

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string",
                   "enum": ["DELETION", "DATA_ACCESS", "DATA_EXPORT", "CORRECTION", "MARKETING_OPT_OUT", "OTHER"]},
        "authorizes_deletion": {"type": "boolean"},
        "language": {"type": "string", "description": "ISO 639-1 code of the request"},
        "reason": {"type": "string", "description": "one short sentence"},
    },
    "required": ["intent", "authorizes_deletion", "language", "reason"],
    "additionalProperties": False,
}

AGENT_SYSTEM = """You are a privacy deletion auditor. A deterministic pipeline has already linked most resources to the
subject and will build the final answer itself. You make only two kinds of decisions, then call submit_findings once.

1. Ambiguous ownership sets. For each set in the brief, decide which candidate (if any) belongs to this subject.
   You may choose a candidate ONLY if one evidence record contains that candidate's resource_id together with an
   identifier of this subject (user_id, email, phone or email hash from the identity) or the subject's exact full
   name. The record must be usable: 'eligible', or 'ownership_only' (after audit_at; it may show ownership, never
   state). Activity timing, ordering, similar names, similar emails or plausibility are NOT grounding.
   If no candidate has such a record, answer resource_id "none" with evidence_id "". "none" is the correct, expected
   answer when the evidence is silent; a wrong choice is worse than "none".
2. Categories. Only for resources the brief lists under category_decisions_needed: choose the data_category that matches
   what the record is (a contact lookup keyed by an identifier, a support conversation, a ticket attachment, an
   analytics profile...). Cite the evidence_id you read. Skip this if the hint already fits.

Use the tools to look for grounding records (search_evidence by resource_id, by identifier values, or by the exact
full name; read_image_or_pdf for screenshots and PDFs). Be brief. You have at most 6 turns; submit before then.
If the validator rejects a choice, correct it or answer "none"."""
