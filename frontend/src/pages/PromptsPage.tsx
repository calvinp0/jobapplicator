import { useCallback, useEffect, useState } from "react";
import {
  deletePromptOverride,
  getPromptHarness,
  listPromptHarnesses,
  savePromptOverride,
  validatePromptHarness,
} from "../api";
import type {
  PromptHarnessDetail,
  PromptHarnessSummary,
  PromptValidationResult,
} from "../api";
import { extractApiDetail } from "../lib/api-errors";

type Tab = "effective" | "default" | "override";

export function PromptsPage() {
  const [summaries, setSummaries] = useState<PromptHarnessSummary[] | null>(
    null,
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PromptHarnessDetail | null>(null);
  const [tab, setTab] = useState<Tab>("effective");
  const [draftOverride, setDraftOverride] = useState<string>("");
  const [validation, setValidation] = useState<PromptValidationResult | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);

  const loadDetail = useCallback(async (promptId: string) => {
    setDetail(null);
    setValidation(null);
    setActionError(null);
    setActionMessage(null);
    try {
      const fresh = await getPromptHarness(promptId);
      setDetail(fresh);
      setDraftOverride(fresh.override_content ?? fresh.default_content);
      setTab(fresh.has_override ? "override" : "effective");
    } catch (err: unknown) {
      setLoadError(extractApiDetail(err));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    listPromptHarnesses()
      .then((rows) => {
        if (cancelled) return;
        setSummaries(rows);
        if (rows.length > 0) {
          setSelectedId(rows[0].id);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(extractApiDetail(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  function refreshSummaries(updated: PromptHarnessDetail) {
    setSummaries((prev) =>
      prev === null
        ? prev
        : prev.map((row) =>
            row.id === updated.id
              ? {
                  ...row,
                  has_override: updated.has_override,
                  effective_source: updated.effective_source,
                  updated_at: updated.updated_at,
                }
              : row,
          ),
    );
  }

  async function handleCreateOverride() {
    if (detail === null) return;
    setIsSaving(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const updated = await savePromptOverride(
        detail.id,
        detail.default_content,
      );
      setDetail(updated);
      setDraftOverride(updated.override_content ?? updated.default_content);
      setTab("override");
      refreshSummaries(updated);
      setActionMessage("Override created from default.");
    } catch (err: unknown) {
      setActionError(extractApiDetail(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSaveOverride() {
    if (detail === null) return;
    if (!draftOverride.trim()) {
      setActionError("Override content cannot be empty.");
      return;
    }
    setIsSaving(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const updated = await savePromptOverride(detail.id, draftOverride);
      setDetail(updated);
      setDraftOverride(updated.override_content ?? updated.default_content);
      refreshSummaries(updated);
      setActionMessage("Override saved.");
    } catch (err: unknown) {
      setActionError(extractApiDetail(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleRestoreDefault() {
    if (detail === null) return;
    if (!detail.has_override) return;
    setIsRestoring(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const updated = await deletePromptOverride(detail.id);
      setDetail(updated);
      setDraftOverride(updated.override_content ?? updated.default_content);
      setTab("effective");
      refreshSummaries(updated);
      setActionMessage("Override removed. Using default prompt again.");
    } catch (err: unknown) {
      setActionError(extractApiDetail(err));
    } finally {
      setIsRestoring(false);
    }
  }

  async function handleValidate() {
    if (detail === null) return;
    setIsValidating(true);
    setActionError(null);
    try {
      const result = await validatePromptHarness(detail.id);
      setValidation(result);
    } catch (err: unknown) {
      setActionError(extractApiDetail(err));
    } finally {
      setIsValidating(false);
    }
  }

  async function handleCopyEffective() {
    if (detail === null) return;
    try {
      await navigator.clipboard.writeText(detail.effective_content);
      setActionMessage("Effective prompt copied to clipboard.");
    } catch {
      setActionError("Could not copy to clipboard.");
    }
  }

  function renderTabBody() {
    if (detail === null) return null;
    if (tab === "default") {
      return (
        <textarea
          className="prompt-textarea"
          value={detail.default_content}
          readOnly
          rows={24}
          aria-label="Default prompt content (read-only)"
          data-testid="prompt-default-textarea"
        />
      );
    }
    if (tab === "effective") {
      return (
        <textarea
          className="prompt-textarea"
          value={detail.effective_content}
          readOnly
          rows={24}
          aria-label="Effective prompt content (read-only)"
          data-testid="prompt-effective-textarea"
        />
      );
    }
    if (!detail.has_override) {
      return (
        <p className="settings-empty">
          No override yet. Use "Create override from default" to start
          editing.
        </p>
      );
    }
    return (
      <textarea
        className="prompt-textarea"
        value={draftOverride}
        onChange={(e) => {
          setDraftOverride(e.target.value);
          setActionMessage(null);
        }}
        rows={24}
        aria-label="Override prompt content"
        data-testid="prompt-override-textarea"
      />
    );
  }

  return (
    <section className="prompts-page settings-page">
      <h2>Prompt harnesses</h2>
      <p className="settings-helper">
        The resume tailoring and revision workers ship Claude Code a
        markdown prompt. Edits here override the bundled default with a
        local copy under <code>candidate_context/settings/prompt_overrides/</code>.
        Changes can break run output validation if you remove required
        files like <code>tailored_resume.md</code> or
        <code> claim_audit.md</code> — keep the contract intact.
      </p>

      {loadError ? (
        <p role="alert" className="error">
          {loadError}
        </p>
      ) : null}

      <div className="prompts-layout">
        <aside className="prompts-list" aria-label="Prompt harnesses">
          {summaries === null ? (
            <p>Loading…</p>
          ) : summaries.length === 0 ? (
            <p className="settings-empty">No prompt harnesses registered.</p>
          ) : (
            <ul className="settings-list">
              {summaries.map((row) => (
                <li
                  key={row.id}
                  className={
                    row.id === selectedId
                      ? "settings-list-item settings-list-item-active"
                      : "settings-list-item"
                  }
                >
                  <button
                    type="button"
                    className="prompts-list-button"
                    onClick={() => setSelectedId(row.id)}
                    data-testid={`prompt-select-${row.id}`}
                  >
                    <strong>{row.label}</strong>
                    <span className="settings-meta">
                      {row.has_override
                        ? "Using local override"
                        : "Using default prompt"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className="prompts-detail">
          {detail === null ? (
            <p>Loading…</p>
          ) : (
            <>
              <header className="prompts-detail-header">
                <h3>{detail.label}</h3>
                <p>{detail.description}</p>
                <dl className="run-meta">
                  <dt>Default file</dt>
                  <dd>
                    <code>{detail.default_path}</code>
                  </dd>
                  <dt>Source</dt>
                  <dd data-testid="prompt-effective-source">
                    {detail.effective_source === "override"
                      ? "Using local override"
                      : "Using default prompt"}
                  </dd>
                  <dt>Effective hash</dt>
                  <dd>
                    <code>{detail.effective_hash.slice(0, 12)}…</code>
                  </dd>
                </dl>
              </header>

              <div role="tablist" aria-label="Prompt views" className="prompts-tabs">
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === "effective"}
                  className={
                    tab === "effective"
                      ? "prompts-tab prompts-tab-active"
                      : "prompts-tab"
                  }
                  onClick={() => setTab("effective")}
                >
                  Effective
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === "default"}
                  className={
                    tab === "default"
                      ? "prompts-tab prompts-tab-active"
                      : "prompts-tab"
                  }
                  onClick={() => setTab("default")}
                >
                  Default
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={tab === "override"}
                  className={
                    tab === "override"
                      ? "prompts-tab prompts-tab-active"
                      : "prompts-tab"
                  }
                  onClick={() => setTab("override")}
                >
                  Override
                </button>
              </div>

              {renderTabBody()}

              <p className="settings-helper prompts-warning" role="status">
                <strong>Warning:</strong> Changing prompts can break run
                output validation if required files are omitted. Use
                "Validate" before saving to spot missing contract
                elements.
              </p>

              <div className="settings-card-form-actions prompts-actions">
                {!detail.has_override ? (
                  <button
                    type="button"
                    onClick={handleCreateOverride}
                    disabled={isSaving}
                    data-testid="prompt-create-override"
                  >
                    {isSaving ? "Working…" : "Create override from default"}
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={handleSaveOverride}
                      disabled={isSaving || tab !== "override"}
                      data-testid="prompt-save-override"
                    >
                      {isSaving ? "Saving…" : "Save override"}
                    </button>
                    <button
                      type="button"
                      className="button button-secondary"
                      onClick={handleRestoreDefault}
                      disabled={isRestoring}
                      data-testid="prompt-restore-default"
                    >
                      {isRestoring ? "Restoring…" : "Restore default"}
                    </button>
                  </>
                )}
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={handleValidate}
                  disabled={isValidating}
                  data-testid="prompt-validate"
                >
                  {isValidating ? "Validating…" : "Validate"}
                </button>
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={handleCopyEffective}
                  data-testid="prompt-copy"
                >
                  Copy effective
                </button>
              </div>

              {validation ? (
                <div
                  className={
                    validation.valid
                      ? "settings-success"
                      : "error prompts-validation"
                  }
                  role="status"
                  data-testid="prompt-validation-result"
                >
                  {validation.valid ? (
                    <p>Prompt mentions every required contract element.</p>
                  ) : (
                    <>
                      <p>Validation warnings:</p>
                      <ul>
                        {validation.warnings.map((w, idx) => (
                          <li key={idx}>{w}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              ) : null}

              {actionError ? (
                <p role="alert" className="error">
                  {actionError}
                </p>
              ) : null}
              {actionMessage ? (
                <p role="status" className="settings-success">
                  {actionMessage}
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
