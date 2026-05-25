import { useEffect, useState } from "react";
import {
  createEvidenceBank,
  createMasterResume,
  deleteGmailOAuthSettings,
  getGmailAuthUrl,
  getGmailOAuthSettings,
  getGmailStatus,
  getLlmProviderSetting,
  listEvidenceBanks,
  listMasterResumes,
  setGmailOAuthSettings,
  setLlmProviderSetting,
} from "../api";
import type {
  EvidenceBank,
  GmailOAuthSettings,
  GmailStatusResponse,
  LlmProvider,
  MasterResume,
} from "../api";
import { extractApiDetail } from "../lib/api-errors";

const DEFAULT_REDIRECT_URI = "http://localhost:8000/gmail/oauth/callback";
const DEFAULT_TOKEN_PATH = "candidate_context/gmail/token.json";

interface SeedEntity {
  id: string;
  name: string;
  source_path: string | null;
  created_at: string;
}

interface CreatePayload {
  name: string;
  source_path?: string | null;
  content_markdown: string;
}

interface SeedCardProps<T extends SeedEntity> {
  title: string;
  items: T[] | null;
  emptyLabel: string;
  addButtonLabel: string;
  onCreate: (payload: CreatePayload) => Promise<T>;
  onCreated: (item: T) => void;
  contentLabel: string;
}

function SeedCard<T extends SeedEntity>({
  title,
  items,
  emptyLabel,
  addButtonLabel,
  onCreate,
  onCreated,
  contentLabel,
}: SeedCardProps<T>) {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [contentMarkdown, setContentMarkdown] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function resetForm() {
    setName("");
    setSourcePath("");
    setContentMarkdown("");
    setSubmitError(null);
  }

  function handleCancel() {
    resetForm();
    setIsFormOpen(false);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || !contentMarkdown.trim()) {
      setSubmitError("Name and content are required.");
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const created = await onCreate({
        name: name.trim(),
        source_path: sourcePath.trim() ? sourcePath.trim() : null,
        content_markdown: contentMarkdown,
      });
      onCreated(created);
      resetForm();
      setIsFormOpen(false);
    } catch (err: unknown) {
      setSubmitError(extractApiDetail(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="settings-card">
      <header className="settings-card-header">
        <h3>{title}</h3>
        {!isFormOpen ? (
          <button
            type="button"
            className="button button-secondary"
            onClick={() => setIsFormOpen(true)}
          >
            {`+ ${addButtonLabel}`}
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
              <span className="settings-meta">
                {new Date(item.created_at).toLocaleString()}
                {item.source_path ? ` · ${item.source_path}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}

      {isFormOpen ? (
        <form onSubmit={handleSubmit} noValidate className="settings-card-form">
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
            <span>Source path (optional)</span>
            <input
              type="text"
              value={sourcePath}
              onChange={(e) => setSourcePath(e.target.value)}
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

          {submitError ? (
            <p role="alert" className="error">
              {submitError}
            </p>
          ) : null}

          <div className="settings-card-form-actions">
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving…" : addButtonLabel}
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

export function SettingsPage() {
  const [resumes, setResumes] = useState<MasterResume[] | null>(null);
  const [evidenceBanks, setEvidenceBanks] = useState<EvidenceBank[] | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listMasterResumes(), listEvidenceBanks()])
      .then(([r, b]) => {
        if (cancelled) return;
        setResumes(r);
        setEvidenceBanks(b);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(extractApiDetail(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="settings-page">
      <h2>Settings</h2>
      {loadError ? (
        <p role="alert" className="error">
          {loadError}
        </p>
      ) : null}

      <SeedCard<MasterResume>
        title="Master resumes"
        items={resumes}
        emptyLabel="No master resumes yet — add one to enable tailoring."
        addButtonLabel="Add master resume"
        onCreate={createMasterResume}
        onCreated={(item) =>
          setResumes((prev) => (prev === null ? [item] : [item, ...prev]))
        }
        contentLabel="Content (markdown)"
      />

      <SeedCard<EvidenceBank>
        title="Evidence banks"
        items={evidenceBanks}
        emptyLabel="No evidence banks yet — optional, but useful for grounded tailoring."
        addButtonLabel="Add evidence bank"
        onCreate={createEvidenceBank}
        onCreated={(item) =>
          setEvidenceBanks((prev) =>
            prev === null ? [item] : [item, ...prev],
          )
        }
        contentLabel="Content (markdown)"
      />

      <LlmProviderCard />

      <GmailIntegrationCard />
    </section>
  );
}
