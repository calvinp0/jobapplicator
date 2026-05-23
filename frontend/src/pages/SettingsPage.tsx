import { useEffect, useState } from "react";
import {
  ApiError,
  createEvidenceBank,
  createMasterResume,
  listEvidenceBanks,
  listMasterResumes,
} from "../api";
import type { EvidenceBank, MasterResume } from "../api";

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

interface SectionProps<T extends SeedEntity> {
  title: string;
  items: T[] | null;
  emptyLabel: string;
  onCreate: (payload: CreatePayload) => Promise<T>;
  onCreated: (item: T) => void;
  contentLabel: string;
  submitLabel: string;
}

function extractServerMessage(body: unknown): string | null {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (
      detail &&
      typeof detail === "object" &&
      "message" in detail &&
      typeof (detail as { message: unknown }).message === "string"
    ) {
      return (detail as { message: string }).message;
    }
    if (Array.isArray(detail)) {
      const first = detail[0];
      if (
        first &&
        typeof first === "object" &&
        "msg" in first &&
        typeof (first as { msg: unknown }).msg === "string"
      ) {
        return (first as { msg: string }).msg;
      }
    }
  }
  return null;
}

function SeedSection<T extends SeedEntity>({
  title,
  items,
  emptyLabel,
  onCreate,
  onCreated,
  contentLabel,
  submitLabel,
}: SectionProps<T>) {
  const [name, setName] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [contentMarkdown, setContentMarkdown] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

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
      setName("");
      setSourcePath("");
      setContentMarkdown("");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setSubmitError(extractServerMessage(err.body) ?? err.message);
      } else {
        setSubmitError(`Failed to create ${title.toLowerCase()}`);
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="settings-section">
      <h3>{title}</h3>
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

      <form onSubmit={handleSubmit} noValidate>
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

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : submitLabel}
        </button>
      </form>
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
        const message =
          err instanceof ApiError ? err.message : "Failed to load settings";
        setLoadError(message);
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

      <SeedSection<MasterResume>
        title="Master resumes"
        items={resumes}
        emptyLabel="No master resumes yet."
        onCreate={createMasterResume}
        onCreated={(item) =>
          setResumes((prev) => (prev === null ? [item] : [item, ...prev]))
        }
        contentLabel="Content (markdown)"
        submitLabel="Add master resume"
      />

      <SeedSection<EvidenceBank>
        title="Evidence banks"
        items={evidenceBanks}
        emptyLabel="No evidence banks yet."
        onCreate={createEvidenceBank}
        onCreated={(item) =>
          setEvidenceBanks((prev) =>
            prev === null ? [item] : [item, ...prev],
          )
        }
        contentLabel="Content (markdown)"
        submitLabel="Add evidence bank"
      />
    </section>
  );
}
