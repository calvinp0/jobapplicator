import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./layout/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { CapturesPage } from "./pages/CapturesPage";
import { CaptureDetailPage } from "./pages/CaptureDetailPage";
import { JobsPage } from "./pages/JobsPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { RunsPage } from "./pages/RunsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { ResumeVersionDetailPage } from "./pages/ResumeVersionDetailPage";
import { ResumeReviewPage } from "./pages/ResumeReviewPage";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { ApplicationDetailPage } from "./pages/ApplicationDetailPage";
import { PromptsPage } from "./pages/PromptsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { LocalLlmMonitorPage } from "./pages/LocalLlmMonitorPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="/captures" element={<CapturesPage />} />
        <Route path="/captures/:captureId" element={<CaptureDetailPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:jobId" element={<JobDetailPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
        <Route
          path="/resume-versions/:versionId"
          element={<ResumeVersionDetailPage />}
        />
        <Route
          path="/resume-versions/:versionId/review"
          element={<ResumeReviewPage />}
        />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route
          path="/applications/:applicationId"
          element={<ApplicationDetailPage />}
        />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/admin/local-llm" element={<LocalLlmMonitorPage />} />
        <Route path="/prompts" element={<PromptsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
