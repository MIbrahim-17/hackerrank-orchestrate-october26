"""Regression tests for identity.py and evidence.py, pinned to facts proven on the samples (docs/inferred_rules.md).

Run: .venv/bin/python -m unittest discover -s code/tests
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import load_requests, read_csv  # noqa: E402
from activity_links import build_activity_links  # noqa: E402
from evidence import build_index  # noqa: E402
from identity import email_hash, resolve_identity  # noqa: E402

INDEX = build_index(transcribe_images=False)
REQUESTS = {r.case_id: r for r in load_requests() + load_requests("sample_deletion_requests.csv")}
SAMPLES = {r.case_id: r for r in load_requests("sample_deletion_requests.csv")}


def linked(case_id: str) -> tuple[set[str], list]:
    r = REQUESTS[case_id]
    eligible, excluded = INDEX.search(resolve_identity(r.email)[0].keys, r.requested_at, r.audit_at)
    return {o.resource_id for o in eligible}, excluded


class IdentityTests(unittest.TestCase):
    def test_every_request_resolves_to_exactly_one_user(self) -> None:
        self.assertTrue(all(len(resolve_identity(r.email)) == 1 for r in REQUESTS.values()))

    def test_multi_hop_chain_from_oldest_email(self) -> None:  # E2: case_10 uses the oldest of 3 emails
        s = resolve_identity("nadia.ionescu@yahoo.com")[0]
        self.assertEqual((s.user_id, s.email_hops, s.matched.current), ("user_10", 2, False))
        self.assertIn("email:n.petrescu@yahoo.com", s.keys)

    def test_old_hash_is_known(self) -> None:  # E3: case_12 is matched only by the pre-change hash
        self.assertIn("hash:" + email_hash("minjun.kim90@gmail.com"), resolve_identity("minjun.kim@gmail.com")[0].keys)

    def test_case_insensitive_email(self) -> None:
        self.assertEqual(resolve_identity("MINJUN.KIM@GMAIL.COM")[0].user_id, "user_12")


class EvidenceLinkTests(unittest.TestCase):
    def test_no_extra_resources_on_samples(self) -> None:  # D6 window + exact matching: 0 extras
        gold = {r["case_id"]: {s["resource_id"] for s in json.loads(r["steps_json"])} for r in read_csv("sample_output.csv")}
        for case_id in SAMPLES:
            got, _ = linked(case_id)
            self.assertFalse(got - gold[case_id], f"{case_id} extra {got - gold[case_id]}")

    def test_decoys_never_match(self) -> None:  # E1
        self.assertNotIn("search_8814", linked("case_06")[0])  # jonas.berglund next to jonas.berg
        self.assertNotIn("support_5914", linked("case_10")[0])  # nadia.popescu next to nadia.ionescu

    def test_record_gate_traps(self) -> None:  # D3: eligible file holds NOT_FOUND at audit_at and FOUND two days later
        for case_id, rid, file_id in (("case_135", "account_1417", "evidence_13"), ("case_383", "account_5043", "evidence_36")):
            r = REQUESTS[case_id]
            eligible, excluded = INDEX.for_resource(rid, r.requested_at, r.audit_at)
            self.assertEqual({(file_id, "ABSENT")}, {(o.source_id, o.state) for o in eligible})
            self.assertIn((file_id, "PRESENT", "record timestamp after audit_at"),
                          {(o.source_id, o.state, why) for o, why in excluded})

    def test_file_gate(self) -> None:  # D3: evidence_02 (captured 09-17) never counts for 09-15 audits
        got, excluded = linked("case_23")
        self.assertNotIn("audit_record_4128", got)
        self.assertTrue(any(o.source_id == "evidence_02" and why == "file captured after audit_at" for o, why in excluded))

    def test_earlier_lifecycle_excluded(self) -> None:  # D6: case_17's March lifecycle belongs to case_46
        got, excluded = linked("case_17")
        self.assertFalse({"account_6523", "tombstone_17"} & got)
        self.assertTrue({"account_6523", "tombstone_17"} <= {o.resource_id for o, why in excluded if "earlier lifecycle" in why})

    def test_referenced_resource_is_not_present(self) -> None:  # search_001 row references account_006
        got, _ = linked("case_06")
        self.assertNotIn("account_006", got)
        r = SAMPLES["case_06"]
        eligible, _ = INDEX.search(resolve_identity(r.email)[0].keys, r.requested_at, r.audit_at)
        self.assertIn("account_006", {ref for o in eligible for ref in o.refs})


class OwnershipTests(unittest.TestCase):
    def test_post_audit_ownership_only(self) -> None:  # DECISIONS 2026-10-25: 8 resources in 7 sample cases
        expected = {("case_09", "account_3960"): "evidence_06", ("case_09", "audit_record_4902"): "evidence_06",
                    ("case_23", "audit_record_4128"): "evidence_02", ("case_24", "audit_record_7095"): "evidence_02",
                    ("case_26", "account_5684"): "evidence_02", ("case_27", "account_3866"): "evidence_02",
                    ("case_29", "audit_record_3954"): "evidence_02", ("case_30", "audit_record_1707"): "evidence_02"}
        for (case_id, rid), source in expected.items():
            r = REQUESTS[case_id]
            owned = INDEX.owned_after_audit(resolve_identity(r.email)[0].keys, r.requested_at, r.audit_at)
            self.assertEqual([source], owned.get(rid), f"{case_id} {rid}")
            eligible, _ = INDEX.for_resource(rid, r.requested_at, r.audit_at)  # state never comes from the owner file
            self.assertNotIn(source, {o.source_id for o in eligible})

    def test_complete_case_cites_pre_audit_state(self) -> None:  # gold cites evidence_92 for both accounts
        for case_id, rid in (("case_26", "account_5684"), ("case_27", "account_3866")):
            r = REQUESTS[case_id]
            eligible, _ = INDEX.for_resource(rid, r.requested_at, r.audit_at)
            self.assertEqual({("evidence_92", "ABSENT")}, {(o.source_id, o.state) for o in eligible})


class ActivityLinkTests(unittest.TestCase):
    LINKS = build_activity_links(INDEX, list(REQUESTS.values()))

    def test_emitted_links_are_correct(self) -> None:  # DECISIONS 2026-10-25: 14 recovered, 0 extras
        gold = {r["case_id"]: {s["resource_id"] for s in json.loads(r["steps_json"])} for r in read_csv("sample_output.csv")}
        emitted = {(c, x) for c in SAMPLES for link in self.LINKS[c].values() if link.status == "one" for x in link.candidates}
        wrong = {(c, x) for c, x in emitted if x not in gold[c]}
        self.assertFalse(wrong)
        self.assertGreaterEqual(len(emitted), 14)

    def test_status_filter_resolves_shared_window(self) -> None:  # case_31 COMPLETE/SUCCESS, case_32 PARTIAL/PARTIAL
        self.assertEqual(("one", ("account_4857",)), (self.LINKS["case_31"]["account"].status, self.LINKS["case_31"]["account"].candidates))
        self.assertEqual(("one", ("account_8858",)), (self.LINKS["case_32"]["account"].status, self.LINKS["case_32"]["account"].candidates))

    def test_true_tie_stays_ambiguous(self) -> None:  # case_28/29: same reported_at, both NOT_STARTED -> FAILED rows
        for case_id in ("case_28", "case_29"):
            link = self.LINKS[case_id]["account"]
            self.assertEqual(("ambiguous", ("account_5482", "account_7012")), (link.status, link.candidates))


class StateTests(unittest.TestCase):
    def states(self, case_id: str, rid: str) -> set[tuple[str, str, bool]]:
        r = REQUESTS[case_id]
        eligible, _ = INDEX.for_resource(rid, r.requested_at, r.audit_at)
        return {(o.source_id, o.state, o.exposes_pii) for o in eligible}

    def test_replica_copy_present(self) -> None:  # D2: account_005 only in the failover replica
        self.assertIn(("evidence_54", "PRESENT", True), self.states("case_05", "account_005"))

    def test_handover_not_found_is_absent(self) -> None:  # D1: activity says FAILED, evidence says NOT_FOUND
        self.assertEqual({("evidence_03", "ABSENT", False)}, self.states("case_13", "account_9335"))

    def test_tombstone_pii(self) -> None:  # C4
        self.assertTrue(all(pii for _, _, pii in self.states("case_32", "tombstone_9178")))
        self.assertFalse(any(pii for _, _, pii in self.states("case_31", "tombstone_440")))

    def test_flows_and_backups(self) -> None:  # C5
        self.assertIn(("evidence_03", "ACTIVE", False), self.states("case_11", "data_flow_9522"))  # email is the handover subject column
        self.assertIn(("evidence_92", "BLOCKED", False), self.states("case_26", "backup_3120"))
        self.assertIn(("evidence_93", "RESTORABLE", True), self.states("case_09", "backup_4978"))

    def test_explicit_state_sets_pii(self) -> None:  # IDENTIFIABLE in the handover must read as exposed
        self.assertEqual({("evidence_03", "IDENTIFIABLE", True)}, self.states("case_11", "support_864"))

    def test_anonymized_analytics_has_no_pii(self) -> None:
        self.assertEqual({("evidence_92", "PRESENT", False)}, self.states("case_25", "analytics_1895"))

    def test_404_lookup_is_absent(self) -> None:  # D5
        self.assertIn(("evidence_92", "ABSENT", False), self.states("case_25", "account_3136"))


if __name__ == "__main__":
    unittest.main()
