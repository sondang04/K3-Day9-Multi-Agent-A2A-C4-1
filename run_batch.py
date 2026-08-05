"""Batch runner - resolve every case in ``input/`` and write ``output/EC_XXX.json``.

Flow per case::

    input/EC_XXX.json
        -> data_loader.build_case_context   (CaseContext)
        -> coordinator_agent                (khi da co) hoac pipeline noi bo
        -> verifier_agent.verify            (hard gate)
        -> output/EC_XXX.json + 1 dong trace.jsonl

``coordinator_agent.py`` la phan viec cua A (Phase 3).  Chung nao file do chua
ton tai, runner dung pipeline noi bo o duoi: goi dung 4 sub-agent cua B/C roi
tong hop theo README muc 6.  Khi A push coordinator len, runner tu dong dung
coordinator (``--pipeline coordinator`` de bat buoc, ``--pipeline local`` de
ep dung pipeline noi bo).

Vi du::

    python run_batch.py                 # chay ca 50 case
    python run_batch.py --limit 5       # 5 case dau (task 3.4)
    python run_batch.py --cases EC_001 EC_010 EC_025
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Optional

import config
from data_loader import get_loader
from delivery_agent import analyze_delivery
from order_seller_agent import analyze_order_seller
from payment_agent import analyze_payment
from policy_agent import decide
from schema import CaseContext
from trace import DEFAULT_TRACE_PATH, MIRROR_TRACE_PATH, TraceRecorder, TraceWriter
from verifier_agent import VerificationResult, verify

# Ten ham entrypoint co the co trong coordinator_agent.py cua A.
COORDINATOR_ENTRYPOINTS = ("process_case", "run_case", "handle_case", "resolve_case", "coordinate")

VERIFIER_REPORT_PATH = config.LOG_DIR / "verifier_report.json"


# ---------------------------------------------------------------------------
# Output assembly (pipeline noi bo)
# ---------------------------------------------------------------------------


def _prioritized_item_ids(ctx: CaseContext, delivery: dict[str, Any]) -> list[str]:
    """Item da tre handoff dung truoc - do la evidence dat gia nhat cua case."""
    late = [item_id for item_id in delivery.get("late_item_ids", []) if item_id in ctx.item_ids]
    rest = [item_id for item_id in ctx.item_ids if item_id not in late]
    return late + rest


def _prioritized_seller_ids(ctx: CaseContext, delivery: dict[str, Any]) -> list[str]:
    late = [sid for sid in delivery.get("late_seller_ids", []) if sid in ctx.seller_ids]
    rest = [sid for sid in ctx.seller_ids if sid not in late]
    return late + rest


def select_evidence(ctx: CaseContext, delivery: dict[str, Any]) -> list[str]:
    """Chon toi da 10 evidence ID, moi loai toi da 5, uu tien theo do lien quan.

    ``order:`` va ``policy:`` luon duoc giu; phan con lai chia deu (round-robin)
    cho item / payment / seller de khong loai bo han mot loai evidence nao.
    """
    order_ev = [f"order:{ctx.order.order_id}"] if ctx.order is not None else []
    policy_ev = (
        [f"policy:{ctx.root_cause}"]
        if ctx.root_cause in config.ROOT_CAUSE_CODES
        else []
    )

    cap = config.MAX_IDS_PER_ENTITY
    item_ev = [f"item:{key}" for key in _prioritized_item_ids(ctx, delivery)][:cap]
    payment_ev = [f"payment:{ctx.get_payment_key(p)}" for p in ctx.payments][:cap]
    seller_ev = [f"seller:{sid}" for sid in _prioritized_seller_ids(ctx, delivery)][:cap]

    budget = config.MAX_EVIDENCE_IDS - len(order_ev) - len(policy_ev)
    pools = [list(item_ev), list(payment_ev), list(seller_ev)]
    chosen: list[list[str]] = [[], [], []]
    while budget > 0 and any(pools):
        for index, pool in enumerate(pools):
            if not pool or budget == 0:
                continue
            chosen[index].append(pool.pop(0))
            budget -= 1

    return order_ev + chosen[0] + chosen[1] + chosen[2] + policy_ev


def assemble_output(ctx: CaseContext, delivery: dict[str, Any]) -> dict[str, Any]:
    """Build the README muc 6 payload from a CaseContext already decided by policy."""
    cap = config.MAX_IDS_PER_ENTITY

    order_ids = [ctx.order.order_id] if ctx.order is not None else []
    item_ids = _prioritized_item_ids(ctx, delivery)[:cap]
    seller_ids = _prioritized_seller_ids(ctx, delivery)[:cap]
    payment_ids = [ctx.get_payment_key(p) for p in ctx.payments][:cap]

    payment_total = round(ctx.payment_total, 2)
    refund = round(min(ctx.recommended_refund, ctx.payment_total), 2)

    evidence_ids = select_evidence(ctx, delivery)
    ctx.evidence_ids = evidence_ids  # giu ctx dong bo voi file da ghi

    ranked_causes = (
        [{"cause_code": ctx.root_cause, "rank": 1}]
        if ctx.root_cause in config.ROOT_CAUSE_CODES
        else []
    )

    return {
        "case_id": ctx.case_id,
        "assessment": {
            "primary_issue": ctx.primary_issue,
            "case_status": ctx.case_status,
            "confidence": round(ctx.confidence, 2),
        },
        "affected_entities": {
            "order_ids": order_ids,
            "item_ids": item_ids,
            "seller_ids": seller_ids,
            "payment_ids": payment_ids,
        },
        "root_cause_analysis": {
            "ranked_causes": ranked_causes,
            "responsible_parties": [
                {"party_type": party["party_type"], "party_id": party["party_id"]}
                for party in ctx.responsible_parties[: config.MAX_RESPONSIBLE_PARTIES]
            ],
        },
        "evidence_ids": evidence_ids,
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": round(ctx.item_total, 2),
            "freight_total_brl": round(ctx.freight_total, 2),
            "payment_total_brl": payment_total,
            "recommended_refund_brl": refund,
        },
        "resolution_actions": ctx.resolution_actions[: config.MAX_ACTIONS],
    }


def local_pipeline(ctx: CaseContext, recorder: TraceRecorder) -> dict[str, Any]:
    """Goi 4 sub-agent theo dung thu tu handoff roi tong hop output."""
    with recorder.step("order_seller_agent") as step:
        order_signals = analyze_order_seller(ctx)
        step["summary"] = {
            "order_status": order_signals["order_status"],
            "item_count": len(order_signals["item_ids"]),
            "seller_count": len(order_signals["seller_ids"]),
            "multi_seller": order_signals["multi_seller"],
        }

    with recorder.step("delivery_agent") as step:
        delivery_signals = analyze_delivery(ctx)
        step["summary"] = {
            "carrier_after_limit": delivery_signals["carrier_after_limit"],
            "delivered_after_estimate": delivery_signals["delivered_after_estimate"],
            "late_item_ids": delivery_signals["late_item_ids"][: config.MAX_IDS_PER_ENTITY],
        }

    with recorder.step("payment_agent") as step:
        payment_signals = analyze_payment(ctx)
        step["summary"] = {
            "payment_total": round(payment_signals["payment_total"], 2),
            "payment_mismatch": round(payment_signals["payment_mismatch"], 2),
            "valid_split_payment": payment_signals["valid_split_payment"],
        }

    late_sellers = delivery_signals["late_seller_ids"]
    policy_signals = {
        "order_status": order_signals["order_status"],
        "item_total": payment_signals["item_total"],
        "freight_total": payment_signals["freight_total"],
        "payment_total": payment_signals["payment_total"],
        "is_valid_match": payment_signals["is_valid_match"],
        "valid_split_payment": payment_signals["valid_split_payment"],
        "carrier_after_limit": delivery_signals["carrier_after_limit"],
        "delivered_after_estimate": delivery_signals["delivered_after_estimate"],
        "violating_seller_id": late_sellers[0] if late_sellers else None,
    }

    with recorder.step("policy_agent") as step:
        decide(ctx, policy_signals)
        step["summary"] = {
            "primary_issue": ctx.primary_issue,
            "root_cause": ctx.root_cause,
            "recommended_refund_brl": ctx.recommended_refund,
            "confidence": ctx.confidence,
        }

    return assemble_output(ctx, delivery_signals)


# ---------------------------------------------------------------------------
# Coordinator hookup (Phase 3 cua A)
# ---------------------------------------------------------------------------


def load_coordinator() -> Optional[Callable[..., Any]]:
    """Return coordinator entrypoint neu coordinator_agent.py da ton tai."""
    try:
        import coordinator_agent
    except ImportError:
        return None
    for name in COORDINATOR_ENTRYPOINTS:
        entrypoint = getattr(coordinator_agent, name, None)
        if callable(entrypoint):
            return entrypoint
    return None


def call_coordinator(entrypoint: Callable[..., Any], case_data: dict, ctx: CaseContext, loader) -> dict:
    """Goi coordinator, khop tham so theo ten de khong phu thuoc chu ky ham cua A."""
    available = {
        "case_data": case_data,
        "case": case_data,
        "case_json": case_data,
        "case_input": case_data,
        "ctx": ctx,
        "context": ctx,
        "case_context": ctx,
        "loader": loader,
        "data_loader": loader,
    }
    args: list[Any] = []
    for name, parameter in inspect.signature(entrypoint).parameters.items():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if name in available:
            args.append(available[name])
        elif parameter.default is parameter.empty:
            raise TypeError(f"coordinator can tham so '{name}' ma run_batch khong biet truyen")
        else:
            break
    return entrypoint(*args)


# ---------------------------------------------------------------------------
# Per-case driver
# ---------------------------------------------------------------------------


def process_case(
    case_data: dict,
    loader,
    coordinator: Optional[Callable[..., Any]] = None,
) -> tuple[dict[str, Any], VerificationResult, dict[str, Any]]:
    """Run one case end-to-end. Returns (output, verification, trace_record)."""
    case_id = case_data["case_id"]
    order_id = case_data["customer_request"]["claimed_order_id"]
    orchestrator = "coordinator_agent" if coordinator is not None else "run_batch"
    recorder = TraceRecorder(case_id, order_id, orchestrator=orchestrator)

    with recorder.step("data_loader", source="run_batch") as step:
        ctx = loader.build_case_context(case_data)
        step["summary"] = {
            "order_found": ctx.order is not None,
            "items": len(ctx.items),
            "payments": len(ctx.payments),
        }

    if coordinator is not None:
        with recorder.step("coordinator_agent", source="run_batch") as step:
            output = call_coordinator(coordinator, case_data, ctx, loader)
            step["summary"] = {"delegated": True}
    else:
        output = local_pipeline(ctx, recorder)

    with recorder.step("verifier_agent", source="run_batch") as step:
        verification = verify(output, ctx, loader=loader)
        step["summary"] = {
            "passed": verification.passed,
            "errors": verification.errors[:3],
            "checked_evidence": verification.checked_evidence,
        }

    return output, verification, recorder.build_record(output, verification)


def load_cases(input_dir: Path, only: Optional[list[str]], limit: Optional[int]) -> list[dict]:
    paths = sorted(input_dir.glob("EC_*.json"))
    if only:
        wanted = {case_id.upper() for case_id in only}
        paths = [path for path in paths if path.stem.upper() in wanted]
    if limit is not None:
        paths = paths[:limit]

    cases = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            cases.append(json.load(handle))
    return cases


def write_output(output: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{output['case_id']}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run(
    input_dir: Path = config.INPUT_DIR,
    output_dir: Path = config.OUTPUT_DIR,
    trace_path: Path = DEFAULT_TRACE_PATH,
    only: Optional[list[str]] = None,
    limit: Optional[int] = None,
    pipeline: str = "auto",
    write_trace_file: bool = True,
    quiet: bool = False,
) -> int:
    cases = load_cases(input_dir, only, limit)
    if not cases:
        print(f"[ERROR] Khong tim thay case nao trong {input_dir}", file=sys.stderr)
        return 1

    coordinator = None
    if pipeline in ("auto", "coordinator"):
        coordinator = load_coordinator()
        if coordinator is None and pipeline == "coordinator":
            print("[ERROR] Khong import duoc coordinator_agent", file=sys.stderr)
            return 1
    source = "coordinator_agent" if coordinator else "local pipeline (B/C agents)"
    print(f"Chay {len(cases)} case qua {source}")

    loader = get_loader(str(config.DATA_DIR))

    issues: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    crashed: list[str] = []

    with TraceWriter(trace_path, (MIRROR_TRACE_PATH,), enabled=write_trace_file) as writer:
        for case_data in cases:
            case_id = case_data["case_id"]
            try:
                output, verification, record = process_case(case_data, loader, coordinator)
            except Exception as exc:  # noqa: BLE001 - 1 case hong khong duoc lam chet batch
                crashed.append(case_id)
                traceback.print_exc()
                writer.write(
                    TraceRecorder(
                        case_id,
                        case_data["customer_request"]["claimed_order_id"],
                        orchestrator="coordinator_agent" if coordinator else "run_batch",
                    ).build_record(error=f"{type(exc).__name__}: {exc}")
                )
                continue

            write_output(output, output_dir)
            writer.write(record)

            issues[output["assessment"]["primary_issue"] or "unknown"] += 1
            if not verification.passed:
                failures.append(
                    {
                        "case_id": case_id,
                        "primary_issue": output["assessment"]["primary_issue"],
                        "errors": verification.errors,
                        "warnings": verification.warnings,
                    }
                )

            if not quiet:
                flag = "OK  " if verification.passed else "FAIL"
                print(
                    f"  [{flag}] {case_id}  {output['assessment']['primary_issue']:<24}"
                    f" refund={output['financial_resolution']['recommended_refund_brl']:>8.2f}"
                    f" conf={output['assessment']['confidence']:.2f}"
                )

    written = len(cases) - len(crashed)
    print("\n=== Tong ket ===")
    print(f"  Case xu ly       : {len(cases)}")
    print(f"  File output ghi  : {written} -> {output_dir}")
    print(f"  Verifier pass    : {written - len(failures)}")
    print(f"  Verifier fail    : {len(failures)}")
    if crashed:
        print(f"  Case loi runtime : {len(crashed)} -> {', '.join(crashed)}")
    if write_trace_file:
        print(f"  Trace            : {trace_path} (+ {MIRROR_TRACE_PATH})")

    print("\n  Phan bo primary_issue:")
    for issue, count in issues.most_common():
        print(f"    {issue:<26} {count}")

    if failures:
        VERIFIER_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(VERIFIER_REPORT_PATH, "w", encoding="utf-8") as handle:
            json.dump(failures, handle, ensure_ascii=False, indent=2)
        print(f"\n  Case Verifier fail (chi tiet: {VERIFIER_REPORT_PATH}):")
        for failure in failures:
            first_error = failure["errors"][0] if failure["errors"] else ""
            print(f"    {failure['case_id']}: {first_error}")

    return 0 if not crashed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Chay batch 50 case dispute resolution")
    parser.add_argument("--input-dir", type=Path, default=config.INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=config.OUTPUT_DIR)
    parser.add_argument("--trace-path", type=Path, default=DEFAULT_TRACE_PATH)
    parser.add_argument("--cases", nargs="+", help="Chi chay cac case_id nay, vd EC_001 EC_010")
    parser.add_argument("--limit", type=int, help="Chi chay N case dau tien")
    parser.add_argument(
        "--pipeline",
        choices=("auto", "coordinator", "local"),
        default="auto",
        help="auto: dung coordinator_agent neu co, nguoc lai dung pipeline noi bo",
    )
    parser.add_argument("--no-trace", action="store_true", help="Khong ghi trace.jsonl")
    parser.add_argument("--quiet", action="store_true", help="Khong in tung case")
    args = parser.parse_args()

    return run(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        trace_path=args.trace_path,
        only=args.cases,
        limit=args.limit,
        pipeline=args.pipeline,
        write_trace_file=not args.no_trace,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    raise SystemExit(main())
