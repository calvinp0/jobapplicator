"""In-memory diagnostics for experimental local LLM requests.

The store is intentionally process-local and rolling. It records operational
metadata, counters, timings, and short sanitized errors, but never raw prompts,
API keys, authorization headers, thinking text, or generated content.
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse


MAX_EVENTS = 1000
MAX_REQUESTS = 50

STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_FALLBACK = "fallback"
STATUS_DEGRADED_SKIP = "degraded_skip"

TIMEOUT_CONNECT = "connect_timeout"
TIMEOUT_READ = "read_timeout"
TIMEOUT_GENERATION = "generation_timeout"
TIMEOUT_STALLED = "stalled_generation_timeout"
TIMEOUT_DEGRADED_SKIP = "provider_degraded_skip"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def _elapsed_ms(started_at: str, completed_at: Optional[str] = None) -> int:
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(completed_at) if completed_at else utc_now()
        return max(0, int((end - start).total_seconds() * 1000))
    except ValueError:
        return 0


def _safe_error(error: Optional[str]) -> Optional[str]:
    if not error:
        return None
    compact = " ".join(str(error).split())
    return compact[:500]


def split_endpoint(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    path = parsed.path or "/"
    return host, path


@dataclass
class LocalLLMDiagnosticEvent:
    event_id: str
    request_id: Optional[str]
    run_id: Optional[str]
    step: Optional[str]
    created_at: str
    message: str
    kind: str = "info"

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LocalLLMDiagnosticRecord:
    request_id: str
    run_id: Optional[str]
    step: Optional[str]
    provider: str
    model: str
    endpoint_host: str
    endpoint_path: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    elapsed_ms: int = 0
    configured_context_budget_tokens: Optional[int] = None
    usable_input_budget_tokens: Optional[int] = None
    estimated_input_tokens: Optional[int] = None
    requested_num_ctx: Optional[int] = None
    num_ctx_sent: bool = False
    num_predict: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False
    server_reported_context_tokens: Optional[int] = None
    active_runner_context_tokens: Optional[int] = None
    context_trust_status: str = "unverified"
    time_to_first_chunk_ms: Optional[int] = None
    time_to_first_content_ms: Optional[int] = None
    prompt_eval_count: Optional[int] = None
    prompt_eval_duration_ms: Optional[int] = None
    eval_count: int = 0
    eval_duration_ms: int = 0
    total_duration_ms: Optional[int] = None
    load_duration_ms: Optional[int] = None
    tokens_per_second: Optional[float] = None
    approx_generated_chars: int = 0
    approx_generated_tokens: int = 0
    thinking_detected: bool = False
    content_detected: bool = False
    last_chunk_at: Optional[str] = None
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    error: Optional[str] = None
    timeout_kind: Optional[str] = None

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["elapsed_ms"] = _elapsed_ms(self.started_at, self.completed_at)
        return data


class LocalLLMDiagnosticStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: deque[LocalLLMDiagnosticEvent] = deque(maxlen=MAX_EVENTS)
        self._requests: deque[str] = deque(maxlen=MAX_REQUESTS)
        self._records: dict[str, LocalLLMDiagnosticRecord] = {}
        self._provider_degraded: dict[str, dict[str, Any]] = {}

    def create_request(
        self,
        *,
        run_id: Optional[str],
        step: Optional[str],
        provider: str,
        model: str,
        endpoint_url: str,
        configured_context_budget_tokens: Optional[int],
        usable_input_budget_tokens: Optional[int],
        estimated_input_tokens: Optional[int],
        requested_num_ctx: Optional[int],
        num_predict: Optional[int],
        temperature: Optional[float],
        stream: bool,
        server_reported_context_tokens: Optional[int] = None,
    ) -> LocalLLMDiagnosticRecord:
        endpoint_host, endpoint_path = split_endpoint(endpoint_url)
        request_id = str(uuid.uuid4())
        record = LocalLLMDiagnosticRecord(
            request_id=request_id,
            run_id=run_id,
            step=step,
            provider=provider,
            model=model,
            endpoint_host=endpoint_host,
            endpoint_path=endpoint_path,
            status=STATUS_RUNNING,
            started_at=iso_now(),
            configured_context_budget_tokens=configured_context_budget_tokens,
            usable_input_budget_tokens=usable_input_budget_tokens,
            estimated_input_tokens=estimated_input_tokens,
            requested_num_ctx=requested_num_ctx,
            num_ctx_sent=requested_num_ctx is not None,
            num_predict=num_predict,
            temperature=temperature,
            stream=stream,
            server_reported_context_tokens=server_reported_context_tokens,
            context_trust_status=(
                "server_reported"
                if server_reported_context_tokens is not None
                else "unverified"
            ),
        )
        with self._lock:
            self._records[request_id] = record
            self._requests.appendleft(request_id)
            while len(self._records) > MAX_REQUESTS:
                keep = set(self._requests)
                for old_id in list(self._records):
                    if old_id not in keep:
                        self._records.pop(old_id, None)
        self.add_event(request_id, run_id, step, "request created")
        return record

    def add_event(
        self,
        request_id: Optional[str],
        run_id: Optional[str],
        step: Optional[str],
        message: str,
        *,
        kind: str = "info",
    ) -> None:
        event = LocalLLMDiagnosticEvent(
            event_id=str(uuid.uuid4()),
            request_id=request_id,
            run_id=run_id,
            step=step,
            created_at=iso_now(),
            message=_safe_error(message) or "",
            kind=kind,
        )
        with self._lock:
            self._events.appendleft(event)

    def update_chunk(
        self,
        request_id: str,
        *,
        thinking_chars: int = 0,
        content_chars: int = 0,
    ) -> None:
        now = iso_now()
        with self._lock:
            record = self._records.get(request_id)
            if record is None:
                return
            if record.time_to_first_chunk_ms is None:
                record.time_to_first_chunk_ms = _elapsed_ms(record.started_at)
            if content_chars > 0 and record.time_to_first_content_ms is None:
                record.time_to_first_content_ms = _elapsed_ms(record.started_at)
            record.last_chunk_at = now
            if thinking_chars > 0:
                record.thinking_detected = True
            if content_chars > 0:
                record.content_detected = True
                record.approx_generated_chars += content_chars
                record.approx_generated_tokens = max(
                    record.approx_generated_tokens,
                    max(1, round(record.approx_generated_chars / 4)),
                )

    def update_final_metrics(self, request_id: str, body: dict[str, Any]) -> None:
        with self._lock:
            record = self._records.get(request_id)
            if record is None:
                return
            record.prompt_eval_count = _optional_int(body.get("prompt_eval_count"))
            record.prompt_eval_duration_ms = _ns_to_ms(
                _optional_int(body.get("prompt_eval_duration"))
            )
            record.eval_count = _optional_int(body.get("eval_count")) or record.eval_count
            record.eval_duration_ms = (
                _ns_to_ms(_optional_int(body.get("eval_duration")))
                or record.eval_duration_ms
            )
            record.total_duration_ms = _ns_to_ms(_optional_int(body.get("total_duration")))
            record.load_duration_ms = _ns_to_ms(_optional_int(body.get("load_duration")))
            if record.eval_count and record.eval_duration_ms:
                record.tokens_per_second = round(
                    record.eval_count / (record.eval_duration_ms / 1000), 1
                )
            if record.eval_count:
                record.approx_generated_tokens = record.eval_count

    def complete_request(
        self,
        request_id: str,
        *,
        status: str,
        fallback_used: bool = False,
        fallback_reason: Optional[str] = None,
        error: Optional[str] = None,
        timeout_kind: Optional[str] = None,
    ) -> None:
        completed_at = iso_now()
        with self._lock:
            record = self._records.get(request_id)
            if record is None:
                return
            record.status = status
            record.completed_at = completed_at
            record.elapsed_ms = _elapsed_ms(record.started_at, completed_at)
            record.fallback_used = fallback_used
            record.fallback_reason = _safe_error(fallback_reason)
            record.error = _safe_error(error)
            record.timeout_kind = timeout_kind
        message = status
        if timeout_kind:
            message = f"{timeout_kind}; fallback used" if fallback_used else timeout_kind
        elif fallback_used and fallback_reason:
            message = f"fallback used: {fallback_reason}"
        self.add_event(request_id, None, None, message, kind=status)

    def mark_provider_degraded(
        self,
        *,
        run_id: Optional[str],
        reason: str,
        timeout_failures: int,
    ) -> None:
        payload = {
            "run_id": run_id,
            "degraded": True,
            "reason": _safe_error(reason),
            "timeout_failures": timeout_failures,
            "updated_at": iso_now(),
        }
        key = run_id or "global"
        with self._lock:
            self._provider_degraded[key] = payload
        self.add_event(
            None,
            run_id,
            None,
            f"local provider marked degraded after {timeout_failures} timeout failures",
            kind="degraded",
        )

    def record_degraded_skip(
        self,
        *,
        run_id: Optional[str],
        step: Optional[str],
        provider: str,
        model: str,
        reason: str,
    ) -> None:
        record = self.create_request(
            run_id=run_id,
            step=step,
            provider=provider,
            model=model,
            endpoint_url="local://provider-degraded/skip",
            configured_context_budget_tokens=None,
            usable_input_budget_tokens=None,
            estimated_input_tokens=None,
            requested_num_ctx=None,
            num_predict=None,
            temperature=None,
            stream=False,
        )
        self.complete_request(
            record.request_id,
            status=STATUS_DEGRADED_SKIP,
            fallback_used=True,
            fallback_reason=reason,
            timeout_kind=TIMEOUT_DEGRADED_SKIP,
        )
        self.add_event(
            record.request_id,
            run_id,
            step,
            "remaining local LLM steps skipped",
            kind="degraded",
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = [self._records[rid].public_dict() for rid in self._requests if rid in self._records]
            events = [event.public_dict() for event in self._events]
            degraded = list(self._provider_degraded.values())
        active = [r for r in records if r["status"] == STATUS_RUNNING]
        return {
            "active_request": active[0] if active else None,
            "active_requests": active,
            "recent_requests": records,
            "recent_events": events,
            "provider_degraded": degraded,
        }

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._requests.clear()
            self._records.clear()
            self._provider_degraded.clear()


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ns_to_ms(value: Optional[int]) -> Optional[int]:
    return round(value / 1_000_000) if value is not None else None


diagnostics_store = LocalLLMDiagnosticStore()

