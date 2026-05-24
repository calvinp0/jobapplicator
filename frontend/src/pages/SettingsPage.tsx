import { useEffect, useState } from "react";
import {
  createEvidenceBank,
  createMasterResume,
  listEvidenceBanks,
  listMasterResumes,
} from "../api";
import type { EvidenceBank, MasterResume } from "../api";
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
    </section>
  );
}
