"""
data_loader.py - Load and cache Olist CSV data for fast O(1) lookups
Allows agents to retrieve order, item, payment, seller data by ID without full scans.
"""

import os
import pandas as pd
from pathlib import Path
from typing import Optional
from schema import (
    CaseContext, OrderInfo, OrderItemInfo, PaymentInfo,
    SellerInfo, CustomerInfo, ReviewInfo, ProductInfo
)


class DataLoader:
    """
    Loads all 9 Olist CSV files and provides O(1) lookup by various IDs.
    Implements singleton-like caching to avoid reloading on every case.
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)

        # Lookup dictionaries
        self._orders: dict[str, OrderInfo] = {}
        self._order_items: dict[str, list[OrderItemInfo]] = {}  # order_id -> list
        self._payments: dict[str, list[PaymentInfo]] = {}  # order_id -> list
        self._sellers: dict[str, SellerInfo] = {}
        self._customers: dict[str, CustomerInfo] = {}
        self._reviews: dict[str, list[ReviewInfo]] = {}  # order_id -> list
        self._products: dict[str, ProductInfo] = {}
        self._geolocation: dict[int, dict] = {}

        self._loaded = False

    def load_all(self):
        """Load all CSV files into memory. Call once at startup."""
        if self._loaded:
            return

        print("Loading Olist datasets...")

        # Load customers
        customers_df = pd.read_csv(self.data_dir / "olist_customers_dataset.csv")
        for _, row in customers_df.iterrows():
            customer = CustomerInfo(
                customer_id=str(row["customer_id"]),
                customer_unique_id=str(row["customer_unique_id"]),
                customer_zip_code_prefix=str(row["customer_zip_code_prefix"]),
                customer_city=str(row["customer_city"]),
                customer_state=str(row["customer_state"])
            )
            self._customers[customer.customer_id] = customer
        print(f"  Loaded {len(self._customers)} customers")

        # Load orders
        orders_df = pd.read_csv(self.data_dir / "olist_orders_dataset.csv")
        for _, row in orders_df.iterrows():
            order = OrderInfo(
                order_id=str(row["order_id"]),
                customer_id=str(row["customer_id"]),
                order_status=str(row["order_status"]),
                order_purchase_timestamp=str(row["order_purchase_timestamp"]) if pd.notna(row["order_purchase_timestamp"]) else None,
                order_approved_at=str(row["order_approved_at"]) if pd.notna(row["order_approved_at"]) else None,
                order_delivered_carrier_date=str(row["order_delivered_carrier_date"]) if pd.notna(row["order_delivered_carrier_date"]) else None,
                order_delivered_customer_date=str(row["order_delivered_customer_date"]) if pd.notna(row["order_delivered_customer_date"]) else None,
                order_estimated_delivery_date=str(row["order_estimated_delivery_date"]) if pd.notna(row["order_estimated_delivery_date"]) else None
            )
            self._orders[order.order_id] = order
        print(f"  Loaded {len(self._orders)} orders")

        # Load order items
        order_items_df = pd.read_csv(self.data_dir / "olist_order_items_dataset.csv")
        for _, row in order_items_df.iterrows():
            item = OrderItemInfo(
                order_id=str(row["order_id"]),
                order_item_id=int(row["order_item_id"]),
                product_id=str(row["product_id"]),
                seller_id=str(row["seller_id"]),
                shipping_limit_date=str(row["shipping_limit_date"]),
                price=float(row["price"]),
                freight_value=float(row["freight_value"])
            )
            if item.order_id not in self._order_items:
                self._order_items[item.order_id] = []
            self._order_items[item.order_id].append(item)
        print(f"  Loaded {len(order_items_df)} order items")

        # Load payments
        payments_df = pd.read_csv(self.data_dir / "olist_order_payments_dataset.csv")
        for _, row in payments_df.iterrows():
            payment = PaymentInfo(
                order_id=str(row["order_id"]),
                payment_sequential=int(row["payment_sequential"]),
                payment_type=str(row["payment_type"]),
                payment_installments=int(row["payment_installments"]),
                payment_value=float(row["payment_value"])
            )
            if payment.order_id not in self._payments:
                self._payments[payment.order_id] = []
            self._payments[payment.order_id].append(payment)
        print(f"  Loaded {len(payments_df)} payments")

        # Load sellers
        sellers_df = pd.read_csv(self.data_dir / "olist_sellers_dataset.csv")
        for _, row in sellers_df.iterrows():
            seller = SellerInfo(
                seller_id=str(row["seller_id"]),
                seller_zip_code_prefix=str(row["seller_zip_code_prefix"]),
                seller_city=str(row["seller_city"]),
                seller_state=str(row["seller_state"])
            )
            self._sellers[seller.seller_id] = seller
        print(f"  Loaded {len(self._sellers)} sellers")

        # Load reviews
        reviews_df = pd.read_csv(self.data_dir / "olist_order_reviews_dataset.csv")
        for _, row in reviews_df.iterrows():
            review = ReviewInfo(
                review_id=str(row["review_id"]),
                order_id=str(row["order_id"]),
                review_score=int(row["review_score"]) if pd.notna(row["review_score"]) else 0,
                review_comment_title=str(row["review_comment_title"]) if pd.notna(row["review_comment_title"]) else None,
                review_comment_message=str(row["review_comment_message"]) if pd.notna(row["review_comment_message"]) else None,
                review_creation_date=str(row["review_creation_date"]) if pd.notna(row["review_creation_date"]) else None,
                review_answer_timestamp=str(row["review_answer_timestamp"]) if pd.notna(row["review_answer_timestamp"]) else None
            )
            if review.order_id not in self._reviews:
                self._reviews[review.order_id] = []
            self._reviews[review.order_id].append(review)
        print(f"  Loaded {len(reviews_df)} reviews")

        # Load products
        products_df = pd.read_csv(self.data_dir / "olist_products_dataset.csv")
        for _, row in products_df.iterrows():
            product = ProductInfo(
                product_id=str(row["product_id"]),
                product_category_name=str(row["product_category_name"]) if pd.notna(row["product_category_name"]) else "",
                product_name_lenght=int(row["product_name_lenght"]) if pd.notna(row["product_name_lenght"]) else 0,
                product_description_lenght=int(row["product_description_lenght"]) if pd.notna(row["product_description_lenght"]) else 0,
                product_photos_qty=int(row["product_photos_qty"]) if pd.notna(row["product_photos_qty"]) else 0,
                product_weight_g=int(row["product_weight_g"]) if pd.notna(row["product_weight_g"]) else 0,
                product_length_cm=int(row["product_length_cm"]) if pd.notna(row["product_length_cm"]) else 0,
                product_height_cm=int(row["product_height_cm"]) if pd.notna(row["product_height_cm"]) else 0,
                product_width_cm=int(row["product_width_cm"]) if pd.notna(row["product_width_cm"]) else 0
            )
            self._products[product.product_id] = product
        print(f"  Loaded {len(self._products)} products")

        self._loaded = True
        print("All datasets loaded successfully!")

    def get_order(self, order_id: str) -> Optional[OrderInfo]:
        """Get order by order_id - O(1)"""
        return self._orders.get(order_id)

    def get_order_items(self, order_id: str) -> list[OrderItemInfo]:
        """Get all items for an order - O(1)"""
        return self._order_items.get(order_id, [])

    def get_payments(self, order_id: str) -> list[PaymentInfo]:
        """Get all payments for an order - O(1)"""
        return self._payments.get(order_id, [])

    def get_seller(self, seller_id: str) -> Optional[SellerInfo]:
        """Get seller by seller_id - O(1)"""
        return self._sellers.get(seller_id)

    def get_customer(self, customer_id: str) -> Optional[CustomerInfo]:
        """Get customer by customer_id - O(1)"""
        return self._customers.get(customer_id)

    def get_reviews(self, order_id: str) -> list[ReviewInfo]:
        """Get all reviews for an order - O(1)"""
        return self._reviews.get(order_id, [])

    def get_product(self, product_id: str) -> Optional[ProductInfo]:
        """Get product by product_id - O(1)"""
        return self._products.get(product_id)

    def build_case_context(self, case_data: dict) -> CaseContext:
        """
        Build complete CaseContext from case input data.
        Loads all related entities in O(1) per entity type.
        """
        case_id = case_data["case_id"]
        claimed_order_id = case_data["customer_request"]["claimed_order_id"]

        ctx = CaseContext(
            case_id=case_id,
            opened_at=case_data["opened_at"],
            claimed_order_id=claimed_order_id,
            customer_message=case_data["customer_request"]["message"],
            language=case_data["customer_request"]["language"],
            policy_version=case_data["policy_version"]
        )

        # Load order
        ctx.order = self.get_order(claimed_order_id)
        if ctx.order:
            ctx.order_status = ctx.order.order_status

            # Load customer
            ctx.customer = self.get_customer(ctx.order.customer_id)

            # Load items
            ctx.items = self.get_order_items(claimed_order_id)
            ctx.item_ids = [ctx.get_order_item_key(item) for item in ctx.items]

            # Load sellers
            for item in ctx.items:
                if item.seller_id not in ctx.sellers:
                    seller = self.get_seller(item.seller_id)
                    if seller:
                        ctx.sellers[item.seller_id] = seller
            ctx.seller_ids = list(ctx.sellers.keys())

            # Load payments
            ctx.payments = self.get_payments(claimed_order_id)
            ctx.has_split_payment = len(ctx.payments) >= 2

            # Load reviews
            ctx.reviews = self.get_reviews(claimed_order_id)

            # Load products
            for item in ctx.items:
                if item.product_id not in ctx.products:
                    product = self.get_product(item.product_id)
                    if product:
                        ctx.products[item.product_id] = product

            # Compute financials
            ctx.compute_totals()

        return ctx


# Global singleton instance
_loader: Optional[DataLoader] = None


def get_loader(data_dir: str = "data") -> DataLoader:
    """Get or create global DataLoader instance"""
    global _loader
    if _loader is None:
        _loader = DataLoader(data_dir)
        _loader.load_all()
    return _loader


def reset_loader():
    """Reset global loader - useful for testing"""
    global _loader
    _loader = None
