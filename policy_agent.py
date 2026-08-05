import config
from schema import CaseContext

def decide(ctx: CaseContext, signals: dict) -> None:
    """
    Applies business rules to determine resolution.
    Updates ctx directly with decisions.
    """
    order_status = ctx.order_status or (ctx.order.order_status if ctx.order else None)
    payment_total = signals.get("payment_total", ctx.payment_total)
    
    # 1. canceled_order_paid
    if order_status == 'canceled' and payment_total > 0:
        _apply_decision(ctx, "canceled_order_paid", "ORDER_CANCELED_AFTER_PAYMENT", 
                       "platform", "OLIST_PLATFORM", "issue_full_refund", payment_total)
        return

    # 2. unavailable_order_paid
    if order_status == 'unavailable' and payment_total > 0:
        _apply_decision(ctx, "unavailable_order_paid", "ORDER_UNAVAILABLE_AFTER_PAYMENT", 
                       "platform", "OLIST_PLATFORM", "issue_full_refund", payment_total)
        return

    # Assuming delivery signals are either in ctx or signals
    delivered_after_estimate = signals.get("delivered_after_estimate", ctx.delivered_after_estimate)
    carrier_after_limit = signals.get("carrier_after_limit", ctx.carrier_after_limit)

    # If no items, freight_total is 0. 
    freight_total = signals.get("freight_total", ctx.freight_total)
    
    # 3. late_delivery_seller
    if delivered_after_estimate and carrier_after_limit:
        seller_id = signals.get("violating_seller_id")
        if not seller_id and ctx.seller_ids:
            seller_id = ctx.seller_ids[0]
            
        _apply_decision(ctx, "late_delivery_seller", "SELLER_HANDOFF_AFTER_LIMIT", 
                       "seller", seller_id, "refund_freight", freight_total)
        return

    # 4. late_delivery_logistics
    if delivered_after_estimate and not carrier_after_limit:
        _apply_decision(ctx, "late_delivery_logistics", "CARRIER_DELIVERED_AFTER_ESTIMATE", 
                       "logistics_provider", "LOGISTICS_PROVIDER", "refund_freight", freight_total)
        return

    # 5. valid_split_payment
    valid_split_payment = signals.get("valid_split_payment", ctx.has_split_payment)
    if valid_split_payment:
        _apply_decision(ctx, "valid_split_payment", "MULTIPLE_PAYMENTS_RECONCILED", 
                       None, None, "explain_valid_split_payment", 0.0)
        return

    # 6. unsupported_late_claim
    is_valid_match = signals.get("is_valid_match", ctx.payment_mismatch <= config.PAYMENT_TOLERANCE_BRL)
    if not delivered_after_estimate and is_valid_match:
        _apply_decision(ctx, "unsupported_late_claim", "DELIVERY_WITHIN_ESTIMATE", 
                       None, None, "reject_late_refund", 0.0)
        return
        
    # Default fallback if no rules match
    ctx.primary_issue = "unknown"
    ctx.case_status = "no_action"
    ctx.confidence = 0.5
    ctx.recommended_refund = 0.0


def _apply_decision(ctx: CaseContext, primary_issue: str, cause_code: str, 
                   party_type: str, party_id: str, action: str, refund: float):
    
    ctx.primary_issue = primary_issue
    ctx.root_cause = cause_code
    
    if party_type and party_id:
        ctx.responsible_parties = [{"party_type": party_type, "party_id": party_id}]
    else:
        ctx.responsible_parties = []
        
    ctx.resolution_actions = [action]
    ctx.recommended_refund = round(refund, 2)
    
    if ctx.recommended_refund > 0:
        ctx.case_status = "action_required"
    else:
        ctx.case_status = "no_action"
        
    # Calculate confidence based on rules
    if not ctx.has_items():
        ctx.confidence = 0.90
    elif ctx.has_split_payment or ctx.has_multiple_sellers():
        ctx.confidence = 0.85
    else:
        ctx.confidence = 0.95 # Clearly defined
        
    # Add policy evidence
    policy_evidence = config.EVIDENCE_ID_FORMATS["policy"].format(root_cause_code=cause_code)
    if policy_evidence not in ctx.evidence_ids:
        ctx.evidence_ids.append(policy_evidence)
