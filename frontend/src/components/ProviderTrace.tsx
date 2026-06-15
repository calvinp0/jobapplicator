import type { ProviderSummary, ProviderTraceEvent } from "../api/types";
import { Link } from "react-router-dom";

/**
 * Provider/run trace display (task 129).
 *
 * Three levels of visibility, kept deliberately compact:
 *   1. an always-visible one-line provider summary;
 *   2. a collapsed-by-default "Run trace" disclosure with per-step rows;
 *   3. a nested "Details" disclosure per row for advanced/technical fields
 *      (context budget, requested num_ctx, server-reported context, …).
 *
 * No large diagnostics panel, no per-step colour pills, no endpoint URLs in
 * the default view — only the host (when present) shows behind the nested
 * details, and credentials never reach the client at all.
 */

function formatDuration(ms?: number | null): string {
  if (ms == null) return "";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

function providerModel(event: ProviderTraceEvent): string {
  return event.model
    ? `${event.provider_label} / ${event.model}`
    : event.provider_label;
}

function hasAdvancedDetails(event: ProviderTraceEvent): boolean {
  return Boolean(event.details && Object.keys(event.details).length > 0);
}

function ProviderTraceRow({ event }: { event: ProviderTraceEvent }) {
  const details = event.details ?? {};
  return (
    <li
      className="provider-trace-row"
      data-testid={`provider-trace-row-${event.step}`}
    >
      <div className="provider-trace-row-main">
        <span className="provider-trace-step">{event.label}</span>
        <span className="provider-trace-provider">{providerModel(event)}</span>
        <span
          className={`provider-trace-status provider-trace-status-${event.status}`}
        >
          {event.status}
        </span>
        <span className="provider-trace-duration">
          {formatDuration(event.duration_ms)}
        </span>
      </div>
      {event.warning ? (
        <p className="provider-trace-row-warning">{event.warning}</p>
      ) : null}
      {details.diagnostic_request_id || event.warning?.toLowerCase().includes("local llm") ? (
        <p className="provider-trace-diagnostics-link">
          <Link to="/admin/local-llm">Open Local LLM diagnostics</Link>
          {details.diagnostic_request_id ? (
            <span> request {details.diagnostic_request_id.slice(0, 8)}</span>
          ) : null}
        </p>
      ) : null}
      {hasAdvancedDetails(event) ? (
        <details className="provider-trace-advanced">
          <summary>Details</summary>
          <dl className="provider-trace-advanced-list">
            <dt>Provider</dt>
            <dd>{event.provider}</dd>
            {event.model ? (
              <>
                <dt>Model</dt>
                <dd>{event.model}</dd>
              </>
            ) : null}
            {details.endpoint_host ? (
              <>
                <dt>Endpoint host</dt>
                <dd>{details.endpoint_host}</dd>
              </>
            ) : null}
            {details.context_budget_tokens != null ? (
              <>
                <dt>Context budget</dt>
                <dd>{details.context_budget_tokens} tokens</dd>
              </>
            ) : null}
            {details.usable_input_tokens != null ? (
              <>
                <dt>Usable input</dt>
                <dd>{details.usable_input_tokens} tokens</dd>
              </>
            ) : null}
            {details.requested_num_ctx != null ? (
              <>
                <dt>Requested num_ctx</dt>
                <dd>{details.requested_num_ctx}</dd>
              </>
            ) : null}
            {details.server_reported_context_tokens != null ? (
              <>
                <dt>Server context</dt>
                <dd>{details.server_reported_context_tokens} tokens</dd>
              </>
            ) : null}
            {details.context_verified != null ? (
              <>
                <dt>Context verified</dt>
                <dd>{details.context_verified ? "yes" : "no"}</dd>
              </>
            ) : null}
            {event.compression_used ? (
              <>
                <dt>Compression</dt>
                <dd>used</dd>
              </>
            ) : null}
            {event.fallback_used ? (
              <>
                <dt>Fallback</dt>
                <dd>used</dd>
              </>
            ) : null}
          </dl>
        </details>
      ) : null}
    </li>
  );
}

/**
 * Run-detail provider trace: compact summary line + collapsed "Run trace"
 * disclosure. Renders nothing when there is no trace at all (older runs).
 */
export function ProviderTracePanel({
  summary,
  trace,
}: {
  summary?: ProviderSummary | null;
  trace?: ProviderTraceEvent[];
}) {
  const rows = trace ?? [];
  if (!summary && rows.length === 0) return null;
  return (
    <section className="provider-trace" data-testid="provider-trace">
      {summary?.label ? (
        <p
          className="provider-trace-summary"
          data-testid="provider-trace-summary"
        >
          {summary.label}
        </p>
      ) : null}
      {summary?.has_warnings && summary.warnings && summary.warnings.length ? (
        <p
          className="provider-trace-summary-warning"
          role="status"
          data-testid="provider-trace-summary-warning"
        >
          {summary.warnings.join(" · ")}
        </p>
      ) : null}
      {rows.length > 0 ? (
        <details className="provider-trace-disclosure">
          <summary>Run trace</summary>
          <ul className="provider-trace-rows">
            {rows.map((event) => (
              <ProviderTraceRow key={event.step} event={event} />
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

/**
 * Compact provenance strip for the resume review workspace — a single quiet
 * line that names the providers behind the draft without competing with the
 * document preview or AI review panel.
 */
export function ProvenanceStrip({
  summary,
}: {
  summary?: ProviderSummary | null;
}) {
  if (!summary?.label) return null;
  return (
    <p className="review-provenance" data-testid="review-provenance">
      <span className="review-provenance-label">Generated with:</span>{" "}
      {summary.label}
      {summary.has_warnings && summary.warnings && summary.warnings.length ? (
        <span className="review-provenance-warning">
          {" "}
          · {summary.warnings.join("; ")}
        </span>
      ) : null}
    </p>
  );
}
