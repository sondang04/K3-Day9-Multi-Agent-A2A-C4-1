"""Verifier Agent - final gate before an output JSON is written to disk.

The verifier never invents data.  It re-checks the coordinator output against
two independent sources:

1. the raw CSV rows reachable through :mod:`data_loader` (evidence / entity IDs
   must really exist), and
2. the :class:`schema.CaseContext` built for this case (amounts, entity scope).

Anything the verifier reports as an *error* is a hard gate: the case would lose
points in grading (false-positive evidence, broken schema, impossible amount).
*Warnings* are non-fatal hygiene notes.

Usage::

    from verifier_agent import verify

    result = verify(output_dict, ctx, loader=loader)
    if not result.passed:
        print(result.errors)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import config
from schema import CaseContext

# ---------------------------------------------------------------------------
# Allowed vocabularies (README muc 4 + muc 6)
# ---------------------------------------------------------------------------

CASE_STATUSES = {"action_required", "no_action"}
PARTY_TYPES = {"platform", "seller", "logistics_provider"}
CURRENCY = "BRL"

# primary_issue -> canonical cause code / action / responsible party.
# ``party_id`` is None when the ID depends on the case (the violating seller).
# ``refund_basis`` names the CaseContext total the refund must equal.
RULE_TABLE: dict[str, dict[str, Optional[str]]] = {
    "canceled_order_paid": {
        "cause_code": "ORDER_CANCELED_AFTER_PAYMENT",
        "action": "issue_full_refund",
        "party_type": "platform",
        "party_id": "OLIST_PLATFORM",
        "refund_basis": "payment_total",
    },
    "unavailable_order_paid": {
        "cause_code": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "action": "issue_full_refund",
        "party_type": "platform",
        "party_id": "OLIST_PLATFORM",
        "refund_basis": "payment_total",
    },
    "late_delivery_seller": {
        "cause_code": "SELLER_HANDOFF_AFTER_LIMIT",
        "action": "refund_freight",
        "party_type": "seller",
        "party_id": None,
        "refund_basis": "freight_total",
    },
    "late_delivery_logistics": {
        "cause_code": "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "action": "refund_freight",
        "party_type": "logistics_provider",
        "party_id": "LOGISTICS_PROVIDER",
        "refund_basis": "freight_total",
    },
    "valid_split_payment": {
        "cause_code": "MULTIPLE_PAYMENTS_RECONCILED",
        "action": "explain_valid_split_payment",
        "party_type": None,
        "party_id": None,
        "refund_basis": "zero",
    },
    "unsupported_late_claim": {
        "cause_code": "DELIVERY_WITHIN_ESTIMATE",
        "action": "reject_late_refund",
        "party_type": None,
        "party_id": None,
        "refund_basis": "zero",
    },
}

PRIMARY_ISSUES = set(RULE_TABLE)
RESOLUTION_ACTIONS = {rule["action"] for rule in RULE_TABLE.values()}

# Amounts are compared with a small tolerance: floats coming from pandas sums
# are not bit-exact against the 2-decimal values written to JSON.
MONEY_EPSILON = 0.01

_EVIDENCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "order": re.compile(r"^order:([0-9a-zA-Z_-]+)$"),
    "item": re.compile(r"^item:([0-9a-zA-Z_-]+):(\d+)$"),
    "payment": re.compile(r"^payment:([0-9a-zA-Z_-]+):(\d+)$"),
    "seller": re.compile(r"^seller:([0-9a-zA-Z_-]+)$"),
    "policy": re.compile(r"^policy:([A-Z_]+)$"),
}

_ENTITY_KEY_PATTERN = re.compile(r"^([0-9a-zA-Z_-]+):(\d+)$")


# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    """Outcome of one verification pass."""

    case_id: str
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked_evidence: int = 0
    checked_entities: int = 0

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.passed = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable summary (used by trace.py)."""
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checked_evidence": self.checked_evidence,
            "checked_entities": self.checked_entities,
        }

    def __bool__(self) -> bool:
        return self.passed


# ---------------------------------------------------------------------------
# Existence lookups (CSV first, CaseContext as fallback)
# ---------------------------------------------------------------------------


def _order_exists(order_id: str, ctx: CaseContext, loader) -> bool:
    if loader is not None:
        return loader.get_order(order_id) is not None
    return ctx.order is not None and ctx.order.order_id == order_id


def _item_exists(order_id: str, order_item_id: int, ctx: CaseContext, loader) -> bool:
    if loader is not None:
        items = loader.get_order_items(order_id)
    elif order_id == ctx.claimed_order_id:
        items = ctx.items
    else:
        items = []
    return any(item.order_item_id == order_item_id for item in items)


def _payment_exists(order_id: str, sequential: int, ctx: CaseContext, loader) -> bool:
    if loader is not None:
        payments = loader.get_payments(order_id)
    elif order_id == ctx.claimed_order_id:
        payments = ctx.payments
    else:
        payments = []
    return any(payment.payment_sequential == sequential for payment in payments)


def _seller_exists(seller_id: str, ctx: CaseContext, loader) -> bool:
    if loader is not None:
        return loader.get_seller(seller_id) is not None
    return seller_id in ctx.sellers or seller_id in ctx.seller_ids


# ---------------------------------------------------------------------------
# Typed field helpers
# ---------------------------------------------------------------------------


def _get_dict(parent: Any, key: str, path: str, result: VerificationResult) -> Optional[dict]:
    if not isinstance(parent, dict) or key not in parent:
        result.add_error(f"schema: thieu field '{path}'")
        return None
    value = parent[key]
    if not isinstance(value, dict):
        result.add_error(f"schema: '{path}' phai la object, nhan {type(value).__name__}")
        return None
    return value


def _get_str(parent: Any, key: str, path: str, result: VerificationResult) -> Optional[str]:
    if not isinstance(parent, dict) or key not in parent:
        result.add_error(f"schema: thieu field '{path}'")
        return None
    value = parent[key]
    if not isinstance(value, str):
        result.add_error(f"schema: '{path}' phai la string, nhan {type(value).__name__}")
        return None
    return value


def _get_number(parent: Any, key: str, path: str, result: VerificationResult) -> Optional[float]:
    if not isinstance(parent, dict) or key not in parent:
        result.add_error(f"schema: thieu field '{path}'")
        return None
    value = parent[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        result.add_error(f"schema: '{path}' phai la number, nhan {type(value).__name__}")
        return None
    return float(value)


def _get_str_list(parent: Any, key: str, path: str, result: VerificationResult) -> Optional[list[str]]:
    if not isinstance(parent, dict) or key not in parent:
        result.add_error(f"schema: thieu field '{path}'")
        return None
    value = parent[key]
    if not isinstance(value, list):
        result.add_error(f"schema: '{path}' phai la list, nhan {type(value).__name__}")
        return None
    if not all(isinstance(entry, str) for entry in value):
        result.add_error(f"schema: '{path}' chi duoc chua string")
        return None
    return value


def _is_rounded(value: float) -> bool:
    return abs(round(value, 2) - value) < 1e-9


# ---------------------------------------------------------------------------
# Individual checks (2D.2 - 2D.5)
# ---------------------------------------------------------------------------


def _check_evidence_ids(
    evidence_ids: list[str],
    ctx: CaseContext,
    loader,
    result: VerificationResult,
) -> None:
    """2D.2 + 2D.3 - every evidence ID must be well formed, real and in scope."""
    if len(evidence_ids) > config.MAX_EVIDENCE_IDS:
        result.add_error(
            f"limit: evidence_ids co {len(evidence_ids)} phan tu, toi da {config.MAX_EVIDENCE_IDS}"
        )

    seen: set[str] = set()
    per_type: dict[str, int] = {}

    for evidence_id in evidence_ids:
        result.checked_evidence += 1

        if evidence_id in seen:
            result.add_error(f"evidence: '{evidence_id}' bi lap")
            continue
        seen.add(evidence_id)

        kind = evidence_id.split(":", 1)[0] if ":" in evidence_id else ""
        pattern = _EVIDENCE_PATTERNS.get(kind)
        if pattern is None:
            result.add_error(f"evidence: '{evidence_id}' sai dinh dang (prefix khong hop le)")
            continue

        match = pattern.match(evidence_id)
        if match is None:
            result.add_error(f"evidence: '{evidence_id}' sai dinh dang cho loai '{kind}'")
            continue

        per_type[kind] = per_type.get(kind, 0) + 1

        if kind == "order":
            order_id = match.group(1)
            if not _order_exists(order_id, ctx, loader):
                result.add_error(f"evidence: order '{order_id}' khong ton tai trong CSV")
            elif order_id != ctx.claimed_order_id:
                result.add_error(f"evidence: '{evidence_id}' khong thuoc order cua case")
        elif kind == "item":
            order_id, raw_item_id = match.group(1), int(match.group(2))
            if order_id != ctx.claimed_order_id:
                result.add_error(f"evidence: '{evidence_id}' khong thuoc order cua case")
            elif not _item_exists(order_id, raw_item_id, ctx, loader):
                result.add_error(f"evidence: item '{order_id}:{raw_item_id}' khong ton tai trong CSV")
        elif kind == "payment":
            order_id, sequential = match.group(1), int(match.group(2))
            if order_id != ctx.claimed_order_id:
                result.add_error(f"evidence: '{evidence_id}' khong thuoc order cua case")
            elif not _payment_exists(order_id, sequential, ctx, loader):
                result.add_error(
                    f"evidence: payment '{order_id}:{sequential}' khong ton tai trong CSV"
                )
        elif kind == "seller":
            seller_id = match.group(1)
            if not _seller_exists(seller_id, ctx, loader):
                result.add_error(f"evidence: seller '{seller_id}' khong ton tai trong CSV")
            elif ctx.seller_ids and seller_id not in ctx.seller_ids:
                result.add_error(f"evidence: seller '{seller_id}' khong ban item nao trong order nay")
        elif kind == "policy":
            cause_code = match.group(1)
            if cause_code not in config.ROOT_CAUSE_CODES:
                result.add_error(f"evidence: root cause '{cause_code}' khong nam trong bang policy")

    for kind, count in per_type.items():
        if count > config.MAX_IDS_PER_ENTITY:
            result.add_error(
                f"limit: evidence loai '{kind}' co {count} ID, toi da {config.MAX_IDS_PER_ENTITY}"
            )


def _check_affected_entities(
    entities: dict,
    ctx: CaseContext,
    loader,
    result: VerificationResult,
) -> None:
    """2D.2 + 2D.3 - affected_entities must be real IDs, in scope, within limits."""
    order_ids = _get_str_list(entities, "order_ids", "affected_entities.order_ids", result)
    item_ids = _get_str_list(entities, "item_ids", "affected_entities.item_ids", result)
    seller_ids = _get_str_list(entities, "seller_ids", "affected_entities.seller_ids", result)
    payment_ids = _get_str_list(entities, "payment_ids", "affected_entities.payment_ids", result)

    for name, values in (
        ("order_ids", order_ids),
        ("item_ids", item_ids),
        ("seller_ids", seller_ids),
        ("payment_ids", payment_ids),
    ):
        if values is None:
            continue
        result.checked_entities += len(values)
        if len(values) > config.MAX_IDS_PER_ENTITY:
            result.add_error(
                f"limit: affected_entities.{name} co {len(values)} ID, "
                f"toi da {config.MAX_IDS_PER_ENTITY}"
            )
        if len(set(values)) != len(values):
            result.add_error(f"affected_entities.{name}: co ID bi lap")

    for order_id in order_ids or []:
        if not _order_exists(order_id, ctx, loader):
            result.add_error(f"affected_entities.order_ids: '{order_id}' khong ton tai trong CSV")
        elif order_id != ctx.claimed_order_id:
            result.add_error(f"affected_entities.order_ids: '{order_id}' khong phai order cua case")

    for item_key in item_ids or []:
        match = _ENTITY_KEY_PATTERN.match(item_key)
        if match is None:
            result.add_error(
                f"affected_entities.item_ids: '{item_key}' sai dinh dang '<order_id>:<order_item_id>'"
            )
            continue
        order_id, order_item_id = match.group(1), int(match.group(2))
        if order_id != ctx.claimed_order_id:
            result.add_error(f"affected_entities.item_ids: '{item_key}' khong thuoc order cua case")
        elif not _item_exists(order_id, order_item_id, ctx, loader):
            result.add_error(f"affected_entities.item_ids: '{item_key}' khong ton tai trong CSV")

    for payment_key in payment_ids or []:
        match = _ENTITY_KEY_PATTERN.match(payment_key)
        if match is None:
            result.add_error(
                f"affected_entities.payment_ids: '{payment_key}' sai dinh dang "
                "'<order_id>:<payment_sequential>'"
            )
            continue
        order_id, sequential = match.group(1), int(match.group(2))
        if order_id != ctx.claimed_order_id:
            result.add_error(
                f"affected_entities.payment_ids: '{payment_key}' khong thuoc order cua case"
            )
        elif not _payment_exists(order_id, sequential, ctx, loader):
            result.add_error(
                f"affected_entities.payment_ids: '{payment_key}' khong ton tai trong CSV"
            )

    for seller_id in seller_ids or []:
        if not _seller_exists(seller_id, ctx, loader):
            result.add_error(f"affected_entities.seller_ids: '{seller_id}' khong ton tai trong CSV")
        elif ctx.seller_ids and seller_id not in ctx.seller_ids:
            result.add_error(
                f"affected_entities.seller_ids: '{seller_id}' khong ban item nao trong order nay"
            )

    # README muc 6: order khong co item row -> item_ids/seller_ids rong.
    if ctx.order is not None and not ctx.has_items():
        if item_ids:
            result.add_error("edge case: order khong co item row nhung item_ids khong rong")
        if seller_ids:
            result.add_error("edge case: order khong co item row nhung seller_ids khong rong")


def _check_financials(
    financials: dict,
    ctx: CaseContext,
    primary_issue: Optional[str],
    case_status: Optional[str],
    result: VerificationResult,
) -> Optional[float]:
    """2D.4 - amounts must reconcile with the CSV totals and with the rule table."""
    currency = _get_str(financials, "currency", "financial_resolution.currency", result)
    if currency is not None and currency != CURRENCY:
        result.add_error(f"financial_resolution.currency phai la '{CURRENCY}', nhan '{currency}'")

    item_total = _get_number(financials, "item_total_brl", "financial_resolution.item_total_brl", result)
    freight_total = _get_number(
        financials, "freight_total_brl", "financial_resolution.freight_total_brl", result
    )
    payment_total = _get_number(
        financials, "payment_total_brl", "financial_resolution.payment_total_brl", result
    )
    refund = _get_number(
        financials, "recommended_refund_brl", "financial_resolution.recommended_refund_brl", result
    )

    expected = {
        "item_total_brl": (item_total, ctx.item_total),
        "freight_total_brl": (freight_total, ctx.freight_total),
        "payment_total_brl": (payment_total, ctx.payment_total),
    }
    for name, (reported, computed) in expected.items():
        if reported is None:
            continue
        if not _is_rounded(reported):
            result.add_error(f"financial_resolution.{name}={reported} chua lam tron 2 chu so")
        if reported < 0:
            result.add_error(f"financial_resolution.{name}={reported} khong duoc am")
        if abs(reported - round(computed, 2)) > MONEY_EPSILON:
            result.add_error(
                f"financial_resolution.{name}={reported} lech voi CSV ({round(computed, 2)})"
            )

    if refund is None:
        return None

    if not _is_rounded(refund):
        result.add_error(f"recommended_refund_brl={refund} chua lam tron 2 chu so")
    if refund < 0:
        result.add_error(f"recommended_refund_brl={refund} khong duoc am")
    if payment_total is not None and refund > payment_total + MONEY_EPSILON:
        result.add_error(
            f"recommended_refund_brl={refund} lon hon payment_total_brl={payment_total}"
        )

    # Refund must equal the basis named by the rule table for this issue.
    rule = RULE_TABLE.get(primary_issue or "")
    if rule is not None:
        basis = rule["refund_basis"]
        if basis == "payment_total":
            target = round(ctx.payment_total, 2)
        elif basis == "freight_total":
            target = round(ctx.freight_total, 2)
        else:
            target = 0.0
        if abs(refund - target) > MONEY_EPSILON:
            result.add_error(
                f"refund: primary_issue='{primary_issue}' phai hoan {target} BRL, nhan {refund}"
            )

    # case_status <-> refund consistency (README muc 6).
    if case_status == "action_required" and refund <= 0:
        result.add_error("case_status='action_required' nhung recommended_refund_brl = 0")
    if case_status == "no_action" and refund > 0:
        result.add_error(f"case_status='no_action' nhung recommended_refund_brl = {refund}")

    return refund


def _check_root_cause_analysis(
    analysis: dict,
    primary_issue: Optional[str],
    ctx: CaseContext,
    result: VerificationResult,
) -> None:
    """2D.3 + 2D.5 - ranked causes and responsible parties."""
    ranked = analysis.get("ranked_causes")
    if not isinstance(ranked, list):
        result.add_error("schema: 'root_cause_analysis.ranked_causes' phai la list")
        ranked = []
    elif len(ranked) > config.MAX_ROOT_CAUSES:
        result.add_error(
            f"limit: ranked_causes co {len(ranked)} phan tu, toi da {config.MAX_ROOT_CAUSES}"
        )
    elif not ranked:
        result.add_error("root_cause_analysis.ranked_causes khong duoc rong")

    seen_ranks: set[int] = set()
    for index, entry in enumerate(ranked):
        path = f"root_cause_analysis.ranked_causes[{index}]"
        if not isinstance(entry, dict):
            result.add_error(f"schema: '{path}' phai la object")
            continue
        cause_code = _get_str(entry, "cause_code", f"{path}.cause_code", result)
        rank = entry.get("rank")
        if cause_code is not None and cause_code not in config.ROOT_CAUSE_CODES:
            result.add_error(f"{path}.cause_code='{cause_code}' khong nam trong bang root cause")
        if isinstance(rank, bool) or not isinstance(rank, int):
            result.add_error(f"schema: '{path}.rank' phai la int")
        elif rank < 1:
            result.add_error(f"{path}.rank={rank} phai >= 1")
        elif rank in seen_ranks:
            result.add_error(f"{path}.rank={rank} bi trung")
        else:
            seen_ranks.add(rank)

    rule = RULE_TABLE.get(primary_issue or "")
    if rule is not None and ranked:
        top = next(
            (entry for entry in ranked if isinstance(entry, dict) and entry.get("rank") == 1),
            ranked[0] if isinstance(ranked[0], dict) else None,
        )
        top_code = top.get("cause_code") if isinstance(top, dict) else None
        if top_code != rule["cause_code"]:
            result.add_error(
                f"mapping: primary_issue='{primary_issue}' phai co cause_code rank 1 "
                f"la '{rule['cause_code']}', nhan '{top_code}'"
            )

    parties = analysis.get("responsible_parties")
    if not isinstance(parties, list):
        result.add_error("schema: 'root_cause_analysis.responsible_parties' phai la list")
        return
    if len(parties) > config.MAX_RESPONSIBLE_PARTIES:
        result.add_error(
            f"limit: responsible_parties co {len(parties)} phan tu, "
            f"toi da {config.MAX_RESPONSIBLE_PARTIES}"
        )

    for index, entry in enumerate(parties):
        path = f"root_cause_analysis.responsible_parties[{index}]"
        if not isinstance(entry, dict):
            result.add_error(f"schema: '{path}' phai la object")
            continue
        party_type = _get_str(entry, "party_type", f"{path}.party_type", result)
        party_id = _get_str(entry, "party_id", f"{path}.party_id", result)
        if party_type is not None and party_type not in PARTY_TYPES:
            result.add_error(f"{path}.party_type='{party_type}' khong hop le")
        if party_type == "seller" and party_id and ctx.seller_ids and party_id not in ctx.seller_ids:
            result.add_error(f"{path}.party_id='{party_id}' khong phai seller cua order nay")
        if party_type == "platform" and party_id not in (None, "OLIST_PLATFORM"):
            result.add_error(f"{path}.party_id='{party_id}' phai la 'OLIST_PLATFORM'")
        if party_type == "logistics_provider" and party_id not in (None, "LOGISTICS_PROVIDER"):
            result.add_error(f"{path}.party_id='{party_id}' phai la 'LOGISTICS_PROVIDER'")

    if rule is not None:
        if rule["party_type"] is None and parties:
            result.add_error(
                f"mapping: primary_issue='{primary_issue}' khong co responsible party, "
                f"nhan {len(parties)}"
            )
        if rule["party_type"] is not None:
            if not parties:
                result.add_error(
                    f"mapping: primary_issue='{primary_issue}' phai co responsible party "
                    f"'{rule['party_type']}'"
                )
            else:
                types = {p.get("party_type") for p in parties if isinstance(p, dict)}
                if rule["party_type"] not in types:
                    result.add_error(
                        f"mapping: primary_issue='{primary_issue}' phai co party_type "
                        f"'{rule['party_type']}', nhan {sorted(t for t in types if t)}"
                    )


def _check_resolution_actions(
    actions: Optional[list[str]],
    primary_issue: Optional[str],
    result: VerificationResult,
) -> None:
    """2D.3 + 2D.5 - action list."""
    if actions is None:
        return
    if len(actions) > config.MAX_ACTIONS:
        result.add_error(
            f"limit: resolution_actions co {len(actions)} phan tu, toi da {config.MAX_ACTIONS}"
        )
    if not actions:
        result.add_error("resolution_actions khong duoc rong")
    for action in actions:
        if action not in RESOLUTION_ACTIONS:
            result.add_error(f"resolution_actions: '{action}' khong nam trong bang policy")
    if len(set(actions)) != len(actions):
        result.add_error("resolution_actions: co action bi lap")

    rule = RULE_TABLE.get(primary_issue or "")
    if rule is not None and actions and actions[0] != rule["action"]:
        result.add_error(
            f"mapping: primary_issue='{primary_issue}' phai co action '{rule['action']}', "
            f"nhan '{actions[0]}'"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify(
    output: dict,
    ctx: CaseContext,
    loader=None,
    check_csv: bool = True,
) -> VerificationResult:
    """Verify one coordinator output against the case context and the CSVs.

    Args:
        output: the dict that would be written to ``output/<case_id>.json``.
        ctx: the CaseContext the agents worked on.
        loader: an existing :class:`data_loader.DataLoader`.  When omitted and
            ``check_csv`` is True the global singleton is used.
        check_csv: set False in unit tests with synthetic contexts - existence
            is then checked against ``ctx`` only, no CSV load happens.

    Returns:
        VerificationResult with ``passed`` False when any hard gate failed.
    """
    result = VerificationResult(case_id=str(output.get("case_id", ctx.case_id)))

    if not isinstance(output, dict):
        result.add_error("schema: output phai la object JSON")
        return result

    if loader is None and check_csv:
        from data_loader import get_loader  # imported lazily: loading 9 CSVs is slow

        loader = get_loader(str(config.DATA_DIR))

    # --- 2D.5: top level schema -------------------------------------------
    case_id = _get_str(output, "case_id", "case_id", result)
    if case_id is not None and case_id != ctx.case_id:
        result.add_error(f"case_id='{case_id}' khong khop context ('{ctx.case_id}')")

    known_keys = {
        "case_id",
        "assessment",
        "affected_entities",
        "root_cause_analysis",
        "evidence_ids",
        "financial_resolution",
        "resolution_actions",
    }
    for extra in sorted(set(output) - known_keys):
        result.add_warning(f"schema: field thua '{extra}' (khong co trong README muc 6)")

    assessment = _get_dict(output, "assessment", "assessment", result)
    primary_issue: Optional[str] = None
    case_status: Optional[str] = None
    if assessment is not None:
        primary_issue = _get_str(assessment, "primary_issue", "assessment.primary_issue", result)
        case_status = _get_str(assessment, "case_status", "assessment.case_status", result)
        confidence = _get_number(assessment, "confidence", "assessment.confidence", result)

        if primary_issue is not None and primary_issue not in PRIMARY_ISSUES:
            result.add_error(f"assessment.primary_issue='{primary_issue}' khong nam trong 6 rule")
        if case_status is not None and case_status not in CASE_STATUSES:
            result.add_error(f"assessment.case_status='{case_status}' khong hop le")
        # 2D.4: confidence in [0, 1]
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            result.add_error(f"assessment.confidence={confidence} nam ngoai [0, 1]")

    entities = _get_dict(output, "affected_entities", "affected_entities", result)
    if entities is not None:
        _check_affected_entities(entities, ctx, loader, result)

    analysis = _get_dict(output, "root_cause_analysis", "root_cause_analysis", result)
    if analysis is not None:
        _check_root_cause_analysis(analysis, primary_issue, ctx, result)

    evidence_ids = _get_str_list(output, "evidence_ids", "evidence_ids", result)
    if evidence_ids is not None:
        _check_evidence_ids(evidence_ids, ctx, loader, result)
        if primary_issue in RULE_TABLE:
            expected_policy = f"policy:{RULE_TABLE[primary_issue]['cause_code']}"
            if expected_policy not in evidence_ids:
                result.add_warning(f"evidence: thieu '{expected_policy}'")

    financials = _get_dict(output, "financial_resolution", "financial_resolution", result)
    if financials is not None:
        _check_financials(financials, ctx, primary_issue, case_status, result)

    actions = _get_str_list(output, "resolution_actions", "resolution_actions", result)
    _check_resolution_actions(actions, primary_issue, result)

    return result


def verify_file(path: str, ctx: CaseContext, loader=None) -> VerificationResult:
    """Convenience wrapper: verify an output JSON already written to disk."""
    import json

    with open(path, encoding="utf-8") as handle:
        return verify(json.load(handle), ctx, loader=loader)
