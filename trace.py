"""Execution trace for the multi-agent run - one JSON line per case.

``trace.jsonl`` must reflect the *latest* run only, so the writer truncates the
file when it opens (never appends to an older run).

Each line records:

- ``case_id``
- ``handoff_steps``: which agent produced which signals, in execution order
- ``primary_issue`` / ``confidence`` (final assessment)
- ``verifier_pass`` plus the verifier errors when it failed

Usage::

    from trace import TraceRecorder, TraceWriter

    with TraceWriter() as writer:
        recorder = TraceRecorder("EC_001")
        with recorder.step("order_seller_agent") as step:
            signals = analyze_order_seller(ctx)
            step["summary"] = {"order_status": signals["order_status"]}
        writer.write(recorder.build_record(output, verification))
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

import config

# README muc 8 expects trace.jsonl at repo root; logging/ keeps a mirror copy
# so every run artifact of the team lives in one folder as well.
DEFAULT_TRACE_PATH = config.BASE_DIR / "trace.jsonl"
MIRROR_TRACE_PATH = config.LOG_DIR / "trace.jsonl"

COORDINATOR = "coordinator_agent"


class TraceRecorder:
    """Collects the handoff steps of a single case."""

    def __init__(
        self,
        case_id: str,
        order_id: Optional[str] = None,
        orchestrator: str = COORDINATOR,
    ):
        self.case_id = case_id
        self.order_id = order_id
        # Ten module dieu phoi thuc te (coordinator_agent, hoac run_batch khi
        # chay pipeline noi bo) - dung lam gia tri "from" mac dinh cua step.
        self.orchestrator = orchestrator
        self.steps: list[dict[str, Any]] = []
        self._started = time.perf_counter()
        self._started_at = datetime.now().isoformat(timespec="seconds")

    def record(
        self,
        agent: str,
        *,
        source: Optional[str] = None,
        summary: Optional[dict[str, Any]] = None,
        status: str = "ok",
        duration_ms: float = 0.0,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        """Append one handoff step and return it."""
        step: dict[str, Any] = {
            "step": len(self.steps) + 1,
            "from": source or self.orchestrator,
            "to": agent,
            "status": status,
            "duration_ms": round(duration_ms, 2),
        }
        if summary:
            step["summary"] = summary
        if error:
            step["error"] = error
        self.steps.append(step)
        return step

    @contextmanager
    def step(self, agent: str, *, source: Optional[str] = None) -> Iterator[dict[str, Any]]:
        """Time one agent call.

        Yields a mutable dict; put anything JSON-serializable under
        ``step["summary"]`` and it lands in the trace line.  Exceptions are
        recorded as a failed step and re-raised.
        """
        holder: dict[str, Any] = {}
        started = time.perf_counter()
        try:
            yield holder
        except Exception as exc:  # noqa: BLE001 - recorded then re-raised
            self.record(
                agent,
                source=source,
                summary=holder.get("summary"),
                status="error",
                duration_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        self.record(
            agent,
            source=source,
            summary=holder.get("summary"),
            status=holder.get("status", "ok"),
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    def build_record(
        self,
        output: Optional[dict[str, Any]] = None,
        verification=None,
        *,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build the single JSONL line for this case.

        ``verification`` accepts a :class:`verifier_agent.VerificationResult`
        (or any object exposing ``passed`` / ``errors`` / ``warnings``).
        """
        assessment = (output or {}).get("assessment", {}) if isinstance(output, dict) else {}
        financials = (output or {}).get("financial_resolution", {}) if isinstance(output, dict) else {}

        verifier_pass = bool(getattr(verification, "passed", False)) if verification else False
        verifier_errors = list(getattr(verification, "errors", []) or []) if verification else []
        verifier_warnings = list(getattr(verification, "warnings", []) or []) if verification else []

        record: dict[str, Any] = {
            "case_id": self.case_id,
            "order_id": self.order_id,
            "orchestrator": self.orchestrator,
            "started_at": self._started_at,
            "duration_ms": round((time.perf_counter() - self._started) * 1000, 2),
            "handoff_steps": self.steps,
            "primary_issue": assessment.get("primary_issue"),
            "case_status": assessment.get("case_status"),
            "confidence": assessment.get("confidence"),
            "recommended_refund_brl": financials.get("recommended_refund_brl"),
            "verifier_pass": verifier_pass,
            "verifier_errors": verifier_errors,
            "verifier_warnings": verifier_warnings,
        }
        if error:
            record["error"] = error
            record["verifier_pass"] = False
        return record


class TraceWriter:
    """Writes trace records as JSONL, overwriting any previous run."""

    def __init__(
        self,
        path: Path | str = DEFAULT_TRACE_PATH,
        mirrors: Iterable[Path | str] = (MIRROR_TRACE_PATH,),
        *,
        enabled: bool = True,
    ):
        self.path = Path(path)
        self.mirrors = [Path(mirror) for mirror in mirrors if Path(mirror) != Path(path)]
        self.enabled = enabled
        self.count = 0
        self._handles: list[Any] = []

    def open(self) -> "TraceWriter":
        if not self.enabled:
            return self
        for target in [self.path, *self.mirrors]:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._handles.append(open(target, "w", encoding="utf-8"))  # truncate: khong append
        return self

    def write(self, record: dict[str, Any]) -> None:
        if not self.enabled:
            return
        if not self._handles:
            self.open()
        line = json.dumps(record, ensure_ascii=False)
        for handle in self._handles:
            handle.write(line + "\n")
            handle.flush()
        self.count += 1

    def close(self) -> None:
        for handle in self._handles:
            handle.close()
        self._handles = []

    def __enter__(self) -> "TraceWriter":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def write_trace(
    records: Iterable[dict[str, Any]],
    path: Path | str = DEFAULT_TRACE_PATH,
    mirrors: Iterable[Path | str] = (MIRROR_TRACE_PATH,),
) -> int:
    """Write a full list of records at once (overwrites the file)."""
    with TraceWriter(path, mirrors) as writer:
        for record in records:
            writer.write(record)
        return writer.count


def read_trace(path: Path | str = DEFAULT_TRACE_PATH) -> list[dict[str, Any]]:
    """Read back a trace file - used by the batch summary and by tests."""
    trace_path = Path(path)
    if not trace_path.exists():
        return []
    with open(trace_path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
