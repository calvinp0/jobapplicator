import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getLocalLlmDiagnostics } from "../api";
import type {
  LocalLlmDiagnosticEvent,
  LocalLlmDiagnosticRecord,
  LocalLlmDiagnosticsSnapshot,
} from "../api";
import { EmptyState, PageHeader, SectionCard, StatusBadge } from "../components/ui";
import type { StatusBadgeVariant } from "../components/ui/StatusBadge";

export const LOCAL_LLM_MONITOR_POLL_MS = 2000;

function formatTime(value?: string | null): string {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDuration(ms?: number | null): string {
  if (ms == null) return "unknown";
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function yesNo(value: boolean): string {
  return value ? "yes" : "no";
}

function valueOrUnknown(value: unknown, suffix = ""): string {
  if (value === null || value === undefined || value === "") return "unknown";
  return `${value}${suffix}`;
}

function statusVariant(status: string): StatusBadgeVariant {
  if (status === "running") return "running";
  if (status === "succeeded") return "completed";
  if (status === "failed") return "failed";
  if (status.includes("fallback") || status.includes("degraded")) return "pending";
  return "default";
}

function FieldList({ rows }: { rows: Array<[string, string]> }) {
  return (
    <dl className="monitor-fields">
      {rows.map(([label, value]) => (
        <div key={label} className="monitor-field">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ActiveRequest({ request }: { request: LocalLlmDiagnosticRecord | null }) {
  if (!request) {
    return (
      <SectionCard title="Active request" data-testid="local-llm-active-request">
        <EmptyState
          title="No active local LLM request"
          description="The next local preflight call will appear here while it is running."
        />
      </SectionCard>
    );
  }
  return (
    <SectionCard
      title="Active request"
      actions={<StatusBadge variant={statusVariant(request.status)}>{request.status}</StatusBadge>}
      data-testid="local-llm-active-request"
    >
      <FieldList
        rows={[
          ["Run", request.run_id ?? "unknown"],
          ["Step", request.step ?? "unknown"],
          ["Provider", request.provider],
          ["Model", request.model],
          ["Endpoint", `${request.endpoint_host} ${request.endpoint_path}`],
          ["Started", formatTime(request.started_at)],
          ["Elapsed", formatDuration(request.elapsed_ms)],
          ["Status", request.status],
        ]}
      />
    </SectionCard>
  );
}

function RequestOptions({ request }: { request: LocalLlmDiagnosticRecord | null }) {
  return (
    <SectionCard title="Request options" data-testid="local-llm-request-options">
      <FieldList
        rows={[
          ["Configured budget", valueOrUnknown(request?.configured_context_budget_tokens, " tokens")],
          ["Estimated input", valueOrUnknown(request?.estimated_input_tokens, " tokens")],
          ["Requested num_ctx", valueOrUnknown(request?.requested_num_ctx)],
          ["num_predict", valueOrUnknown(request?.num_predict)],
          ["Temperature", valueOrUnknown(request?.temperature)],
          ["Stream", request ? yesNo(request.stream) : "unknown"],
        ]}
      />
    </SectionCard>
  );
}

function LiveGeneration({ request }: { request: LocalLlmDiagnosticRecord | null }) {
  const lastTokenAge = useMemo(() => {
    if (!request?.last_chunk_at) return "unknown";
    const ageMs = Date.now() - new Date(request.last_chunk_at).getTime();
    if (Number.isNaN(ageMs)) return "unknown";
    return `${Math.max(0, ageMs / 1000).toFixed(1)}s`;
  }, [request]);
  return (
    <SectionCard title="Live generation" data-testid="local-llm-live-generation">
      <FieldList
        rows={[
          [
            "Prompt eval",
            request?.prompt_eval_count
              ? `done / ${request.prompt_eval_count} tokens / ${formatDuration(request.prompt_eval_duration_ms)}`
              : "pending",
          ],
          ["Generated", `${request?.eval_count || request?.approx_generated_tokens || 0} tokens`],
          ["Tokens/sec", valueOrUnknown(request?.tokens_per_second)],
          ["Thinking detected", request ? yesNo(request.thinking_detected) : "unknown"],
          ["Content detected", request ? yesNo(request.content_detected) : "unknown"],
          ["Last token age", lastTokenAge],
        ]}
      />
    </SectionCard>
  );
}

function ServerContext({ request }: { request: LocalLlmDiagnosticRecord | null }) {
  return (
    <SectionCard title="Server / context" data-testid="local-llm-server-context">
      <FieldList
        rows={[
          [
            "Server-reported max context",
            valueOrUnknown(request?.server_reported_context_tokens, " tokens"),
          ],
          ["Requested num_ctx", valueOrUnknown(request?.requested_num_ctx)],
          [
            "Active runner context",
            valueOrUnknown(request?.active_runner_context_tokens, " tokens"),
          ],
          ["Trust status", request?.context_trust_status ?? "unverified"],
          ["Manual check", "run `ollama ps` on the Ollama server"],
        ]}
      />
    </SectionCard>
  );
}

function EventTimeline({ events }: { events: LocalLlmDiagnosticEvent[] }) {
  return (
    <SectionCard title="Event timeline" data-testid="local-llm-event-timeline">
      {events.length === 0 ? (
        <EmptyState title="No diagnostic events yet" />
      ) : (
        <ol className="monitor-events">
          {events.slice(0, 30).map((event) => (
            <li key={event.event_id}>
              <time>{formatTime(event.created_at)}</time>
              <span>{event.message}</span>
            </li>
          ))}
        </ol>
      )}
    </SectionCard>
  );
}

function RecentRequests({ requests }: { requests: LocalLlmDiagnosticRecord[] }) {
  return (
    <SectionCard title="Recent local LLM requests" data-testid="local-llm-recent-requests">
      {requests.length === 0 ? (
        <EmptyState title="No recent local LLM requests" />
      ) : (
        <div className="monitor-table-wrap">
          <table className="monitor-table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Run</th>
                <th>Step</th>
                <th>Status</th>
                <th>Timeout</th>
                <th>Thinking</th>
                <th>Content</th>
                <th>Request</th>
              </tr>
            </thead>
            <tbody>
              {requests.slice(0, 20).map((request) => (
                <tr key={request.request_id}>
                  <td>{formatTime(request.started_at)}</td>
                  <td>{request.run_id ?? "unknown"}</td>
                  <td>{request.step ?? "unknown"}</td>
                  <td>{request.status}</td>
                  <td>{request.timeout_kind ?? request.fallback_reason ?? ""}</td>
                  <td>{yesNo(request.thinking_detected)}</td>
                  <td>{yesNo(request.content_detected)}</td>
                  <td className="mono">{request.request_id.slice(0, 8)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

function DegradedState({
  snapshot,
}: {
  snapshot: LocalLlmDiagnosticsSnapshot;
}) {
  if (snapshot.provider_degraded.length === 0) return null;
  return (
    <SectionCard title="Provider degraded state" data-testid="local-llm-degraded">
      <ul className="monitor-degraded">
        {snapshot.provider_degraded.map((item) => (
          <li key={`${item.run_id ?? "global"}-${item.updated_at}`}>
            local provider marked degraded after {item.timeout_failures} timeout failures
            {item.reason ? `: ${item.reason}` : ""}
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

export function LocalLlmMonitorPage() {
  const [snapshot, setSnapshot] = useState<LocalLlmDiagnosticsSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const next = await getLocalLlmDiagnostics();
        if (cancelled) return;
        setSnapshot(next);
        setError(null);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load diagnostics");
      }
    }
    void load();
    const id = setInterval(load, LOCAL_LLM_MONITOR_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const active = snapshot?.active_request ?? null;
  const selected = active ?? snapshot?.recent_requests[0] ?? null;

  return (
    <div className="local-llm-monitor-page">
      <PageHeader
        title="Local LLM Monitor"
        description="Live diagnostics for experimental local LLM preflight requests."
        actions={<Link to="/settings">Local LLM settings</Link>}
      />
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      <div className="monitor-grid">
        <ActiveRequest request={active} />
        <RequestOptions request={selected} />
        <LiveGeneration request={selected} />
        <ServerContext request={selected} />
      </div>
      {snapshot ? (
        <>
          <DegradedState snapshot={snapshot} />
          <EventTimeline events={snapshot.recent_events} />
          <RecentRequests requests={snapshot.recent_requests} />
        </>
      ) : null}
    </div>
  );
}
