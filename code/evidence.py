"""Parse every evidence file once into Observation records and index them.

One Observation = one record's state as seen in one source at one time:
  logs  -> one per (trace, resource)      JSON -> one per object with a resource_id
  SQL   -> one per table row              TXT  -> one per handover line
  PDF   -> one per resource mentioned     PNG  -> one per transcribed row (Gemini, cached)
  activity LINK_RESOURCE_IDENTITY rows -> identity links (state LINKED)

Eligibility (inferred_rules.md D3, D6) is applied at search time, never at parse time:
  file gate      manifest captured_at <= audit_at
  record gate    observed_at <= audit_at   (the record's own timestamp, interpreted per format)
  lifecycle      observed_at >= requested_at
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from data import EvidenceFile, load_activity, load_manifest
from identity import ident_key

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
HASH_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
USER_RE = re.compile(r"\buser_\d+\b")
PHONE_RE = re.compile(r"\+\d[\d ()\-]{6,}\d")
RID_RE = re.compile(r"\b(?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|legal_hold"
                    r"|email_delivery|cache|marketing|object|telemetry)_\d+\b")
TS_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
KV_RE = re.compile(r'(\w+)=("((?:[^"\\]|\\.)*)"|\S+)')

# Resource prefix -> system_id (fixed in every sample, inferred_rules.md A6).
PREFIX_SYSTEM = {
    "account": "account_service", "search": "search_service", "analytics": "analytics_platform",
    "support": "support_platform", "export": "export_service", "data_flow": "integration_service",
    "backup": "backup_service", "audit_record": "security_service", "tombstone": "identity_service",
    "legal_hold": "legal_service", "email_delivery": "email_delivery_service", "cache": "cache_service",
    "marketing": "marketing_platform", "object": "object_storage", "telemetry": "analytics_platform",
}
# Collection / table / log-event hints -> data_category. Only confident mappings; the agent decides the rest.
CATEGORY_HINTS = [
    ("deleted_customer_references", "ACCOUNT_TOMBSTONE"), ("ticket_attachment", "SUPPORT_ATTACHMENT"),
    ("attachment", "SUPPORT_ATTACHMENT"), ("support_conversations", "SUPPORT_MESSAGE"),
    ("support_ticket", "SUPPORT_MESSAGE"), ("security_audit", "SECURITY_AUDIT_LOG"), ("audit_record", "SECURITY_AUDIT_LOG"),
    ("retained_order", "LEGAL_HOLD_RECORD"), ("backup", "BACKUP_ARCHIVE"), ("restore", "BACKUP_ARCHIVE"),
    ("connector", "DATA_FLOW"), ("export", "USER_EXPORT"), ("search", "SEARCH_INDEX_ENTRY"), ("index_query", "SEARCH_INDEX_ENTRY"),
    ("analytics_profile", "ANALYTICS_PROFILE"), ("analytics_report", "ANALYTICS_PROFILE"),
    ("customer_profiles", "USER_PROFILE"), ("profile_lookup", "USER_PROFILE"),
    ("analytics_platform/profiles", "ANALYTICS_PROFILE"),
]
# Prefixes that map to exactly one category. analytics_ and support_ are deliberately absent: the same prefix
# carries different categories (analytics_2034 vs analytics_9914, support_864 vs support_4218).
PREFIX_CATEGORY = {
    "account": "USER_PROFILE", "search": "SEARCH_INDEX_ENTRY", "export": "USER_EXPORT", "data_flow": "DATA_FLOW",
    "backup": "BACKUP_ARCHIVE", "audit_record": "SECURITY_AUDIT_LOG", "tombstone": "ACCOUNT_TOMBSTONE",
    "legal_hold": "LEGAL_HOLD_RECORD", "email_delivery": "EMAIL_DELIVERY_LOG", "cache": "CACHE_ENTRY",
    "marketing": "MARKETING_PROFILE",
}
# Fields naming who/what was looked up rather than data the record holds; they never count as exposed PII.
LOOKUP_FIELDS = {"subject", "subject_reference", "subject_ref", "lookup_key", "match_key", "scan_key", "query",
                 "correlation_key", "lookup_value"}
NAME_FIELDS = {"full_name", "display_name", "requester_name", "name", "customer", "customer_name"}
STATE_FROM_RESULT = {"FOUND": "PRESENT", "NOT_FOUND": "ABSENT", "IDENTIFIABLE": "IDENTIFIABLE",
                     "ANONYMIZED": "ANONYMIZED", "REDACTED": "REDACTED", "DISABLED": "DISABLED", "BLOCKED": "BLOCKED"}
# An explicit state from the source wins over field inspection (keeps exposes_pii consistent with state).
EXPLICIT_PII = {"IDENTIFIABLE": True, "REDACTED": False, "ANONYMIZED": False, "ABSENT": False}
LOG_SERVICE_ALIASES = {"support_replica": "support_platform"}


@dataclass(frozen=True)
class Observation:
    source_id: str  # file_id or activity_id
    captured_at: str  # manifest captured_at (file gate); activity event_time for activity rows
    observed_at: str  # when this record's state was observed (record gate + lifecycle bound)
    system_id: str
    resource_id: str
    collection: str  # table / snapshot collection / log events / "document"
    record_type: str | None  # explicit label (SUPPORT_MESSAGE, ...) when the source states one
    category_hint: str | None  # explicit label or a confident collection mapping
    state: str  # PRESENT ABSENT IDENTIFIABLE REDACTED ANONYMIZED ACTIVE DISABLED RESTORABLE BLOCKED LINKED
    exposes_pii: bool  # record still holds a direct identifier (email, phone, hash or name)
    identifiers: frozenset[str]  # normalized keys found in the record ("email:...", "user:...", ...)
    refs: tuple[str, ...]  # other resource IDs the record mentions (links only, no state)
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "captured_at": self.captured_at, "observed_at": self.observed_at,
                "system_id": self.system_id, "resource_id": self.resource_id, "collection": self.collection,
                "record_type": self.record_type, "category_hint": self.category_hint, "state": self.state,
                "exposes_pii": self.exposes_pii, "refs": list(self.refs), "snippet": self.snippet}


@dataclass(frozen=True)
class Coverage:
    """A full snapshot of one collection/table: a resource missing from it was absent at observed_at."""
    source_id: str
    captured_at: str
    observed_at: str
    system_id: str
    collection: str
    resource_ids: frozenset[str]


@dataclass
class EvidenceIndex:
    observations: list[Observation] = field(default_factory=list)
    coverage: list[Coverage] = field(default_factory=list)
    documents: dict[str, str] = field(default_factory=dict)  # file_id -> readable text (PDF text / PNG transcription)
    warnings: list[str] = field(default_factory=list)
    by_identifier: dict[str, list[Observation]] = field(default_factory=lambda: defaultdict(list))
    by_resource: dict[str, list[Observation]] = field(default_factory=lambda: defaultdict(list))

    def add(self, obs: Iterable[Observation]) -> None:
        for o in obs:
            self.observations.append(o)
            self.by_resource[o.resource_id].append(o)
            for key in o.identifiers:
                self.by_identifier[key].append(o)

    def search(self, keys: Iterable[str], requested_at: str, audit_at: str,
               resource_id: str | None = None) -> tuple[list[Observation], list[tuple[Observation, str]]]:
        """Observations matching any identifier key (and resource_id if given): (eligible, [(excluded, reason)])."""
        found = {id(o): o for k in keys for o in self.by_identifier.get(k, [])}
        if resource_id:
            found = {i: o for i, o in found.items() if o.resource_id == resource_id}
        return gate(found.values(), requested_at, audit_at)

    def owned_after_audit(self, keys: Iterable[str], requested_at: str, audit_at: str) -> dict[str, list[str]]:
        """Ownership-only links: resource_id -> post-audit source_ids that tie it to the subject.

        Used solely to learn that a resource belongs to the subject. These observations never establish state
        and are never cited (DECISIONS 2026-10-25). The lifecycle lower bound still applies.
        """
        owned: dict[str, list[str]] = defaultdict(list)
        for o in {id(o): o for k in keys for o in self.by_identifier.get(k, [])}.values():
            if exclusion_reason(o.captured_at, o.observed_at, requested_at, audit_at) in (
                    "file captured after audit_at", "record timestamp after audit_at"):
                owned[o.resource_id].append(o.source_id)
        return {rid: sorted(set(src)) for rid, src in owned.items()}

    def for_resource(self, resource_id: str, requested_at: str,
                     audit_at: str) -> tuple[list[Observation], list[tuple[Observation, str]]]:
        """All observations of one resource, identity-linked or not (e.g. a bare 404 lookup)."""
        return gate(self.by_resource.get(resource_id, []), requested_at, audit_at)


def exclusion_reason(captured_at: str, observed_at: str, requested_at: str, audit_at: str) -> str | None:
    if captured_at > audit_at:
        return "file captured after audit_at"
    if observed_at > audit_at:
        return "record timestamp after audit_at"
    if observed_at < requested_at:
        return "before requested_at (earlier lifecycle)"
    return None


def gate(obs: Iterable[Observation], requested_at: str,
         audit_at: str) -> tuple[list[Observation], list[tuple[Observation, str]]]:
    eligible, excluded = [], []
    for o in obs:
        reason = exclusion_reason(o.captured_at, o.observed_at, requested_at, audit_at)
        if reason:
            excluded.append((o, reason))
        else:
            eligible.append(o)
    key = lambda o: (o.observed_at, o.source_id)
    return sorted(eligible, key=key), sorted(excluded, key=lambda t: key(t[0]))


# ---------- helpers ----------

def identifiers_in(text: str) -> frozenset[str]:
    keys = {ident_key("email", m) for m in EMAIL_RE.findall(text)}
    keys |= {ident_key("hash", m) for m in HASH_RE.findall(text)}
    keys |= {ident_key("user", m) for m in USER_RE.findall(text)}
    keys |= {ident_key("phone", m) for m in PHONE_RE.findall(text) if len(re.sub(r"\D", "", m)) >= 8}
    return frozenset(keys)


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out.update(_flatten(v, f"{prefix}{k}."))
        return out
    if isinstance(value, list):
        out = {}
        for i, v in enumerate(value):
            out.update(_flatten(v, f"{prefix}{i}."))
        return out
    return {prefix[:-1]: value}


def _exposes_pii(fields: dict[str, Any]) -> bool:
    for name, value in fields.items():
        if value in (None, "", "null", "None"):
            continue
        leaf = name.rsplit(".", 1)[-1].lower()
        if leaf in LOOKUP_FIELDS:
            continue
        text = str(value)
        if leaf in NAME_FIELDS or EMAIL_RE.search(text) or PHONE_RE.search(text):
            return True
        if HASH_RE.search(text) and not text.startswith("sha256:") and "correlation" not in leaf:
            return True
    return False


def _category_hint(*names: str | None) -> str | None:
    joined = " ".join(n.lower() for n in names if n)
    return next((cat for needle, cat in CATEGORY_HINTS if needle in joined), None)


def _truthy(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return None


def infer_state(fields: dict[str, Any], record_type: str | None) -> str:
    """Normalize the many ways sources express state into one vocabulary."""
    leaves = {k.rsplit(".", 1)[-1].lower(): v for k, v in fields.items()}
    result = str(leaves.get("result", "")).upper()
    if result == "ACTIVE":
        return "RESTORABLE" if record_type == "BACKUP_ARCHIVE" else "ACTIVE"
    if result in STATE_FROM_RESULT:
        return STATE_FROM_RESULT[result]
    for key in ("http_status", "status_code"):
        if str(leaves.get(key, "")) == "404":
            return "ABSENT"
    if str(leaves.get("rows", "")) == "0":
        return "ABSENT"
    if "restore_allowed" in leaves and _truthy(leaves["restore_allowed"]) is not None:
        return "RESTORABLE" if _truthy(leaves["restore_allowed"]) else "BLOCKED"
    if "enabled" in leaves and _truthy(leaves["enabled"]) is not None:
        return "ACTIVE" if _truthy(leaves["enabled"]) else "DISABLED"
    if record_type == "DATA_FLOW":  # consoles show connector status words instead of an enabled flag
        words = " ".join(str(leaves.get(k, "")) for k in ("status", "mode", "sync mode", "last_delivery_status")).lower()
        if re.search(r"\b(disabled|paused|stopped|inactive)\b", words):
            return "DISABLED"
        if re.search(r"\b(healthy|live|active|enabled|continuous|delivered)\b", words):
            return "ACTIVE"
    return "PRESENT"


def _obs(f: EvidenceFile | None, source_id: str, captured_at: str, observed_at: str, resource_id: str, collection: str,
         fields: dict[str, Any], record_type: str | None = None, system_id: str | None = None,
         extra_identifiers: frozenset[str] = frozenset(), snippet: str | None = None) -> Observation:
    flat = _flatten(fields)
    text = " ".join(str(v) for v in flat.values() if v is not None)
    record_type = record_type or None
    prefix = resource_id.rsplit("_", 1)[0]
    hint = record_type or _category_hint(collection) or PREFIX_CATEGORY.get(prefix)
    state = infer_state(flat, hint)
    return Observation(
        source_id=source_id, captured_at=captured_at, observed_at=observed_at,
        system_id=PREFIX_SYSTEM.get(prefix) or system_id or prefix,
        resource_id=resource_id, collection=collection, record_type=record_type, category_hint=hint,
        state=state, exposes_pii=EXPLICIT_PII.get(state, _exposes_pii(flat)),
        identifiers=identifiers_in(text) | extra_identifiers,
        refs=tuple(sorted(set(RID_RE.findall(text)) - {resource_id})),
        snippet=(snippet or json.dumps(fields, ensure_ascii=False, default=str))[:600],
    )


# ---------- parsers ----------

def _unquote(raw: str) -> str:
    return raw[1:-1].replace('\\"', '"') if raw.startswith('"') else raw


def parse_kv(text: str) -> dict[str, str]:
    out = {m.group(1): _unquote(m.group(2)) for m in KV_RE.finditer(text)}
    if "message" in out and "=" in out["message"]:  # cloud runtime export nests key="value" pairs in message
        out.update(parse_kv(out.pop("message")))
    return out


def parse_log_line(line: str) -> tuple[str, dict[str, str]] | None:
    m = TS_RE.match(line)
    if not m:
        return None
    ts, rest = m.group(0), line[m.end():].strip()
    if rest.startswith("{"):
        d = {k: str(v) for k, v in json.loads(rest).items()}
    elif rest.startswith("<"):  # RFC5424: <pri>1 host service trace - - k="v" ...
        parts = rest.split(" ", 6)
        d = {"service": parts[2], "trace_id": parts[3], **parse_kv(parts[6] if len(parts) > 6 else "")}
    elif rest.startswith("["):  # [LEVEL] [service] [trace] event: k="v"
        b = re.match(r"\[(\w+)\] \[([^\]]+)\] \[([^\]]+)\] (\w+):\s*(.*)", rest)
        d = {"level": b.group(1), "service": b.group(2), "trace_id": b.group(3), "event": b.group(4), **parse_kv(b.group(5))} if b else parse_kv(rest)
    elif re.match(r"\w+ \| ", rest):  # LEVEL | service | trace | event | k="v"
        p = rest.split(" | ", 4)
        d = {"level": p[0], "service": p[1], "trace_id": p[2], "event": p[3], **parse_kv(p[4] if len(p) > 4 else "")}
    else:
        d = parse_kv(rest)
    d.setdefault("service", d.get("logger") or d.get("function") or "")
    d.setdefault("trace_id", d.get("requestId", ""))
    return ts, d


def parse_log(f: EvidenceFile) -> list[Observation]:
    groups: dict[str, list[tuple[str, dict[str, str], str]]] = defaultdict(list)
    for n, line in enumerate(f.path.read_text(encoding="utf-8").splitlines()):
        parsed = parse_log_line(line)
        if not parsed:
            continue
        ts, d = parsed
        trace = d.get("trace_id") if re.match(r"^(tr|rb)-", d.get("trace_id", "")) else None
        groups[trace or f"line{n}"].append((ts, d, line))
    out = []
    for lines in groups.values():
        merged: dict[str, Any] = {}
        for _, d, _ in lines:
            merged.update({k: v for k, v in d.items() if k not in ("level", "severity")})
        resources = list(dict.fromkeys(d["resource_id"] for _, d, _ in lines if RID_RE.fullmatch(d.get("resource_id", ""))))
        if not resources:
            continue
        text = " ".join(" ".join(str(v) for v in d.values()) for _, d, _ in lines)
        idents = identifiers_in(text)
        events = " ".join(d.get("event", "") for _, d, _ in lines)
        service = LOG_SERVICE_ALIASES.get(merged.get("service", ""), merged.get("service", ""))
        for rid in resources:
            fields = {k: v for k, v in merged.items() if k not in ("instance", "pod", "region", "trace_id", "requestId", "logger", "function")}
            fields["resource_id"] = rid
            system = merged.get("system") or (service if service.endswith(("_service", "_platform")) else None)
            out.append(_obs(f, f.file_id, f.captured_at, lines[-1][0], rid, f"log:{events.strip()}", fields,
                            record_type=merged.get("record_type"), system_id=system, extra_identifiers=idents,
                            snippet="\n".join(l for _, _, l in lines)))
    return out


def parse_txt(f: EvidenceFile) -> list[Observation]:
    out = []
    for line in f.path.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.lstrip("- ").split("|")]
        if len(parts) == 6 and TS_RE.fullmatch(parts[0]) and RID_RE.fullmatch(parts[2]):
            ts, system, rid, rtype, result, subject = parts
            fields = {"system": system, "resource_id": rid, "record_type": rtype, "result": result, "subject": subject}
            out.append(_obs(f, f.file_id, f.captured_at, ts, rid, "handover", fields, record_type=rtype,
                            system_id=system, snippet=line))
    return out


def _json_records(node: Any, ctx: dict[str, str]) -> Iterable[tuple[dict[str, Any], dict[str, str]]]:
    if isinstance(node, dict):
        ctx = dict(ctx)
        for key in ("captured_at", "observed_at", "recorded_at", "exported_at"):
            if isinstance(node.get(key), str) and TS_RE.fullmatch(node[key]):
                ctx["ts"] = node[key]
        for key in ("data_store", "collection", "source", "origin"):
            if isinstance(node.get(key), str):
                ctx[key] = node[key]
        if isinstance(node.get("resource_id"), str):
            yield node, ctx
            return
        for k, v in node.items():
            yield from _json_records(v, {**ctx, "path": f"{ctx.get('path', '')}/{k}"} if isinstance(v, (dict, list)) else ctx)
    elif isinstance(node, list):
        for v in node:
            yield from _json_records(v, ctx)


def parse_json(f: EvidenceFile, index: EvidenceIndex) -> list[Observation]:
    doc = json.loads(f.path.read_text(encoding="utf-8"))
    out = []
    for rec, ctx in _json_records(doc, {"ts": f.captured_at}):
        path = ctx.get("path", "").strip("/").split("/")
        collection = ctx.get("collection") or "/".join(path[-2:])  # e.g. "analytics_platform/profiles"
        system = rec.get("system") if isinstance(rec.get("system"), str) else None
        if not system and ctx.get("data_store") and ctx["data_store"] not in ("support_storage_service", "privacy_treatment_service", "backup_restore_service"):
            system = ctx["data_store"]
        out.append(_obs(f, f.file_id, f.captured_at, ctx["ts"], rec["resource_id"], collection, rec,
                        record_type=rec.get("record_type"), system_id=system))
    for snap in doc.get("snapshots", []) if isinstance(doc, dict) else []:  # full collection snapshots -> coverage
        index.coverage.append(Coverage(f.file_id, f.captured_at, snap["captured_at"], snap["data_store"], snap["collection"],
                                       frozenset(r["resource_id"] for r in snap["records"] if "resource_id" in r)))
    return out


def parse_sql(f: EvidenceFile, index: EvidenceIndex) -> list[Observation]:
    script = f.path.read_text(encoding="utf-8")
    m = re.search(r"Captured at:\s*(\S+)", script)
    snap_ts = m.group(1) if m else f.captured_at
    con = sqlite3.connect(":memory:")
    con.executescript(script)
    con.row_factory = sqlite3.Row
    out = []
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        rows = [dict(r) for r in con.execute(f'SELECT * FROM "{table}"')]
        if table == "snapshot_scope" or not rows or "resource_id" not in rows[0]:
            continue
        for row in rows:
            fields = dict(row)
            if isinstance(fields.get("record_json"), str):
                fields.update(json.loads(fields.pop("record_json")))
            collection = f"{table}:{fields.get('collection_name', '')}".rstrip(":")
            system = fields.get("origin_system")
            out.append(_obs(f, f.file_id, f.captured_at, snap_ts, fields["resource_id"], collection, fields,
                            system_id=system if isinstance(system, str) else None))
        index.coverage.append(Coverage(f.file_id, f.captured_at, snap_ts, PREFIX_SYSTEM.get(rows[0]["resource_id"].rsplit("_", 1)[0], ""),
                                       table, frozenset(r["resource_id"] for r in rows)))
    con.close()
    return out


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def parse_document(f: EvidenceFile, text: str) -> list[Observation]:
    """PDFs are single-subject business documents: every resource they mention gets the document's identifiers."""
    idents = identifiers_in(text)
    return [_obs(f, f.file_id, f.captured_at, f.captured_at, rid, "document", {"document": f.path.name},
                 extra_identifiers=idents, snippet=text[:600]) for rid in dict.fromkeys(RID_RE.findall(text))]


def transcribe_image(f: EvidenceFile) -> dict[str, Any]:
    from config import GEMINI_IMAGE_THINKING
    from llm import call_gemini
    from prompts import IMAGE_TRANSCRIPTION_SCHEMA, IMAGE_TRANSCRIPTION_SYSTEM
    return call_gemini(purpose="image_transcription", case_id=f.file_id, system=IMAGE_TRANSCRIPTION_SYSTEM,
                       parts=[f.path, "Transcribe this screenshot."], schema=IMAGE_TRANSCRIPTION_SCHEMA,
                       thinking_level=GEMINI_IMAGE_THINKING)


def render_transcription(t: dict[str, Any]) -> str:
    lines = [f"{t.get('application', '')} | {t.get('page_title', '')} | {t.get('subtitle', '')}"]
    for r in t.get("records", []):
        cells = "; ".join(f"{c['name']}={c['value']}" for c in r.get("fields", []))
        lines.append(f"[{r.get('role')}] {r.get('resource_id') or '-'}: {cells}")
    lines += t.get("other_text", [])
    return "\n".join(lines)


def parse_image(f: EvidenceFile, t: dict[str, Any]) -> list[Observation]:
    """One observation per transcribed record that has a resource_id; identifiers come from that record only,
    plus the page subject's identifiers when the record is the page subject or its detail panel."""
    subject_text = " ".join(f"{c['value']}" for r in t.get("records", []) if r.get("role") == "page_subject"
                            for c in r.get("fields", []) if c.get("value")) + f" {t.get('page_title', '')} {t.get('subtitle', '')}"
    out = []
    for r in t.get("records", []):
        fields = {c["name"]: c["value"] for c in r.get("fields", [])}
        if r.get("role") == "page_subject":  # header text (name, email, phone) belongs to the page subject
            fields["page_header"] = f"{t.get('page_title', '')} | {t.get('subtitle', '')}"
        rid = r.get("resource_id") or ""
        if RID_RE.fullmatch(rid):
            rids = [rid]
        else:  # e.g. page subject keyed by user_20 with analytics_7438 in a field, or support_1034 only in the subtitle
            text = " ".join(str(v) for v in fields.values() if v)
            if r.get("role") == "page_subject":
                text += f" {t.get('subtitle', '')}"
            rids = list(dict.fromkeys(RID_RE.findall(text)))
        extra = identifiers_in(subject_text) if r.get("role") != "table_row" else frozenset()
        for rid in rids:
            out.append(_obs(f, f.file_id, f.captured_at, f.captured_at, rid, f"screenshot:{t.get('page_title', '')}", fields,
                            extra_identifiers=extra, snippet=f"{t.get('page_title', '')}: {json.dumps(fields, ensure_ascii=False)}"))
    return out


def parse_activity_links() -> list[Observation]:
    """LINK_RESOURCE_IDENTITY rows are grounded identity links (state LINKED); all other activity rows are claims."""
    return [_obs(None, a.activity_id, a.event_time, a.event_time, a.resource_id, "activity:LINK_RESOURCE_IDENTITY",
                 {"details": a.details}, system_id=a.target_system, snippet=a.details)
            for a in load_activity() if a.event_type == "LINK_RESOURCE_IDENTITY"]


def build_index(transcribe_images: bool = True) -> EvidenceIndex:
    index = EvidenceIndex()
    for f in load_manifest():
        ext = f.path.suffix.lower()
        if ext == ".log":
            index.add(parse_log(f))
        elif ext == ".txt":
            index.add(parse_txt(f))
        elif ext == ".json":
            index.add(parse_json(f, index))
        elif ext == ".sql":
            index.add(parse_sql(f, index))
        elif ext == ".pdf":
            index.documents[f.file_id] = pdf_text(f.path)
            index.add(parse_document(f, index.documents[f.file_id]))
        elif ext == ".png":
            if not transcribe_images:
                index.warnings.append(f"{f.file_id}: image not transcribed (transcribe_images=False)")
                continue
            try:
                t = transcribe_image(f)
            except RuntimeError as e:  # missing API key: index the rest, report the gap
                index.warnings.append(f"{f.file_id}: image not transcribed ({e})")
                continue
            index.documents[f.file_id] = render_transcription(t)
            index.add(parse_image(f, t))
    index.add(parse_activity_links())
    for w in index.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return index
