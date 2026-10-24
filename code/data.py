"""Load the participant-facing CSVs from dataset/ into small typed records."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import DATASET_DIR


@dataclass(frozen=True)
class Request:
    case_id: str
    email: str
    requested_at: str
    reported_status: str
    reported_at: str
    audit_at: str
    request_text: str


@dataclass(frozen=True)
class AuditChange:
    audit_id: str
    user_id: str
    event_time: str
    field_name: str
    old_value: str
    new_value: str


@dataclass(frozen=True)
class Activity:
    activity_id: str
    event_time: str
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    data_category: str
    condition: str
    required_action: str


@dataclass(frozen=True)
class EvidenceFile:
    file_id: str
    path: Path
    origin: str
    captured_at: str


def read_csv(name: str) -> list[dict[str, str]]:
    with open(DATASET_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_requests(name: str = "deletion_requests.csv") -> list[Request]:
    return [Request(**r) for r in read_csv(name)]


@lru_cache(maxsize=1)
def load_identities() -> dict[str, dict[str, str]]:
    return {r["user_id"]: r for r in read_csv("user_identities.csv")}


@lru_cache(maxsize=1)
def load_audit_log() -> tuple[AuditChange, ...]:
    return tuple(AuditChange(**r) for r in read_csv("user_audit_log.csv"))


@lru_cache(maxsize=1)
def load_activity() -> tuple[Activity, ...]:
    return tuple(Activity(**r) for r in read_csv("system_activity.csv"))


@lru_cache(maxsize=1)
def load_rules() -> tuple[Rule, ...]:
    return tuple(Rule(**r) for r in read_csv("deletion_rules.csv"))


@lru_cache(maxsize=1)
def load_manifest() -> tuple[EvidenceFile, ...]:
    return tuple(
        EvidenceFile(r["file_id"], DATASET_DIR / r["file_path"], r["origin"], r["captured_at"])
        for r in read_csv("evidence_files.csv")
    )
