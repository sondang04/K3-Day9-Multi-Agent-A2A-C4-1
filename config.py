"""
Configuration file for Multi-Agent E-commerce Dispute Resolution
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logging"

# Model configuration - OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL_NAME = os.getenv("OPENROUTER_MODEL", "qwen/qwen3.5-9b")

# Ollama fallback (if using)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# Business rules thresholds
PAYMENT_TOLERANCE_BRL = 0.10

# Evidence ID format
EVIDENCE_ID_FORMATS = {
    "order": "order:{order_id}",
    "item": "item:{order_id}:{order_item_id}",
    "payment": "payment:{order_id}:{payment_sequential}",
    "seller": "seller:{seller_id}",
    "policy": "policy:{root_cause_code}"
}

# Root cause codes
ROOT_CAUSE_CODES = [
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE"
]

# Output schema limits
MAX_IDS_PER_ENTITY = 5
MAX_EVIDENCE_IDS = 10
MAX_ROOT_CAUSES = 3
MAX_RESPONSIBLE_PARTIES = 3
MAX_ACTIONS = 5
