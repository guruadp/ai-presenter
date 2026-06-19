import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  FileText,
  FolderOpen,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useRef, useState } from "react";
import { KB, ago, kbApi } from "../api/kbs";
import { Project, ToneProfile, projectApi } from "../api/projects";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Input from "../components/ui/Input";
import Modal from "../components/ui/Modal";
import Spinner from "../components/ui/Spinner";
import Textarea from "../components/ui/Textarea";

const defaultTone: ToneProfile = {
  formality: "balanced",
  pace: "normal",
  persona: "helpful presenter",
  dos: [],
  donts: [],
  language: "en",
  voice_id: null,
};

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);

  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: projectApi.list,
  });

  const { data: kbs = [] } = useQuery({
    queryKey: ["kbs"],
    queryFn: kbApi.list,
  });

  return (
    <>
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Projects</h1>
          <p className="text-sm text-gray-500 mt-1">
            Pair a slide deck with version-pinned knowledge bases
          </p>
        </div>
        <Button icon={<Plus size={15} />} onClick={() => setShowCreate(true)}>
          New Project
        </Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center pt-20">
          <Spinner size="lg" />
        </div>
      ) : !projects?.length ? (
        <EmptyState
          icon={<FolderOpen size={48} />}
          title="No projects yet"
          description="Create a project, attach knowledge bases, and upload a PPTX deck for scripting."
          action={
            <Button icon={<Plus size={15} />} onClick={() => setShowCreate(true)}>
              Create Project
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              kbs={kbs}
              onDelete={() => setDeleteTarget(project)}
              onChanged={() => {
                queryClient.invalidateQueries({ queryKey: ["projects"] });
              }}
            />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateProjectModal
          kbs={kbs}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["projects"] });
            setShowCreate(false);
          }}
        />
      )}

      {deleteTarget && (
        <DeleteProjectModal
          project={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => {
            queryClient.invalidateQueries({ queryKey: ["projects"] });
            setDeleteTarget(null);
          }}
        />
      )}
    </>
  );
}

function ProjectCard({
  project,
  kbs,
  onDelete,
  onChanged,
}: {
  project: Project;
  kbs: KB[];
  onDelete: () => void;
  onChanged: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const uploadMutation = useMutation({
    mutationFn: (file: File) => projectApi.uploadDeck(project.id, file),
    onSuccess: onChanged,
  });
  const kbNames = project.knowledge_bases.map((link) => {
    const kb = kbs.find((item) => item.id === link.kb_id);
    return {
      label: kb?.name ?? link.kb_id.slice(0, 8),
      version: link.pinned_version,
    };
  });

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-9 h-9 bg-indigo-50 rounded-lg flex items-center justify-center shrink-0">
              <FolderOpen size={18} className="text-indigo-600" />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-gray-900 truncate">
                {project.name}
              </h3>
              <p className="text-xs text-gray-400">
                by {project.owner} · updated {ago(project.updated_at)}
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={<Upload size={14} />}
            loading={uploadMutation.isPending}
            onClick={() => fileRef.current?.click()}
          >
            Upload PPTX
          </Button>
          <Button
            variant="danger"
            size="sm"
            icon={<Trash2 size={14} />}
            onClick={onDelete}
            aria-label={`Delete ${project.name}`}
          >
            Delete
          </Button>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".pptx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadMutation.mutate(file);
            e.target.value = "";
          }}
        />
      </div>

      <div className="flex items-center gap-2 flex-wrap mt-4">
        {kbNames.length ? (
          kbNames.map((kb) => (
            <Badge key={`${kb.label}-${kb.version}`} variant="indigo">
              {kb.label} v{kb.version}
            </Badge>
          ))
        ) : (
          <span className="text-xs text-gray-400">No knowledge bases attached</span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4 text-sm">
        <div className="bg-gray-50 rounded-lg px-3 py-2">
          <p className="text-xs text-gray-400">Slides</p>
          <p className="font-semibold text-gray-900">{project.slides.length}</p>
        </div>
        <div className="bg-gray-50 rounded-lg px-3 py-2">
          <p className="text-xs text-gray-400">Persona</p>
          <p className="font-semibold text-gray-900 truncate">
            {project.tone_profile.persona}
          </p>
        </div>
        <div className="bg-gray-50 rounded-lg px-3 py-2">
          <p className="text-xs text-gray-400">Voice</p>
          <p className="font-semibold text-gray-900 truncate">
            {project.tone_profile.voice_id || "Not set"}
          </p>
        </div>
      </div>

      {project.slides.length > 0 && (
        <div className="mt-4 border-t border-gray-100 pt-4">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
            Parsed slides ({project.slides.length})
          </p>
          <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
            {project.slides.map((slide) => (
              <div key={slide.id} className="flex items-center gap-2 text-sm">
                <FileText size={14} className="text-gray-300 shrink-0" />
                <span className="text-gray-500">#{slide.position}</span>
                <span className="font-medium text-gray-800 truncate">
                  {slide.title || "Untitled slide"}
                </span>
                {slide.vision_summary && (
                  <Badge variant="green">Vision ready</Badge>
                )}
              </div>
            ))}
          </div>
          {project.slides[0]?.vision_summary && (
            <p className="text-xs text-gray-500 mt-3 line-clamp-2">
              Vision summaries are ready for all{" "}
              {
                project.slides.filter((slide) => slide.vision_summary).length
              }{" "}
              parsed slides.
            </p>
          )}
        </div>
      )}

      {uploadMutation.error && (
        <p className="text-xs text-red-500 mt-3">
          {(uploadMutation.error as Error).message}
        </p>
      )}
    </div>
  );
}

function DeleteProjectModal({
  project,
  onClose,
  onDeleted,
}: {
  project: Project;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const deleteMutation = useMutation({
    mutationFn: () => projectApi.delete(project.id),
    onSuccess: onDeleted,
  });

  return (
    <Modal
      title="Delete Project"
      onClose={onClose}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={deleteMutation.isPending}
            icon={<Trash2 size={14} />}
            onClick={() => deleteMutation.mutate()}
          >
            Delete
          </Button>
        </>
      }
    >
      <p className="text-sm text-gray-600">
        Delete{" "}
        <span className="font-semibold text-gray-900">{project.name}</span>?
        This removes the project, uploaded deck, parsed slides, and vision
        summaries from the database.
      </p>
      {deleteMutation.error && (
        <p className="text-xs text-red-500 mt-3">
          {(deleteMutation.error as Error).message}
        </p>
      )}
    </Modal>
  );
}

function CreateProjectModal({
  kbs,
  onClose,
  onCreated,
}: {
  kbs: KB[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState({
    name: "",
    owner: "",
    kbIds: [] as string[],
    formality: defaultTone.formality,
    pace: defaultTone.pace,
    persona: defaultTone.persona,
    language: defaultTone.language,
    voiceId: "",
    dos: "",
    donts: "",
  });
  const [kbDropdownOpen, setKbDropdownOpen] = useState(false);

  const createMutation = useMutation({
    mutationFn: () =>
      projectApi.create({
        name: form.name.trim(),
        owner: form.owner.trim(),
        kb_ids: form.kbIds,
        tone_profile: {
          formality: form.formality,
          pace: form.pace,
          persona: form.persona,
          language: form.language,
          voice_id: form.voiceId.trim() || null,
          dos: splitLines(form.dos),
          donts: splitLines(form.donts),
        },
      }),
    onSuccess: onCreated,
  });

  function toggleKb(kbId: string) {
    setForm((current) => ({
      ...current,
      kbIds: current.kbIds.includes(kbId)
        ? current.kbIds.filter((id) => id !== kbId)
        : [...current.kbIds, kbId],
    }));
  }

  return (
    <Modal
      title="New Project"
      onClose={onClose}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            loading={createMutation.isPending}
            disabled={!form.name.trim() || !form.owner.trim()}
            onClick={() => createMutation.mutate()}
          >
            Create Project
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input
          label="Name"
          placeholder="e.g. Launch Demo"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          autoFocus
        />
        <Input
          label="Owner"
          placeholder="e.g. alice"
          value={form.owner}
          onChange={(e) => setForm((f) => ({ ...f, owner: e.target.value }))}
        />
        <Input
          label="Persona"
          placeholder="e.g. product strategist"
          value={form.persona}
          onChange={(e) => setForm((f) => ({ ...f, persona: e.target.value }))}
        />
        <Input
          label="Voice ID"
          placeholder="Optional"
          value={form.voiceId}
          onChange={(e) => setForm((f) => ({ ...f, voiceId: e.target.value }))}
        />
        <Input
          label="Formality"
          value={form.formality}
          onChange={(e) =>
            setForm((f) => ({ ...f, formality: e.target.value }))
          }
        />
        <Input
          label="Pace"
          value={form.pace}
          onChange={(e) => setForm((f) => ({ ...f, pace: e.target.value }))}
        />
        <Input
          label="Language"
          value={form.language}
          onChange={(e) =>
            setForm((f) => ({ ...f, language: e.target.value }))
          }
        />

        <div className="sm:col-span-2">
          <p className="text-sm font-medium text-gray-700 mb-2">
            Knowledge Bases
          </p>
          {kbs.length ? (
            <div className="relative">
              <button
                type="button"
                onClick={() => setKbDropdownOpen((open) => !open)}
                className="w-full min-h-10 flex items-center justify-between gap-3 bg-white border border-gray-300 rounded-lg px-3 py-2 text-left focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              >
                <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                  {form.kbIds.length ? (
                    form.kbIds.map((kbId) => {
                      const kb = kbs.find((item) => item.id === kbId);
                      return (
                        <span
                          key={kbId}
                          className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700"
                        >
                          <span className="max-w-40 truncate">
                            {kb?.name ?? kbId.slice(0, 8)}
                          </span>
                          <span
                            role="button"
                            tabIndex={0}
                            className="rounded hover:bg-indigo-100"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleKb(kbId);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                e.stopPropagation();
                                toggleKb(kbId);
                              }
                            }}
                          >
                            <X size={12} />
                          </span>
                        </span>
                      );
                    })
                  ) : (
                    <span className="text-sm text-gray-400">
                      Select one or more knowledge bases
                    </span>
                  )}
                </div>
                <ChevronDown
                  size={16}
                  className={`text-gray-400 shrink-0 transition-transform ${
                    kbDropdownOpen ? "rotate-180" : ""
                  }`}
                />
              </button>

              {kbDropdownOpen && (
                <div className="absolute z-20 mt-1 w-full max-h-56 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg py-1">
                  {kbs.map((kb) => {
                    const checked = form.kbIds.includes(kb.id);
                    return (
                      <label
                        key={kb.id}
                        className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-gray-50"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleKb(kb.id)}
                          className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span className="min-w-0">
                          <span className="block text-sm font-medium text-gray-800 truncate">
                            {kb.name}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
              <p className="text-xs text-gray-400 mt-1">
                Selected KB versions are pinned when the project is created.
              </p>
            </div>
          ) : (
            <p className="text-sm text-gray-400">
              No knowledge bases yet. You can create the project now and attach
              knowledge later through the API.
            </p>
          )}
        </div>

        {/* Keep the tone guidance fields below the dropdown so the menu has room. */}
        <Textarea
          label="Do"
          placeholder="One guidance item per line"
          value={form.dos}
          onChange={(e) => setForm((f) => ({ ...f, dos: e.target.value }))}
          rows={3}
        />
        <Textarea
          label="Don't"
          placeholder="One avoidance item per line"
          value={form.donts}
          onChange={(e) => setForm((f) => ({ ...f, donts: e.target.value }))}
          rows={3}
        />
      </div>

      {createMutation.error && (
        <p className="text-xs text-red-500 mt-4">
          {(createMutation.error as Error).message}
        </p>
      )}
    </Modal>
  );
}

function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}
