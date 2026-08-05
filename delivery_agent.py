"""Delivery timing agent for Olist dispute cases."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from schema import CaseContext


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse Olist timestamps safely.

    Olist CSV timestamps normally use ``YYYY-mm-dd HH:MM:SS``.  ``fromisoformat``
    also supports the ISO variants used elsewhere in this repository.
    """
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.lower() == "nan":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def analyze_delivery(ctx: CaseContext) -> dict[str, Any]:
    """Compute handoff and final-delivery lateness signals.

    ``carrier_after_limit_by_item`` is keyed by the canonical item ID
    ``<order_id>:<order_item_id>``.  An item is late at handoff only when both
    timestamps exist and the carrier received the order strictly after that
    item's ``shipping_limit_date``.
    """
    carrier_date = _parse_timestamp(
        ctx.order.order_delivered_carrier_date if ctx.order else None
    )
    customer_date = _parse_timestamp(
        ctx.order.order_delivered_customer_date if ctx.order else None
    )
    estimated_date = _parse_timestamp(
        ctx.order.order_estimated_delivery_date if ctx.order else None
    )

    carrier_after_limit_by_item: dict[str, bool] = {}
    late_item_ids: list[str] = []
    late_seller_ids: list[str] = []

    for item in ctx.items:
        item_id = ctx.get_order_item_key(item)
        limit_date = _parse_timestamp(item.shipping_limit_date)
        is_late = bool(carrier_date and limit_date and carrier_date > limit_date)
        carrier_after_limit_by_item[item_id] = is_late
        if is_late:
            late_item_ids.append(item_id)
            if item.seller_id not in late_seller_ids:
                late_seller_ids.append(item.seller_id)

    carrier_after_limit = any(carrier_after_limit_by_item.values())
    delivered_after_estimate = bool(
        customer_date and estimated_date and customer_date > estimated_date
    )

    evidence_ids: list[str] = []
    if ctx.order is not None:
        evidence_ids.append(f"order:{ctx.order.order_id}")
    evidence_ids.extend(f"item:{item_id}" for item_id in carrier_after_limit_by_item)
    evidence_ids.extend(f"seller:{seller_id}" for seller_id in late_seller_ids)

    ctx.carrier_after_limit = carrier_after_limit
    ctx.delivered_after_estimate = delivered_after_estimate

    return {
        "carrier_after_limit": carrier_after_limit,
        "carrier_after_limit_by_item": carrier_after_limit_by_item,
        "delivered_after_estimate": delivered_after_estimate,
        "late_item_ids": late_item_ids,
        "late_seller_ids": late_seller_ids,
        "evidence_ids": evidence_ids,
    }
