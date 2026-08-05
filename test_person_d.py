"""Unit tests for Person D: verifier_agent + trace.

Cac test dung CaseContext tong hop (khong doc CSV) nen chay rat nhanh:
``verify(..., check_csv=False)`` kiem tra su ton tai cua ID dua tren chinh
CaseContext thay vi DataLoader.

Chay: python test_person_d.py
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from schema import CaseContext, OrderInfo, OrderItemInfo, PaymentInfo, SellerInfo
from trace import TraceRecorder, TraceWriter, read_trace, write_trace
from verifier_agent import verify

ORDER_ID = "e2a03ccf5ea816036608b2d8c3ab8e60"
SELLER_ID = "4a3ca9315b744ce9f8e9374361493884"


def build_ctx() -> CaseContext:
    ctx = CaseContext(
        case_id="EC_001",
        opened_at="2018-10-18T00:00:00-03:00",
        claimed_order_id=ORDER_ID,
        customer_message="Don hang giao tre",
        language="vi",
        policy_version="EC_POLICY_V1",
    )
    ctx.order = OrderInfo(
        order_id=ORDER_ID,
        customer_id="CUST1",
        order_status="delivered",
        order_purchase_timestamp="2018-01-01 10:00:00",
        order_approved_at="2018-01-01 10:30:00",
        order_delivered_carrier_date="2018-01-06 10:00:00",
        order_delivered_customer_date="2018-01-14 10:00:00",
        order_estimated_delivery_date="2018-01-12 00:00:00",
    )
    ctx.order_status = "delivered"
    ctx.items = [OrderItemInfo(ORDER_ID, 1, "PROD1", SELLER_ID, "2018-01-05 10:00:00", 100.0, 15.0)]
    ctx.item_ids = [f"{ORDER_ID}:1"]
    ctx.sellers = {SELLER_ID: SellerInfo(SELLER_ID, "01001", "sao paulo", "SP")}
    ctx.seller_ids = [SELLER_ID]
    ctx.payments = [PaymentInfo(ORDER_ID, 1, "credit_card", 1, 115.0)]
    ctx.compute_totals()
    return ctx


def build_output() -> dict:
    """Output hop le cho rule late_delivery_seller (refund = freight = 15.0)."""
    return {
        "case_id": "EC_001",
        "assessment": {
            "primary_issue": "late_delivery_seller",
            "case_status": "action_required",
            "confidence": 0.95,
        },
        "affected_entities": {
            "order_ids": [ORDER_ID],
            "item_ids": [f"{ORDER_ID}:1"],
            "seller_ids": [SELLER_ID],
            "payment_ids": [f"{ORDER_ID}:1"],
        },
        "root_cause_analysis": {
            "ranked_causes": [{"cause_code": "SELLER_HANDOFF_AFTER_LIMIT", "rank": 1}],
            "responsible_parties": [{"party_type": "seller", "party_id": SELLER_ID}],
        },
        "evidence_ids": [
            f"order:{ORDER_ID}",
            f"item:{ORDER_ID}:1",
            f"payment:{ORDER_ID}:1",
            f"seller:{SELLER_ID}",
            "policy:SELLER_HANDOFF_AFTER_LIMIT",
        ],
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": 100.0,
            "freight_total_brl": 15.0,
            "payment_total_brl": 115.0,
            "recommended_refund_brl": 15.0,
        },
        "resolution_actions": ["refund_freight"],
    }


class TestVerifierHappyPath(unittest.TestCase):
    def setUp(self):
        self.ctx = build_ctx()
        self.output = build_output()

    def _verify(self, output=None):
        return verify(output or self.output, self.ctx, check_csv=False)

    def test_valid_output_passes(self):
        result = self._verify()
        self.assertTrue(result.passed, result.errors)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.checked_evidence, 5)

    def test_valid_no_action_output_passes(self):
        self.output["assessment"]["primary_issue"] = "unsupported_late_claim"
        self.output["assessment"]["case_status"] = "no_action"
        self.output["root_cause_analysis"]["ranked_causes"] = [
            {"cause_code": "DELIVERY_WITHIN_ESTIMATE", "rank": 1}
        ]
        self.output["root_cause_analysis"]["responsible_parties"] = []
        self.output["evidence_ids"][-1] = "policy:DELIVERY_WITHIN_ESTIMATE"
        self.output["financial_resolution"]["recommended_refund_brl"] = 0.0
        self.output["resolution_actions"] = ["reject_late_refund"]
        result = self._verify()
        self.assertTrue(result.passed, result.errors)


class TestVerifierEvidence(unittest.TestCase):
    """2D.2 - evidence ID phai ton tai va thuoc dung case."""

    def setUp(self):
        self.ctx = build_ctx()
        self.output = build_output()

    def _errors(self) -> str:
        return " | ".join(verify(self.output, self.ctx, check_csv=False).errors)

    def test_item_not_in_data_fails(self):
        self.output["evidence_ids"][1] = f"item:{ORDER_ID}:9"
        self.assertIn("khong ton tai", self._errors())

    def test_payment_not_in_data_fails(self):
        self.output["evidence_ids"][2] = f"payment:{ORDER_ID}:7"
        self.assertIn("khong ton tai", self._errors())

    def test_evidence_of_other_order_fails(self):
        self.output["evidence_ids"][0] = "order:deadbeefdeadbeefdeadbeefdeadbeef"
        self.assertIn("khong ton tai", self._errors())

    def test_malformed_evidence_fails(self):
        self.output["evidence_ids"].append("invoice:123")
        self.assertIn("sai dinh dang", self._errors())

    def test_unknown_root_cause_fails(self):
        self.output["evidence_ids"][-1] = "policy:SOMETHING_ELSE"
        self.assertIn("khong nam trong bang policy", self._errors())

    def test_duplicate_evidence_fails(self):
        self.output["evidence_ids"].append(f"order:{ORDER_ID}")
        self.assertIn("bi lap", self._errors())

    def test_unrelated_seller_fails(self):
        self.output["evidence_ids"][3] = "seller:" + "f" * 32
        self.assertIn("khong ton tai", self._errors())


class TestVerifierLimits(unittest.TestCase):
    """2D.3 - <=5 ID/loai, <=10 evidence, <=3 cause, <=3 party, <=5 action."""

    def setUp(self):
        self.ctx = build_ctx()
        self.output = build_output()

    def _errors(self) -> str:
        return " | ".join(verify(self.output, self.ctx, check_csv=False).errors)

    def test_too_many_evidence_ids(self):
        self.output["evidence_ids"] = [f"item:{ORDER_ID}:{i}" for i in range(1, 12)]
        self.assertIn("toi da 10", self._errors())

    def test_too_many_entity_ids(self):
        self.output["affected_entities"]["item_ids"] = [f"{ORDER_ID}:{i}" for i in range(1, 7)]
        self.assertIn("toi da 5", self._errors())

    def test_too_many_root_causes(self):
        self.output["root_cause_analysis"]["ranked_causes"] = [
            {"cause_code": "SELLER_HANDOFF_AFTER_LIMIT", "rank": 1},
            {"cause_code": "CARRIER_DELIVERED_AFTER_ESTIMATE", "rank": 2},
            {"cause_code": "DELIVERY_WITHIN_ESTIMATE", "rank": 3},
            {"cause_code": "MULTIPLE_PAYMENTS_RECONCILED", "rank": 4},
        ]
        self.assertIn("toi da 3", self._errors())

    def test_too_many_actions(self):
        self.output["resolution_actions"] = ["refund_freight"] * 6
        self.assertIn("toi da 5", self._errors())


class TestVerifierAmounts(unittest.TestCase):
    """2D.4 - confidence trong [0,1], refund <= payment_total."""

    def setUp(self):
        self.ctx = build_ctx()
        self.output = build_output()

    def _errors(self) -> str:
        return " | ".join(verify(self.output, self.ctx, check_csv=False).errors)

    def test_confidence_out_of_range(self):
        self.output["assessment"]["confidence"] = 1.4
        self.assertIn("nam ngoai [0, 1]", self._errors())

    def test_negative_confidence(self):
        self.output["assessment"]["confidence"] = -0.1
        self.assertIn("nam ngoai [0, 1]", self._errors())

    def test_refund_over_payment_total(self):
        self.ctx.items[0].freight_value = 999.0
        self.ctx.compute_totals()
        self.output["financial_resolution"]["freight_total_brl"] = 999.0
        self.output["financial_resolution"]["recommended_refund_brl"] = 999.0
        self.assertIn("lon hon payment_total_brl", self._errors())

    def test_totals_must_match_context(self):
        self.output["financial_resolution"]["item_total_brl"] = 42.0
        self.assertIn("lech voi CSV", self._errors())

    def test_refund_basis_must_match_rule(self):
        self.output["financial_resolution"]["recommended_refund_brl"] = 115.0
        self.assertIn("phai hoan 15.0 BRL", self._errors())

    def test_status_refund_inconsistency(self):
        self.output["assessment"]["case_status"] = "no_action"
        self.assertIn("recommended_refund_brl = 15.0", self._errors())


class TestVerifierSchema(unittest.TestCase):
    """2D.5 - dung schema README muc 6."""

    def setUp(self):
        self.ctx = build_ctx()
        self.output = build_output()

    def _result(self):
        return verify(self.output, self.ctx, check_csv=False)

    def test_missing_section_fails(self):
        del self.output["financial_resolution"]
        result = self._result()
        self.assertFalse(result.passed)
        self.assertIn("thieu field 'financial_resolution'", " | ".join(result.errors))

    def test_wrong_type_fails(self):
        self.output["evidence_ids"] = f"order:{ORDER_ID}"
        self.assertIn("phai la list", " | ".join(self._result().errors))

    def test_unknown_primary_issue_fails(self):
        self.output["assessment"]["primary_issue"] = "late_delivery"
        self.assertIn("khong nam trong 6 rule", " | ".join(self._result().errors))

    def test_wrong_currency_fails(self):
        self.output["financial_resolution"]["currency"] = "USD"
        self.assertIn("phai la 'BRL'", " | ".join(self._result().errors))

    def test_cause_code_must_match_primary_issue(self):
        self.output["root_cause_analysis"]["ranked_causes"] = [
            {"cause_code": "DELIVERY_WITHIN_ESTIMATE", "rank": 1}
        ]
        self.assertIn("cause_code rank 1", " | ".join(self._result().errors))

    def test_action_must_match_primary_issue(self):
        self.output["resolution_actions"] = ["issue_full_refund"]
        self.assertIn("phai co action 'refund_freight'", " | ".join(self._result().errors))

    def test_extra_field_is_warning_only(self):
        self.output["debug_notes"] = "abc"
        result = self._result()
        self.assertTrue(result.passed, result.errors)
        self.assertIn("field thua 'debug_notes'", " | ".join(result.warnings))


class TestVerifierNoItemEdgeCase(unittest.TestCase):
    """README muc 6: order khong co item row -> list rong, total = 0.0."""

    def setUp(self):
        self.ctx = build_ctx()
        self.ctx.items = []
        self.ctx.item_ids = []
        self.ctx.sellers = {}
        self.ctx.seller_ids = []
        self.ctx.compute_totals()

        self.output = build_output()
        self.output["assessment"] = {
            "primary_issue": "canceled_order_paid",
            "case_status": "action_required",
            "confidence": 0.9,
        }
        self.output["affected_entities"] = {
            "order_ids": [ORDER_ID],
            "item_ids": [],
            "seller_ids": [],
            "payment_ids": [f"{ORDER_ID}:1"],
        }
        self.output["root_cause_analysis"] = {
            "ranked_causes": [{"cause_code": "ORDER_CANCELED_AFTER_PAYMENT", "rank": 1}],
            "responsible_parties": [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}],
        }
        self.output["evidence_ids"] = [
            f"order:{ORDER_ID}",
            f"payment:{ORDER_ID}:1",
            "policy:ORDER_CANCELED_AFTER_PAYMENT",
        ]
        self.output["financial_resolution"] = {
            "currency": "BRL",
            "item_total_brl": 0.0,
            "freight_total_brl": 0.0,
            "payment_total_brl": 115.0,
            "recommended_refund_brl": 115.0,
        }
        self.output["resolution_actions"] = ["issue_full_refund"]

    def test_empty_lists_pass(self):
        result = verify(self.output, self.ctx, check_csv=False)
        self.assertTrue(result.passed, result.errors)

    def test_non_empty_item_ids_fail(self):
        self.output["affected_entities"]["item_ids"] = [f"{ORDER_ID}:1"]
        result = verify(self.output, self.ctx, check_csv=False)
        self.assertFalse(result.passed)


class TestTrace(unittest.TestCase):
    """2D.6 - trace.jsonl: 1 dong/case, ghi de chu khong append."""

    def setUp(self):
        self.ctx = build_ctx()
        self.output = build_output()
        self.verification = verify(self.output, self.ctx, check_csv=False)
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _record(self, case_id: str = "EC_001") -> dict:
        recorder = TraceRecorder(case_id, ORDER_ID)
        for agent in ("order_seller_agent", "delivery_agent", "payment_agent", "policy_agent"):
            with recorder.step(agent) as step:
                step["summary"] = {"agent": agent}
        return recorder.build_record(self.output, self.verification)

    def test_record_has_required_fields(self):
        record = self._record()
        for key in ("case_id", "handoff_steps", "primary_issue", "confidence", "verifier_pass"):
            self.assertIn(key, record)
        self.assertEqual(record["case_id"], "EC_001")
        self.assertEqual(record["primary_issue"], "late_delivery_seller")
        self.assertEqual(record["confidence"], 0.95)
        self.assertTrue(record["verifier_pass"])
        self.assertEqual(len(record["handoff_steps"]), 4)
        self.assertEqual([s["step"] for s in record["handoff_steps"]], [1, 2, 3, 4])

    def test_failed_step_is_recorded_and_reraised(self):
        recorder = TraceRecorder("EC_002", ORDER_ID)
        with self.assertRaises(ValueError):
            with recorder.step("payment_agent"):
                raise ValueError("boom")
        self.assertEqual(recorder.steps[0]["status"], "error")
        self.assertIn("boom", recorder.steps[0]["error"])

    def test_writer_overwrites_previous_run(self):
        write_trace([self._record("EC_001"), self._record("EC_002")], self.path, mirrors=())
        write_trace([self._record("EC_003")], self.path, mirrors=())
        records = read_trace(self.path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["case_id"], "EC_003")

    def test_one_json_line_per_case(self):
        with TraceWriter(self.path, mirrors=()) as writer:
            for case_id in ("EC_001", "EC_002", "EC_003"):
                writer.write(self._record(case_id))
        lines = self.path.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 3)
        self.assertEqual([json.loads(line)["case_id"] for line in lines],
                         ["EC_001", "EC_002", "EC_003"])

    def test_error_record_marks_verifier_fail(self):
        record = TraceRecorder("EC_050", ORDER_ID).build_record(error="RuntimeError: x")
        self.assertFalse(record["verifier_pass"])
        self.assertEqual(record["error"], "RuntimeError: x")


class TestEvidenceSelection(unittest.TestCase):
    """run_batch.select_evidence phai luon nam trong gioi han cua verifier."""

    def test_selection_respects_limits(self):
        from run_batch import assemble_output, select_evidence

        ctx = build_ctx()
        ctx.items = [
            OrderItemInfo(ORDER_ID, i, f"PROD{i}", f"SELLER{i}", "2018-01-05 10:00:00", 10.0, 2.0)
            for i in range(1, 9)
        ]
        ctx.item_ids = [f"{ORDER_ID}:{i}" for i in range(1, 9)]
        ctx.seller_ids = [f"SELLER{i}" for i in range(1, 9)]
        ctx.payments = [PaymentInfo(ORDER_ID, i, "credit_card", 1, 12.0) for i in range(1, 9)]
        ctx.compute_totals()
        ctx.root_cause = "SELLER_HANDOFF_AFTER_LIMIT"
        ctx.primary_issue = "late_delivery_seller"

        evidence = select_evidence(ctx, {"late_item_ids": [], "late_seller_ids": []})
        self.assertLessEqual(len(evidence), 10)
        self.assertEqual(len(set(evidence)), len(evidence))
        self.assertIn(f"order:{ORDER_ID}", evidence)
        self.assertIn("policy:SELLER_HANDOFF_AFTER_LIMIT", evidence)
        for prefix in ("item", "payment", "seller"):
            count = sum(1 for e in evidence if e.startswith(prefix + ":"))
            self.assertLessEqual(count, 5)
            self.assertGreaterEqual(count, 1)

        output = assemble_output(ctx, {"late_item_ids": [], "late_seller_ids": []})
        for name in ("order_ids", "item_ids", "seller_ids", "payment_ids"):
            self.assertLessEqual(len(output["affected_entities"][name]), 5)

    def test_late_seller_evidence_is_prioritized(self):
        from run_batch import select_evidence

        ctx = build_ctx()
        ctx.items = [
            OrderItemInfo(ORDER_ID, 1, "PROD1", "SELLER_A", "2018-01-05 10:00:00", 10.0, 2.0),
            OrderItemInfo(ORDER_ID, 2, "PROD2", "SELLER_B", "2018-01-05 10:00:00", 10.0, 2.0),
        ]
        ctx.item_ids = [f"{ORDER_ID}:1", f"{ORDER_ID}:2"]
        ctx.seller_ids = ["SELLER_A", "SELLER_B"]
        ctx.root_cause = "SELLER_HANDOFF_AFTER_LIMIT"

        delivery = {"late_item_ids": [f"{ORDER_ID}:2"], "late_seller_ids": ["SELLER_B"]}
        evidence = select_evidence(ctx, delivery)
        items = [e for e in evidence if e.startswith("item:")]
        sellers = [e for e in evidence if e.startswith("seller:")]
        self.assertEqual(items[0], f"item:{ORDER_ID}:2")
        self.assertEqual(sellers[0], "seller:SELLER_B")


if __name__ == "__main__":
    unittest.main(verbosity=2)
