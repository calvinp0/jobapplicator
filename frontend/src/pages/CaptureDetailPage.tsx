import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, confirmCapture, getCapture } from "../api";
import type { JobCapture } from "../api";

const REQUIRED_FIELDS = ["company", "title", "description_text"] as const;

type FormState = {
  company: string;
  title: string;
  location: string;
  external_url: string;
  description_text: string;
  application_method: string;
};

function structuredExtractionFailed(capture: JobCapture): boolean {
  const matched = capture.diagnostics?.selectors_matched;
  if (!matched) {
    // No diagnostics — fall back to a structural check on the fields
    // themselves so older captures still surface a warning if they came
    // through empty.
    return (
      !capture.title?.trim() ||
      !capture.company?.trim() ||
      !capture.description_text?.trim()
    );
  }
  return (
    matched.title === false ||
    matched.company === false ||
    matched.description === false
  );
}

function bestFallbackDescription(capture: JobCapture): string {
  // Order: structured description → user selection → raw_text from the
  // job container → bounded page_text excerpt. The earlier wins are
  // tighter and don't include navigation chrome, so we prefer them when
  // present.
  const existing = capture.description_text?.trim();
  if (existing) return capture.description_text;
  if (capture.selected_text?.trim()) return capture.selected_text;
  if (capture.raw_text?.trim()) return capture.raw_text;
  if (capture.page_text?.trim()) return capture.page_text;
  return "";
}

function fallbackTitleForForm(capture: JobCapture): string {
  if (capture.title?.trim()) return capture.title;
  const docTitle = capture.page_title?.trim();
  if (docTitle) {
    // The extension already strips the "| LinkedIn" suffix when it falls
    // back, but older captures may have stored the raw <title>. Keep
    // whatever we got — the user can edit before confirming.
    return capture.page_title ?? "";
  }
  return "";
}

function toFormState(capture: JobCapture): FormState {
  return {
    company: capture.company ?? "",
    title: fallbackTitleForForm(capture),
    location: capture.location ?? "",
    external_url: capture.external_url ?? "",
    description_text: bestFallbackDescription(capture),
    application_method: capture.application_method ?? "",
  };
}

function describeMissingField(name: string): string {
  switch (name) {
    case "company":
      return "Company";
    case "title":
      return "Title";
    case "description_text":
      return "Description";
    default:
      return name;
  }
}

export function CaptureDetailPage() {
  const { captureId } = useParams<{ captureId: string }>();
  const navigate = useNavigate();
  const [capture, setCapture] = useState<JobCapture | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!captureId) return;
    let cancelled = false;
    getCapture(captureId)
      .then((row) => {
        if (cancelled) return;
        setCapture(row);
        setForm(toFormState(row));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load capture";
        setLoadError(message);
      });
    return () => {
      cancelled = true;
    };
  }, [captureId]);

  function updateField(field: keyof FormState, value: string) {
    setForm((prev) => (prev === null ? prev : { ...prev, [field]: value }));
  }

  function computeMissing(state: FormState): string[] {
    return REQUIRED_FIELDS.filter((field) => state[field].trim().length === 0);
  }

  async function handleConfirm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!captureId || !form) return;

    const missing = computeMissing(form);
    if (missing.length > 0) {
      setMissingFields(missing);
      setSubmitError(
        `Missing required fields: ${missing
          .map(describeMissingField)
          .join(", ")}`,
      );
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    setMissingFields([]);

    try {
      const job = await confirmCapture(captureId);
      navigate(`/jobs/${job.id}`);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const detail = extractDetail(err.body);
        if (detail && Array.isArray(detail.missing_fields)) {
          setMissingFields(detail.missing_fields);
          setSubmitError(
            `Missing required fields: ${detail.missing_fields
              .map(describeMissingField)
              .join(", ")}`,
          );
        } else if (detail?.message) {
          setSubmitError(detail.message);
        } else {
          setSubmitError(err.message);
        }
      } else {
        setSubmitError("Failed to confirm capture");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <section className="capture-detail">
        <h2>Capture</h2>
        <p role="alert" className="error">
          {loadError}
        </p>
      </section>
    );
  }

  if (!capture || !form) {
    return (
      <section className="capture-detail">
        <h2>Capture</h2>
        <p>Loading…</p>
      </section>
    );
  }

  if (capture.user_confirmed && capture.job_id) {
    return (
      <section className="capture-detail">
        <h2>Capture</h2>
        <p>Job created from this capture.</p>
        <Link to={`/jobs/${capture.job_id}`}>Open job</Link>
      </section>
    );
  }

  const extractionFailed = structuredExtractionFailed(capture);
  const rawPreview =
    capture.page_text?.trim() || capture.raw_text?.trim() || "";

  return (
    <section className="capture-detail">
      <h2>Review Capture</h2>
      <p className="capture-meta">
        From {capture.source_platform} ({capture.capture_method}) ·{" "}
        {new Date(capture.captured_at).toLocaleString()}
      </p>
      {extractionFailed ? (
        <p role="status" className="warning" data-testid="extraction-warning">
          Structured LinkedIn fields were not detected. We filled what we
          could from page text. Please review before confirming.
        </p>
      ) : null}
      <form onSubmit={handleConfirm} noValidate>
        <label className="field">
          <span>Company</span>
          <input
            type="text"
            value={form.company}
            onChange={(e) => updateField("company", e.target.value)}
            aria-invalid={missingFields.includes("company") || undefined}
            required
          />
        </label>
        <label className="field">
          <span>Title</span>
          <input
            type="text"
            value={form.title}
            onChange={(e) => updateField("title", e.target.value)}
            aria-invalid={missingFields.includes("title") || undefined}
            required
          />
        </label>
        <label className="field">
          <span>Location</span>
          <input
            type="text"
            value={form.location}
            onChange={(e) => updateField("location", e.target.value)}
          />
        </label>
        <label className="field">
          <span>URL</span>
          <input
            type="url"
            value={form.external_url}
            onChange={(e) => updateField("external_url", e.target.value)}
          />
        </label>
        <label className="field">
          <span>Application method</span>
          <input
            type="text"
            value={form.application_method}
            onChange={(e) => updateField("application_method", e.target.value)}
          />
        </label>
        <label className="field">
          <span>Description</span>
          <textarea
            value={form.description_text}
            rows={10}
            onChange={(e) => updateField("description_text", e.target.value)}
            aria-invalid={
              missingFields.includes("description_text") || undefined
            }
            required
          />
        </label>

        {submitError ? (
          <p role="alert" className="error">
            {submitError}
          </p>
        ) : null}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Confirming…" : "Confirm"}
        </button>
      </form>
      {rawPreview ? (
        <details
          className="capture-raw-preview"
          data-testid="raw-text-preview"
        >
          <summary>Raw captured text preview</summary>
          <pre>
            {rawPreview.length > 4000
              ? `${rawPreview.slice(0, 4000)}…`
              : rawPreview}
          </pre>
        </details>
      ) : null}
    </section>
  );
}

interface ConfirmErrorDetail {
  message?: string;
  missing_fields?: string[];
}

function extractDetail(body: unknown): ConfirmErrorDetail | null {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (detail && typeof detail === "object") {
      return detail as ConfirmErrorDetail;
    }
    if (typeof detail === "string") {
      return { message: detail };
    }
  }
  return null;
}
