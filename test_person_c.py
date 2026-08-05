import unittest
from schema import CaseContext, OrderInfo, OrderItemInfo, PaymentInfo
from payment_agent import analyze_payment
from policy_agent import decide

class TestPersonC(unittest.TestCase):
    def setUp(self):
        self.ctx = CaseContext(
            case_id="EC_TEST",
            opened_at="2018-10-18T00:00:00-03:00",
            claimed_order_id="TEST_ORDER",
            customer_message="Test message",
            language="vi",
            policy_version="EC_POLICY_V1"
        )
        self.ctx.order = OrderInfo(
            order_id="TEST_ORDER", customer_id="CUST1", order_status="delivered",
            order_purchase_timestamp="2018-01-01", order_approved_at="2018-01-01",
            order_delivered_carrier_date="2018-01-02", order_delivered_customer_date="2018-01-10",
            order_estimated_delivery_date="2018-01-12"
        )
        self.ctx.order_status = "delivered"
        self.ctx.items = [
            OrderItemInfo("TEST_ORDER", 1, "PROD1", "SELL1", "2018-01-05", 100.0, 15.0)
        ]
        self.ctx.seller_ids = ["SELL1"]
        self.ctx.payments = [
            PaymentInfo("TEST_ORDER", 1, "credit_card", 1, 115.0)
        ]

    def test_payment_agent_normal(self):
        signals = analyze_payment(self.ctx)
        self.assertEqual(signals["payment_total"], 115.0)
        self.assertEqual(signals["item_total"], 100.0)
        self.assertEqual(signals["freight_total"], 15.0)
        self.assertTrue(signals["is_valid_match"])
        self.assertFalse(signals["valid_split_payment"])
        self.assertIn("payment:TEST_ORDER:1", signals["payment_evidences"])

    def test_payment_agent_split(self):
        self.ctx.payments = [
            PaymentInfo("TEST_ORDER", 1, "voucher", 1, 50.0),
            PaymentInfo("TEST_ORDER", 2, "credit_card", 1, 65.0)
        ]
        signals = analyze_payment(self.ctx)
        self.assertTrue(signals["valid_split_payment"])

    def test_policy_rule1_canceled_order_paid(self):
        self.ctx.order_status = "canceled"
        signals = analyze_payment(self.ctx)
        decide(self.ctx, signals)
        self.assertEqual(self.ctx.primary_issue, "canceled_order_paid")
        self.assertEqual(self.ctx.root_cause, "ORDER_CANCELED_AFTER_PAYMENT")
        self.assertEqual(self.ctx.recommended_refund, 115.0)
        self.assertEqual(self.ctx.resolution_actions, ["issue_full_refund"])
        self.assertIn("policy:ORDER_CANCELED_AFTER_PAYMENT", self.ctx.evidence_ids)

    def test_policy_rule2_unavailable_order_paid(self):
        self.ctx.order_status = "unavailable"
        signals = analyze_payment(self.ctx)
        decide(self.ctx, signals)
        self.assertEqual(self.ctx.primary_issue, "unavailable_order_paid")
        self.assertEqual(self.ctx.root_cause, "ORDER_UNAVAILABLE_AFTER_PAYMENT")
        self.assertEqual(self.ctx.recommended_refund, 115.0)
        self.assertEqual(self.ctx.resolution_actions, ["issue_full_refund"])

    def test_policy_rule3_late_delivery_seller(self):
        signals = analyze_payment(self.ctx)
        signals["delivered_after_estimate"] = True
        signals["carrier_after_limit"] = True
        signals["violating_seller_id"] = "SELL1"
        decide(self.ctx, signals)
        self.assertEqual(self.ctx.primary_issue, "late_delivery_seller")
        self.assertEqual(self.ctx.root_cause, "SELLER_HANDOFF_AFTER_LIMIT")
        self.assertEqual(self.ctx.recommended_refund, 15.0)
        self.assertEqual(self.ctx.resolution_actions, ["refund_freight"])

    def test_policy_rule4_late_delivery_logistics(self):
        signals = analyze_payment(self.ctx)
        signals["delivered_after_estimate"] = True
        signals["carrier_after_limit"] = False
        decide(self.ctx, signals)
        self.assertEqual(self.ctx.primary_issue, "late_delivery_logistics")
        self.assertEqual(self.ctx.root_cause, "CARRIER_DELIVERED_AFTER_ESTIMATE")
        self.assertEqual(self.ctx.recommended_refund, 15.0)
        self.assertEqual(self.ctx.resolution_actions, ["refund_freight"])

    def test_policy_rule5_valid_split_payment(self):
        self.ctx.payments = [
            PaymentInfo("TEST_ORDER", 1, "voucher", 1, 50.0),
            PaymentInfo("TEST_ORDER", 2, "credit_card", 1, 65.0)
        ]
        signals = analyze_payment(self.ctx)
        signals["delivered_after_estimate"] = False
        decide(self.ctx, signals)
        self.assertEqual(self.ctx.primary_issue, "valid_split_payment")
        self.assertEqual(self.ctx.root_cause, "MULTIPLE_PAYMENTS_RECONCILED")
        self.assertEqual(self.ctx.recommended_refund, 0.0)
        self.assertEqual(self.ctx.resolution_actions, ["explain_valid_split_payment"])

    def test_policy_rule6_unsupported_late_claim(self):
        signals = analyze_payment(self.ctx)
        signals["delivered_after_estimate"] = False
        decide(self.ctx, signals)
        self.assertEqual(self.ctx.primary_issue, "unsupported_late_claim")
        self.assertEqual(self.ctx.root_cause, "DELIVERY_WITHIN_ESTIMATE")
        self.assertEqual(self.ctx.recommended_refund, 0.0)
        self.assertEqual(self.ctx.resolution_actions, ["reject_late_refund"])

if __name__ == '__main__':
    unittest.main()
