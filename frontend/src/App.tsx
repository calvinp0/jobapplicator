import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./layout/Layout";
import { CapturesPage } from "./pages/CapturesPage";
import { JobsPage } from "./pages/JobsPage";
import { RunsPage } from "./pages/RunsPage";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/captures" replace />} />
        <Route path="/captures" element={<CapturesPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/captures" replace />} />
      </Route>
    </Routes>
  );
}
