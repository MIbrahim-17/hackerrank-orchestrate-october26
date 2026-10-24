"""Deterministic investigation tools for the agent, bound to one case (its subject, requested_at and audit_at).

Every tool is read-only and returns compact JSON. Evidence outside the case's gates is never shown as state:
search results say whether each record is eligible, post-audit (ownership only) or from an earlier lifecycle.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from activity_links import ActivityLink
from data import Request, load_activity, load_manifest, load_rules
from evidence import EvidenceIndex, Observation, exclusion_reason, identifiers_in
from identity import resolve_identity

MAX_ROWS = 40


def _obs_view(o: Observation, r: Request) -> dict[str, Any]:
    why = exclusion_reason(o.captured_at, o.observed_at, r.requested_at, r.audit_at)
    usable = "eligible" if why is None else ("ownership_only" if "after audit_at" in why else "excluded")
    return {"evidence_id": o.source_id, "observed_at": o.observed_at, "resource_id": o.resource_id,
            "system_id": o.system_id, "collection": o.collection, "record_type": o.record_type,
            "category_hint": o.category_hint, "state": o.state, "exposes_pii": o.exposes_pii,
            "usable": usable, "why": why, "snippet": o.snippet[:400]}


@dataclass
class CaseTools:
    request: Request
    index: EvidenceIndex
    links: dict[str, ActivityLink]

    # ---- tools ----
    def resolve_identity(self, email: str) -> dict[str, Any]:
        return {"subjects": [s.to_dict() for s in resolve_identity(email)]}

    def search_evidence(self, values: list[str] | None = None, resource_id: str | None = None,
                        text: str | None = None) -> dict[str, Any]:
        """Records matching any identifier value (email, phone, hash, user_id), a resource_id, or a free-text phrase."""
        found: dict[int, Observation] = {}
        keys: set[str] = set()
        for v in values or []:
            keys |= identifiers_in(v)  # emails, hashes, phones and user_ids, normalized
        for k in keys:
            for o in self.index.by_identifier.get(k, []):
                found[id(o)] = o
        if resource_id:
            for o in self.index.by_resource.get(resource_id, []):
                found[id(o)] = o
        if text:
            pattern = re.compile(rf"(?<!\w){re.escape(text)}(?!\w)", re.IGNORECASE)
            for o in self.index.observations:
                if pattern.search(o.snippet):
                    found[id(o)] = o
        rows = sorted(found.values(), key=lambda o: (o.observed_at, o.source_id))
        return {"count": len(rows), "records": [_obs_view(o, self.request) for o in rows[:MAX_ROWS]],
                "truncated": len(rows) > MAX_ROWS}

    def query_sql_snapshot(self, file_id: str, sql: str) -> dict[str, Any]:
        """Read-only single SELECT on one SQL snapshot captured at or before audit_at."""
        f = next((m for m in load_manifest() if m.file_id == file_id), None)
        if not f or f.path.suffix != ".sql":
            return {"error": f"{file_id} is not a SQL snapshot"}
        if f.captured_at > self.request.audit_at:
            return {"error": f"{file_id} was captured after audit_at; it cannot establish state"}
        if not re.match(r"(?is)^\s*select\b", sql) or ";" in sql.strip().rstrip(";"):
            return {"error": "only a single SELECT statement is allowed"}
        con = sqlite3.connect(":memory:")
        con.executescript(f.path.read_text(encoding="utf-8"))
        con.execute("PRAGMA query_only = ON")
        try:
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description or []]
            rows = [dict(zip(cols, row)) for row in cur.fetchmany(MAX_ROWS + 1)]
        except sqlite3.Error as e:
            return {"error": str(e)}
        finally:
            con.close()
        return {"captured_at": f.captured_at, "rows": rows[:MAX_ROWS], "truncated": len(rows) > MAX_ROWS}

    def get_activity(self, resource_ids: list[str] | None = None, start: str | None = None,
                     end: str | None = None) -> dict[str, Any]:
        """system_activity rows up to audit_at (claims, not proof), plus this case's ownership-link status."""
        end = min(end or self.request.audit_at, self.request.audit_at)
        rows = [a for a in load_activity()
                if a.event_time <= end and (not start or a.event_time >= start)
                and (not resource_ids or a.resource_id in resource_ids or any(x in a.details for x in resource_ids))]
        return {"note": "activity rows are claims; reported_result is not proof of state",
                "case_links": {k: {"status": v.status, "candidates": list(v.candidates)} for k, v in self.links.items()},
                "rows": [a.__dict__ for a in rows[:MAX_ROWS]], "truncated": len(rows) > MAX_ROWS}

    def read_image_or_pdf(self, file_id: str) -> dict[str, Any]:
        f = next((m for m in load_manifest() if m.file_id == file_id), None)
        if not f or file_id not in self.index.documents:
            return {"error": f"{file_id} is not a transcribed image or PDF"}
        usable = "eligible" if f.captured_at <= self.request.audit_at else "ownership_only (captured after audit_at)"
        return {"captured_at": f.captured_at, "usable": usable, "text": self.index.documents[file_id][:6000]}

    def lookup_policy(self, data_category: str) -> dict[str, Any]:
        return {"rules": [r.__dict__ for r in load_rules() if r.data_category == data_category.upper()]}

    # ---- dispatch ----
    def call(self, name: str, args: dict[str, Any]) -> str:
        fn = {"resolve_identity": self.resolve_identity, "search_evidence": self.search_evidence,
              "query_sql_snapshot": self.query_sql_snapshot, "get_activity": self.get_activity,
              "read_image_or_pdf": self.read_image_or_pdf, "lookup_policy": self.lookup_policy}.get(name)
        if fn is None:
            raise ValueError(f"unknown tool {name}")
        return json.dumps(fn(**args), ensure_ascii=False, default=str)


CATEGORIES = sorted({r.data_category for r in load_rules()} | {"DATA_FLOW"})

TOOL_DEFS = [
    {"name": "resolve_identity", "description": "Resolve an email (current or historical) to the user and every identifier they ever held.",
     "input_schema": {"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]}},
    {"name": "search_evidence",
     "description": "Find evidence records by identifier values (email, phone, email hash, user_id), by resource_id, or by an exact "
                    "free-text phrase such as a full name. Each record says whether it is usable for this case: 'eligible' "
                    "(at/before audit_at, in this request's lifecycle), 'ownership_only' (after audit_at: may prove the resource "
                    "belongs to the subject, never its state) or 'excluded' (earlier lifecycle).",
     "input_schema": {"type": "object", "properties": {
         "values": {"type": "array", "items": {"type": "string"}}, "resource_id": {"type": "string"},
         "text": {"type": "string"}}}},
    {"name": "query_sql_snapshot", "description": "Run one read-only SELECT on a SQL snapshot file captured at or before audit_at. "
                                                  "Use it to compare primary and replica tables.",
     "input_schema": {"type": "object", "properties": {"file_id": {"type": "string"}, "sql": {"type": "string"}},
                      "required": ["file_id", "sql"]}},
    {"name": "get_activity", "description": "system_activity rows up to audit_at, filtered by resource_ids and/or time range, plus "
                                            "this case's ownership-link status. Activity rows are claims, never proof of state.",
     "input_schema": {"type": "object", "properties": {
         "resource_ids": {"type": "array", "items": {"type": "string"}}, "start": {"type": "string"}, "end": {"type": "string"}}}},
    {"name": "read_image_or_pdf", "description": "Full text of a PDF or the transcription of a screenshot, by file_id.",
     "input_schema": {"type": "object", "properties": {"file_id": {"type": "string"}}, "required": ["file_id"]}},
    {"name": "lookup_policy", "description": "Rows of deletion_rules.csv for a data_category.",
     "input_schema": {"type": "object", "properties": {"data_category": {"type": "string"}}, "required": ["data_category"]}},
    {"name": "submit_findings", "strict": True,
     "description": "Submit your decisions and end the investigation. Call this exactly once, as your last action.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["choices", "categories", "notes"], "properties": {
         "choices": {"type": "array", "description": "One entry per ambiguous ownership set listed in the case brief.",
                     "items": {"type": "object", "additionalProperties": False,
                               "required": ["kind", "resource_id", "evidence_id", "reason"],
                               "properties": {"kind": {"type": "string", "enum": ["account", "analytics"]},
                                              "resource_id": {"type": "string", "description": "a candidate, or 'none'"},
                                              "evidence_id": {"type": "string", "description": "record tying it to the subject; '' for none"},
                                              "reason": {"type": "string"}}}},
         "categories": {"type": "array", "description": "Only for resources listed as having no source label.",
                        "items": {"type": "object", "additionalProperties": False,
                                  "required": ["resource_id", "data_category", "evidence_id", "reason"],
                                  "properties": {"resource_id": {"type": "string"},
                                                 "data_category": {"type": "string", "enum": CATEGORIES},
                                                 "evidence_id": {"type": "string"}, "reason": {"type": "string"}}}},
         "notes": {"type": "string"}}}},
]
