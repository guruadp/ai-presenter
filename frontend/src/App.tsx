import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import KBDetailPage from "./pages/KBDetailPage";
import KBsPage from "./pages/KBsPage";
import PresenterControlPage from "./pages/PresenterControlPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import ProjectsPage from "./pages/ProjectsPage";
import ShowViewerPage from "./pages/ShowViewerPage";

export default function App() {
  return (
    <Routes>
      <Route path="/viewer/:projectId/:showFileId" element={<ShowViewerPage />} />
      <Route path="/present/:projectId/:showFileId" element={<PresenterControlPage />} />
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/kbs" replace />} />
        <Route path="kbs" element={<KBsPage />} />
        <Route path="kbs/:id" element={<KBDetailPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:id" element={<ProjectDetailPage />} />
      </Route>
    </Routes>
  );
}
