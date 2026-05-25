import { useEffect, useState } from "react";
import {
  createEvidenceBank,
  createMasterResume,
  getGmailAuthUrl,
  getGmailStatus,
  getLlmProviderSetting,
  listEvidenceBanks,
  listMasterResumes,
  setLlmProviderSetting,
} from "../api";
import type {
  EvidenceBank,
  GmailStatusResponse,
  LlmProvider,
  MasterResume,
} from "../api";
import { extractApiDetail } from "../lib/api-errors";

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

function GmailIntegrationCard() {
  const [status, setStatus] = useState<GmailStatusResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getGmailStatus()
      .then((s) => {
        if (cancelled) return;
        setStatus(s);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(extractApiDetail(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  let statusText = "Loading…";
  if (status) {
    if (!status.configured) statusText = "Not configured";
    else if (!status.connected) statusText = "Not connected";
    else statusText = status.email ? `Connected as ${status.email}` : "Connected";
  }

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
      </dl>

      {status && !status.configured ? (
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
            See the install docs for setup details (Optional Gmail Read-Only
            Connection in <code>docs/install.md</code>).
          </p>
        </div>
      ) : null}

      {status && status.configured && !status.connected ? (
        <div className="settings-card-form-actions">
          <button
            type="button"
            onClick={handleConnect}
            disabled={isConnecting}
            data-testid="gmail-connect-button"
          >
            {isConnecting ? "Opening…" : "Connect Gmail"}
          </button>
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
