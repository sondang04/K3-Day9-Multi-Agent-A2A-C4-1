"""Focused unit tests for Person B agents.

The project-wide DataLoader eagerly materializes all nine large Olist tables.
For fast unit tests, this module loads only rows belonging to EC_001, EC_010,
and EC_025 while still constructing the official CaseContext schema.

Run with: python test_person_b.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from delivery_agent import analyze_delivery
from order_seller_agent import analyze_order_seller
from schema import CaseContext, OrderInfo, OrderItemInfo, SellerInfo

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CASE_IDS = ("EC_001", "EC_010", "EC_025")


def _case_data(case_id: str) -> dict:
    with open(ROOT / "input" / f"{case_id}.json", encoding="utf-8") as f:
        return json.load(f)


def _target_orders() -> dict[str, dict]:
    cases = {case_id: _case_data(case_id) for case_id in CASE_IDS}
    return {
        data["customer_request"]["claimed_order_id"]: data
        for data in cases.values()
    }


def load_contexts() -> dict[str, CaseContext]:
    targets = _target_orders()
    contexts: dict[str, CaseContext] = {}

    for order_id, case in targets.items():
        request = case["customer_request"]
        contexts[order_id] = CaseContext(
            case_id=case["case_id"],
            opened_at=case["opened_at"],
            claimed_order_id=order_id,
            customer_message=request["message"],
            language=request["language"],
            policy_version=case["policy_version"],
        )

    with open(DATA / "olist_orders_dataset.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            order_id = row["order_id"]
            if order_id not in contexts:
                continue
            ctx = contexts[order_id]
            ctx.order = OrderInfo(
                order_id=order_id,
                customer_id=row["customer_id"],
                order_status=row["order_status"],
                order_purchase_timestamp=row["order_purchase_timestamp"] or None,
                order_approved_at=row["order_approved_at"] or None,
                order_delivered_carrier_date=row["order_delivered_carrier_date"] or None,
                order_delivered_customer_date=row["order_delivered_customer_date"] or None,
                order_estimated_delivery_date=row["order_estimated_delivery_date"] or None,
            )
            ctx.order_status = ctx.order.order_status

    with open(DATA / "olist_order_items_dataset.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            order_id = row["order_id"]
            if order_id not in contexts:
                continue
            contexts[order_id].items.append(
                OrderItemInfo(
                    order_id=order_id,
                    order_item_id=int(row["order_item_id"]),
                    product_id=row["product_id"],
                    seller_id=row["seller_id"],
                    shipping_limit_date=row["shipping_limit_date"],
                    price=float(row["price"]),
                    freight_value=float(row["freight_value"]),
                )
            )

    target_sellers = {item.seller_id for ctx in contexts.values() for item in ctx.items}
    with open(DATA / "olist_sellers_dataset.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            seller_id = row["seller_id"]
            if seller_id not in target_sellers:
                continue
            seller = SellerInfo(
                seller_id=seller_id,
                seller_zip_code_prefix=row["seller_zip_code_prefix"],
                seller_city=row["seller_city"],
                seller_state=row["seller_state"],
            )
            for ctx in contexts.values():
                if any(item.seller_id == seller_id for item in ctx.items):
                    ctx.sellers[seller_id] = seller

    return contexts


def validate_case(ctx: CaseContext) -> None:
    order_signals = analyze_order_seller(ctx)
    delivery_signals = analyze_delivery(ctx)

    assert ctx.order is not None, f"Missing order data for {ctx.case_id}"
    assert order_signals["order_status"] == ctx.order.order_status
    assert order_signals["item_ids"] == [ctx.get_order_item_key(x) for x in ctx.items]
    assert order_signals["seller_ids"] == list(dict.fromkeys(x.seller_id for x in ctx.items))
    assert order_signals["multi_seller"] == (len(order_signals["seller_ids"]) > 1)

    assert set(delivery_signals["carrier_after_limit_by_item"]) == set(order_signals["item_ids"])
    assert delivery_signals["carrier_after_limit"] == any(
        delivery_signals["carrier_after_limit_by_item"].values()
    )

    assert f"order:{ctx.claimed_order_id}" in order_signals["evidence_ids"]
    assert f"order:{ctx.claimed_order_id}" in delivery_signals["evidence_ids"]
    for item_id in order_signals["item_ids"]:
        assert f"item:{item_id}" in order_signals["evidence_ids"]
    for seller_id in order_signals["seller_ids"]:
        assert f"seller:{seller_id}" in order_signals["evidence_ids"]

    print(
        ctx.case_id,
        {
            "order_status": order_signals["order_status"],
            "item_ids": order_signals["item_ids"],
            "seller_ids": order_signals["seller_ids"],
            "multi_seller": order_signals["multi_seller"],
            "carrier_after_limit_by_item": delivery_signals["carrier_after_limit_by_item"],
            "delivered_after_estimate": delivery_signals["delivered_after_estimate"],
            "late_seller_ids": delivery_signals["late_seller_ids"],
        },
    )


def main() -> None:
    contexts = load_contexts()
    by_case_id = {ctx.case_id: ctx for ctx in contexts.values()}
    for case_id in CASE_IDS:
        validate_case(by_case_id[case_id])
    print("[PASS] Person B tests passed for EC_001, EC_010, EC_025")


if __name__ == "__main__":
    main()
