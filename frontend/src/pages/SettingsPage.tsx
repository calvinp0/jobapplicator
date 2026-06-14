import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  createEvidenceBank,
  createMasterResume,
  deleteGmailOAuthSettings,
  getExportSettings,
  getGmailAuthUrl,
  getGmailOAuthSettings,
  getGmailStatus,
  getLlmProviderSetting,
  getLocalLlmSettings,
  importEvidenceSourceFile,
  importMasterResumeFile,
  listEvidenceSources,
  listLocalLlmModels,
  listMasterResumes,
  pullLocalLlmModel,
  resetLocalData,
  setGmailOAuthSettings,
  setLlmProviderSetting,
  setLocalLlmSettings,
  testLocalLlmConnection,
} from "../api";
import type {
  EvidenceSource,
  GmailOAuthSettings,
  GmailStatusResponse,
  LlmProvider,
  LocalLlmPullEvent,
  LocalLlmSettings,
  MasterResume,
} from "../api";
import { extractApiDetail } from "../lib/api-errors";
import { Button, PageHeader, SettingsGroup } from "../components/ui";

const DEFAULT_REDIRECT_URI = "http://localhost:8000/gmail/oauth/callback";
const DEFAULT_TOKEN_PATH = "candidate_context/gmail/token.json";

interface SourceListEntry {
  id: string;
  name: string;
  meta: string;
}

type ImportMode = "file" | "manual";

interface ImportPasteCardProps {
  title: string;
  testId: string;
  items: SourceListEntry[] | null;
  emptyLabel: string;
  /** Verb fragment used for the reveal button + submit, e.g. "master resume". */
  addNoun: string;
  /** ``accept`` attribute for the file input, e.g. ".docx,.md,.txt". */
  acceptExtensions: string;
  /** Human description of accepted files shown under the picker. */
  acceptHint: string;
  contentLabel: string;
  onImportFile: (file: File) => Promise<void>;
  onCreateManual: (name: string, content: string) => Promise<void>;
}

/**
 * A settings card that lists app-managed sources and offers two ways to add
 * one: upload a file (copied into candidate_context) or paste content
 * manually. The old free-text "Source path" field is gone — users never type
 * a local path, which browsers cannot reliably expose anyway (task 121).
 */
function ImportPasteCard({
  title,
  testId,
  items,
  emptyLabel,
  addNoun,
  acceptExtensions,
  acceptHint,
  contentLabel,
  onImportFile,
  onCreateManual,
}: ImportPasteCardProps) {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [mode, setMode] = useState<ImportMode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [contentMarkdown, setContentMarkdown] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const addLabel = `Add ${addNoun}`;

  function resetForm() {
    setMode("file");
    setFile(null);
    setName("");
    setContentMarkdown("");
    setSubmitError(null);
  }

  function handleCancel() {
    resetForm();
    setIsFormOpen(false);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);

    if (mode === "file") {
      if (!file) {
        setSubmitError("Choose a file to upload.");
        return;
      }
    } else if (!name.trim() || !contentMarkdown.trim()) {
      setSubmitError("Name and content are required.");
      return;
    }

    setIsSubmitting(true);
    try {
      if (mode === "file" && file) {
        await onImportFile(file);
      } else {
        await onCreateManual(name.trim(), contentMarkdown);
      }
      resetForm();
      setIsFormOpen(false);
    } catch (err: unknown) {
      setSubmitError(extractApiDetail(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="settings-card" data-testid={testId}>
      <header className="settings-card-header">
        <h3>{title}</h3>
        {!isFormOpen ? (
          <button
            type="button"
            className="button button-secondary"
            onClick={() => setIsFormOpen(true)}
          >
            {`+ ${addLabel}`}
          </button>
        ) : null}
      </header>

      {items === null ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
        <p className="settings-empty">{emptyLabel}</p>
      ) : (
        <ul className="settings-list">
          {items.map((item) => (
            <li key={item.id} className="settings-list-item">
              <strong>{item.name}</strong>
              <span className="settings-meta">{item.meta}</span>
            </li>
          ))}
        </ul>
      )}

      {isFormOpen ? (
        <form onSubmit={handleSubmit} noValidate className="settings-card-form">
          <fieldset className="settings-mode-toggle">
            <legend>How do you want to add it?</legend>
            <label>
              <input
                type="radio"
                name={`${testId}-mode`}
                value="file"
                checked={mode === "file"}
                onChange={() => {
                  setMode("file");
                  setSubmitError(null);
                }}
              />
              <span>Upload a source file</span>
            </label>
            <label>
              <input
                type="radio"
                name={`${testId}-mode`}
                value="manual"
                checked={mode === "manual"}
                onChange={() => {
                  setMode("manual");
                  setSubmitError(null);
                }}
              />
              <span>Paste content manually</span>
            </label>
          </fieldset>

          {mode === "file" ? (
            <label className="field">
              <span>Source file</span>
              <input
                type="file"
                accept={acceptExtensions}
                aria-label="Source file"
                data-testid={`${testId}-file-input`}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setSubmitError(null);
                }}
              />
              {file ? (
                <span className="settings-meta" data-testid={`${testId}-filename`}>
                  {file.name}
                </span>
              ) : (
                <span className="settings-helper">{acceptHint}</span>
              )}
            </label>
          ) : (
            <>
              <label className="field">
                <span>Name</span>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>{contentLabel}</span>
                <textarea
                  value={contentMarkdown}
                  rows={8}
                  onChange={(e) => setContentMarkdown(e.target.value)}
                  required
                />
              </label>
            </>
          )}

          {submitError ? (
            <p role="alert" className="error">
              {submitError}
            </p>
          ) : null}

          <div className="settings-card-form-actions">
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? mode === "file"
                  ? "Importing…"
                  : "Saving…"
                : mode === "file"
                  ? `Import ${addNoun}`
                  : addLabel}
            </button>
            <button
              type="button"
              className="button button-secondary"
              onClick={handleCancel}
              disabled={isSubmitting}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}

function DangerZoneCard() {
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [isResetting, setIsResetting] = useState(false);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function openDialog() {
    setConfirmText("");
    setErrorMessage(null);
    setResultMessage(null);
    setIsDialogOpen(true);
  }

  function closeDialog() {
    setIsDialogOpen(false);
    setConfirmText("");
    setErrorMessage(null);
  }

  async function handleConfirm() {
    if (confirmText !== "RESET") return;
    setIsResetting(true);
    setErrorMessage(null);
    try {
      const result = await resetLocalData("RESET");
      const summary = Object.entries(result.deleted)
        .map(([key, count]) => `${count} ${key}`)
        .join(", ");
      setResultMessage(
        `Local data reset. Deleted ${summary}.` +
          (result.backup_path
            ? ` A backup was saved to ${result.backup_path}.`
            : ""),
      );
      setIsDialogOpen(false);
      setConfirmText("");
    } catch (err: unknown) {
      setErrorMessage(extractApiDetail(err));
    } finally {
      setIsResetting(false);
    }
  }

  return (
    <section className="settings-card" data-testid="danger-zone-card">
      <header className="settings-card-header">
        <h3>Reset local data</h3>
      </header>
      <p className="settings-helper">
        This will delete local jobs, applications, runs, captures, drafts, and
        generated artifacts, and clear Gmail tracking state. It will not delete
        your master resumes, evidence banks, or any source files outside
        JobApplicator. A timestamped database backup is created first.
      </p>

      {resultMessage ? (
        <p role="status" className="settings-success">
          {resultMessage}
        </p>
      ) : null}

      {!isDialogOpen ? (
        <div className="settings-card-form-actions">
          <button
            type="button"
            className="button button-danger"
            onClick={openDialog}
            data-testid="reset-local-data-button"
          >
            Reset local data
          </button>
        </div>
      ) : null}

      {isDialogOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Reset local data"
          className="settings-confirm-dialog"
          data-testid="reset-confirm-dialog"
        >
          <p>
            This permanently deletes local jobs, applications, runs, captures,
            and drafts. This cannot be undone (except by restoring the backup).
          </p>
          <label className="field">
            <span>Type RESET to confirm.</span>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              aria-label="Type RESET to confirm"
              autoComplete="off"
            />
          </label>

          {errorMessage ? (
            <p role="alert" className="error">
              {errorMessage}
            </p>
          ) : null}

          <div className="settings-card-form-actions">
            <button
              type="button"
              className="button button-danger"
              onClick={handleConfirm}
              disabled={confirmText !== "RESET" || isResetting}
              data-testid="reset-confirm-button"
            >
              {isResetting ? "Resetting…" : "Reset local data"}
            </button>
            <button
              type="button"
              className="button button-secondary"
              onClick={closeDialog}
              disabled={isResetting}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function LlmProviderCard() {
  const [providers, setProviders] = useState<LlmProvider[] | null>(null);
  const [selectedId, setSelectedId] = useState<string>("");
  const [savedId, setSavedId] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getLlmProviderSetting()
      .then((data) => {
        if (cancelled) return;
        setProviders(data.available);
        setSelectedId(data.default_provider);
        setSavedId(data.default_provider);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(extractApiDetail(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || selectedId === savedId) return;
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      const updated = await setLlmProviderSetting(selectedId);
      setProviders(updated.available);
      setSavedId(updated.default_provider);
      setSelectedId(updated.default_provider);
      setSaveSuccess("Saved.");
    } catch (err: unknown) {
      setSaveError(extractApiDetail(err));
    } finally {
      setIsSaving(false);
    }
  }

  const isDirty = selectedId !== "" && selectedId !== savedId;

  return (
    <section className="settings-card">
      <header className="settings-card-header">
        <h3>Tailoring LLM</h3>
      </header>

      <p className="settings-helper">
        Controls which CLI-based LLM the "Generate Automatically" flow
        invokes for new runs. The Claude for Word handoff is unaffected.
      </p>

      {loadError ? (
        <p role="alert" className="error">
          {loadError}
        </p>
      ) : providers === null ? (
        <p>Loading…</p>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="settings-card-form">
          <label className="field">
            <span>Default provider</span>
            <select
              value={selectedId}
              onChange={(e) => {
                setSelectedId(e.target.value);
                setSaveSuccess(null);
                setSaveError(null);
              }}
              disabled={isSaving}
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {`${p.display_name} (${p.id})`}
                </option>
              ))}
            </select>
          </label>

          {saveError ? (
            <p role="alert" className="error">
              {saveError}
            </p>
          ) : null}
          {saveSuccess ? (
            <p role="status" className="settings-success">
              {saveSuccess}
            </p>
          ) : null}

          <div className="settings-card-form-actions">
            <button type="submit" disabled={isSaving || !isDirty}>
              {isSaving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

// Human labels for the toggleable local-LLM tasks. Order is driven by the
// backend's task_policy so high-risk tasks render last.
const LOCAL_TASK_LABELS: Record<string, string> = {
  job_summary: "Job summary",
  ats_keywords: "ATS keyword extraction",
  role_requirements: "Role requirement extraction",
  evidence_gap_plan: "Evidence gap planning",
  email_classification: "Email classification",
  resume_suggestions: "Resume suggestions (experimental)",
  resume_tailoring: "Full resume tailoring (experimental)",
  claim_audit: "Claim audit (experimental)",
};

// Disk/VRAM-unknown advisory shown before and during a model pull (task 139).
// It mirrors the backend's ``PULL_DISK_VRAM_ADVISORY`` (task 137), which is also
// streamed as the first line of the pull response, so the warning is visible at
// confirmation time even before the stream starts.
const PULL_DISK_VRAM_ADVISORY =
  "The backend cannot verify whether this model will fit the host's available " +
  "disk or VRAM. The pull may fail partway, fill the disk, or download a model " +
  "the host cannot actually run.";

/**
 * Turn a classified connection failure (task 136) into a distinct, actionable
 * message. The backend tags each failure with a stable ``error_kind`` so the
 * UI can explain *why* the test failed instead of echoing a raw transport
 * error. Unknown / ``unexpected`` kinds fall back to the underlying detail.
 */
function describeConnectionFailure(
  errorKind: string | null,
  detail: string,
  model: string,
  installedModels: string[],
): string {
  switch (errorKind) {
    case "endpoint_unavailable":
      return `Could not reach the server. Check the host and port and that the local LLM server is running. (${detail})`;
    case "bad_url":
      return `The endpoint looks wrong: the host is reachable but the API path was not found. Check the base URL and the selected provider — for the OpenAI-compatible provider the base URL must include /v1. (${detail})`;
    case "model_not_installed": {
      const installed = installedModels.length
        ? installedModels.join(", ")
        : "(none)";
      return `Model "${model}" is not installed on this Ollama server. Installed: ${installed}. Pick an installed model below or pull it.`;
    }
    default:
      return detail;
  }
}

/**
 * Experimental local LLM provider card (task 123).
 *
 * Lets the user point the app at a local OpenAI-compatible endpoint
 * (Ollama, vLLM, LM Studio, …) for *low-risk* tasks only. Full resume
 * tailoring and claim audits default to off and are clearly flagged as
 * experimental; Claude Code remains the default for those.
 */
function LocalLlmCard() {
  const [settings, setSettings] = useState<LocalLlmSettings | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [provider, setProvider] = useState("openai_compatible");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState(60);
  const [contextWindowTokens, setContextWindowTokens] = useState(8192);
  const [reservedOutputTokens, setReservedOutputTokens] = useState(1200);
  const [maxInputTokens, setMaxInputTokens] = useState(6500);
  // Kept as a string so the input can distinguish "blank = unset (null)"
  // from an explicit number.
  const [numCtx, setNumCtx] = useState("");
  // Optional output cap (task 140). Same blank-means-unset string handling as
  // numCtx so an empty field round-trips as null ("use the server's limit").
  const [maxOutputTokens, setMaxOutputTokens] = useState("");
  const [allowCompression, setAllowCompression] = useState(true);
  const [allowFallback, setAllowFallback] = useState(true);
  const [abortOnOverBudget, setAbortOnOverBudget] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [allowedTasks, setAllowedTasks] = useState<Record<string, boolean>>({});

  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
    errorKind: string | null;
    installedModels: string[];
    serverReportedContextTokens: number | null;
    contextVerified: boolean;
    contextWarning: string | null;
  } | null>(null);

  // Installed-model listing (task 135). Populated by the "List models" button
  // (or by a model_not_installed test failure, which carries the list too) so
  // the picker can offer real models instead of free text. ``modelsListed``
  // distinguishes "not listed yet" from "listed and empty".
  const [installedModels, setInstalledModels] = useState<string[]>([]);
  const [isListingModels, setIsListingModels] = useState(false);
  const [modelsListed, setModelsListed] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);

  // Explicit, confirmation-gated model pull (task 139). The pull is offered
  // only for the Ollama-native provider and never fires on the first click:
  // ``pullConfirming`` shows the confirm step (with the disk/VRAM warning) and
  // only "Confirm pull" sends the request. ``pullStatus`` / ``pullProgress``
  // are driven by the streamed progress events; ``pullResult`` is the terminal
  // state; ``pullError`` carries a request-level failure (e.g. a 409 refusal).
  const [pullConfirming, setPullConfirming] = useState(false);
  const [isPulling, setIsPulling] = useState(false);
  const [pullStatus, setPullStatus] = useState<string | null>(null);
  const [pullProgress, setPullProgress] = useState<{
    completed: number | null;
    total: number | null;
  } | null>(null);
  const [pullResult, setPullResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);
  const [pullError, setPullError] = useState<string | null>(null);

  function clearModels() {
    setInstalledModels([]);
    setModelsListed(false);
    setModelsError(null);
  }

  function resetPull() {
    setPullConfirming(false);
    setPullStatus(null);
    setPullProgress(null);
    setPullResult(null);
    setPullError(null);
  }

  function applySettings(data: LocalLlmSettings) {
    setSettings(data);
    setEnabled(data.enabled);
    setProvider(data.provider);
    setBaseUrl(data.base_url);
    setModel(data.model);
    setTimeoutSeconds(data.timeout_seconds);
    setContextWindowTokens(data.context_window_tokens ?? 8192);
    setReservedOutputTokens(data.reserved_output_tokens ?? 1200);
    setMaxInputTokens(data.max_input_tokens ?? 6500);
    setNumCtx(data.num_ctx != null ? String(data.num_ctx) : "");
    setMaxOutputTokens(
      data.max_output_tokens != null ? String(data.max_output_tokens) : "",
    );
    setAllowCompression(data.allow_compression ?? true);
    setAllowFallback(data.allow_fallback ?? true);
    setAbortOnOverBudget(data.abort_on_over_budget ?? false);
    setAllowedTasks(data.allowed_tasks);
    setApiKey("");
  }

  useEffect(() => {
    let cancelled = false;
    getLocalLlmSettings()
      .then((data) => {
        if (cancelled) return;
        applySettings(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(extractApiDetail(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function clearFeedback() {
    setSaveSuccess(null);
    setSaveError(null);
    setTestResult(null);
  }

  // Blank means "unset": the server keeps its own default context length.
  const parsedNumCtx = numCtx.trim() === "" ? null : Number(numCtx);
  // Blank means "unset": the server keeps its own output limit.
  const parsedMaxOutputTokens =
    maxOutputTokens.trim() === "" ? null : Number(maxOutputTokens);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const computedMax = contextWindowTokens - reservedOutputTokens;
    if (computedMax <= 0) {
      setSaveError(
        "Reserved output tokens must be smaller than context window tokens.",
      );
      setSaveSuccess(null);
      return;
    }
    if (maxInputTokens <= 0 || maxInputTokens > computedMax) {
      setSaveError(
        "Max input tokens must be positive and no larger than context minus reserved output.",
      );
      setSaveSuccess(null);
      return;
    }
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      const updated = await setLocalLlmSettings({
        enabled,
        provider,
        base_url: baseUrl,
        model,
        timeout_seconds: timeoutSeconds,
        context_window_tokens: contextWindowTokens,
        reserved_output_tokens: reservedOutputTokens,
        max_input_tokens: maxInputTokens,
        num_ctx: parsedNumCtx,
        max_output_tokens: parsedMaxOutputTokens,
        allow_compression: allowCompression,
        allow_fallback: allowFallback,
        abort_on_over_budget: abortOnOverBudget,
        allowed_tasks: allowedTasks,
        api_key: apiKey ? apiKey : null,
        preserve_existing_key: !apiKey,
      });
      applySettings(updated);
      setSaveSuccess("Saved.");
    } catch (err: unknown) {
      setSaveError(extractApiDetail(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTestConnection() {
    setIsTesting(true);
    setTestResult(null);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      const result = await testLocalLlmConnection({
        base_url: baseUrl,
        model,
        timeout_seconds: timeoutSeconds,
        context_window_tokens: contextWindowTokens,
        reserved_output_tokens: reservedOutputTokens,
        max_input_tokens: maxInputTokens,
        num_ctx: parsedNumCtx,
        provider,
        api_key: apiKey ? apiKey : null,
        preserve_existing_key: !apiKey,
      });
      const installed = result.installed_models ?? [];
      setTestResult({
        ok: result.ok,
        message: result.ok
          ? result.message
          : result.error || result.message,
        errorKind: result.error_kind ?? null,
        installedModels: installed,
        serverReportedContextTokens:
          result.server_reported_context_tokens ?? null,
        contextVerified: Boolean(result.context_verified),
        contextWarning: result.context_warning ?? null,
      });
      // A model_not_installed failure carries the server's installed models, so
      // surface them in the picker too — that is exactly the list the user
      // needs to fix the problem.
      if (!result.ok && installed.length > 0) {
        setInstalledModels(installed);
        setModelsListed(true);
        setModelsError(null);
      }
    } catch (err: unknown) {
      setTestResult({
        ok: false,
        message: extractApiDetail(err),
        errorKind: null,
        installedModels: [],
        serverReportedContextTokens: null,
        contextVerified: false,
        contextWarning: null,
      });
    } finally {
      setIsTesting(false);
    }
  }

  async function handleListModels() {
    setIsListingModels(true);
    setModelsError(null);
    setModelsListed(false);
    try {
      const result = await listLocalLlmModels({
        base_url: baseUrl,
        provider,
      });
      if (result.ok) {
        setInstalledModels(result.models);
        setModelsListed(true);
      } else {
        setInstalledModels([]);
        setModelsListed(true);
        setModelsError(
          result.error_kind === "unsupported"
            ? "Listing installed models is only available for the Ollama provider. Switch the provider to Ollama, or type a model name below."
            : result.error || "Could not list installed models.",
        );
      }
    } catch (err: unknown) {
      setInstalledModels([]);
      setModelsListed(true);
      setModelsError(extractApiDetail(err));
    } finally {
      setIsListingModels(false);
    }
  }

  // Step 1 of the gated pull: reveal the confirmation step. No request is sent
  // here — only "Confirm pull" actually contacts the server.
  function requestPull() {
    clearFeedback();
    setPullResult(null);
    setPullError(null);
    setPullStatus(null);
    setPullProgress(null);
    setPullConfirming(true);
  }

  // Step 2: the user confirmed, so issue the explicit pull and render the
  // streamed progress. Refreshes the installed-model list on success so the
  // newly installed model appears in the picker.
  async function handleConfirmPull() {
    const target = model.trim();
    if (!target) {
      setPullError("Enter a model name to pull.");
      return;
    }
    setPullConfirming(false);
    setIsPulling(true);
    setPullStatus(null);
    setPullProgress(null);
    setPullResult(null);
    setPullError(null);
    let pulledOk = false;
    try {
      await pullLocalLlmModel(
        {
          model: target,
          provider,
          base_url: baseUrl,
          api_key: apiKey ? apiKey : null,
          preserve_existing_key: !apiKey,
        },
        (event: LocalLlmPullEvent) => {
          if (event.type === "progress") {
            setPullStatus(event.status);
            setPullProgress({
              completed: event.completed,
              total: event.total,
            });
          } else if (event.type === "result") {
            pulledOk = event.ok;
            setPullResult({
              ok: event.ok,
              message: event.ok
                ? `Pulled "${target}". It is now installed on this server.`
                : event.error ||
                  "The pull failed. Check the model name and the server.",
            });
          }
        },
      );
    } catch (err: unknown) {
      setPullError(extractApiDetail(err));
    } finally {
      setIsPulling(false);
    }
    // Refresh the installed-model list on success so the newly installed model
    // surfaces in the picker. Best-effort: a listing failure is shown inline.
    if (pulledOk) {
      void handleListModels();
    }
  }

  const configurableTasks = (settings?.task_policy ?? []).filter(
    (t) => t.configurable,
  );
  const usableBudget = Math.max(0, maxInputTokens);
  const smallContext = contextWindowTokens < 4096;
  // Percent complete for the pull progress bar, when the server reports byte
  // totals. Null leaves the bar indeterminate (Ollama omits totals for the
  // manifest/verify phases).
  const pullPercent =
    pullProgress && pullProgress.total
      ? Math.min(
          100,
          Math.floor(((pullProgress.completed ?? 0) / pullProgress.total) * 100),
        )
      : null;

  return (
    <section className="settings-card" data-testid="local-llm-card">
      <header className="settings-card-header">
        <h3>Local LLM (experimental)</h3>
      </header>

      <p className="settings-helper" role="note">
        Local LLM support is experimental. High-risk outputs such as final
        resume tailoring and claim audits should use Claude Code unless you
        review carefully.
      </p>
      <p className="settings-helper">
        Local models have limited context windows. JobApplicator will estimate
        prompt size before each local call and will compress, fall back, or
        abort rather than silently truncate inputs.
      </p>

      {loadError ? (
        <p role="alert" className="error">
          {loadError}
        </p>
      ) : settings === null ? (
        <p>Loading…</p>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="settings-card-form">
          <label className="field-inline">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => {
                setEnabled(e.target.checked);
                clearFeedback();
              }}
            />
            <span>Enable local LLM (experimental)</span>
          </label>

          <label className="field">
            <span>Provider</span>
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                clearFeedback();
                clearModels();
                resetPull();
              }}
            >
              <option value="openai_compatible">OpenAI-compatible</option>
              <option value="ollama">Ollama</option>
            </select>
          </label>

          <label className="field">
            <span>Local LLM endpoint</span>
            <input
              type="text"
              value={baseUrl}
              placeholder={
                provider === "ollama"
                  ? "http://localhost:11434"
                  : "http://localhost:11434/v1"
              }
              onChange={(e) => {
                setBaseUrl(e.target.value);
                clearFeedback();
                clearModels();
                resetPull();
              }}
            />
          </label>
          <p className="settings-helper">
            {provider === "ollama" ? (
              <>
                Ollama provider: use the server base URL like{" "}
                <code>http://localhost:11434</code>. The backend calls Ollama&apos;s
                native <code>/api/chat</code> endpoint.
              </>
            ) : (
              <>
                OpenAI-compatible provider: use a base URL like{" "}
                <code>http://localhost:11434/v1</code> (the backend appends{" "}
                <code>/chat/completions</code>). For Ollama&apos;s
                OpenAI-compatible surface the base URL <strong>must</strong>{" "}
                include <code>/v1</code>.
              </>
            )}
          </p>

          <label className="field">
            <span>Model name</span>
            <input
              type="text"
              value={model}
              placeholder="llama3.1:8b"
              onChange={(e) => {
                setModel(e.target.value);
                clearFeedback();
                resetPull();
              }}
            />
          </label>

          <div className="local-llm-models" data-testid="local-llm-models">
            <div className="settings-card-form-actions">
              <button
                type="button"
                onClick={handleListModels}
                disabled={isListingModels}
              >
                {isListingModels ? "Listing…" : "List installed models"}
              </button>
            </div>
            {provider === "openai_compatible" ? (
              <p
                className="settings-helper"
                role="note"
                data-testid="models-unsupported"
              >
                Model listing is Ollama-only — an OpenAI-compatible endpoint has
                no portable way to list installed models. Type the model name
                above to match what your server runs.
              </p>
            ) : null}
            {modelsListed && installedModels.length > 0 ? (
              <label className="field">
                <span>Installed models</span>
                <select
                  data-testid="installed-models-select"
                  value={installedModels.includes(model) ? model : ""}
                  onChange={(e) => {
                    setModel(e.target.value);
                    clearFeedback();
                  }}
                >
                  <option value="">Select an installed model…</option>
                  {installedModels.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {modelsListed &&
            installedModels.length === 0 &&
            !modelsError &&
            provider === "ollama" ? (
              <p className="settings-helper" data-testid="models-empty">
                No models are installed on this server. Pull one with{" "}
                <code>ollama pull &lt;model&gt;</code>, then list again.
              </p>
            ) : null}
            {modelsError ? (
              <p
                role="alert"
                className="error"
                data-testid="models-error"
              >
                {modelsError}
              </p>
            ) : null}

            {/* Explicit, confirmation-gated pull (task 139). Ollama-native
                only — the server's /api/pull has no OpenAI-compatible
                equivalent. No request is sent until the user clicks "Pull
                model" and then confirms. */}
            {provider === "ollama" ? (
              <div className="local-llm-pull" data-testid="local-llm-pull">
                {!pullConfirming && !isPulling ? (
                  <div className="settings-card-form-actions">
                    <button
                      type="button"
                      onClick={requestPull}
                      disabled={!model.trim()}
                    >
                      Pull model
                    </button>
                  </div>
                ) : null}

                {pullConfirming ? (
                  <div
                    className="local-llm-pull-confirm"
                    data-testid="pull-confirm"
                    role="group"
                    aria-label="Confirm model pull"
                  >
                    <p
                      role="alert"
                      className="settings-warning"
                      data-testid="pull-advisory-warning"
                    >
                      {PULL_DISK_VRAM_ADVISORY}
                    </p>
                    <p className="settings-helper">
                      Pull <code>{model.trim() || "(no model)"}</code> onto this
                      Ollama server now? This downloads the model and may take a
                      while.
                    </p>
                    <div className="settings-card-form-actions">
                      <button type="button" onClick={handleConfirmPull}>
                        Confirm pull
                      </button>
                      <button
                        type="button"
                        onClick={() => setPullConfirming(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}

                {isPulling || pullStatus || pullProgress ? (
                  <div
                    className="local-llm-pull-progress"
                    data-testid="pull-progress"
                    role="status"
                    aria-live="polite"
                  >
                    <p className="settings-helper">
                      {isPulling ? "Pulling…" : "Pull finished."}
                      {pullStatus ? ` ${pullStatus}` : ""}
                      {pullPercent != null ? ` (${pullPercent}%)` : ""}
                    </p>
                    {pullPercent != null ? (
                      <progress
                        data-testid="pull-progress-bar"
                        max={100}
                        value={pullPercent}
                      />
                    ) : isPulling ? (
                      <progress data-testid="pull-progress-bar" />
                    ) : null}
                  </div>
                ) : null}

                {pullResult ? (
                  <p
                    role={pullResult.ok ? "status" : "alert"}
                    className={pullResult.ok ? "settings-success" : "error"}
                    data-testid="pull-result"
                    data-pull-ok={pullResult.ok ? "true" : "false"}
                  >
                    {pullResult.message}
                  </p>
                ) : null}

                {pullError ? (
                  <p role="alert" className="error" data-testid="pull-error">
                    {pullError}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>

          <label className="field">
            <span>Timeout (seconds)</span>
            <input
              type="number"
              min={1}
              value={timeoutSeconds}
              onChange={(e) => {
                setTimeoutSeconds(Number(e.target.value));
                clearFeedback();
              }}
            />
          </label>

          <label className="field">
            <span>JobApplicator context budget</span>
            <input
              type="number"
              min={512}
              value={contextWindowTokens}
              onChange={(e) => {
                const next = Number(e.target.value);
                setContextWindowTokens(next);
                setMaxInputTokens(Math.max(0, next - reservedOutputTokens));
                clearFeedback();
              }}
            />
          </label>
          <p className="settings-helper">
            This budget only changes how JobApplicator sizes its prompts. It
            does not change the running model server&apos;s context window —
            the server keeps its own context unless configured separately
            (e.g. Ollama <code>num_ctx</code>).
          </p>

          <label className="field">
            <span>Reserved output tokens</span>
            <input
              type="number"
              min={1}
              value={reservedOutputTokens}
              onChange={(e) => {
                const next = Number(e.target.value);
                setReservedOutputTokens(next);
                setMaxInputTokens(Math.max(0, contextWindowTokens - next));
                clearFeedback();
              }}
            />
          </label>

          <label className="field">
            <span>Max input tokens</span>
            <input
              type="number"
              min={1}
              value={maxInputTokens}
              onChange={(e) => {
                setMaxInputTokens(Number(e.target.value));
                clearFeedback();
              }}
            />
          </label>

          {provider === "ollama" ? (
            <>
              <label className="field">
                <span>Ollama context length (num_ctx, optional)</span>
                <input
                  type="number"
                  min={1}
                  value={numCtx}
                  placeholder="Leave blank to use the server default"
                  onChange={(e) => {
                    setNumCtx(e.target.value);
                    clearFeedback();
                  }}
                />
              </label>
              <p className="settings-helper">
                Sets the Ollama server&apos;s running context length so the
                model actually runs at that size. Leave blank to keep the
                server&apos;s own default.
              </p>
            </>
          ) : null}

          {provider === "openai_compatible" ? (
            <p
              className="settings-helper"
              role="note"
              data-testid="openai-context-note"
            >
              An OpenAI-compatible endpoint does not expose its context
              window, so JobApplicator cannot verify the server&apos;s real
              context — treat the configured budget as an assumption.
            </p>
          ) : null}

          <label className="field">
            <span>Max output tokens (optional)</span>
            <input
              type="number"
              min={1}
              value={maxOutputTokens}
              placeholder="Leave blank to use the server's own limit"
              onChange={(e) => {
                setMaxOutputTokens(e.target.value);
                clearFeedback();
              }}
            />
          </label>
          <p className="settings-helper">
            Optional cap on how much a local model may generate per call, sent
            as the provider&apos;s own field — Ollama <code>num_predict</code> /
            OpenAI-compatible <code>max_tokens</code>. It bounds generation at
            the source before the deterministic fallback. Leave blank to use the
            server&apos;s own limit.
          </p>

          <dl className="run-meta">
            <dt>JobApplicator context budget</dt>
            <dd>{contextWindowTokens} tokens</dd>
            <dt>Usable input budget</dt>
            <dd>{usableBudget} tokens</dd>
          </dl>

          {smallContext ? (
            <p role="alert" className="error">
              This context window is small. Local LLM will only be used for
              compact preflight tasks. Large evidence-heavy tasks will use
              deterministic fallback or Claude Code.
            </p>
          ) : null}

          <fieldset className="field">
            <legend>Over-budget handling</legend>
            <label className="field-inline">
              <input
                type="checkbox"
                checked={allowCompression}
                onChange={(e) => {
                  setAllowCompression(e.target.checked);
                  clearFeedback();
                }}
              />
              <span>Allow deterministic compression</span>
            </label>
            <label className="field-inline">
              <input
                type="checkbox"
                checked={allowFallback}
                onChange={(e) => {
                  setAllowFallback(e.target.checked);
                  clearFeedback();
                }}
              />
              <span>Allow deterministic fallback</span>
            </label>
            <label className="field-inline">
              <input
                type="checkbox"
                checked={abortOnOverBudget}
                onChange={(e) => {
                  setAbortOnOverBudget(e.target.checked);
                  clearFeedback();
                }}
              />
              <span>Abort local task when still over budget</span>
            </label>
          </fieldset>

          <label className="field">
            <span>
              API key (optional)
              {settings.has_api_key ? " — saved" : ""}
            </span>
            <input
              type="password"
              value={apiKey}
              placeholder={
                settings.has_api_key
                  ? settings.api_key_preview
                  : "Leave blank if not required"
              }
              onChange={(e) => {
                setApiKey(e.target.value);
                clearFeedback();
              }}
            />
          </label>

          <fieldset className="field">
            <legend>Use local LLM for</legend>
            {configurableTasks.map((task) => (
              <label key={task.task} className="field-inline">
                <input
                  type="checkbox"
                  checked={Boolean(allowedTasks[task.task])}
                  onChange={(e) => {
                    setAllowedTasks((prev) => ({
                      ...prev,
                      [task.task]: e.target.checked,
                    }));
                    clearFeedback();
                  }}
                />
                <span>
                  {LOCAL_TASK_LABELS[task.task] ?? task.task}
                  {task.risk === "high" ? (
                    <em className="local-llm-risk"> (high risk — off by default)</em>
                  ) : null}
                </span>
              </label>
            ))}
          </fieldset>

          {saveError ? (
            <p role="alert" className="error">
              {saveError}
            </p>
          ) : null}
          {saveSuccess ? (
            <p role="status" className="settings-success">
              {saveSuccess}
            </p>
          ) : null}
          {testResult ? (
            <p
              role={testResult.ok ? "status" : "alert"}
              className={testResult.ok ? "settings-success" : "error"}
              data-testid="test-connection-result"
              data-error-kind={testResult.ok ? undefined : testResult.errorKind ?? undefined}
            >
              {testResult.ok
                ? testResult.message
                : describeConnectionFailure(
                    testResult.errorKind,
                    testResult.message,
                    model,
                    testResult.installedModels,
                  )}
            </p>
          ) : null}
          {/* When the configured model is missing on an Ollama server, make the
              explicit pull the obvious next step — clicking opens the same
              confirmation-gated flow for the named model. */}
          {testResult &&
          !testResult.ok &&
          testResult.errorKind === "model_not_installed" &&
          provider === "ollama" &&
          model.trim() &&
          !isPulling &&
          !pullConfirming ? (
            <div className="settings-card-form-actions">
              <button
                type="button"
                onClick={requestPull}
                data-testid="pull-missing-model"
              >
                Pull “{model.trim()}”
              </button>
            </div>
          ) : null}
          {testResult?.ok &&
          testResult.contextVerified &&
          testResult.serverReportedContextTokens != null ? (
            <p
              role="status"
              className="settings-helper"
              data-testid="server-context-verified"
            >
              Server-reported context: {testResult.serverReportedContextTokens}{" "}
              tokens
            </p>
          ) : null}
          {testResult && !testResult.contextVerified && testResult.contextWarning ? (
            <p
              role="alert"
              className="settings-warning"
              data-testid="server-context-warning"
            >
              {testResult.contextWarning}
            </p>
          ) : null}

          <div className="settings-card-form-actions">
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={isTesting}
            >
              {isTesting ? "Testing…" : "Test connection"}
            </button>
            <button type="submit" disabled={isSaving}>
              {isSaving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

interface GmailOAuthFormState {
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  tokenPath: string;
}

function GmailIntegrationCard() {
  const [status, setStatus] = useState<GmailStatusResponse | null>(null);
  const [oauthSettings, setOauthSettings] =
    useState<GmailOAuthSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [form, setForm] = useState<GmailOAuthFormState>({
    clientId: "",
    clientSecret: "",
    redirectUri: DEFAULT_REDIRECT_URI,
    tokenPath: DEFAULT_TOKEN_PATH,
  });
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [isDeletingConfig, setIsDeletingConfig] = useState(false);

  async function refreshAll() {
    const [s, c] = await Promise.all([
      getGmailStatus(),
      getGmailOAuthSettings(),
    ]);
    setStatus(s);
    setOauthSettings(c);
    return { status: s, settings: c };
  }

  useEffect(() => {
    let cancelled = false;
    refreshAll().catch((err: unknown) => {
      if (cancelled) return;
      setLoadError(extractApiDetail(err));
    });
    return () => {
      cancelled = true;
    };
    // refreshAll is stable in scope; ignore exhaustive-deps for the
    // initial-mount load — re-runs go through the explicit handlers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openForm() {
    setForm({
      clientId: oauthSettings?.google_client_id ?? "",
      clientSecret: "",
      redirectUri:
        oauthSettings?.google_redirect_uri ?? DEFAULT_REDIRECT_URI,
      tokenPath: oauthSettings?.gmail_token_path ?? DEFAULT_TOKEN_PATH,
    });
    setSaveError(null);
    setSaveSuccess(null);
    setIsFormOpen(true);
  }

  function cancelForm() {
    setIsFormOpen(false);
    setSaveError(null);
  }

  async function handleConnect() {
    setIsConnecting(true);
    setConnectError(null);
    try {
      const payload = await getGmailAuthUrl();
      window.open(payload.auth_url, "_blank", "noopener,noreferrer");
    } catch (err: unknown) {
      setConnectError(extractApiDetail(err));
    } finally {
      setIsConnecting(false);
    }
  }

  async function handleSaveConfig(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaveError(null);
    setSaveSuccess(null);

    const clientId = form.clientId.trim();
    const clientSecret = form.clientSecret;
    const redirectUri = form.redirectUri.trim() || DEFAULT_REDIRECT_URI;
    const tokenPath = form.tokenPath.trim() || DEFAULT_TOKEN_PATH;

    if (!clientId) {
      setSaveError("Client ID is required.");
      return;
    }
    const hasExistingSecret =
      oauthSettings?.source === "settings" &&
      oauthSettings.has_google_client_secret;
    if (!clientSecret && !hasExistingSecret) {
      setSaveError("Client secret is required.");
      return;
    }

    setIsSavingConfig(true);
    try {
      await setGmailOAuthSettings({
        google_client_id: clientId,
        google_client_secret: clientSecret || null,
        google_redirect_uri: redirectUri,
        gmail_token_path: tokenPath,
        preserve_existing_secret: !clientSecret && hasExistingSecret,
      });
      await refreshAll();
      setForm((prev) => ({ ...prev, clientSecret: "" }));
      setSaveSuccess("Gmail config saved.");
      setIsFormOpen(false);
    } catch (err: unknown) {
      setSaveError(extractApiDetail(err));
    } finally {
      setIsSavingConfig(false);
    }
  }

  async function handleDeleteConfig() {
    setIsDeletingConfig(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      await deleteGmailOAuthSettings();
      await refreshAll();
      setSaveSuccess("Local Gmail config deleted.");
      setIsFormOpen(false);
    } catch (err: unknown) {
      setSaveError(extractApiDetail(err));
    } finally {
      setIsDeletingConfig(false);
    }
  }

  let statusText = "Loading…";
  if (status) {
    if (!status.configured) statusText = "Not configured";
    else if (!status.connected) statusText = "Not connected";
    else statusText = status.email ? `Connected as ${status.email}` : "Connected";
  }

  const showForm = isFormOpen || (status !== null && !status.configured);
  const settingsSource = oauthSettings?.source ?? "none";
  const hasSavedSecret =
    settingsSource === "settings" &&
    (oauthSettings?.has_google_client_secret ?? false);

  return (
    <section className="settings-card" data-testid="gmail-integration-card">
      <header className="settings-card-header">
        <h3>Gmail integration</h3>
      </header>

      <p className="settings-helper">
        Gmail is used read-only for application tracking. JobApplicator does
        not send, delete, archive, or label emails.
      </p>

      {loadError ? (
        <p role="alert" className="error">
          {loadError}
        </p>
      ) : null}

      <dl className="run-meta">
        <dt>Status</dt>
        <dd data-testid="gmail-settings-status">{statusText}</dd>
        {status && status.connected && status.scopes.length > 0 ? (
          <>
            <dt>Scopes</dt>
            <dd>{status.scopes.join(", ")}</dd>
          </>
        ) : null}
        {oauthSettings ? (
          <>
            <dt>Config source</dt>
            <dd data-testid="gmail-config-source">
              {settingsSource === "settings"
                ? "Local settings"
                : settingsSource === "environment"
                  ? "Environment variables"
                  : "Not configured"}
            </dd>
          </>
        ) : null}
      </dl>

      {oauthSettings && settingsSource === "environment" ? (
        <p
          className="settings-helper"
          data-testid="gmail-env-source-note"
          role="status"
        >
          Gmail OAuth config is loaded from environment variables. You can
          override it by saving local settings below.
        </p>
      ) : null}

      {status && !status.configured && !isFormOpen ? (
        <div
          className="settings-empty"
          data-testid="gmail-not-configured"
          role="status"
        >
          <p>
            Gmail OAuth is not configured.
            {status.missing_config.length > 0
              ? ` Missing: ${status.missing_config.join(", ")}.`
              : null}
          </p>
          <p>
            Save your Google OAuth client ID and secret below to enable Gmail
            tracking. Environment variables remain supported as a fallback.
          </p>
        </div>
      ) : null}

      {showForm ? (
        <form
          onSubmit={handleSaveConfig}
          noValidate
          className="settings-card-form"
          data-testid="gmail-oauth-form"
        >
          <label className="field">
            <span>Google Client ID</span>
            <input
              type="text"
              value={form.clientId}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, clientId: e.target.value }))
              }
              autoComplete="off"
              required
            />
          </label>
          <label className="field">
            <span>
              Google Client Secret
              {hasSavedSecret ? (
                <em
                  style={{ marginLeft: "0.5em", fontStyle: "italic" }}
                  data-testid="gmail-secret-saved-hint"
                >
                  (Client secret saved — leave blank to keep)
                </em>
              ) : null}
            </span>
            <input
              type="password"
              value={form.clientSecret}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  clientSecret: e.target.value,
                }))
              }
              autoComplete="new-password"
              placeholder={hasSavedSecret ? "••••••••" : ""}
            />
          </label>
          <label className="field">
            <span>Redirect URI</span>
            <input
              type="text"
              value={form.redirectUri}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, redirectUri: e.target.value }))
              }
              required
            />
          </label>
          <label className="field">
            <span>Token path</span>
            <input
              type="text"
              value={form.tokenPath}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, tokenPath: e.target.value }))
              }
            />
          </label>

          {saveError ? (
            <p role="alert" className="error">
              {saveError}
            </p>
          ) : null}

          <div className="settings-card-form-actions">
            <button
              type="submit"
              disabled={isSavingConfig}
              data-testid="gmail-save-config-button"
            >
              {isSavingConfig ? "Saving…" : "Save Gmail config"}
            </button>
            {status && status.configured ? (
              <button
                type="button"
                className="button button-secondary"
                onClick={cancelForm}
                disabled={isSavingConfig}
              >
                Cancel
              </button>
            ) : null}
          </div>
        </form>
      ) : null}

      {saveSuccess ? (
        <p role="status" className="settings-success">
          {saveSuccess}
        </p>
      ) : null}

      {status && status.configured && !isFormOpen ? (
        <div className="settings-card-form-actions">
          {!status.connected ? (
            <button
              type="button"
              onClick={handleConnect}
              disabled={isConnecting}
              data-testid="gmail-connect-button"
            >
              {isConnecting ? "Opening…" : "Connect Gmail"}
            </button>
          ) : null}
          <button
            type="button"
            className="button button-secondary"
            onClick={openForm}
            data-testid="gmail-edit-config-button"
          >
            {settingsSource === "settings"
              ? "Edit Gmail config"
              : "Override with local settings"}
          </button>
          {settingsSource === "settings" ? (
            <button
              type="button"
              className="button button-secondary"
              onClick={handleDeleteConfig}
              disabled={isDeletingConfig}
              data-testid="gmail-delete-config-button"
            >
              {isDeletingConfig
                ? "Deleting…"
                : "Delete local Gmail config"}
            </button>
          ) : null}
        </div>
      ) : null}

      {connectError ? (
        <p role="alert" className="error">
          {connectError}
        </p>
      ) : null}
    </section>
  );
}

function ExportsCard() {
  const [path, setPath] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getExportSettings()
      .then((data) => {
        if (!cancelled) setPath(data.path);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(extractApiDetail(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleCopy() {
    if (!path) return;
    try {
      await navigator.clipboard?.writeText(path);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="settings-card" data-testid="exports-card">
      <header className="settings-card-header">
        <h3>Export folder</h3>
      </header>
      <p className="settings-helper">
        When you export a tailored resume, the app copies the DOCX and its
        audits into a per-application subfolder here. Each export keeps a
        human-readable DOCX filename.
      </p>
      {loadError ? (
        <p role="alert" className="error">
          {loadError}
        </p>
      ) : path ? (
        <p className="settings-export-path">
          <code>{path}</code>{" "}
          <Button variant="ghost" size="sm" onClick={() => void handleCopy()}>
            {copied ? "Copied" : "Copy path"}
          </Button>
        </p>
      ) : (
        <p className="settings-helper">Loading…</p>
      )}
    </section>
  );
}

function describeResume(resume: MasterResume): string {
  const kind = resume.source === "filesystem" ? "file" : "manual";
  const format = resume.source_format ? ` · ${resume.source_format}` : "";
  return `${kind}${format}`;
}

function describeEvidence(source: EvidenceSource): string {
  const kind = source.source === "filesystem" ? "file" : "manual";
  const format = source.source_format ? ` · ${source.source_format}` : "";
  return `${source.source_type} · ${kind}${format}`;
}

export function SettingsPage() {
  const [resumes, setResumes] = useState<MasterResume[] | null>(null);
  const [evidenceSources, setEvidenceSources] = useState<
    EvidenceSource[] | null
  >(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function refreshResumes() {
    setResumes(await listMasterResumes());
  }

  async function refreshEvidence() {
    setEvidenceSources(await listEvidenceSources());
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([listMasterResumes(), listEvidenceSources()])
      .then(([r, e]) => {
        if (cancelled) return;
        setResumes(r);
        setEvidenceSources(e);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(extractApiDetail(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const resumeItems =
    resumes === null
      ? null
      : resumes.map((r) => ({
          id: r.id,
          name: r.name,
          meta: describeResume(r),
        }));
  const evidenceItems =
    evidenceSources === null
      ? null
      : evidenceSources.map((e) => ({
          id: e.id,
          name: e.name,
          meta: describeEvidence(e),
        }));

  return (
    <section className="settings-page">
      <PageHeader
        title="Settings"
        description="Manage your candidate context, model providers, and integrations from one hub."
      />
      {loadError ? (
        <p role="alert" className="error">
          {loadError}
        </p>
      ) : null}

      <SettingsGroup
        label="Gmail integration"
        description="Read-only Gmail access for application tracking. Drives the Sync Gmail action on the Applications page."
      >
        <GmailIntegrationCard />
      </SettingsGroup>

      <SettingsGroup
        label="Document tooling"
        description="Master resumes and evidence sources used as inputs to tailoring runs. Upload a file (copied into your candidate context) or paste content directly."
      >
        <ImportPasteCard
          title="Master resumes"
          testId="master-resumes-card"
          items={resumeItems}
          emptyLabel="No master resumes yet — add one to enable tailoring."
          addNoun="master resume"
          acceptExtensions=".docx,.md,.txt"
          acceptHint="DOCX, Markdown, or text files."
          contentLabel="Content (markdown)"
          onImportFile={async (file) => {
            await importMasterResumeFile(file);
            await refreshResumes();
          }}
          onCreateManual={async (name, content) => {
            await createMasterResume({ name, content_markdown: content });
            await refreshResumes();
          }}
        />

        <ImportPasteCard
          title="Evidence sources"
          testId="evidence-sources-card"
          items={evidenceItems}
          emptyLabel="No evidence sources yet — optional, but useful for grounded tailoring."
          addNoun="evidence source"
          acceptExtensions=".md,.txt,.docx"
          acceptHint="Markdown, text, or DOCX files."
          contentLabel="Content (markdown)"
          onImportFile={async (file) => {
            await importEvidenceSourceFile(file);
            await refreshEvidence();
          }}
          onCreateManual={async (name, content) => {
            await createEvidenceBank({ name, content_markdown: content });
            await refreshEvidence();
          }}
        />
      </SettingsGroup>

      <SettingsGroup
        label="Claude / LLM"
        description="Pick which CLI-based provider drives the automatic tailoring flow."
      >
        <LlmProviderCard />
      </SettingsGroup>

      <SettingsGroup
        label="LLM Providers"
        description="Experimental: route low-risk tasks to a local LLM (Ollama or an OpenAI-compatible endpoint). Claude Code remains the default for resume tailoring."
      >
        <LocalLlmCard />
      </SettingsGroup>

      <SettingsGroup
        label="Exports"
        description="Where tailored resumes land when you export them from a run or review."
      >
        <ExportsCard />
      </SettingsGroup>

      <SettingsGroup
        label="Browser extension"
        description="Capture jobs straight from your browser into the cockpit."
      >
        <section className="settings-card" data-testid="extension-card">
          <header className="settings-card-header">
            <h3>Browser capture extension</h3>
          </header>
          <p className="settings-helper">
            Load the unpacked extension from the <code>extension/</code>{" "}
            directory in this repo to enable one-click job capture from
            LinkedIn, Greenhouse, and Lever postings. Captured jobs land in
            the <Link to="/captures">Captures</Link> queue for confirmation.
          </p>
        </section>
      </SettingsGroup>

      <SettingsGroup
        label="Prompt harnesses"
        description="Tune the system prompts the tailoring runs use."
      >
        <section className="settings-card" data-testid="prompts-card">
          <header className="settings-card-header">
            <h3>Prompt editor</h3>
          </header>
          <p className="settings-helper">
            Edit and version the system prompts driving each tailoring
            harness.{" "}
            <Link to="/prompts">Open the prompt editor</Link> to view
            available harnesses and their current text.
          </p>
        </section>
      </SettingsGroup>

      <SettingsGroup
        label="Danger zone"
        description="Operations that are difficult to reverse. The cockpit will always confirm before doing anything destructive."
      >
        <DangerZoneCard />
      </SettingsGroup>
    </section>
  );
}
