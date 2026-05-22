import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./layout/Layout";
import { CapturesPage } from "./pages/CapturesPage";
import { CaptureDetailPage } from "./pages/CaptureDetailPage";
import { JobsPage } from "./pages/JobsPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { RunsPage } from "./pages/RunsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/captures" replace />} />
        <Route path="/captures" element={<CapturesPage />} />
        <Route path="/captures/:captureId" element={<CaptureDetailPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:jobId" element={<JobDetailPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/captures" replace />} />
      </Route>
    </Routes>
  );
}
