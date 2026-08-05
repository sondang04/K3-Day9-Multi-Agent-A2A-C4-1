"""
test_data_loader.py - Test Phase 1: Schema & Data Loader
Run with: python test_data_loader.py
"""

import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from data_loader import get_loader, reset_loader
from schema import CaseContext


def test_data_loader():
    """Test all Phase 1 deliverables"""
    print("=" * 60)
    print("Phase 1: Schema & Data Loader Test")
    print("=" * 60)

    # Reset and load
    reset_loader()
    loader = get_loader()

    # Test 1: Load all CSVs
    print("\n[Test 1] Loading all CSV files...")
    print(f"  Orders: {len(loader._orders)}")
    print(f"  Order Items: {sum(len(v) for v in loader._order_items.values())}")
    print(f"  Payments: {sum(len(v) for v in loader._payments.values())}")
    print(f"  Sellers: {len(loader._sellers)}")
    print(f"  Customers: {len(loader._customers)}")
    print(f"  Reviews: {sum(len(v) for v in loader._reviews.values())}")
    print(f"  Products: {len(loader._products)}")
    assert len(loader._orders) > 0, "No orders loaded!"
    assert len(loader._sellers) > 0, "No sellers loaded!"
    print("  [PASS] All CSVs loaded successfully")

    # Test 2: O(1) lookup
    print("\n[Test 2] O(1) Lookup Performance...")
    first_order_id = list(loader._orders.keys())[0]
    import time
    start = time.time()
    for _ in range(10000):
        _ = loader.get_order(first_order_id)
        _ = loader.get_order_items(first_order_id)
        _ = loader.get_payments(first_order_id)
    elapsed = time.time() - start
    print(f"  10,000 lookups in {elapsed:.3f}s ({elapsed/10000*1000:.4f}ms each)")
    assert elapsed < 1.0, "Lookup too slow!"
    print("  [PASS] O(1) lookup verified")

    # Test 3: Build CaseContext with sample order
    print("\n[Test 3] Build CaseContext...")
    sample_order_id = first_order_id

    # Create mock case data
    case_data = {
        "case_id": "EC_TEST_001",
        "opened_at": "2018-10-18T00:00:00-03:00",
        "customer_request": {
            "language": "vi",
            "message": "Test case for data loader",
            "claimed_order_id": sample_order_id
        },
        "policy_version": "EC_POLICY_V1"
    }

    ctx = loader.build_case_context(case_data)

    print(f"  Case ID: {ctx.case_id}")
    print(f"  Order ID: {ctx.claimed_order_id}")
    print(f"  Order Status: {ctx.order_status}")
    print(f"  Items: {len(ctx.items)}")
    print(f"  Sellers: {len(ctx.sellers)}")
    print(f"  Payments: {len(ctx.payments)}")
    print(f"  Item IDs: {ctx.item_ids[:3]}...")
    print(f"  Seller IDs: {ctx.seller_ids[:3]}...")

    # Verify computed fields
    print(f"\n  Computed Financials:")
    print(f"    item_total: {ctx.item_total:.2f} BRL")
    print(f"    freight_total: {ctx.freight_total:.2f} BRL")
    print(f"    payment_total: {ctx.payment_total:.2f} BRL")
    print(f"    payment_mismatch: {ctx.payment_mismatch:.2f} BRL")
    print(f"    has_split_payment: {ctx.has_split_payment}")

    # Verify evidence IDs format
    print(f"\n  Evidence ID format check:")
    for item in ctx.items[:1]:
        item_key = ctx.get_order_item_key(item)
        print(f"    item: {item_key}")
        assert ":" in item_key, "Invalid item key format"
    for payment in ctx.payments[:1]:
        payment_key = ctx.get_payment_key(payment)
        print(f"    payment: {payment_key}")
        assert ":" in payment_key, "Invalid payment key format"

    print("  [PASS] CaseContext built successfully")

    # Test 4: CaseContext with order having no items
    print("\n[Test 4] Edge case: Order without items...")
    # Find an order with no items (unavailable/canceled orders might have no items)
    orders_no_items = [oid for oid, items in loader._order_items.items() if len(items) == 0]
    if orders_no_items:
        test_order_id = orders_no_items[0]
        case_data_no_items = {
            "case_id": "EC_TEST_002",
            "opened_at": "2018-10-18T00:00:00-03:00",
            "customer_request": {
                "language": "vi",
                "message": "Order possibly without items",
                "claimed_order_id": test_order_id
            },
            "policy_version": "EC_POLICY_V1"
        }
        ctx2 = loader.build_case_context(case_data_no_items)
        print(f"  Order: {test_order_id}")
        print(f"  Items: {len(ctx2.items)}")
        print(f"  item_total: {ctx2.item_total}")
        print(f"  freight_total: {ctx2.freight_total}")
        assert ctx2.item_total == 0.0, "Empty order should have 0 item_total"
        assert ctx2.freight_total == 0.0, "Empty order should have 0 freight_total"
        print("  [PASS] Edge case handled correctly")
    else:
        print("  [SKIP] No orders without items found, skipping")

    # Test 5: Schema validation
    print("\n[Test 5] Schema validation...")
    assert isinstance(ctx.case_id, str), "case_id should be str"
    assert isinstance(ctx.claimed_order_id, str), "claimed_order_id should be str"
    assert isinstance(ctx.item_total, float), "item_total should be float"
    assert isinstance(ctx.items, list), "items should be list"
    assert isinstance(ctx.sellers, dict), "sellers should be dict"
    print("  [PASS] Schema validation passed")

    print("=" * 60)
    print("Phase 1 Test: ALL PASSED!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    try:
        success = test_data_loader()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
