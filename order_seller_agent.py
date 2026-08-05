"""Order and seller domain agent.

This module only derives order/item/seller signals from an already-built
:class:`schema.CaseContext`.  It does not apply refund policy.
"""

from __future__ import annotations

from typing import Any

from schema import CaseContext


def analyze_order_seller(ctx: CaseContext) -> dict[str, Any]:
    """Analyze order structure and seller participation.

    Returns deterministic, JSON-serializable signals for the coordinator.
    The function also synchronizes the corresponding computed fields on
    ``ctx`` so it remains compatible with the current project architecture.
    """
    order_status = ctx.order.order_status if ctx.order else ctx.order_status
    item_ids = [ctx.get_order_item_key(item) for item in ctx.items]
    seller_ids = list(dict.fromkeys(item.seller_id for item in ctx.items))
    multi_seller = len(seller_ids) > 1

    evidence_ids: list[str] = []
    if ctx.order is not None:
        evidence_ids.append(f"order:{ctx.order.order_id}")
    elif ctx.claimed_order_id:
        # Claimed IDs are not treated as verified order evidence when lookup
        # failed, therefore do not emit order evidence here.
        pass

    evidence_ids.extend(f"item:{item_id}" for item_id in item_ids)
    evidence_ids.extend(f"seller:{seller_id}" for seller_id in seller_ids)

    ctx.order_status = order_status
    ctx.item_ids = item_ids
    ctx.seller_ids = seller_ids

    return {
        "order_status": order_status,
        "item_ids": item_ids,
        "seller_ids": seller_ids,
        "multi_seller": multi_seller,
        "evidence_ids": evidence_ids,
    }
