"""Link deletion-worker activity rows to cases when no evidence ties the resource to the subject.

Some resources never appear next to an identifier: a deleted account seen only as a bare 404, or an analytics
record whose identifiers were all nulled. Their only tie to a case is the deletion worker's own activity row.
The rule (DECISIONS 2026-10-25, proven on the samples: 7/23 recovered, 0 extras) is:

  window   per detail template, relative to reported_at:
             "reported the requested operation" / "completed some internal work"   reported_at +/- 15 min
             "submitted primary profile <account>"                                reported_at -1.5h .. -0.5h
             "Policy action completed for <analytics>"                            reported_at -0.6h .. -0.4h
  kinds    account   = DELETE_RECORD -> account_service
           analytics = ANONYMIZE_RECORD -> analytics_platform
  status   account rows must match the case's reported_status (COMPLETE: SUCCESS, NOT_STARTED: FAILED,
           PARTIALLY_COMPLETE: PARTIAL or SUCCESS), since the workflow status summarizes that row
  skip     a kind that evidence already links to the subject (a case has one primary account)
  exclude  a candidate whose evidence ties it to a different user
  assign   constraint propagation: each row serves exactly one request, so a row in exactly one open case's
           window goes to that case and leaves every other set; repeat until stable. Whatever is left is
           "ambiguous": candidates are kept for the agent, the validator checks its choice.

These rows are claims about an operation, not proof of state: they only say which resource belongs to the case.
State still comes from eligible evidence (or the step stays uncited where the rules allow).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from data import Activity, Request, load_activity
from evidence import EvidenceIndex
from identity import identifier_owners, resolve_identity

KINDS = {
    "account": ("DELETE_RECORD", "account_service"),
    "analytics": ("ANONYMIZE_RECORD", "analytics_platform"),
}
# The workflow's reported_status summarizes the primary-profile delete row's result (all sample accounts:
# COMPLETE<->SUCCESS 20/20, NOT_STARTED<->FAILED 12/12, PARTIALLY_COMPLETE<->PARTIAL 3 or SUCCESS 2).
# Analytics rows show no such relation, so the filter applies to accounts only.
ACCOUNT_RESULT_FOR_STATUS = {"COMPLETE": {"SUCCESS"}, "NOT_STARTED": {"FAILED"}, "PARTIALLY_COMPLETE": {"PARTIAL", "SUCCESS"}}
COMPLETED_TEMPLATES = ("reported the requested operation", "completed some internal work")


@dataclass(frozen=True)
class ActivityLink:
    status: str  # linked (evidence already has one) | one | ambiguous | none
    candidates: tuple[str, ...]  # resource_ids
    activity_ids: tuple[str, ...]


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def in_window(a: Activity, reported_at: str) -> bool:
    delta = _ts(a.event_time) - _ts(reported_at)
    if any(t in a.details for t in COMPLETED_TEMPLATES):
        return abs(delta) <= timedelta(minutes=15)
    if "submitted primary profile" in a.details:
        return timedelta(hours=-1.5) <= delta <= timedelta(hours=-0.5)
    if "Policy action completed" in a.details:
        return timedelta(hours=-0.6) <= delta <= timedelta(hours=-0.4)
    return False


def _evidence_owners(index: EvidenceIndex) -> dict[str, set[str]]:
    owners_by_key = identifier_owners()
    owners: dict[str, set[str]] = defaultdict(set)
    for o in index.observations:
        for key in o.identifiers:
            if key in owners_by_key:
                owners[o.resource_id].add(owners_by_key[key])
    return owners


def _linked_kinds(index: EvidenceIndex, r: Request) -> set[str]:
    keys = resolve_identity(r.email)[0].keys
    eligible, _ = index.search(keys, r.requested_at, r.audit_at)
    ids = {o.resource_id for o in eligible} | {ref for o in eligible for ref in o.refs}
    ids |= set(index.owned_after_audit(keys, r.requested_at, r.audit_at))
    return {kind for kind in KINDS if any(rid.startswith(f"{kind}_") for rid in ids)}


def build_activity_links(index: EvidenceIndex, requests: list[Request],
                         non_deletion: frozenset[str] = frozenset()) -> dict[str, dict[str, ActivityLink]]:
    """case_id -> kind -> ActivityLink. `requests` must be every known request (constraints are global).

    Constraint propagation: each deletion_worker row serves exactly one request. A row that falls in exactly one
    open case's window is assigned to that case; assigned rows leave every other case's candidate set; repeat until
    nothing changes. Cases in `non_deletion` (intent NOT_APPLICABLE) claim no rows.
    """
    owners = _evidence_owners(index)
    rows = [a for a in load_activity() if a.source_system == "deletion_worker"]
    by_id = {a.activity_id: a for a in rows}
    links: dict[str, dict[str, ActivityLink]] = {r.case_id: {} for r in requests}
    for kind, (event_type, target) in KINDS.items():
        candidates: dict[str, set[str]] = {}
        for r in requests:
            if r.case_id in non_deletion:
                links[r.case_id][kind] = ActivityLink("none", (), ())
                continue
            if kind in _linked_kinds(index, r):
                links[r.case_id][kind] = ActivityLink("linked", (), ())
                continue
            subject = resolve_identity(r.email)[0].user_id
            candidates[r.case_id] = {
                a.activity_id for a in rows
                if a.event_type == event_type and a.target_system == target and in_window(a, r.reported_at)
                and not (owners.get(a.resource_id) and subject not in owners[a.resource_id])
                and (kind != "account" or a.reported_result in ACCOUNT_RESULT_FOR_STATUS.get(r.reported_status, set()))}
        assigned: dict[str, str] = {}
        changed = True
        while changed:
            changed = False
            holders: dict[str, set[str]] = defaultdict(set)
            for case_id, acts in candidates.items():
                if case_id not in assigned:
                    for act in acts - set(assigned.values()):
                        holders[act].add(case_id)
            for act, cases in sorted(holders.items()):
                case_id = next(iter(cases))
                if len(cases) == 1 and case_id not in assigned:
                    assigned[case_id] = act
                    changed = True
        taken = set(assigned.values())
        for case_id, acts in candidates.items():
            if case_id in assigned:
                act = by_id[assigned[case_id]]
                links[case_id][kind] = ActivityLink("one", (act.resource_id,), (act.activity_id,))
            elif acts - taken:
                left = sorted(acts - taken)
                links[case_id][kind] = ActivityLink(
                    "ambiguous", tuple(sorted({by_id[a].resource_id for a in left})), tuple(left))
            else:
                links[case_id][kind] = ActivityLink("none", (), ())
    return links
