import config
from schema import CaseContext

def analyze_payment(ctx: CaseContext) -> dict:
    """
    Analyzes payment information for a case.
    Updates ctx with payment analysis results and returns a signals dictionary.
    """
    # Ensure totals are computed
    ctx.compute_totals()
    
    # Check for split payment
    is_split_payment = len(ctx.payments) >= 2
    is_valid_match = ctx.payment_mismatch <= config.PAYMENT_TOLERANCE_BRL
    
    ctx.has_split_payment = is_split_payment and is_valid_match
    
    # Generate payment evidence IDs
    payment_evidences = []
    for payment in ctx.payments:
        evidence_id = config.EVIDENCE_ID_FORMATS["payment"].format(
            order_id=payment.order_id, 
            payment_sequential=payment.payment_sequential
        )
        payment_evidences.append(evidence_id)
        if evidence_id not in ctx.evidence_ids:
            ctx.evidence_ids.append(evidence_id)
        
    return {
        "payment_total": ctx.payment_total,
        "item_total": ctx.item_total,
        "freight_total": ctx.freight_total,
        "payment_mismatch": ctx.payment_mismatch,
        "is_valid_match": is_valid_match,
        "is_split_payment": is_split_payment,
        "valid_split_payment": ctx.has_split_payment,
        "payment_evidences": payment_evidences
    }
