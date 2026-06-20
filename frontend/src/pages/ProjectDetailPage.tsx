import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Archive,
  BarChart2,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Clock,
  Edit3,
  FileText,
  Download,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  ScreenShare,
  Sparkles,
  Trash2,
  Upload,
  Wand2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { FAQ, FAQCandidate, PackageGate, ProjectSlide, ShowFile, projectApi } from "../api/projects";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Input from "../components/ui/Input";
import Spinner from "../components/ui/Spinner";
import Textarea from "../components/ui/Textarea";

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const { data: project, isLoading } = useQuery({
    queryKey: ["projects", id],
    queryFn: () => projectApi.get(id!),
    enabled: !!id,
  });
  const { data: packageGate } = useQuery({
    queryKey: ["projects", id, "package-gate"],
    queryFn: () => projectApi.packageGate(id!),
    enabled: !!id && !!project?.slides.length,
  });

  useEffect(() => {
    if (project?.slides.length && selectedIndex >= project.slides.length) {
      setSelectedIndex(project.slides.length - 1);
    }
  }, [project?.slides.length, selectedIndex]);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => projectApi.uploadDeck(id!, file),
    onSuccess: () => {
      setSelectedIndex(0);
      invalidateProject(queryClient, id);
    },
  });

  const generateMutation = useMutation({
    mutationFn: () => projectApi.generateScripts(id!),
    onSuccess: () => invalidateProject(queryClient, id),
  });
  const packageMutation = useMutation({
    mutationFn: () => projectApi.packageShowFile(id!),
    onSuccess: () => invalidateProject(queryClient, id),
  });

  if (isLoading) {
    return (
      <div className="flex justify-center pt-20">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!project) {
    return (
      <EmptyState
        icon={<FileText size={44} />}
        title="Project not found"
        description="This project may have been deleted."
        action={
          <Button variant="secondary" onClick={() => navigate("/projects")}>
            Back to Projects
          </Button>
        }
      />
    );
  }

  const selectedSlide = project.slides[selectedIndex] ?? null;
  const approvedCount = project.slides.filter((slide) => slide.script?.status === "approved").length;

  return (
    <>
      <div className="mb-6">
        <button
          onClick={() => navigate("/projects")}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-700 mb-4 transition-colors"
        >
          <ArrowLeft size={14} />
          Projects
        </button>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-semibold text-gray-900">
                {project.name}
              </h1>
              <Badge variant={approvedCount === project.slides.length && project.slides.length ? "green" : "amber"}>
                {approvedCount}/{project.slides.length} approved
              </Badge>
            </div>
            <p className="text-sm text-gray-500">
              by {project.owner} · {project.tone_profile.persona}
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="secondary"
              icon={<Upload size={14} />}
              loading={uploadMutation.isPending}
              onClick={() => fileRef.current?.click()}
            >
              Upload PPTX
            </Button>
            <Button
              icon={<Wand2 size={14} />}
              loading={generateMutation.isPending}
              disabled={!project.slides.length}
              onClick={() => generateMutation.mutate()}
            >
              Generate Scripts
            </Button>
            <Button
              variant="secondary"
              icon={<Archive size={14} />}
              loading={packageMutation.isPending}
              disabled={!project.slides.length || packageGate?.ok === false}
              onClick={() => packageMutation.mutate()}
            >
              Package Show File
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

        {(uploadMutation.error || generateMutation.error || packageMutation.error) && (
          <p className="text-xs text-red-500 mt-3">
            {((uploadMutation.error || generateMutation.error || packageMutation.error) as Error).message}
          </p>
        )}
      </div>

      {!project.slides.length ? (
        <EmptyState
          icon={<Upload size={44} />}
          title="Upload a deck to begin"
          description="Once slides are parsed, this page becomes your slide and script workspace."
          action={
            <Button icon={<Upload size={14} />} onClick={() => fileRef.current?.click()}>
              Upload PPTX
            </Button>
          }
        />
      ) : (
        <div className="space-y-4">
          <PackagePanel
            projectId={project.id}
            gate={packageGate}
            showFiles={project.show_files}
          />
          <SlidePager
            slides={project.slides}
            selectedIndex={selectedIndex}
            onSelect={setSelectedIndex}
          />

          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.1fr)_minmax(380px,0.9fr)] gap-5 items-start">
            <SlidePanel projectId={project.id} slide={selectedSlide} />
            <ScriptPanel
              projectId={project.id}
              slide={selectedSlide}
              onChanged={() => invalidateProject(queryClient, id)}
            />
          </div>

          {/* S12.3: Q&A Analytics */}
          <QAAnalyticsPanel projectId={project.id} />

          {/* S12.4: FAQ Management */}
          <FAQPanel projectId={project.id} />
        </div>
      )}
    </>
  );
}

function SlidePager({
  slides,
  selectedIndex,
  onSelect,
}: {
  slides: ProjectSlide[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}) {
  return (
    <div className="flex items-center gap-2 overflow-x-auto rounded-lg border border-gray-200 bg-white p-2">
      <Button
        variant="secondary"
        size="sm"
        icon={<ChevronLeft size={14} />}
        disabled={selectedIndex === 0}
        onClick={() => onSelect(selectedIndex - 1)}
      >
        Prev
      </Button>
      <div className="flex items-center gap-1">
        {slides.map((slide, index) => (
          <button
            key={slide.id}
            type="button"
            onClick={() => onSelect(index)}
            className={`relative h-8 min-w-8 rounded-md px-2 text-sm font-medium transition-colors ${
              selectedIndex === index
                ? "bg-indigo-600 text-white"
                : "bg-gray-50 text-gray-600 hover:bg-gray-100"
            }`}
            aria-label={`Go to slide ${slide.position}`}
          >
            {slide.position}
            {slide.script && (
              <span
                className={`absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border border-white ${
                  slide.script.status === "approved"
                    ? "bg-emerald-500"
                    : slide.script.status === "stale"
                      ? "bg-red-500"
                      : "bg-amber-400"
                }`}
              />
            )}
          </button>
        ))}
      </div>
      <Button
        variant="secondary"
        size="sm"
        icon={<ChevronRight size={14} />}
        disabled={selectedIndex === slides.length - 1}
        onClick={() => onSelect(selectedIndex + 1)}
      >
        Next
      </Button>
    </div>
  );
}

function PackagePanel({
  projectId,
  gate,
  showFiles,
}: {
  projectId: string;
  gate: PackageGate | undefined;
  showFiles: ShowFile[];
}) {
  const latest = [...showFiles].sort((a, b) => b.version - a.version)[0];

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Archive size={16} className="text-gray-400" />
            <h2 className="font-semibold text-gray-900">Packaging Gate</h2>
            {gate?.ok ? (
              <Badge variant="green">Ready</Badge>
            ) : (
              <Badge variant="amber">Needs review</Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-gray-500">
            Approved scripts are frozen with slide images and pre-rendered audio into an immutable Show File.
          </p>
          {gate && !gate.ok && (
            <ul className="mt-2 space-y-1 text-xs text-amber-700">
              {gate.errors.slice(0, 5).map((error) => (
                <li key={error}>• {error}</li>
              ))}
              {gate.errors.length > 5 && (
                <li>• {gate.errors.length - 5} more gate checks...</li>
              )}
            </ul>
          )}
        </div>

        {latest ? (
          <div className="rounded-lg bg-gray-50 px-3 py-2 text-sm">
            <div className="flex items-center gap-2">
              <Badge variant={latest.status === "ready" ? "green" : "red"}>
                Show v{latest.version} {latest.status}
              </Badge>
              <span className="text-xs text-gray-400">{latest.tts_provider}</span>
            </div>
            {latest.validation_errors.length > 0 && (
              <p className="mt-1 text-xs text-red-500">
                {latest.validation_errors.join(" · ")}
              </p>
            )}
            <div className="mt-2 flex items-center gap-2">
              <a
                href={`/present/${projectId}/${latest.id}`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
              >
                <ScreenShare size={13} />
                Launch Presenter
              </a>
              <a
                href={`/viewer/${projectId}/${latest.id}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-gray-700 border border-gray-300 hover:bg-gray-50"
              >
                <ScreenShare size={13} />
                Open Viewer
              </a>
              <a
                href={projectApi.showFileDownloadUrl(projectId, latest.id)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-gray-700 border border-gray-300 hover:bg-gray-50"
              >
                <Download size={13} />
                Download
              </a>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-400">No packaged Show File yet.</p>
        )}
      </div>
    </section>
  );
}

function SlidePanel({
  projectId,
  slide,
}: {
  projectId: string;
  slide: ProjectSlide | null;
}) {
  if (!slide) return null;

  return (
    <section className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <div>
          <p className="text-xs text-gray-400">Slide {slide.position}</p>
          <h2 className="font-semibold text-gray-900">
            {slide.title || "Untitled slide"}
          </h2>
        </div>
        {slide.vision_summary && <Badge variant="green">Vision ready</Badge>}
      </div>

      <div className="bg-gray-950 p-4">
        <div className="aspect-video overflow-hidden rounded-lg bg-white shadow-sm">
          {slide.image_path ? (
            <img
              src={projectApi.slideImageUrl(projectId, slide.id)}
              alt={`Slide ${slide.position}`}
              className="h-full w-full object-contain"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-gray-400">
              No rendered slide image yet
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 p-4 text-sm">
        {slide.body && (
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
              Extracted Text
            </p>
            <p className="mt-1 whitespace-pre-wrap text-gray-700">{slide.body}</p>
          </div>
        )}
        {slide.vision_summary && (
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
              Vision Summary
            </p>
            <p className="mt-1 line-clamp-3 text-gray-600">
              {slide.vision_summary}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function ScriptPanel({
  projectId,
  slide,
  onChanged,
}: {
  projectId: string;
  slide: ProjectSlide | null;
  onChanged: () => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [makeShorter, setMakeShorter] = useState(false);
  const [moreEnergy, setMoreEnergy] = useState(false);
  const [moreCitations, setMoreCitations] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [draftNarration, setDraftNarration] = useState("");
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);
  const [previewSegment, setPreviewSegment] = useState<number | null>(null);
  const [previewAudioUrl, setPreviewAudioUrl] = useState<string | null>(null);
  const [toneOverride, setToneOverride] = useState({
    persona: "",
    formality: "",
    pace: "",
  });
  const [previewConfig, setPreviewConfig] = useState({
    voice_id: "",
    emphasis: "balanced",
    pause_ms: "250",
  });

  useEffect(() => {
    setFeedback("");
    setMakeShorter(false);
    setMoreEnergy(false);
    setMoreCitations(false);
    setIsEditing(false);
    setSelectedCitationId(null);
    setPreviewSegment(null);
    if (previewAudioUrl) URL.revokeObjectURL(previewAudioUrl);
    setPreviewAudioUrl(null);
    setDraftNarration(slide?.script?.narration ?? "");
    setToneOverride({
      persona: stringValue(slide?.script?.tone_override.persona),
      formality: stringValue(slide?.script?.tone_override.formality),
      pace: stringValue(slide?.script?.tone_override.pace),
    });
    setPreviewConfig({
      voice_id: stringValue(slide?.script?.preview_config.voice_id),
      emphasis: stringValue(slide?.script?.preview_config.emphasis) || "balanced",
      pause_ms: stringValue(slide?.script?.preview_config.pause_ms) || "250",
    });
  }, [slide?.id, slide?.script]);

  const regenerateMutation = useMutation({
    mutationFn: () =>
      projectApi.regenerateScript(projectId, slide!.id, {
        feedback: feedback.trim() || undefined,
        make_shorter: makeShorter,
        more_energy: moreEnergy,
        more_citations: moreCitations,
        tone_override: compactObject(toneOverride),
      }),
    onSuccess: () => onChanged(),
  });
  const editMutation = useMutation({
    mutationFn: () => projectApi.editScript(projectId, slide!.id, draftNarration),
    onSuccess: () => {
      setIsEditing(false);
      onChanged();
    },
  });
  const approveMutation = useMutation({
    mutationFn: () => projectApi.approveScript(projectId, slide!.id),
    onSuccess: () => onChanged(),
  });
  const revertMutation = useMutation({
    mutationFn: () => projectApi.revertScript(projectId, slide!.id),
    onSuccess: () => {
      setIsEditing(false);
      onChanged();
    },
  });
  const settingsMutation = useMutation({
    mutationFn: () =>
      projectApi.updateReviewSettings(projectId, slide!.id, {
        tone_override: compactObject(toneOverride),
        preview_config: compactObject(previewConfig),
      }),
    onSuccess: () => onChanged(),
  });
  const previewAudioMutation = useMutation({
    mutationFn: async (segmentIndex: number) => {
      const blob = await projectApi.previewSegmentAudio(
        projectId,
        slide!.id,
        segmentIndex,
        compactObject(previewConfig)
      );
      return { segmentIndex, url: URL.createObjectURL(blob) };
    },
    onSuccess: ({ segmentIndex, url }) => {
      if (previewAudioUrl) URL.revokeObjectURL(previewAudioUrl);
      setPreviewSegment(segmentIndex);
      setPreviewAudioUrl(url);
    },
  });

  if (!slide) return null;

  const script = slide.script;

  return (
    <section className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <div>
          <p className="text-xs text-gray-400">Script</p>
          <h2 className="font-semibold text-gray-900">
            Slide {slide.position} narration
          </h2>
        </div>
        {script ? (
          <div className="flex items-center gap-2">
            <ScriptStatusBadge status={script.status} />
            <Badge variant="indigo">v{script.version}</Badge>
            <span className="inline-flex items-center gap-1 text-xs text-gray-400">
              <Clock size={12} />
              {script.duration_seconds}s
            </span>
          </div>
        ) : (
          <Badge variant="amber">Not generated</Badge>
        )}
      </div>

      <div className="p-4 space-y-4">
        {script ? (
          <>
            {script.stale_reasons.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                {script.stale_reasons.join(" · ")}
              </div>
            )}

            <div className="flex items-center gap-2 flex-wrap">
              <Button
                size="sm"
                variant="secondary"
                icon={<Edit3 size={13} />}
                onClick={() => {
                  setDraftNarration(script.narration);
                  setIsEditing((editing) => !editing);
                }}
              >
                {isEditing ? "Cancel Edit" : "Edit"}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                icon={<RotateCcw size={13} />}
                disabled={!script.revision_history.length}
                loading={revertMutation.isPending}
                onClick={() => revertMutation.mutate()}
              >
                Revert
              </Button>
              <Button
                size="sm"
                icon={<Check size={13} />}
                loading={approveMutation.isPending}
                disabled={script.status === "approved"}
                onClick={() => approveMutation.mutate()}
              >
                Approve
              </Button>
            </div>

            <div className="rounded-lg bg-gray-50 p-4">
              {isEditing ? (
                <div className="space-y-3">
                  <Textarea
                    label="Editable narration"
                    value={draftNarration}
                    onChange={(e) => setDraftNarration(e.target.value)}
                    rows={8}
                  />
                  <Button
                    icon={<Save size={14} />}
                    loading={editMutation.isPending}
                    disabled={!draftNarration.trim()}
                    onClick={() => editMutation.mutate()}
                  >
                    Save Version
                  </Button>
                </div>
              ) : (
                <p className="whitespace-pre-wrap text-sm leading-6 text-gray-800">
                  {script.narration}
                </p>
              )}
            </div>

            {script.citations.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                  Citations
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {script.citations.map((citation) => (
                    <button
                      type="button"
                      key={citation.id}
                      onClick={() =>
                        setSelectedCitationId((current) =>
                          current === citation.id ? null : citation.id
                        )
                      }
                      className="inline-flex max-w-full items-center gap-1 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 hover:border-indigo-200 hover:text-indigo-700"
                    >
                      <span className="font-medium truncate">{citation.label}</span>
                      <span className="text-gray-300">·</span>
                      <span className="truncate">{citation.source}</span>
                    </button>
                  ))}
                </div>
                {selectedCitationId && (
                  <div className="mt-2 rounded-lg border border-gray-200 bg-white p-3 text-xs text-gray-600">
                    {script.citations
                      .filter((citation) => citation.id === selectedCitationId)
                      .map((citation) => (
                        <div key={citation.id}>
                          <p className="font-semibold text-gray-900">{citation.label}</p>
                          <p className="mt-1">{citation.value}</p>
                          <p className="mt-1 text-gray-400">
                            {citation.source} · KB v{citation.kb_version ?? "?"}
                          </p>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            )}

            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                Tone Override
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <Input
                  label="Persona"
                  placeholder={String(script.delivery_style.persona ?? "helpful presenter")}
                  value={toneOverride.persona}
                  onChange={(e) => setToneOverride((v) => ({ ...v, persona: e.target.value }))}
                />
                <Input
                  label="Formality"
                  placeholder={String(script.delivery_style.formality ?? "balanced")}
                  value={toneOverride.formality}
                  onChange={(e) => setToneOverride((v) => ({ ...v, formality: e.target.value }))}
                />
                <Input
                  label="Pace"
                  placeholder={String(script.delivery_style.pace ?? "normal")}
                  value={toneOverride.pace}
                  onChange={(e) => setToneOverride((v) => ({ ...v, pace: e.target.value }))}
                />
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
                  Voice + Delivery Preview
                </p>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Save size={13} />}
                  loading={settingsMutation.isPending}
                  onClick={() => settingsMutation.mutate()}
                >
                  Save Preview Settings
                </Button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                <Input
                  label="Voice"
                  placeholder="Voice ID"
                  value={previewConfig.voice_id}
                  onChange={(e) => setPreviewConfig((v) => ({ ...v, voice_id: e.target.value }))}
                />
                <Input
                  label="Emphasis"
                  value={previewConfig.emphasis}
                  onChange={(e) => setPreviewConfig((v) => ({ ...v, emphasis: e.target.value }))}
                />
                <Input
                  label="Pause ms"
                  value={previewConfig.pause_ms}
                  onChange={(e) => setPreviewConfig((v) => ({ ...v, pause_ms: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                {script.segments.map((segment) => (
                  <div
                    key={segment.index}
                    className="rounded-lg border border-gray-200 bg-white p-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm text-gray-700">{segment.text}</p>
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={<Play size={13} />}
                        loading={
                          previewAudioMutation.isPending &&
                          previewAudioMutation.variables === segment.index
                        }
                        onClick={() => previewAudioMutation.mutate(segment.index)}
                      >
                        Preview
                      </Button>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {segment.audio_tags.map((tag) => (
                        <Badge key={tag}>{tag}</Badge>
                      ))}
                    </div>
                    {previewSegment === segment.index && (
                      <div className="mt-2 rounded-md bg-indigo-50 px-2 py-2">
                        <p className="mb-2 text-xs text-indigo-700">
                          Playing with {previewConfig.voice_id || "project voice"}, {previewConfig.emphasis} emphasis, {previewConfig.pause_ms}ms pauses.
                        </p>
                        {previewAudioUrl && (
                          <audio
                            key={previewAudioUrl}
                            src={previewAudioUrl}
                            controls
                            autoPlay
                            className="w-full"
                          />
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <Textarea
              label="Regeneration feedback"
              placeholder="Make it tighter, more executive, warmer, or add more citations"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              rows={3}
            />
            <div className="flex items-center gap-4 flex-wrap">
              <Toggle checked={makeShorter} onChange={setMakeShorter} label="Shorter" />
              <Toggle checked={moreEnergy} onChange={setMoreEnergy} label="More energy" />
              <Toggle checked={moreCitations} onChange={setMoreCitations} label="More citations" />
              <Button
                icon={<RefreshCw size={14} />}
                loading={regenerateMutation.isPending}
                onClick={() => regenerateMutation.mutate()}
              >
                Regenerate Slide
              </Button>
            </div>
          </>
        ) : (
          <EmptyState
            icon={<Wand2 size={40} />}
            title="No script yet"
            description="Generate project scripts to create a narration draft for this slide."
          />
        )}

        {(regenerateMutation.error ||
          editMutation.error ||
          approveMutation.error ||
          revertMutation.error ||
          settingsMutation.error ||
          previewAudioMutation.error) && (
          <p className="text-xs text-red-500">
            {errorMessage(
              regenerateMutation.error ||
                editMutation.error ||
                approveMutation.error ||
                revertMutation.error ||
                settingsMutation.error ||
                previewAudioMutation.error
            )}
          </p>
        )}
      </div>
    </section>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-gray-600">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
      />
      {label}
    </label>
  );
}

function ScriptStatusBadge({ status }: { status: string }) {
  if (status === "approved") return <Badge variant="green">Approved</Badge>;
  if (status === "stale") return <Badge variant="red">Stale</Badge>;
  return <Badge variant="amber">Draft</Badge>;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function compactObject(values: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => String(value ?? "").trim())
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Review action failed";
}

function invalidateProject(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string | undefined
) {
  queryClient.invalidateQueries({ queryKey: ["projects", id] });
  queryClient.invalidateQueries({ queryKey: ["projects"] });
}

// ── S12.3: Q&A Analytics Panel ───────────────────────────────────────────────

function QAAnalyticsPanel({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false);
  const { data: analytics } = useQuery({
    queryKey: ["qa-analytics", projectId],
    queryFn: () => projectApi.getQAAnalytics(projectId),
    enabled: open,
  });

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-5 py-3.5 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <BarChart2 size={15} className="text-indigo-500" />
          <span className="font-medium text-sm text-gray-800">Q&amp;A Analytics</span>
          {analytics && analytics.total_questions > 0 && (
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600">
              {analytics.total_questions} questions
            </span>
          )}
        </div>
        <ChevronDown size={15} className={`text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="border-t border-gray-100 p-5">
          {!analytics || analytics.total_questions === 0 ? (
            <p className="text-sm text-gray-400 text-center py-4">
              No questions recorded yet. Q&amp;A history is captured live during presentations.
            </p>
          ) : (
            <div className="space-y-5">
              {/* Summary row */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "Total asked", value: analytics.total_questions },
                  { label: "Deferred", value: analytics.deferred_count },
                  { label: "Deferral rate", value: `${(analytics.deferral_rate * 100).toFixed(0)}%` },
                  { label: "FAQ served", value: analytics.faq_hit_count },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-lg bg-gray-50 px-3 py-2">
                    <p className="text-xs text-gray-400">{label}</p>
                    <p className="font-semibold text-gray-900 text-sm">{value}</p>
                  </div>
                ))}
              </div>

              {/* Type distribution */}
              {Object.keys(analytics.type_distribution).length > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    By type
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(analytics.type_distribution).map(([type, count]) => (
                      <span key={type} className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs text-indigo-700">
                        {type} · {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Top questions */}
              {analytics.top_questions.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Most asked
                  </p>
                  <div className="space-y-1.5">
                    {analytics.top_questions.slice(0, 5).map((q, i) => (
                      <div key={i} className="flex items-start gap-2 rounded-lg bg-gray-50 px-3 py-2">
                        <span className="text-xs text-gray-400 shrink-0 pt-0.5">{q.count}×</span>
                        <p className="text-sm text-gray-800 min-w-0 break-words">{q.question}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── S12.4: FAQ Management Panel ──────────────────────────────────────────────

function FAQPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"faqs" | "candidates">("faqs");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editAnswer, setEditAnswer] = useState("");

  const { data: faqs = [], isLoading: loadingFaqs } = useQuery({
    queryKey: ["faqs", projectId],
    queryFn: () => projectApi.listFAQs(projectId),
    enabled: open && tab === "faqs",
  });

  const { data: candidates = [], isLoading: loadingCandidates } = useQuery({
    queryKey: ["faq-candidates", projectId],
    queryFn: () => projectApi.getFAQCandidates(projectId),
    enabled: open && tab === "candidates",
  });

  const approveMutation = useMutation({
    mutationFn: (faqId: string) => projectApi.updateFAQ(projectId, faqId, { approved: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["faqs", projectId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (faqId: string) => projectApi.deleteFAQ(projectId, faqId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["faqs", projectId] }),
  });

  const editMutation = useMutation({
    mutationFn: ({ id, answer }: { id: string; answer: string }) =>
      projectApi.updateFAQ(projectId, id, { canonical_answer: answer }),
    onSuccess: () => {
      setEditingId(null);
      queryClient.invalidateQueries({ queryKey: ["faqs", projectId] });
    },
  });

  const preBakeMutation = useMutation({
    mutationFn: (faqId: string) => projectApi.preBakeFAQ(projectId, faqId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["faqs", projectId] }),
  });

  const promoteMutation = useMutation({
    mutationFn: (c: FAQCandidate) =>
      projectApi.createFAQ(projectId, {
        question: c.question,
        canonical_answer: c.answer_text,
        question_type: c.question_type,
        promoted_from_qa: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["faqs", projectId] });
      queryClient.invalidateQueries({ queryKey: ["faq-candidates", projectId] });
    },
  });

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-5 py-3.5 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <BookOpen size={15} className="text-emerald-500" />
          <span className="font-medium text-sm text-gray-800">FAQ Library</span>
          {faqs.length > 0 && (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-600">
              {faqs.filter((f) => f.approved).length} approved
            </span>
          )}
        </div>
        <ChevronDown size={15} className={`text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="border-t border-gray-100">
          {/* Tabs */}
          <div className="flex gap-0 border-b border-gray-100 px-5">
            {(["faqs", "candidates"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`py-2.5 px-3 text-sm font-medium border-b-2 transition-colors ${
                  tab === t
                    ? "border-indigo-500 text-indigo-600"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
              >
                {t === "faqs" ? "Library" : "Candidates"}
              </button>
            ))}
          </div>

          <div className="p-5 space-y-3">
            {tab === "faqs" && (
              <>
                {loadingFaqs ? (
                  <div className="flex justify-center py-4"><Spinner /></div>
                ) : faqs.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-4">
                    No FAQs yet. Promote frequent questions from the Candidates tab or add manually.
                  </p>
                ) : (
                  faqs.map((faq) => (
                    <FAQCard
                      key={faq.id}
                      faq={faq}
                      isEditing={editingId === faq.id}
                      editAnswer={editAnswer}
                      onEditStart={() => { setEditingId(faq.id); setEditAnswer(faq.canonical_answer); }}
                      onEditChange={setEditAnswer}
                      onEditSave={() => editMutation.mutate({ id: faq.id, answer: editAnswer })}
                      onEditCancel={() => setEditingId(null)}
                      onApprove={() => approveMutation.mutate(faq.id)}
                      onDelete={() => deleteMutation.mutate(faq.id)}
                      onPreBake={() => preBakeMutation.mutate(faq.id)}
                      saving={editMutation.isPending}
                      approving={approveMutation.isPending}
                      baking={preBakeMutation.isPending}
                    />
                  ))
                )}
              </>
            )}

            {tab === "candidates" && (
              <>
                {loadingCandidates ? (
                  <div className="flex justify-center py-4"><Spinner /></div>
                ) : candidates.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-4">
                    No candidates yet. Questions asked ≥ 2 times will appear here.
                  </p>
                ) : (
                  candidates.map((c, i) => (
                    <div key={i} className="rounded-lg border border-gray-100 bg-gray-50 p-3 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium text-gray-800 leading-snug">{c.question}</p>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="text-xs text-gray-400">{c.occurrence_count}×</span>
                          <Button
                            size="sm"
                            icon={<Plus size={12} />}
                            loading={promoteMutation.isPending}
                            onClick={() => promoteMutation.mutate(c)}
                          >
                            Promote
                          </Button>
                        </div>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">{c.answer_text}</p>
                      <span className="text-xs text-gray-400">
                        {c.question_type} · {(c.confidence * 100).toFixed(0)}% conf
                      </span>
                    </div>
                  ))
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function FAQCard({
  faq,
  isEditing,
  editAnswer,
  onEditStart,
  onEditChange,
  onEditSave,
  onEditCancel,
  onApprove,
  onDelete,
  onPreBake,
  saving,
  approving,
  baking,
}: {
  faq: FAQ;
  isEditing: boolean;
  editAnswer: string;
  onEditStart: () => void;
  onEditChange: (v: string) => void;
  onEditSave: () => void;
  onEditCancel: () => void;
  onApprove: () => void;
  onDelete: () => void;
  onPreBake: () => void;
  saving: boolean;
  approving: boolean;
  baking: boolean;
}) {
  return (
    <div className={`rounded-lg border p-3 space-y-2 ${faq.approved ? "border-emerald-200 bg-emerald-50/40" : "border-gray-200 bg-white"}`}>
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800 leading-snug">{faq.question}</p>
          <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
            {faq.approved ? (
              <span className="text-xs text-emerald-600 font-medium">✓ Approved</span>
            ) : (
              <span className="text-xs text-amber-600">Pending review</span>
            )}
            <span className="text-xs text-gray-400">·</span>
            <span className="text-xs text-gray-400">{faq.question_type}</span>
            {faq.hit_count > 0 && (
              <>
                <span className="text-xs text-gray-400">·</span>
                <span className="text-xs text-gray-400">served {faq.hit_count}×</span>
              </>
            )}
            {faq.pre_rendered_audio_path && (
              <>
                <span className="text-xs text-gray-400">·</span>
                <span className="text-xs text-indigo-500">🔊 pre-baked</span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {!faq.approved && (
            <button
              onClick={onApprove}
              disabled={approving}
              title="Approve"
              className="rounded-md p-1 text-gray-400 hover:bg-emerald-50 hover:text-emerald-600"
            >
              <Check size={13} />
            </button>
          )}
          {faq.approved && !faq.pre_rendered_audio_path && (
            <button
              onClick={onPreBake}
              disabled={baking}
              title="Pre-bake audio"
              className="rounded-md p-1 text-gray-400 hover:bg-indigo-50 hover:text-indigo-600"
            >
              <Sparkles size={13} />
            </button>
          )}
          <button
            onClick={onEditStart}
            title="Edit answer"
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <Edit3 size={13} />
          </button>
          <button
            onClick={onDelete}
            title="Delete"
            className="rounded-md p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {isEditing ? (
        <div className="space-y-2">
          <textarea
            value={editAnswer}
            onChange={(e) => onEditChange(e.target.value)}
            rows={3}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 resize-none"
          />
          <div className="flex gap-2 justify-end">
            <Button size="sm" variant="secondary" onClick={onEditCancel}>Cancel</Button>
            <Button size="sm" loading={saving} icon={<Save size={12} />} onClick={onEditSave}>Save</Button>
          </div>
        </div>
      ) : (
        <p className="text-xs text-gray-600 line-clamp-3">{faq.canonical_answer}</p>
      )}
    </div>
  );
}
