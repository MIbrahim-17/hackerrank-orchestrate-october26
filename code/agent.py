"""Per-case investigation loop (claude-sonnet-5-5, hand-written tool loop).

The case brief is pre-fetched in code (identity, linked resources, ambiguous candidate sets with every record of each
candidate) so the model starts from facts. The model only decides ambiguous ownership (with cited grounding) and
categories where no source labels one, via submit_findings. The validator checks every choice; rejected choices go
back as a tool error, at most MAX_RETRIES times. MAX_TURNS caps the loop.
"""
from __future__ import annotations

import json
from typing import Any

from activity_links import ActivityLink
from data import Request
from evidence import EvidenceIndex
from identity import resolve_identity
from llm import LEDGER, call_claude
from prompts import AGENT_SYSTEM
from tools import TOOL_DEFS, CaseTools, _obs_view
from validator import category_of, deterministic_owned, state_of, validate_case

MAX_TURNS = 6
MAX_RETRIES = 2
JUDGED_PREFIXES = ("support", "analytics")  # prefixes that carry several categories; others are fixed by prefix


def needs_agent(r: Request, index: EvidenceIndex, links: dict[str, ActivityLink]) -> bool:
    """Route to the agent only when something is undecided: an ambiguous ownership set, or a support_/analytics_
    resource whose category no source labels. Everything else is fully decided by the validator (DECISIONS 2026-10-25)."""
    if any(link.status == "ambiguous" for link in links.values()):
        return True
    return any(rid.split("_", 1)[0] in JUDGED_PREFIXES and not any(o.record_type for o in index.by_resource.get(rid, []))
               for rid in deterministic_owned(index, links, r))


def case_brief(r: Request, index: EvidenceIndex, links: dict[str, ActivityLink]) -> tuple[str, list[str]]:
    """Pre-fetched first message; also returns the resource_ids whose category has no source label."""
    subject = resolve_identity(r.email)[0]
    owned = deterministic_owned(index, links, r)
    linked, unlabeled = [], []
    for rid, o in sorted(owned.items()):
        obs = index.by_resource.get(rid, [])
        labeled = any(x.record_type for x in obs)
        system_id = next((x.system_id for x in obs), rid.rsplit("_", 1)[0])
        st = state_of(index, rid, system_id, r)
        linked.append({"resource_id": rid, "system_id": system_id, "ownership": o.how, "via": o.grounding,
                       "category": category_of(index, rid), "category_source": "label" if labeled else "hint",
                       "state": st.value, "state_evidence": st.evidence_id})
        if not labeled and rid.split("_", 1)[0] in JUDGED_PREFIXES:
            unlabeled.append(rid)
    ambiguous = []
    for kind, link in links.items():
        if link.status != "ambiguous":
            continue
        ambiguous.append({"kind": kind, "candidates": [
            {"resource_id": c, "records": [_obs_view(o, r) for o in index.by_resource.get(c, [])][:8]}
            for c in link.candidates], "activity_rows": list(link.activity_ids)})
    brief = {
        "case": {"case_id": r.case_id, "email": r.email, "requested_at": r.requested_at, "audit_at": r.audit_at,
                 "reported_status (a claim)": r.reported_status, "reported_at": r.reported_at},
        "subject": subject.to_dict(),
        "linked_resources": linked,
        "category_decisions_needed (no source label)": unlabeled,
        "ambiguous_ownership_sets": ambiguous,
    }
    text = ("Case brief (pre-fetched, deterministic):\n" + json.dumps(brief, ensure_ascii=False, default=str) +
            "\n\nDecide the ambiguous sets (or 'none') and any categories, then call submit_findings.")
    return text, unlabeled


def investigate(r: Request, index: EvidenceIndex, links: dict[str, ActivityLink]) -> dict[str, Any]:
    tools = CaseTools(r, index, links)
    brief, unlabeled = case_brief(r, index, links)
    messages: list[dict] = [{"role": "user", "content": brief}]
    system = [{"type": "text", "text": AGENT_SYSTEM, "cache_control": {"type": "ephemeral"}}]
    stats = {"turns": 0, "tool_calls": 0, "retries": 0, "submitted": False}
    result: dict[str, Any] = {"choices": [], "categories": []}
    for _ in range(MAX_TURNS):
        response = call_claude(purpose="agent", case_id=r.case_id, system=system, messages=messages, tools=TOOL_DEFS)
        stats["turns"] += 1
        messages.append({"role": "assistant", "content": response["content"]})
        uses = [b for b in response["content"] if b["type"] == "tool_use"]
        if not uses:
            messages.append({"role": "user", "content": "Call submit_findings now."})
            continue
        results, done = [], False
        for block in uses:
            stats["tool_calls"] += 1
            if block["name"] == "submit_findings":
                candidate = {"choices": block["input"].get("choices", []),
                             "categories": [c for c in block["input"].get("categories", []) if c["resource_id"] in unlabeled]}
                errors = validate_case(r, index, links, True, candidate).errors
                if errors and stats["retries"] < MAX_RETRIES:
                    stats["retries"] += 1
                    results.append({"type": "tool_result", "tool_use_id": block["id"], "is_error": True,
                                    "content": "Validator rejected: " + "; ".join(errors)})
                else:
                    result, done = candidate, True
                    results.append({"type": "tool_result", "tool_use_id": block["id"], "content": "accepted"})
            else:
                try:
                    content = tools.call(block["name"], block["input"])
                    results.append({"type": "tool_result", "tool_use_id": block["id"], "content": content})
                except (TypeError, ValueError) as e:
                    results.append({"type": "tool_result", "tool_use_id": block["id"], "is_error": True, "content": str(e)})
        messages.append({"role": "user", "content": results})
        if done:
            stats["submitted"] = True
            break
    rows = [x for x in LEDGER if x["case_id"] == r.case_id and x["purpose"] == "agent"]
    stats.update({k: sum(x[k] for x in rows) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")})
    result["_stats"] = stats
    return result
