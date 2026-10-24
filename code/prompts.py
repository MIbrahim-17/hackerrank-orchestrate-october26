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
