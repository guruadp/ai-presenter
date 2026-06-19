import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Clock,
  FileText,
  RefreshCw,
  Upload,
  Wand2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ProjectSlide, projectApi } from "../api/projects";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
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
  const scriptedCount = project.slides.filter((slide) => slide.script).length;

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
              <Badge variant={scriptedCount === project.slides.length && project.slides.length ? "green" : "amber"}>
                {scriptedCount}/{project.slides.length} scripted
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

        {(uploadMutation.error || generateMutation.error) && (
          <p className="text-xs text-red-500 mt-3">
            {((uploadMutation.error || generateMutation.error) as Error).message}
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
            className={`h-8 min-w-8 rounded-md px-2 text-sm font-medium transition-colors ${
              selectedIndex === index
                ? "bg-indigo-600 text-white"
                : "bg-gray-50 text-gray-600 hover:bg-gray-100"
            }`}
            aria-label={`Go to slide ${slide.position}`}
          >
            {slide.position}
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

  useEffect(() => {
    setFeedback("");
    setMakeShorter(false);
    setMoreEnergy(false);
    setMoreCitations(false);
  }, [slide?.id]);

  const regenerateMutation = useMutation({
    mutationFn: () =>
      projectApi.regenerateScript(projectId, slide!.id, {
        feedback: feedback.trim() || undefined,
        make_shorter: makeShorter,
        more_energy: moreEnergy,
        more_citations: moreCitations,
      }),
    onSuccess: () => onChanged(),
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
            <Badge variant="indigo">Draft v{script.version}</Badge>
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
            <div className="rounded-lg bg-gray-50 p-4">
              <p className="whitespace-pre-wrap text-sm leading-6 text-gray-800">
                {script.narration}
              </p>
            </div>

            {script.citations.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                  Citations
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {script.citations.map((citation) => (
                    <span
                      key={citation.id}
                      className="inline-flex max-w-full items-center gap-1 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600"
                      title={citation.value}
                    >
                      <span className="font-medium truncate">{citation.label}</span>
                      <span className="text-gray-300">·</span>
                      <span className="truncate">{citation.source}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                Delivery
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(script.delivery_style).map(([key, value]) => (
                  <Badge key={key}>{key}: {String(value)}</Badge>
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

        {regenerateMutation.error && (
          <p className="text-xs text-red-500">
            {(regenerateMutation.error as Error).message}
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

function invalidateProject(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string | undefined
) {
  queryClient.invalidateQueries({ queryKey: ["projects", id] });
  queryClient.invalidateQueries({ queryKey: ["projects"] });
}
