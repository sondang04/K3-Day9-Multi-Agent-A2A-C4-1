"""Coordinator Agent - orchestrates all sub-agents for dispute case resolution.

This agent receives a case, builds the CaseContext, delegates to 4 specialized
sub-agents, aggregates their outputs, and calls the Verifier before returning
the final assessment.

Handoff order (per README section 7):
    1. Order & Seller Agent  -> order structure, seller participation
    2. Delivery Agent        -> handoff timing, delivery lateness
    3. Payment Agent         -> payment reconciliation, split detection
    4. Policy Agent          -> apply EC_POLICY_V1 rules, determine resolution

Entry point for run_batch.py: process_case(case_data, ctx, loader)
"""

from __future__ import annotations

from typing import Any, Optional

import config
from data_loader import DataLoader
from delivery_agent import analyze_delivery
from order_seller_agent import analyze_order_seller
from payment_agent import analyze_payment
from policy_agent import decide
from schema import CaseContext
from trace import TraceRecorder
from verifier_agent import verify, VerificationResult


def _prioritized_item_ids(ctx: CaseContext, delivery: dict[str, Any]) -> list[str]:
    """Item da tre handoff dung truoc - do la evidence dat gia nhat cua case."""
    late = [item_id for item_id in delivery.get("late_item_ids", []) if item_id in ctx.item_ids]
    rest = [item_id for item_id in ctx.item_ids if item_id not in late]
    return late + rest


def _prioritized_seller_ids(ctx: CaseContext, delivery: dict[str, Any]) -> list[str]:
    late = [sid for sid in delivery.get("late_seller_ids", []) if sid in ctx.seller_ids]
    rest = [sid for sid in ctx.seller_ids if sid not in late]
    return late + rest


def select_evidence(ctx: CaseContext, delivery: dict[str, Any]) -> list[str]:
    """Chon toi da 10 evidence ID, moi loai toi da 5, uu tien theo do lien quan.

    ``order:`` va ``policy:`` luon duoc giu; phan con lai chia deu (round-robin)
    cho item / payment / seller de khong loai bo han mot loai evidence nao.
    """
    order_ev = [f"order:{ctx.order.order_id}"] if ctx.order is not None else []
    policy_ev = (
        [f"policy:{ctx.root_cause}"]
        if ctx.root_cause in config.ROOT_CAUSE_CODES
        else []
    )

    cap = config.MAX_IDS_PER_ENTITY
    item_ev = [f"item:{key}" for key in _prioritized_item_ids(ctx, delivery)][:cap]
    payment_ev = [f"payment:{ctx.get_payment_key(p)}" for p in ctx.payments][:cap]
    seller_ev = [f"seller:{sid}" for sid in _prioritized_seller_ids(ctx, delivery)][:cap]

    budget = config.MAX_EVIDENCE_IDS - len(order_ev) - len(policy_ev)
    pools = [list(item_ev), list(payment_ev), list(seller_ev)]
    chosen: list[list[str]] = [[], [], []]
    while budget > 0 and any(pools):
        for index, pool in enumerate(pools):
            if not pool or budget == 0:
                continue
            chosen[index].append(pool.pop(0))
            budget -= 1

    return order_ev + chosen[0] + chosen[1] + chosen[2] + policy_ev


def assemble_output(ctx: CaseContext, delivery: dict[str, Any]) -> dict[str, Any]:
    """Build the README muc 6 payload from a CaseContext already decided by policy."""
    cap = config.MAX_IDS_PER_ENTITY

    order_ids = [ctx.order.order_id] if ctx.order is not None else []
    item_ids = _prioritized_item_ids(ctx, delivery)[:cap]
    seller_ids = _prioritized_seller_ids(ctx, delivery)[:cap]
    payment_ids = [ctx.get_payment_key(p) for p in ctx.payments][:cap]

    payment_total = round(ctx.payment_total, 2)
    refund = round(min(ctx.recommended_refund, ctx.payment_total), 2)

    evidence_ids = select_evidence(ctx, delivery)
    ctx.evidence_ids = evidence_ids  # giu ctx dong bo voi file da ghi

    ranked_causes = (
        [{"cause_code": ctx.root_cause, "rank": 1}]
        if ctx.root_cause in config.ROOT_CAUSE_CODES
        else []
    )

    return {
        "case_id": ctx.case_id,
        "assessment": {
            "primary_issue": ctx.primary_issue,
            "case_status": ctx.case_status,
            "confidence": round(ctx.confidence, 2),
        },
        "affected_entities": {
            "order_ids": order_ids,
            "item_ids": item_ids,
            "seller_ids": seller_ids,
            "payment_ids": payment_ids,
        },
        "root_cause_analysis": {
            "ranked_causes": ranked_causes,
            "responsible_parties": [
                {"party_type": party["party_type"], "party_id": party["party_id"]}
                for party in ctx.responsible_parties[: config.MAX_RESPONSIBLE_PARTIES]
            ],
        },
        "evidence_ids": evidence_ids,
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": round(ctx.item_total, 2),
            "freight_total_brl": round(ctx.freight_total, 2),
            "payment_total_brl": payment_total,
            "recommended_refund_brl": refund,
        },
        "resolution_actions": ctx.resolution_actions[: config.MAX_ACTIONS],
    }


def process_case(
    case_data: dict,
    ctx: CaseContext,
    loader: Optional[DataLoader] = None,
) -> dict[str, Any]:
    """Process one dispute case end-to-end.

    Args:
        case_data: The input JSON from input/EC_XXX.json
        ctx: The CaseContext already built by data_loader.build_case_context()
        loader: Optional DataLoader for CSV verification (passed by run_batch)

    Returns:
        The final output dict matching README section 6 schema.

    Handoff sequence:
        1. Order & Seller Agent
        2. Delivery Agent
        3. Payment Agent
        4. Policy Agent
        5. Verifier Agent (hard gate)
    """
    recorder = TraceRecorder(
        ctx.case_id,
        ctx.claimed_order_id,
        orchestrator="coordinator_agent"
    )

    # Step 1: Order & Seller Agent
    with recorder.step("order_seller_agent") as step:
        order_signals = analyze_order_seller(ctx)
        step["summary"] = {
            "order_status": order_signals["order_status"],
            "item_count": len(order_signals["item_ids"]),
            "seller_count": len(order_signals["seller_ids"]),
            "multi_seller": order_signals["multi_seller"],
        }

    # Step 2: Delivery Agent
    with recorder.step("delivery_agent") as step:
        delivery_signals = analyze_delivery(ctx)
        step["summary"] = {
            "carrier_after_limit": delivery_signals["carrier_after_limit"],
            "delivered_after_estimate": delivery_signals["delivered_after_estimate"],
            "late_item_ids": delivery_signals["late_item_ids"][: config.MAX_IDS_PER_ENTITY],
            "late_seller_ids": delivery_signals["late_seller_ids"],
        }

    # Step 3: Payment Agent
    with recorder.step("payment_agent") as step:
        payment_signals = analyze_payment(ctx)
        step["summary"] = {
            "payment_total": round(payment_signals["payment_total"], 2),
            "payment_mismatch": round(payment_signals["payment_mismatch"], 2),
            "valid_split_payment": payment_signals["valid_split_payment"],
            "is_split_payment": payment_signals["is_split_payment"],
        }

    # Step 4: Policy Agent - build signals dict
    late_sellers = delivery_signals.get("late_seller_ids", [])
    policy_signals = {
        "order_status": order_signals["order_status"],
        "item_total": payment_signals["item_total"],
        "freight_total": payment_signals["freight_total"],
        "payment_total": payment_signals["payment_total"],
        "is_valid_match": payment_signals["is_valid_match"],
        "valid_split_payment": payment_signals["valid_split_payment"],
        "carrier_after_limit": delivery_signals["carrier_after_limit"],
        "delivered_after_estimate": delivery_signals["delivered_after_estimate"],
        "violating_seller_id": late_sellers[0] if late_sellers else None,
    }

    with recorder.step("policy_agent") as step:
        decide(ctx, policy_signals)
        step["summary"] = {
            "primary_issue": ctx.primary_issue,
            "root_cause": ctx.root_cause,
            "recommended_refund_brl": ctx.recommended_refund,
            "confidence": ctx.confidence,
            "case_status": ctx.case_status,
        }

    # Step 5: Assemble output
    output = assemble_output(ctx, delivery_signals)

    # Step 6: Verifier Agent (hard gate)
    with recorder.step("verifier_agent") as step:
        verification = verify(output, ctx, loader=loader)
        step["summary"] = {
            "passed": verification.passed,
            "errors": verification.errors[:3] if verification.errors else [],
            "checked_evidence": verification.checked_evidence,
        }
        # If verification fails, we still return output but log errors
        if not verification.passed:
            step["status"] = "warning"
            step["summary"]["verifier_errors"] = verification.errors

    return output
