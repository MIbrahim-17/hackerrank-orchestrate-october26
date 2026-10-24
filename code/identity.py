"""Resolve a request email to a user and every identifier that user has ever held.

Identity resolution is deliberately time-unbounded (inferred_rules.md D6): every identity change in the
dataset predates its request, so the full user_audit_log history is used. Time windows apply later, to
evidence records, never to who the person is.

Identifiers are compared as normalized keys ("email:<lower>", "phone:<digits>", "hash:<hex>", "user:<id>"),
so matching is exact on the whole identifier (decoys like jonas.berg vs jonas.berglund never match).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache

from data import load_audit_log, load_identities

FIELD_KIND = {"email": "email", "phone": "phone", "email_hash": "hash"}


def norm_email(value: str) -> str:
    return value.strip().lower()


def norm_phone(value: str) -> str:
    return re.sub(r"\D", "", value)


def ident_key(kind: str, value: str) -> str:
    """Normalized identifier key used by both identity resolution and the evidence index."""
    if kind == "email":
        return f"email:{norm_email(value)}"
    if kind == "phone":
        return f"phone:{norm_phone(value)}"
    if kind == "hash":
        return f"hash:{value.strip().lower()}"
    if kind == "user":
        return f"user:{value.strip()}"
    raise ValueError(f"unknown identifier kind: {kind}")


def email_hash(email: str) -> str:
    """email_hash in the dataset is sha256 of the email (verified on all 850 users and 107 changes)."""
    return hashlib.sha256(norm_email(email).encode()).hexdigest()


@dataclass(frozen=True)
class Identifier:
    key: str
    kind: str  # email | phone | hash | user
    value: str
    current: bool
    source: str  # "user_identities", an audit_id, or "derived" (hash computed from an email)


@dataclass(frozen=True)
class Subject:
    user_id: str
    name: str
    identifiers: tuple[Identifier, ...]
    matched: Identifier  # the identifier the request email matched
    email_hops: int  # email changes between the request email and the current email

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(i.key for i in self.identifiers)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "matched": {"value": self.matched.value, "current": self.matched.current, "source": self.matched.source},
            "email_hops": self.email_hops,
            "identifiers": [
                {"kind": i.kind, "value": i.value, "current": i.current, "source": i.source} for i in self.identifiers
            ],
        }


def _identifiers_for(user_id: str) -> list[Identifier]:
    row = load_identities()[user_id]
    found: dict[str, Identifier] = {}

    def add(kind: str, value: str, current: bool, source: str) -> None:
        if not value:
            return
        key = ident_key(kind, value)
        if key not in found or (current and not found[key].current):
            found[key] = Identifier(key, kind, value, current, source)

    add("user", user_id, True, "user_identities")
    for field, kind in FIELD_KIND.items():
        add(kind, row[field], True, "user_identities")
    for change in load_audit_log():
        if change.user_id == user_id and change.field_name in FIELD_KIND:
            kind = FIELD_KIND[change.field_name]
            add(kind, change.old_value, False, change.audit_id)
            add(kind, change.new_value, ident_key(kind, change.new_value) == ident_key(kind, row[change.field_name]),
                change.audit_id)
    for ident in list(found.values()):
        if ident.kind == "email":
            add("hash", email_hash(ident.value), ident.current, "derived")
    return sorted(found.values(), key=lambda i: (i.kind, not i.current, i.value))


@lru_cache(maxsize=1)
def identifier_owners() -> dict[str, str]:
    """Normalized identifier key -> user_id, over every user's full history (no identifier is shared)."""
    return {i.key: user_id for user_id in load_identities() for i in _identifiers_for(user_id)}


def _email_chain(user_id: str) -> list[str]:
    """Emails held by the user, oldest first."""
    changes = sorted((c for c in load_audit_log() if c.user_id == user_id and c.field_name == "email"),
                     key=lambda c: c.event_time)
    if not changes:
        return [norm_email(load_identities()[user_id]["email"])]
    return [norm_email(changes[0].old_value)] + [norm_email(c.new_value) for c in changes]


def resolve_identity(email: str) -> list[Subject]:
    """All users who ever held this email (current snapshot or any audit old/new value). Normally exactly one."""
    target = norm_email(email)
    users = {u for u, r in load_identities().items() if norm_email(r["email"]) == target}
    users |= {c.user_id for c in load_audit_log()
              if c.field_name == "email" and target in (norm_email(c.old_value), norm_email(c.new_value))}
    subjects = []
    for user_id in sorted(users):
        idents = _identifiers_for(user_id)
        matched = next(i for i in idents if i.key == ident_key("email", target))
        chain = _email_chain(user_id)
        hops = len(chain) - 1 - chain.index(target) if target in chain else 0
        subjects.append(Subject(user_id, load_identities()[user_id]["name"], tuple(idents), matched, hops))
    return subjects
