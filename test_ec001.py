"""
test_ec001.py - Test Phase 1 with actual EC_001 case
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from data_loader import get_loader
from schema import CaseContext

# Load EC_001
with open("input/EC_001.json", encoding="utf-8") as f:
    case_data = json.load(f)

print(f"Testing EC_001 with claimed_order_id: {case_data['customer_request']['claimed_order_id']}")

loader = get_loader()
ctx = loader.build_case_context(case_data)

print(f"\n=== CaseContext Summary ===")
print(f"case_id: {ctx.case_id}")
print(f"order_id: {ctx.claimed_order_id}")
print(f"order_status: {ctx.order_status}")
print(f"item_count: {len(ctx.items)}")
print(f"seller_count: {len(ctx.sellers)}")
print(f"payment_count: {len(ctx.payments)}")

print(f"\n=== Financials ===")
print(f"item_total: {ctx.item_total:.2f} BRL")
print(f"freight_total: {ctx.freight_total:.2f} BRL")
print(f"payment_total: {ctx.payment_total:.2f} BRL")
print(f"payment_mismatch: {ctx.payment_mismatch:.2f} BRL")

print(f"\n=== Evidence IDs ===")
for item in ctx.items:
    print(f"  item:{ctx.get_order_item_key(item)}")
for payment in ctx.payments:
    print(f"  payment:{ctx.get_payment_key(payment)}")

if ctx.order:
    print(f"\n  order:{ctx.order.order_id}")
    print(f"  delivered_carrier: {ctx.order.order_delivered_carrier_date}")
    print(f"  estimated_delivery: {ctx.order.order_estimated_delivery_date}")

print("\n[PASS] EC_001 loaded successfully!")
