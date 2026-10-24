"""Deterministic validator: owned resources -> policy -> steps_json. The model never writes steps.

Inputs per case: the resources the subject owns (each with how ownership is known), the evidence index, and
optionally agent choices. For each resource:
  category  explicit label in a source > agent override (only when no label exists) > collection/prefix hint
  state     latest eligible observation (gates: file, record, lifecycle) > absence from a full collection snapshot
            > UNKNOWN (no state evidence: the step stays uncited)
  policy    deletion_rules.csv by category -> required final state
  steps     violation -> FINDING + REMEDIATION + VERIFICATION; compliant -> VERIFICATION only
Status: NOT_APPLICABLE (no deletion intent, []), INCOMPLETE (any finding), else COMPLETE.
Evidence ids: findings cite the observation they rest on; COMPLETE verifications cite the evidence proving the
state; INCOMPLETE remediation and verification are future work and stay "" (inferred_rules.md A2, A3).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from activity_links import ActivityLink
from data import Request, load_rules
from evidence import EvidenceIndex, Observation
from identity import Subject, resolve_identity

OPERATIONS = [
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"), ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"), ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"), ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"), ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"), ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"), ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"), ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
]
OP_INDEX = {op: i for i, (_, op, _) in enumerate(OPERATIONS)}
OP_PHASE_STATE = {op: (phase, state) for phase, op, state in OPERATIONS}

# What each treatment requires: (finding op, remediation op, verification op).
TREATMENT = {
    "DELETE": ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    "REDACT": ("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED"),
    "ANONYMIZE": ("REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED"),
    "RETAIN": (None, None, "VERIFY_RECORD_PRESENT"),
    "BLOCK_RESTORE": ("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED"),  # BACKUP_ARCHIVE: retain, block
    "DISABLE": ("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED"),  # data flows
}
PREFIX_DEFAULT_CATEGORY = {"analytics": "ANALYTICS_PROFILE", "support": "SUPPORT_MESSAGE"}


def treatment_for(category: str) -> str:
    if category == "DATA_FLOW":
        return "DISABLE"
    if category == "BACKUP_ARCHIVE":
        return "BLOCK_RESTORE"
    for rule in load_rules():
        if rule.data_category == category:
            return rule.required_action
    return "DELETE"


@dataclass(frozen=True)
class Owned:
    resource_id: str
    how: str  # evidence | ref | post_audit | activity | agent
    grounding: str  # source id that ties the resource to the subject


@dataclass(frozen=True)
class State:
    value: str  # ABSENT PRESENT IDENTIFIABLE REDACTED ANONYMIZED ACTIVE DISABLED RESTORABLE BLOCKED UNKNOWN
    exposes_pii: bool
    evidence_id: str  # "" when no eligible evidence


@dataclass
class CaseResult:
    case_id: str
    status: str
    steps: list[dict]
    owned: dict[str, Owned] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def steps_json(self) -> str:
        return json.dumps(self.steps, ensure_ascii=False, separators=(",", ":"))


def deterministic_owned(index: EvidenceIndex, links: dict[str, ActivityLink], r: Request) -> dict[str, Owned]:
    keys = resolve_identity(r.email)[0].keys
    eligible, _ = index.search(keys, r.requested_at, r.audit_at)
    owned: dict[str, Owned] = {}
    for o in eligible:
        owned.setdefault(o.resource_id, Owned(o.resource_id, "evidence", o.source_id))
    for o in eligible:
        for ref in o.refs:
            owned.setdefault(ref, Owned(ref, "ref", o.source_id))
    for rid, sources in index.owned_after_audit(keys, r.requested_at, r.audit_at).items():
        owned.setdefault(rid, Owned(rid, "post_audit", sources[0]))
    for link in links.values():
        if link.status == "one":
            owned.setdefault(link.candidates[0], Owned(link.candidates[0], "activity", link.activity_ids[0]))
    return owned


def category_of(index: EvidenceIndex, resource_id: str, override: str | None = None) -> str:
    observations = index.by_resource.get(resource_id, [])
    labels = [o.record_type for o in observations if o.record_type]
    if labels:
        return most_common(labels)
    if override:
        return override
    hints = [o.category_hint for o in observations if o.category_hint]
    if hints:
        return most_common(hints)
    prefix = resource_id.rsplit("_", 1)[0]
    return PREFIX_DEFAULT_CATEGORY.get(prefix, "USER_PROFILE")


HINT_ONLY_SOURCES = ("log:", "screenshot:", "document:", "activity:")  # event names and titles: hints, not labels
ATTACHMENT_FILE = re.compile(r"""\bfile(?:_name)?["']?\s*[:=]\s*["']?[\w.-]+\.(?:pdf|jpe?g|png|zip|docx?)\b""", re.IGNORECASE)
# Fixed priority when explicit labels conflict: the more specific category wins (DECISIONS 2026-10-25).
LABEL_PRIORITY = [
    "ACCOUNT_TOMBSTONE", "LEGAL_HOLD_RECORD", "SECURITY_AUDIT_LOG", "BACKUP_ARCHIVE", "DATA_FLOW", "USER_EXPORT",
    "SUPPORT_ATTACHMENT", "SECONDARY_IDENTIFIER", "MARKETING_PROFILE", "EMAIL_DELIVERY_LOG", "CACHE_ENTRY",
    "SEARCH_INDEX_ENTRY", "SUPPORT_MESSAGE", "PRODUCT_TELEMETRY", "ANALYTICS_PROFILE", "USER_PROFILE",
]
LABEL_CONFLICTS: list[tuple[str, tuple[str, ...], str]] = []  # (resource_id, labels seen, label chosen)


def most_common(values: list[str]) -> str:
    """Most frequent value; ties go to the alphabetically first. Never depends on set order or string hashing."""
    return min(sorted(set(values)), key=lambda v: (-values.count(v), v))


def observation_label(o: Observation) -> str | None:
    """The category a single record states explicitly, or None if it only hints.
    Specific beats generic: a record naming an attachment file labels a support resource as an attachment."""
    if o.record_type:
        return o.record_type
    if o.resource_id.startswith("support_") and ("attachment" in o.collection or ATTACHMENT_FILE.search(o.snippet)):
        return "SUPPORT_ATTACHMENT"
    if o.category_hint and not o.collection.startswith(HINT_ONLY_SOURCES):
        return o.category_hint
    return None


def explicit_label(index: EvidenceIndex, resource_id: str) -> str | None:
    """Category stated by any source at any time (what a resource is does not change; DECISIONS 2026-10-25).
    Conflicting labels resolve by LABEL_PRIORITY and are recorded in LABEL_CONFLICTS."""
    labels = sorted({label for o in index.by_resource.get(resource_id, []) if (label := observation_label(o))},
                    key=lambda c: (LABEL_PRIORITY.index(c) if c in LABEL_PRIORITY else len(LABEL_PRIORITY), c))
    if len(labels) > 1:
        LABEL_CONFLICTS.append((resource_id, tuple(labels), labels[0]))
    return labels[0] if labels else None


def final_category(index: EvidenceIndex, resource_id: str, override: str | None = None) -> str:
    """Category used for the policy: explicit label (any time) > agent judgement > hint > prefix default.
    category_of() stays unchanged because it feeds the agent's frozen first message."""
    return explicit_label(index, resource_id) or override or category_of(index, resource_id)


def state_of(index: EvidenceIndex, resource_id: str, system_id: str, r: Request) -> State:
    eligible, _ = index.for_resource(resource_id, r.requested_at, r.audit_at)
    direct = [o for o in eligible if o.state != "LINKED"]
    if direct:
        latest = max(direct, key=lambda o: (o.observed_at, o.captured_at, o.source_id))
        return State(latest.state, latest.exposes_pii, latest.source_id)
    snapshots = [c for c in index.coverage if c.system_id == system_id and c.captured_at <= r.audit_at
                 and r.requested_at <= c.observed_at <= r.audit_at]
    if snapshots:
        latest_file = max(snapshots, key=lambda c: (c.observed_at, c.source_id)).source_id
        same_file = [c for c in snapshots if c.source_id == latest_file]
        if all(resource_id not in c.resource_ids for c in same_file):
            return State("ABSENT", False, latest_file)
    return State("UNKNOWN", False, "")


def plan(category: str, state: State) -> tuple[str | None, str | None, str]:
    """(finding op or None, remediation op or None, verification op) for one resource."""
    finding, remediation, verification = TREATMENT[treatment_for(category)]
    v = state.value
    violated = {
        "DELETE": v not in ("ABSENT", "UNKNOWN"),
        "REDACT": v == "IDENTIFIABLE" or (v == "PRESENT" and state.exposes_pii),
        "ANONYMIZE": v == "IDENTIFIABLE" or (v == "PRESENT" and state.exposes_pii),
        "RETAIN": False,
        "BLOCK_RESTORE": v == "RESTORABLE",
        "DISABLE": v == "ACTIVE",
    }[treatment_for(category)]
    return (finding, remediation, verification) if violated else (None, None, verification)


def _step(op: str, system_id: str, resource_id: str, evidence_id: str) -> dict:
    phase, state = OP_PHASE_STATE[op]
    return {"step_no": 0, "phase": phase, "system_id": system_id, "resource_id": resource_id,
            "operation": op, "state": state, "evidence_id": evidence_id}


def build_steps(planned: list[tuple[str, str, str | None, str | None, str, State]]) -> tuple[str, list[dict]]:
    """planned: (system_id, resource_id, finding, remediation, verification, state). Returns (status, steps)."""
    incomplete = any(finding for _, _, finding, _, _, _ in planned)
    steps = []
    for system_id, rid, finding, remediation, verification, state in planned:
        if finding:
            steps.append(_step(finding, system_id, rid, state.evidence_id))
            steps.append(_step(remediation, system_id, rid, ""))
        steps.append(_step(verification, system_id, rid, "" if incomplete else state.evidence_id))
    steps.sort(key=lambda s: (OP_INDEX[s["operation"]], s["system_id"], s["resource_id"]))
    for i, s in enumerate(steps, 1):
        s["step_no"] = i
    return ("INCOMPLETE" if incomplete else "COMPLETE"), steps


def grounding_error(index: EvidenceIndex, subject: Subject, r: Request, resource_id: str, evidence_id: str) -> str | None:
    """None if `evidence_id` holds a record of `resource_id` tied to the subject (identifier or exact full name),
    observed at/before audit_at within the lifecycle, or an ownership-only record after audit_at."""
    name = re.compile(rf"(?<!\w){re.escape(subject.name)}(?!\w)", re.IGNORECASE)
    for o in index.by_resource.get(resource_id, []):
        if o.source_id != evidence_id:
            continue
        if o.observed_at < r.requested_at:
            return f"{evidence_id} observes {resource_id} before requested_at (earlier lifecycle)"
        if subject.keys & o.identifiers or name.search(o.snippet):
            return None
        return f"{evidence_id} shows {resource_id} but no identifier or full name of {subject.user_id}"
    return f"{evidence_id} has no record of {resource_id}"


def validate_case(r: Request, index: EvidenceIndex, links: dict[str, ActivityLink], authorizes_deletion: bool,
                  agent: dict | None = None) -> CaseResult:
    """Build the case answer. `agent` (optional): {"choices": [{"kind", "resource_id"|"none", "evidence_id"}],
    "categories": [{"resource_id", "data_category"}]}. Invalid agent items are dropped and reported in errors."""
    if not authorizes_deletion:
        return CaseResult(r.case_id, "NOT_APPLICABLE", [])
    subject = resolve_identity(r.email)[0]
    owned = deterministic_owned(index, links, r)
    errors: list[str] = []
    overrides: dict[str, str] = {}
    for choice in (agent or {}).get("choices", []):
        rid, kind = choice.get("resource_id", "none"), choice.get("kind", "")
        if rid in (None, "", "none"):
            continue
        link = links.get(kind)
        if not link or link.status != "ambiguous" or rid not in link.candidates:
            errors.append(f"{rid}: not a candidate of an ambiguous {kind} set")
            continue
        err = grounding_error(index, subject, r, rid, choice.get("evidence_id", ""))
        if err:
            errors.append(f"{rid}: {err}")
            continue
        owned.setdefault(rid, Owned(rid, "agent", choice["evidence_id"]))
    for item in (agent or {}).get("categories", []):
        overrides[item["resource_id"]] = item["data_category"]
    planned = []
    for rid in sorted(owned):
        prefix = rid.rsplit("_", 1)[0]
        system_id = next((o.system_id for o in index.by_resource.get(rid, [])), None) or {
            "account": "account_service", "analytics": "analytics_platform"}.get(prefix, prefix)
        category = final_category(index, rid, overrides.get(rid))
        state = state_of(index, rid, system_id, r)
        finding, remediation, verification = plan(category, state)
        planned.append((system_id, rid, finding, remediation, verification, state))
    status, steps = build_steps(planned)
    return CaseResult(r.case_id, status, steps, owned, errors)
