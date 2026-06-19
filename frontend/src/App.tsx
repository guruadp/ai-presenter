import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import KBDetailPage from "./pages/KBDetailPage";
import KBsPage from "./pages/KBsPage";
import ProjectsPage from "./pages/ProjectsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/kbs" replace />} />
        <Route path="kbs" element={<KBsPage />} />
        <Route path="kbs/:id" element={<KBDetailPage />} />
        <Route path="projects" element={<ProjectsPage />} />
      </Route>
    </Routes>
  );
}
