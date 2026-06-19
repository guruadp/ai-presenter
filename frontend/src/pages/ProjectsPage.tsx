import { FolderOpen } from "lucide-react";
import EmptyState from "../components/ui/EmptyState";

export default function ProjectsPage() {
  return (
    <>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">Projects</h1>
        <p className="text-sm text-gray-500 mt-1">
          Each project pairs a slide deck with one or more knowledge bases
        </p>
      </div>
      <EmptyState
        icon={<FolderOpen size={48} />}
        title="Projects coming in Epic 2"
        description="Once you've set up your knowledge bases, create a project to upload a deck and generate a verified presentation."
      />
    </>
  );
}
