import { useState } from "react";
import { downloadRunArtifact, downloadRunResume, exportRun } from "../api";
import { extractApiDetail } from "../lib/api-errors";
import { Button } from "./ui";

interface ResumeDownloadActionsProps {
  /** The run whose ``output/`` artifacts back the download/export. */
  runId: string;
  /** Show the "Export to folder" action (managed exports folder). */
  showExport?: boolean;
  /** Show the "Download Markdown" action alongside the DOCX. */
  showMarkdown?: boolean;
  /** Label for the primary DOCX download (e.g. "Download resume"). */
  docxLabel?: string;
}

/**
 * Download/export actions for a tailored resume (task 122). Reused on the run
 * detail page, the resume review workspace, and the application detail page so
 * the download behaviour — human-readable filenames, graceful missing-file
 * errors, and the managed-folder export — stays consistent everywhere.
 */
export function ResumeDownloadActions({
  runId,
  showExport = false,
  showMarkdown = false,
  docxLabel = "Download DOCX",
}: ResumeDownloadActionsProps) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportDir, setExportDir] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleDownload(action: () => Promise<void>) {
    setError(null);
    setIsDownloading(true);
    try {
      await action();
    } catch (err: unknown) {
      setError(extractApiDetail(err));
    } finally {
      setIsDownloading(false);
    }
  }

  async function handleExport() {
    setError(null);
    setExportDir(null);
    setCopied(false);
    setIsExporting(true);
    try {
      const result = await exportRun(runId);
      setExportDir(result.export_dir);
    } catch (err: unknown) {
      setError(extractApiDetail(err));
    } finally {
      setIsExporting(false);
    }
  }

  async function handleCopyPath() {
    if (!exportDir) return;
    try {
      await navigator.clipboard?.writeText(exportDir);
      setCopied(true);
    } catch {
      // Clipboard may be unavailable (insecure context / older browser).
      // The path stays visible for manual copy, so this is non-fatal.
      setCopied(false);
    }
  }

  return (
    <div className="resume-download-actions" data-testid="resume-download-actions">
      <div className="resume-download-buttons">
        <Button
          variant="secondary"
          size="sm"
          disabled={isDownloading}
          onClick={() => void handleDownload(() => downloadRunResume(runId))}
        >
          {isDownloading ? "Preparing…" : docxLabel}
        </Button>
        {showMarkdown ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={isDownloading}
            onClick={() =>
              void handleDownload(() =>
                downloadRunArtifact(runId, "tailored_resume.md"),
              )
            }
          >
            Download Markdown
          </Button>
        ) : null}
        {showExport ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={isExporting}
            onClick={() => void handleExport()}
          >
            {isExporting ? "Exporting…" : "Export to folder"}
          </Button>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="error resume-download-error">
          {error}
        </p>
      ) : null}

      {exportDir ? (
        <div className="resume-export-result" role="status">
          <span className="resume-export-label">Exported to</span>{" "}
          <code className="resume-export-path">{exportDir}</code>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void handleCopyPath()}
          >
            {copied ? "Copied" : "Copy path"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
