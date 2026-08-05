# Multi-Agent E-commerce Dispute Resolution Architecture

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        COORDINATOR AGENT (A)                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  process_case(case_data, ctx, loader)                               │   │
│   │  - Orchestrates all sub-agents in sequence                         │   │
│   │  - Aggregates outputs from all agents                              │   │
│   │  - Calls Verifier before returning final output                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└──────────┬────────────┬─────────────┬─────────────┬─────────────┬───────────┘
           │            │             │             │             │
           ▼            ▼             ▼             ▼             ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   ORDER &    │ │   DELIVERY  │ │   PAYMENT   │ │   POLICY    │ │   VERIFIER  │
│   SELLER     │ │    AGENT    │ │    AGENT    │ │    AGENT    │ │    AGENT    │
│   AGENT (B)  │ │    (B)      │ │    (C)      │ │    (C)      │ │    (D)      │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

## 2. Agent Roles and Responsibilities

### 2.1 Coordinator Agent (Lead - Trần Đình Đăng)
- **File**: `coordinator_agent.py`
- **Entry Point**: `process_case(case_data, ctx, loader)`
- **Responsibilities**:
  - Receive case input from `run_batch.py`
  - Build/verify CaseContext
  - Orchestrate sub-agent execution in correct order
  - Aggregate signals and assemble final output
  - Call Verifier as hard gate
  - Record execution trace

### 2.2 Order & Seller Agent (Dương Mạnh Phong)
- **File**: `order_seller_agent.py`
- **Function**: `analyze_order_seller(ctx)`
- **Data Access**: `orders`, `order_items`, `sellers` (CSV)
- **Signals Produced**:
  - `order_status`: Current status of the order
  - `item_ids`: List of order item IDs in `<order_id>:<order_item_id>` format
  - `seller_ids`: Unique seller IDs for items in the order
  - `multi_seller`: Boolean indicating multiple sellers
  - `evidence_ids`: `order:<id>`, `item:<id>:<n>`, `seller:<id>`
- **Outputs to**: Policy Agent, Coordinator

### 2.3 Delivery Agent (Dương Mạnh Phong)
- **File**: `delivery_agent.py`
- **Function**: `analyze_delivery(ctx)`
- **Data Access**: `orders` (delivery timestamps)
- **Signals Produced**:
  - `carrier_after_limit`: Boolean - carrier received after shipping_limit_date
  - `carrier_after_limit_by_item`: Per-item handoff lateness
  - `delivered_after_estimate`: Boolean - customer delivery after estimated date
  - `late_item_ids`: Items with late handoff
  - `late_seller_ids`: Sellers responsible for late handoff
- **Outputs to**: Policy Agent, Coordinator

### 2.4 Payment Agent (Chu Thành Dũng)
- **File**: `payment_agent.py`
- **Function**: `analyze_payment(ctx)`
- **Data Access**: `order_payments` (CSV)
- **Signals Produced**:
  - `payment_total`: Sum of all payment values
  - `item_total`: Sum of item prices
  - `freight_total`: Sum of freight values
  - `payment_mismatch`: |payment_total - (item_total + freight_total)|
  - `is_valid_match`: Boolean - mismatch within tolerance (0.10 BRL)
  - `is_split_payment`: Boolean - 2+ payment rows
  - `valid_split_payment`: Boolean - split with valid match
  - `payment_evidences`: List of `payment:<order_id>:<sequential>`
- **Outputs to**: Policy Agent, Coordinator

### 2.5 Policy Agent (Chu Thành Dũng)
- **File**: `policy_agent.py`
- **Function**: `decide(ctx, signals)`
- **Policy Version**: EC_POLICY_V1
- **Rule Application Order** (from README Section 4):

| Priority | Primary Issue            | Condition                                           | Responsible    | Refund Basis  |
|----------|--------------------------|-----------------------------------------------------|----------------|---------------|
| 1        | canceled_order_paid       | status=canceled AND payment>0                       | platform       | payment_total |
| 2        | unavailable_order_paid    | status=unavailable AND payment>0                     | platform       | payment_total |
| 3        | late_delivery_seller     | delivered_after_estimate AND carrier_after_limit      | seller         | freight_total |
| 4        | late_delivery_logistics  | delivered_after_estimate AND NOT carrier_after_limit  | logistics      | freight_total |
| 5        | valid_split_payment      | 2+ payments AND mismatch≤0.10                       | none           | 0             |
| 6        | unsupported_late_claim   | NOT delivered_after_estimate AND valid_match         | none           | 0             |

- **Outputs**: `primary_issue`, `root_cause`, `responsible_parties`, `recommended_refund`, `resolution_actions`, `confidence`, `case_status`

### 2.6 Verifier Agent (Đặng Thái Nam Sơn)
- **File**: `verifier_agent.py`
- **Function**: `verify(output, ctx, loader)`
- **Responsibilities**:
  - Hard gate before writing output
  - Validate evidence IDs exist in CSV
  - Check schema compliance
  - Verify financial amounts
  - Validate mappings (primary_issue ↔ cause_code ↔ action ↔ party)
  - Check limits (≤5 IDs/entity, ≤10 evidence, ≤3 causes, ≤3 parties, ≤5 actions)
  - Validate confidence ∈ [0, 1]

## 3. Data Flow

```
Input (EC_XXX.json)
    │
    ▼
┌─────────────────┐
│   Data Loader   │
│ data_loader.py  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  CaseContext    │
│  (Schema)       │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    COORDINATOR AGENT                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │  Order &    │→ │  Delivery   │→ │   Payment   │           │
│  │  Seller     │  │   Agent     │  │   Agent     │           │
│  └─────────────┘  └─────────────┘  └──────┬──────┘           │
│                                            │                   │
│                                            ▼                   │
│                                     ┌─────────────┐            │
│                                     │   Policy    │            │
│                                     │   Agent     │            │
│                                     └──────┬──────┘            │
│                                            │                   │
│                                            ▼                   │
│                                     ┌─────────────┐            │
│                                     │  Verifier   │ ← HARD GATE│
│                                     │   Agent     │            │
│                                     └──────┬──────┘            │
└───────────────────────────────────────────┼────────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐
                                   │  Output (JSON)  │
                                   │  output/EC_XXX  │
                                   └─────────────────┘
```

## 4. Evidence ID Format

| Type     | Format                        | Example                    |
|----------|-------------------------------|----------------------------|
| Order    | `order:<order_id>`            | `order:abc123`             |
| Item     | `item:<order_id>:<order_item_id>` | `item:abc123:1`         |
| Payment  | `payment:<order_id>:<sequential>` | `payment:abc123:1`      |
| Seller   | `seller:<seller_id>`           | `seller:xyz456`            |
| Policy   | `policy:<root_cause_code>`     | `policy:SELLER_HANDOFF_AFTER_LIMIT` |

## 5. Root Cause Codes

| Code                              | Description                                    |
|-----------------------------------|------------------------------------------------|
| SELLER_HANDOFF_AFTER_LIMIT        | Seller handed off after shipping_limit_date    |
| CARRIER_DELIVERED_AFTER_ESTIMATE  | Carrier delivered after estimated date        |
| ORDER_CANCELED_AFTER_PAYMENT       | Order canceled after customer payment          |
| ORDER_UNAVAILABLE_AFTER_PAYMENT   | Order unavailable after customer payment       |
| MULTIPLE_PAYMENTS_RECONCILED      | Split payment reconciled                       |
| DELIVERY_WITHIN_ESTIMATE           | Delivery within estimated window               |

## 6. Resolution Actions

| Action                   | Description                              |
|--------------------------|------------------------------------------|
| issue_full_refund        | Refund entire payment amount             |
| refund_freight           | Refund only freight/shipping cost        |
| explain_valid_split_payment | Explain valid split payment             |
| reject_late_refund       | Reject late delivery claim              |

## 7. File Structure

```
K3-Day9-Multi-Agent-A2A-C4-1/
├── architecture.md           # This file
├── coordinator_agent.py      # Coordinator Agent (A)
├── data_loader.py            # CSV loader with O(1) lookups (A)
├── delivery_agent.py         # Delivery timing analysis (B)
├── order_seller_agent.py     # Order/seller analysis (B)
├── payment_agent.py          # Payment reconciliation (C)
├── policy_agent.py           # Business rule engine (C)
├── schema.py                 # Data schemas (A)
├── verifier_agent.py         # Output validation (D)
├── trace.py                  # Execution trace (D)
├── run_batch.py              # Batch runner (D)
├── config.py                 # Configuration
├── input/                    # 50 case inputs
│   ├── EC_001.json ... EC_050.json
├── output/                   # 50 case outputs
│   ├── EC_001.json ... EC_050.json
├── data/                     # 9 Olist CSV files
├── logging/                  # Execution logs
│   ├── trace.jsonl
│   └── verifier_report.json
├── trace.jsonl               # Execution trace (root)
└── individual_*.md           # Member reports
```

## 8. Execution Flow

### 8.1 Single Case Flow
1. `run_batch.py` loads case from `input/EC_XXX.json`
2. `data_loader.build_case_context()` creates `CaseContext`
3. `coordinator_agent.process_case()` orchestrates:
   - `order_seller_agent.analyze_order_seller()`
   - `delivery_agent.analyze_delivery()`
   - `payment_agent.analyze_payment()`
   - `policy_agent.decide()`
   - `verifier_agent.verify()` (hard gate)
4. Output written to `output/EC_XXX.json`
5. Trace recorded to `trace.jsonl`

### 8.2 Batch Execution
- `run_batch.py --pipeline coordinator` uses Coordinator Agent
- `run_batch.py --pipeline local` uses internal pipeline (no coordinator)
- All 50 cases processed sequentially
- Verifier report generated for any failures

## 9. Confidence Scoring

| Situation                              | Confidence |
|----------------------------------------|------------|
| Evidence clear, single seller/payment  | 0.95       |
| No items in order                      | 0.90       |
| Split payment or multi-seller          | 0.85       |
| Must infer from missing data           | 0.70       |

## 10. Integration Points

### Data Loader (A) → All Agents
- Provides `CaseContext` with pre-loaded order, items, payments, sellers
- O(1) lookups via `get_order()`, `get_order_items()`, etc.

### Agents → Policy Agent
- All agents return signals dict
- Policy Agent combines signals to apply rules

### Policy Agent → Coordinator
- Sets `ctx.primary_issue`, `ctx.root_cause`, `ctx.responsible_parties`, etc.

### Coordinator → Verifier
- Passes assembled output for validation

### Verifier → Coordinator
- Returns `VerificationResult` with errors/warnings
- Hard gate: if failed, case marked but still written
