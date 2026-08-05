"""
schema.py - Data schemas for Multi-Agent E-commerce Dispute Resolution
Defines CaseContext dataclass and related structures used across all agents.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class OrderInfo:
    """Order information from olist_orders_dataset.csv"""
    order_id: str
    customer_id: str
    order_status: str
    order_purchase_timestamp: Optional[str]
    order_approved_at: Optional[str]
    order_delivered_carrier_date: Optional[str]
    order_delivered_customer_date: Optional[str]
    order_estimated_delivery_date: Optional[str]


@dataclass
class OrderItemInfo:
    """Order item information from olist_order_items_dataset.csv"""
    order_id: str
    order_item_id: int
    product_id: str
    seller_id: str
    shipping_limit_date: str
    price: float
    freight_value: float


@dataclass
class PaymentInfo:
    """Payment information from olist_order_payments_dataset.csv"""
    order_id: str
    payment_sequential: int
    payment_type: str
    payment_installments: int
    payment_value: float


@dataclass
class SellerInfo:
    """Seller information from olist_sellers_dataset.csv"""
    seller_id: str
    seller_zip_code_prefix: str
    seller_city: str
    seller_state: str


@dataclass
class CustomerInfo:
    """Customer information from olist_customers_dataset.csv"""
    customer_id: str
    customer_unique_id: str
    customer_zip_code_prefix: str
    customer_city: str
    customer_state: str


@dataclass
class ReviewInfo:
    """Review information from olist_order_reviews_dataset.csv"""
    review_id: str
    order_id: str
    review_score: int
    review_comment_title: Optional[str]
    review_comment_message: Optional[str]
    review_creation_date: Optional[str]
    review_answer_timestamp: Optional[str]


@dataclass
class ProductInfo:
    """Product information from olist_products_dataset.csv"""
    product_id: str
    product_category_name: str
    product_name_lenght: int
    product_description_lenght: int
    product_photos_qty: int
    product_weight_g: int
    product_length_cm: int
    product_height_cm: int
    product_width_cm: int


@dataclass
class CaseContext:
    """
    Complete context for a single case (EC_XXX).
    Aggregates all data needed by agents to make decisions.
    """
    case_id: str
    opened_at: str
    claimed_order_id: str
    customer_message: str
    language: str
    policy_version: str

    # Order data
    order: Optional[OrderInfo] = None

    # Related entities
    customer: Optional[CustomerInfo] = None
    items: list[OrderItemInfo] = field(default_factory=list)
    payments: list[PaymentInfo] = field(default_factory=list)
    sellers: dict[str, SellerInfo] = field(default_factory=dict)
    reviews: list[ReviewInfo] = field(default_factory=list)
    products: dict[str, ProductInfo] = field(default_factory=dict)

    # Computed fields (set by agents)
    order_status: Optional[str] = None
    item_ids: list[str] = field(default_factory=list)
    seller_ids: list[str] = field(default_factory=list)

    # Computed financials
    item_total: float = 0.0
    freight_total: float = 0.0
    payment_total: float = 0.0

    # Delivery analysis
    carrier_after_limit: bool = False
    delivered_after_estimate: bool = False

    # Payment analysis
    has_split_payment: bool = False
    payment_mismatch: float = 0.0  # |payment_total - (item_total + freight_total)|

    # Assessment results (set by Policy Agent)
    primary_issue: Optional[str] = None
    case_status: Optional[str] = None  # "action_required" or "no_action"
    confidence: float = 0.0
    root_cause: Optional[str] = None
    responsible_parties: list[dict] = field(default_factory=list)
    recommended_refund: float = 0.0
    resolution_actions: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)

    def get_order_item_key(self, item: OrderItemInfo) -> str:
        """Generate item ID in format: order_id:order_item_id"""
        return f"{item.order_id}:{item.order_item_id}"

    def get_payment_key(self, payment: PaymentInfo) -> str:
        """Generate payment ID in format: order_id:payment_sequential"""
        return f"{payment.order_id}:{payment.payment_sequential}"

    def compute_totals(self):
        """Compute item_total, freight_total, payment_total from loaded data"""
        self.item_total = sum(item.price for item in self.items)
        self.freight_total = sum(item.freight_value for item in self.items)
        self.payment_total = sum(payment.payment_value for payment in self.payments)
        self.payment_mismatch = abs(self.payment_total - (self.item_total + self.freight_total))

    def has_items(self) -> bool:
        """Check if order has any items"""
        return len(self.items) > 0

    def has_multiple_sellers(self) -> bool:
        """Check if order has items from multiple sellers"""
        return len(set(item.seller_id for item in self.items)) > 1
