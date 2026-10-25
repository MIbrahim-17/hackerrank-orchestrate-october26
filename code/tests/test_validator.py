"""Regression tests for validator.py, the component that writes every output step. No API calls.

Run: .venv/bin/python -m unittest discover -s code/tests
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation"))

import score  # noqa: E402
from activity_links import build_activity_links  # noqa: E402
from data import load_requests, read_csv  # noqa: E402
from evidence import build_index  # noqa: E402
from identity import resolve_identity  # noqa: E402
from validator import State, build_steps, explicit_label, grounding_error, plan, validate_case  # noqa: E402

INDEX = build_index(transcribe_images=False)
SAMPLES = load_requests("sample_deletion_requests.csv")
EVALS = load_requests()
LINKS = build_activity_links(INDEX, SAMPLES + EVALS)
BY_ID = {r.case_id: r for r in SAMPLES + EVALS}


def run(case_id: str):
    return validate_case(BY_ID[case_id], INDEX, LINKS[case_id], True)


class PlanTests(unittest.TestCase):
    """deletion_rules.csv by category -> (finding, remediation, verification)."""

    def test_policy_table(self) -> None:
        present_pii, present_clean = State("PRESENT", True, "e"), State("PRESENT", False, "e")
        cases = [
            ("USER_PROFILE", present_pii, ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT")),
            ("USER_PROFILE", State("ABSENT", False, "e"), (None, None, "VERIFY_RECORD_ABSENT")),
            ("USER_PROFILE", State("UNKNOWN", False, ""), (None, None, "VERIFY_RECORD_ABSENT")),
            ("SUPPORT_MESSAGE", State("IDENTIFIABLE", True, "e"), ("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED")),
            ("SUPPORT_MESSAGE", present_clean, (None, None, "VERIFY_RECORD_REDACTED")),
            ("SUPPORT_ATTACHMENT", present_clean, ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT")),
            ("ANALYTICS_PROFILE", present_pii, ("REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED")),
            ("ANALYTICS_PROFILE", present_clean, (None, None, "VERIFY_RECORD_ANONYMIZED")),
            ("ACCOUNT_TOMBSTONE", present_pii, ("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED")),
            ("SECURITY_AUDIT_LOG", present_pii, (None, None, "VERIFY_RECORD_PRESENT")),
            ("LEGAL_HOLD_RECORD", present_clean, (None, None, "VERIFY_RECORD_PRESENT")),
            ("BACKUP_ARCHIVE", State("RESTORABLE", True, "e"), ("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED")),
            ("BACKUP_ARCHIVE", State("BLOCKED", False, "e"), (None, None, "VERIFY_RESTORE_BLOCKED")),
            ("DATA_FLOW", State("ACTIVE", True, "e"), ("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED")),
            ("DATA_FLOW", State("DISABLED", False, "e"), (None, None, "VERIFY_DATA_FLOW_DISABLED")),
        ]
        for category, state, expected in cases:
            self.assertEqual(expected, plan(category, state), f"{category} {state}")


class BuildStepsTests(unittest.TestCase):
    def test_order_numbering_and_citations(self) -> None:
        planned = [
            ("search_service", "search_2", "REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT", State("PRESENT", True, "ev_s")),
            ("integration_service", "data_flow_1", "REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED", State("ACTIVE", True, "ev_d")),
            ("account_service", "account_1", None, None, "VERIFY_RECORD_ABSENT", State("ABSENT", False, "ev_a")),
        ]
        status, steps = build_steps(planned)
        self.assertEqual("INCOMPLETE", status)
        self.assertEqual(list(range(1, 8)), [s["step_no"] for s in steps])
        self.assertEqual(["REPORT_REMAINING_RECORD", "REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "DELETE_RECORD",
                          "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_ABSENT", "VERIFY_DATA_FLOW_DISABLED"], [s["operation"] for s in steps])
        self.assertEqual(["account_1", "search_2"], [s["resource_id"] for s in steps if s["operation"] == "VERIFY_RECORD_ABSENT"])
        self.assertEqual(["ev_s", "ev_d"], [s["evidence_id"] for s in steps if s["phase"] == "FINDING"])
        self.assertTrue(all(s["evidence_id"] == "" for s in steps if s["phase"] != "FINDING"))  # future work is uncited

    def test_complete_cites_verifications(self) -> None:
        status, steps = build_steps([("account_service", "account_1", None, None, "VERIFY_RECORD_ABSENT", State("ABSENT", False, "ev_a"))])
        self.assertEqual(("COMPLETE", "ev_a"), (status, steps[0]["evidence_id"]))


class LabelTests(unittest.TestCase):
    def test_specific_beats_generic(self) -> None:
        self.assertEqual("SUPPORT_ATTACHMENT", explicit_label(INDEX, "support_4533"))  # attachment_pii_scan file="...pdf"
        self.assertEqual("SUPPORT_ATTACHMENT", explicit_label(INDEX, "support_1370"))  # attachment_scan beats support_records
        self.assertEqual("SUPPORT_MESSAGE", explicit_label(INDEX, "support_864"))  # record_type in the handover
        self.assertIsNone(explicit_label(INDEX, "analytics_9914"))  # log hint only: no explicit label


class CaseTests(unittest.TestCase):
    def test_case_17_restore_risk(self) -> None:
        res = run("case_17")
        self.assertEqual("INCOMPLETE", res.status)
        self.assertIn(("REPORT_RESTORE_RISK", "backup_3245", "evidence_01"),
                      {(s["operation"], s["resource_id"], s["evidence_id"]) for s in res.steps})

    def test_case_31_snapshot_absence_is_cited(self) -> None:
        res = run("case_31")
        self.assertEqual("COMPLETE", res.status)
        self.assertIn(("VERIFY_RECORD_ABSENT", "account_4857", "evidence_51"),
                      {(s["operation"], s["resource_id"], s["evidence_id"]) for s in res.steps})

    def test_not_applicable_is_empty(self) -> None:
        res = validate_case(BY_ID["case_01"], INDEX, LINKS["case_01"], False)
        self.assertEqual(("NOT_APPLICABLE", []), (res.status, res.steps))

    def test_ungrounded_agent_choice_is_rejected(self) -> None:
        r = BY_ID["case_28"]
        subject = resolve_identity(r.email)[0]
        self.assertIsNotNone(grounding_error(INDEX, subject, r, "account_5482", "evidence_92"))
        res = validate_case(r, INDEX, LINKS["case_28"], True,
                            {"choices": [{"kind": "account", "resource_id": "account_5482", "evidence_id": "evidence_92"}]})
        self.assertTrue(res.errors)
        self.assertNotIn("account_5482", {s["resource_id"] for s in res.steps})

    def test_samples_baseline_precision(self) -> None:  # deterministic path: 100% status, 0 extra steps
        gold = score.load(score.DEFAULT_GOLD)
        pred = {r.case_id: (res.status, res.steps) for r in SAMPLES for res in [run(r.case_id)]}
        report = score.score(gold, pred)
        self.assertEqual(1.0, report.status_accuracy)
        self.assertEqual(1.0, report.step_precision)
        self.assertGreaterEqual(report.matched_steps, 181)


if __name__ == "__main__":
    unittest.main()
