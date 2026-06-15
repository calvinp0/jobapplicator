import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { getLocalLlmDiagnosticsMock } = vi.hoisted(() => ({
  getLocalLlmDiagnosticsMock: vi.fn(),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getLocalLlmDiagnostics: getLocalLlmDiagnosticsMock,
  };
});

import { LocalLlmMonitorPage } from "../pages/LocalLlmMonitorPage";
import { ProviderTracePanel } from "../components/ProviderTrace";

const activeRequest = {
  request_id: "abc12345-0000-0000-0000-000000000000",
  run_id: "run-1",
  step: "ats_keywords",
  provider: "local_ollama",
  model: "qwen3.5:9b",
  endpoint_host: "100.104.129.123:11434",
  endpoint_path: "/api/chat",
  status: "running",
  started_at: "2026-06-15T09:14:21Z",
  completed_at: null,
  elapsed_ms: 252000,
  configured_context_budget_tokens: 16000,
  usable_input_budget_tokens: 14800,
  estimated_input_tokens: 3842,
  requested_num_ctx: 16000,
  num_ctx_sent: true,
  num_predict: 384,
  temperature: 0,
  stream: true,
  server_reported_context_tokens: 262144,
  active_runner_context_tokens: null,
  context_trust_status: "unverified",
  time_to_first_chunk_ms: 32000,
  time_to_first_content_ms: null,
  prompt_eval_count: 3842,
  prompt_eval_duration_ms: 31200,
  eval_count: 187,
  eval_duration_ms: 66785,
  total_duration_ms: 98000,
  load_duration_ms: 10,
  tokens_per_second: 2.8,
  approx_generated_chars: 748,
  approx_generated_tokens: 187,
  thinking_detected: true,
  content_detected: false,
  last_chunk_at: "2026-06-15T09:18:32Z",
  fallback_used: false,
  fallback_reason: null,
  error: null,
  timeout_kind: null,
};

function snapshot(overrides = {}) {
  return {
    active_request: activeRequest,
    active_requests: [activeRequest],
    recent_requests: [activeRequest],
    recent_events: [
      {
        event_id: "event-1",
        request_id: activeRequest.request_id,
        run_id: "run-1",
        step: "ats_keywords",
        created_at: "2026-06-15T09:14:53Z",
        message: "thinking stream started",
        kind: "info",
      },
      {
        event_id: "event-2",
        request_id: activeRequest.request_id,
        run_id: "run-1",
        step: "ats_keywords",
        created_at: "2026-06-15T09:24:21Z",
        message: "generation_timeout; fallback used",
        kind: "fallback",
      },
    ],
    provider_degraded: [
      {
        run_id: "run-1",
        degraded: true,
        reason: "generation timed out",
        timeout_failures: 2,
        updated_at: "2026-06-15T09:24:22Z",
      },
    ],
    ...overrides,
  };
}

function renderMonitor() {
  return render(
    <MemoryRouter>
      <LocalLlmMonitorPage />
    </MemoryRouter>,
  );
}

describe("LocalLlmMonitorPage", () => {
  beforeEach(() => {
    getLocalLlmDiagnosticsMock.mockResolvedValue(snapshot());
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("displays the active request and live metrics", async () => {
    renderMonitor();

    expect(await screen.findByRole("heading", { name: "Local LLM Monitor" })).toBeInTheDocument();
    const active = screen.getByTestId("local-llm-active-request");
    expect(within(active).getByText("run-1")).toBeInTheDocument();
    expect(within(active).getByText("qwen3.5:9b")).toBeInTheDocument();
    expect(within(active).getByText("100.104.129.123:11434 /api/chat")).toBeInTheDocument();

    const options = screen.getByTestId("local-llm-request-options");
    expect(within(options).getByText("16000 tokens")).toBeInTheDocument();
    expect(within(options).getByText("3842 tokens")).toBeInTheDocument();
    expect(within(options).getByText("384")).toBeInTheDocument();

    const live = screen.getByTestId("local-llm-live-generation");
    expect(within(live).getByText("187 tokens")).toBeInTheDocument();
    expect(within(live).getByText("2.8")).toBeInTheDocument();
    expect(within(live).getByText("yes")).toBeInTheDocument();
    expect(within(live).getByText("no")).toBeInTheDocument();
  });

  it("renders events, fallback, and degraded state without raw secrets", async () => {
    renderMonitor();

    const timeline = await screen.findByTestId("local-llm-event-timeline");
    expect(within(timeline).getByText("thinking stream started")).toBeInTheDocument();
    expect(within(timeline).getByText("generation_timeout; fallback used")).toBeInTheDocument();
    expect(screen.getByTestId("local-llm-degraded")).toHaveTextContent(
      "local provider marked degraded after 2 timeout failures",
    );
    expect(screen.queryByText(/raw prompt/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/api key/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/private reasoning/i)).not.toBeInTheDocument();
  });
});

describe("ProviderTracePanel diagnostics link", () => {
  it("links local fallback rows to the monitor", () => {
    render(
      <MemoryRouter>
        <ProviderTracePanel
          trace={[
            {
              step: "ats_keywords",
              label: "ATS keywords",
              provider: "ollama",
              provider_label: "Ollama",
              model: "qwen3.5:9b",
              status: "fallback",
              fallback_used: true,
              warning: "Local LLM step fell back to deterministic extractor: generation timeout",
              details: { diagnostic_request_id: "abc12345-0000" },
            },
          ]}
        />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: /open local llm diagnostics/i });
    expect(link).toHaveAttribute("href", "/admin/local-llm");
    expect(screen.getByText(/request abc12345/i)).toBeInTheDocument();
  });
});
