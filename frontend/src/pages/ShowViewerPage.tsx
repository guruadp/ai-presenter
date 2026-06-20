import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  Mic,
  MicOff,
  Play,
  RotateCcw,
  ScreenShare,
  Square,
  StepForward,
  Volume2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AnswerResponse, projectApi } from "../api/projects";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Spinner from "../components/ui/Spinner";
import { LaptopSpeaker } from "../services/audioOutput";

interface ShowSegment {
  index: number;
  text: string;
  audio_path?: string;
}

interface ShowSlide {
  slide_id: string;
  position: number;
  title: string | null;
  image_path: string;
  duration_seconds: number;
  segments: ShowSegment[];
}

type ShowEvent =
  | { type: "render_done"; slide: number; at: string }
  | { type: "tts_complete"; slide: number; segment: number; at: string };

export default function ShowViewerPage() {
  const { projectId, showFileId } = useParams<{
    projectId: string;
    showFileId: string;
  }>();
  const navigate = useNavigate();

  // ── Slide state ────────────────────────────────────────────────────────────
  const [index, setIndex] = useState(0);
  const [jumpStack, setJumpStack] = useState<number[]>([]);
  const [showEvents, setShowEvents] = useState<ShowEvent[]>([]);

  // ── Audio state (S8.1) ─────────────────────────────────────────────────────
  const [segIdx, setSegIdx] = useState<number | null>(null);
  const [autoPlay, setAutoPlay] = useState(true);

  // Refs so async callbacks always see fresh values
  const speakerRef = useRef(new LaptopSpeaker());
  const genRef = useRef(0);        // incremented to invalidate stale onEnded callbacks
  const stopAfterRef = useRef(false);
  const indexRef = useRef(index);
  const autoPlayRef = useRef(autoPlay);
  const slidesLenRef = useRef(0);
  const advanceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const segIdxRef = useRef<number | null>(null);
  // Snapshot of narration state at the moment Q&A interrupted it
  const qaInterruptRef = useRef<{
    segIdx: number | null;
    slideIndex: number;
    wasInGap: boolean;
  } | null>(null);

  const SLIDE_GAP_MS = 2000; // pause between slides when auto-advancing

  // ── Live TTS state (S8.2) ──────────────────────────────────────────────────
  const [speakText, setSpeakText] = useState("");
  const [isSpeaking, setIsSpeaking] = useState(false);
  const liveSpeakerRef = useRef(new LaptopSpeaker());

  // ── Video export state ────────────────────────────────────────────────────
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // ── Q&A state (S9) ────────────────────────────────────────────────────────
  const [sessionId] = useState(() => crypto.randomUUID());
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isAnswering, setIsAnswering] = useState(false);
  const [qaTranscript, setQaTranscript] = useState<string | null>(null);
  const [qaAnswer, setQaAnswer] = useState<AnswerResponse | null>(null);
  const [qaHistory, setQaHistory] = useState<Array<{ question: string; answer: AnswerResponse; at: string }>>([]);
  const [micError, setMicError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // ── Show file data ─────────────────────────────────────────────────────────
  const { data: showFile, isLoading } = useQuery({
    queryKey: ["show-file", projectId, showFileId],
    queryFn: () => projectApi.getShowFile(projectId!, showFileId!),
    enabled: !!projectId && !!showFileId,
  });

  const slides = useMemo(
    () => ((showFile?.manifest.slides as ShowSlide[] | undefined) ?? []),
    [showFile]
  );
  const current = slides[index] ?? null;

  const voiceId = useMemo(
    () =>
      ((showFile?.manifest?.voice_config as Record<string, unknown> | undefined)
        ?.voice_id as string | null) ?? null,
    [showFile]
  );

  // Keep refs in sync with state so async callbacks read fresh values
  indexRef.current = index;
  autoPlayRef.current = autoPlay;
  slidesLenRef.current = slides.length;
  segIdxRef.current = segIdx;

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "ArrowRight" || e.key === "PageDown") next();
      if (e.key === "ArrowLeft" || e.key === "PageUp") prev();
      if (e.key === "Escape") navigate(`/projects/${projectId}`);
      if (e.key === "b") jumpBack();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  });

  // ── Slide navigation ───────────────────────────────────────────────────────
  function goto(nextIndex: number, pushCurrent = true) {
    if (nextIndex < 0 || nextIndex >= slides.length || nextIndex === index) return;
    if (pushCurrent) setJumpStack((stack) => [...stack, index]);
    setIndex(nextIndex);
  }

  function next() {
    goto(Math.min(index + 1, slides.length - 1), false);
  }

  function prev() {
    goto(Math.max(index - 1, 0), false);
  }

  function jumpBack() {
    setJumpStack((stack) => {
      const nextStack = [...stack];
      const previous = nextStack.pop();
      if (previous !== undefined) setIndex(previous);
      return nextStack;
    });
  }

  // ── Narration playback (S8.1) ──────────────────────────────────────────────
  function playSegment(slide: ShowSlide, sIdx: number) {
    const gen = ++genRef.current;
    const seg = slide.segments[sIdx];
    if (!seg?.audio_path || !projectId || !showFileId) {
      setSegIdx(null);
      return;
    }

    setSegIdx(sIdx);
    const url = projectApi.showFileAssetUrl(projectId, showFileId, seg.audio_path);

    speakerRef.current.play(url, () => {
      if (gen !== genRef.current) return; // slide changed or stopped — ignore

      setShowEvents((ev) => [
        {
          type: "tts_complete",
          slide: slide.position,
          segment: seg.index,
          at: new Date().toLocaleTimeString(),
        },
        ...ev.slice(0, 9),
      ]);

      if (stopAfterRef.current) {
        stopAfterRef.current = false;
        setSegIdx(null);
      } else if (sIdx + 1 < slide.segments.length) {
        playSegment(slide, sIdx + 1);
      } else if (autoPlayRef.current && indexRef.current < slidesLenRef.current - 1) {
        // All segments done — pause then advance to next slide
        advanceTimerRef.current = setTimeout(() => {
          if (autoPlayRef.current) setIndex((i) => i + 1);
        }, SLIDE_GAP_MS);
      } else {
        setSegIdx(null);
      }
    });
  }

  function stopAudio() {
    genRef.current++;
    stopAfterRef.current = false;
    qaInterruptRef.current = null; // discard any pending resume
    if (advanceTimerRef.current !== null) {
      clearTimeout(advanceTimerRef.current);
      advanceTimerRef.current = null;
    }
    speakerRef.current.stop();
    setSegIdx(null);
  }

  function scheduleStopAfter() {
    stopAfterRef.current = true;
  }

  // Auto-play when slide changes
  useEffect(() => {
    if (!current) return;
    stopAudio();
    if (autoPlay) playSegment(current, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (advanceTimerRef.current !== null) clearTimeout(advanceTimerRef.current);
      speakerRef.current.stop();
      liveSpeakerRef.current.stop();
    };
  }, []);

  // ── render_done event ──────────────────────────────────────────────────────
  function renderDone(slide: ShowSlide) {
    setShowEvents((ev) => [
      { type: "render_done", slide: slide.position, at: new Date().toLocaleTimeString() },
      ...ev.slice(0, 9),
    ]);
  }

  // ── Video export ──────────────────────────────────────────────────────────
  async function handleExportVideo() {
    if (!projectId || !showFileId || isExporting) return;
    setIsExporting(true);
    setExportError(null);
    try {
      const blob = await projectApi.exportVideo(projectId, showFileId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "presentation.mp4";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setIsExporting(false);
    }
  }

  // ── Live Q&A TTS (S8.2) ───────────────────────────────────────────────────
  async function speakLive() {
    if (!speakText.trim() || !projectId || !showFileId || isSpeaking) return;
    setIsSpeaking(true);
    try {
      const blob = await projectApi.synthesizeSpeech(
        projectId,
        showFileId,
        speakText,
        voiceId
      );
      const url = URL.createObjectURL(blob);
      liveSpeakerRef.current.play(url, () => {
        setIsSpeaking(false);
        URL.revokeObjectURL(url);
      });
    } catch {
      setIsSpeaking(false);
    }
  }

  function stopLive() {
    liveSpeakerRef.current.stop();
    setIsSpeaking(false);
  }

  // ── Q&A: narration pause / resume around Q&A ──────────────────────────────

  /** Stop narration cleanly when PTT is pressed and snapshot where we were. */
  function pauseForQA() {
    const curSegIdx = segIdxRef.current;
    if (curSegIdx !== null) {
      // Clean cut mid-segment — will restart from the top of this segment after Q&A
      genRef.current++;
      speakerRef.current.stop();
      setSegIdx(null);
      qaInterruptRef.current = { segIdx: curSegIdx, slideIndex: indexRef.current, wasInGap: false };
    } else if (advanceTimerRef.current !== null) {
      // In the inter-slide gap — cancel the countdown
      clearTimeout(advanceTimerRef.current);
      advanceTimerRef.current = null;
      qaInterruptRef.current = { segIdx: null, slideIndex: indexRef.current, wasInGap: true };
    }
  }

  /**
   * Play a spoken bridge phrase then restart narration from the segment that was cut.
   * Called after the Q&A answer finishes speaking.
   */
  async function resumeAfterQA() {
    const interrupted = qaInterruptRef.current;
    if (!interrupted) return;
    qaInterruptRef.current = null;

    // Guard: user may have navigated to a different slide during Q&A
    if (interrupted.slideIndex !== indexRef.current) return;
    const slide = slides[interrupted.slideIndex];
    if (!slide) return;

    if (interrupted.segIdx !== null) {
      if (!projectId || !showFileId) return;
      try {
        const bridgeBlob = await projectApi.synthesizeSpeech(
          projectId,
          showFileId,
          "Let's get back to the presentation.",
          voiceId
        );
        const bridgeUrl = URL.createObjectURL(bridgeBlob);
        liveSpeakerRef.current.play(bridgeUrl, () => {
          URL.revokeObjectURL(bridgeUrl);
          if (interrupted.slideIndex === indexRef.current) {
            playSegment(slide, interrupted.segIdx!);
          }
        });
      } catch {
        // Bridge TTS failed — restart the segment directly
        if (interrupted.slideIndex === indexRef.current) {
          playSegment(slide, interrupted.segIdx);
        }
      }
    } else if (interrupted.wasInGap && autoPlayRef.current && indexRef.current < slidesLenRef.current - 1) {
      advanceTimerRef.current = setTimeout(() => {
        if (autoPlayRef.current) setIndex((i) => i + 1);
      }, SLIDE_GAP_MS);
    }
  }

  /** Restore narration with no bridge phrase — for error/cancellation paths. */
  function restoreNarrationDirect() {
    const interrupted = qaInterruptRef.current;
    if (!interrupted) return;
    qaInterruptRef.current = null;

    if (interrupted.slideIndex !== indexRef.current) return;
    const slide = slides[interrupted.slideIndex];
    if (!slide) return;

    if (interrupted.segIdx !== null) {
      playSegment(slide, interrupted.segIdx);
    } else if (interrupted.wasInGap && autoPlayRef.current && indexRef.current < slidesLenRef.current - 1) {
      advanceTimerRef.current = setTimeout(() => {
        if (autoPlayRef.current) setIndex((i) => i + 1);
      }, SLIDE_GAP_MS);
    }
  }

  // ── Q&A: Push-to-talk (S9.1) ──────────────────────────────────────────────
  async function startRecording() {
    setMicError(null);
    pauseForQA(); // freeze narration the moment PTT is pressed
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const mr = new MediaRecorder(stream, { mimeType });
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      mr.onstop = handleRecordingStop;
      mediaRecorderRef.current = mr;
      mr.start();
      setIsRecording(true);
    } catch {
      restoreNarrationDirect(); // mic failed — restore narration with no bridge
      setMicError("Microphone access denied.");
    }
  }

  function stopRecording() {
    const mr = mediaRecorderRef.current;
    if (mr && mr.state === "recording") {
      mr.stop();
      mr.stream.getTracks().forEach((t) => t.stop());
    }
    setIsRecording(false);
  }

  async function handleRecordingStop() {
    if (!projectId || !showFileId || !current) return;
    const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });

    // S9.1 — empty capture handled gracefully
    if (blob.size < 1000) return;

    setIsTranscribing(true);
    let transcribeResult: { question: string; is_empty: boolean };
    try {
      transcribeResult = await projectApi.transcribeAudio(projectId, showFileId, blob);
    } catch {
      setIsTranscribing(false);
      return;
    }
    setIsTranscribing(false);

    if (transcribeResult.is_empty || !transcribeResult.question.trim()) return;
    const question = transcribeResult.question;
    setQaTranscript(question);
    setQaAnswer(null);

    // Repeat-request shortcut — "can you repeat", "say that again", etc.
    const REPEAT_RE = /\b(repeat|say that again|what did you say|could you repeat|can you repeat|come again|say again|pardon|didn't (catch|hear)|one more time)\b/i;
    if (REPEAT_RE.test(question)) {
      const interrupted = qaInterruptRef.current;
      qaInterruptRef.current = null;
      if (interrupted?.segIdx != null && interrupted.slideIndex === indexRef.current) {
        const repeatSlide = slides[interrupted.slideIndex];
        if (repeatSlide && projectId && showFileId) {
          try {
            const bridgeBlob = await projectApi.synthesizeSpeech(
              projectId, showFileId, "Sure, let me repeat that.", voiceId
            );
            const bridgeUrl = URL.createObjectURL(bridgeBlob);
            liveSpeakerRef.current.play(bridgeUrl, () => {
              URL.revokeObjectURL(bridgeUrl);
              if (interrupted.slideIndex === indexRef.current) {
                playSegment(repeatSlide, interrupted.segIdx!);
              }
            });
          } catch {
            if (interrupted.slideIndex === indexRef.current) {
              playSegment(repeatSlide, interrupted.segIdx);
            }
          }
        }
      }
      return;
    }

    // S9.2-S9.5 — classify + KB-grounded answer + feasibility guard
    setIsAnswering(true);
    let answer: AnswerResponse;
    try {
      answer = await projectApi.answerQuestion(
        projectId,
        showFileId,
        question,
        current.title,
        sessionId
      );
    } catch {
      setIsAnswering(false);
      return;
    }
    setIsAnswering(false);
    setQaAnswer(answer);
    setQaHistory((h) => [
      { question, answer, at: new Date().toLocaleTimeString() },
      ...h.slice(0, 9),
    ]);

    // Auto-speak the answer; resume narration when answer finishes
    try {
      const audioBlob = await projectApi.synthesizeSpeech(
        projectId,
        showFileId,
        answer.answer,
        voiceId
      );
      const url = URL.createObjectURL(audioBlob);
      liveSpeakerRef.current.play(url, () => {
        URL.revokeObjectURL(url);
        resumeAfterQA();
      });
    } catch {
      // TTS failed for the answer — restore narration directly, no bridge
      restoreNarrationDirect();
    }
  }

  // ── Loading / error states ─────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-black">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!showFile || !current || !projectId || !showFileId) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-gray-950 text-white">
        <p>Show File not found.</p>
        <Button variant="secondary" onClick={() => navigate("/projects")}>
          Back to Projects
        </Button>
      </div>
    );
  }

  const currentSeg = segIdx !== null ? current.segments[segIdx] : null;
  const isPlaying = segIdx !== null;

  function qtypeColor(type: string) {
    return {
      "product-fact": "bg-blue-500/20 text-blue-300",
      "feasibility": "bg-purple-500/20 text-purple-300",
      "general": "bg-gray-500/20 text-gray-300",
      "sensitive-binding": "bg-amber-500/20 text-amber-300",
    }[type] ?? "bg-gray-500/20 text-gray-300";
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gray-950 text-white">
      {/* Header */}
      <header className="flex items-center justify-between gap-4 border-b border-white/10 bg-black/40 px-4 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm text-gray-300 hover:bg-white/10 hover:text-white"
          >
            <ArrowLeft size={15} />
            Project
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <ScreenShare size={16} className="text-indigo-300" />
              <h1 className="truncate text-sm font-semibold">
                Show File v{showFile.version}
              </h1>
              <Badge variant={showFile.status === "ready" ? "green" : "red"}>
                {showFile.status}
              </Badge>
            </div>
            <p className="text-xs text-gray-400">
              Slide {current.position} of {slides.length} · {showFile.tts_provider}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Slide navigation */}
          <Button
            size="sm"
            variant="secondary"
            icon={<ChevronLeft size={14} />}
            disabled={index === 0}
            onClick={prev}
            className="border-white/20 bg-white/10 text-gray-200 hover:bg-white/20"
          >
            Prev
          </Button>
          <Button
            size="sm"
            variant="secondary"
            icon={<RotateCcw size={14} />}
            disabled={!jumpStack.length}
            onClick={jumpBack}
            className="border-white/20 bg-white/10 text-gray-200 hover:bg-white/20"
          >
            Jump Back
          </Button>
          <Button
            size="sm"
            variant="secondary"
            icon={<ChevronRight size={14} />}
            disabled={index === slides.length - 1}
            onClick={next}
            className="border-white/20 bg-white/10 text-gray-200 hover:bg-white/20"
          >
            Next
          </Button>

          {/* Audio controls */}
          <div className="ml-2 flex items-center gap-1 border-l border-white/10 pl-2">
            {!isPlaying ? (
              <button
                onClick={() => playSegment(current, 0)}
                disabled={!current.segments.length}
                className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-40"
              >
                <Play size={13} />
                Play
              </button>
            ) : (
              <>
                <button
                  onClick={scheduleStopAfter}
                  title="Finish this sentence then stop"
                  className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium ${
                    stopAfterRef.current
                      ? "bg-amber-500/20 text-amber-300"
                      : "text-gray-300 hover:bg-white/10"
                  }`}
                >
                  <StepForward size={13} />
                  After This
                </button>
                <button
                  onClick={stopAudio}
                  className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/20"
                >
                  <Square size={13} />
                  Stop
                </button>
              </>
            )}
            <button
              onClick={() => setAutoPlay((a) => !a)}
              className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                autoPlay
                  ? "text-indigo-300"
                  : "text-gray-600 hover:text-gray-400"
              }`}
            >
              Auto
            </button>
          </div>

          {/* Export video */}
          <div className="ml-2 border-l border-white/10 pl-2">
            <button
              onClick={handleExportVideo}
              disabled={isExporting}
              title={exportError ?? "Download as MP4 with subtitles"}
              className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                exportError
                  ? "text-red-400 hover:bg-red-500/20"
                  : "text-gray-300 hover:bg-white/10 disabled:opacity-50"
              }`}
            >
              {isExporting ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  Exporting…
                </>
              ) : (
                <>
                  <Download size={13} />
                  Export MP4
                </>
              )}
            </button>
          </div>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_300px]">
        {/* Slide area */}
        <section className="relative flex min-h-0 flex-col items-center justify-center bg-black">
          <img
            key={current.slide_id}
            src={projectApi.showFileAssetUrl(projectId, showFileId, current.image_path)}
            alt={current.title || `Slide ${current.position}`}
            onLoad={() => renderDone(current)}
            className="max-h-full max-w-full object-contain shadow-2xl"
          />
          {/* Current segment subtitle */}
          {currentSeg && (
            <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-6 py-3 text-center">
              <p className="text-sm leading-relaxed text-white/90">
                {currentSeg.text}
              </p>
            </div>
          )}
        </section>

        {/* Sidebar */}
        <aside className="min-h-0 overflow-y-auto border-l border-white/10 bg-gray-900 p-4 space-y-5">

          {/* Goto */}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
              Goto
            </p>
            <div className="flex flex-wrap gap-1.5">
              {slides.map((slide, slideIndex) => (
                <button
                  key={slide.slide_id}
                  type="button"
                  onClick={() => goto(slideIndex)}
                  className={`h-8 min-w-8 rounded-md px-2 text-sm font-medium ${
                    index === slideIndex
                      ? "bg-indigo-500 text-white"
                      : "bg-white/10 text-gray-200 hover:bg-white/20"
                  }`}
                >
                  {slide.position}
                </button>
              ))}
            </div>
          </div>

          {/* Now Playing */}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
              Now Playing
            </p>
            <div className="rounded-lg bg-white/5 p-3 space-y-2">
              <p className="font-semibold text-sm">{current.title || `Slide ${current.position}`}</p>
              <p className="text-xs text-gray-400">
                {current.duration_seconds}s · {current.segments.length} segments
              </p>
              {isPlaying ? (
                <div className="space-y-1">
                  {current.segments.map((seg, i) => (
                    <div
                      key={seg.index}
                      className={`rounded px-2 py-1 text-xs transition-colors ${
                        i === segIdx
                          ? "bg-emerald-500/20 text-emerald-200"
                          : i < (segIdx ?? 0)
                          ? "text-gray-600 line-through"
                          : "text-gray-500"
                      }`}
                    >
                      {seg.index}. {seg.text.slice(0, 60)}{seg.text.length > 60 ? "…" : ""}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-600 flex items-center gap-1">
                  <Volume2 size={11} /> Stopped
                </p>
              )}
            </div>
          </div>

          {/* Quick Speak (S8.2) */}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
              Quick Speak
            </p>
            <div className="space-y-2">
              <textarea
                rows={3}
                value={speakText}
                onChange={(e) => setSpeakText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) speakLive();
                }}
                placeholder="Type text to synthesize…"
                className="w-full rounded-lg bg-white/5 px-3 py-2 text-xs text-white placeholder-gray-600 outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
              />
              <div className="flex gap-2">
                {!isSpeaking ? (
                  <button
                    onClick={speakLive}
                    disabled={!speakText.trim()}
                    className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
                  >
                    <Mic size={12} />
                    Speak (⌘↵)
                  </button>
                ) : (
                  <button
                    onClick={stopLive}
                    className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
                  >
                    <MicOff size={12} />
                    Stop Speaking
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Show Events */}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
              Show Events
            </p>
            <div className="space-y-1.5">
              {showEvents.length ? (
                showEvents.map((ev, i) => (
                  <div
                    key={i}
                    className={`rounded-md px-2 py-1 text-xs ${
                      ev.type === "tts_complete"
                        ? "bg-emerald-500/10 text-emerald-200"
                        : "bg-blue-500/10 text-blue-200"
                    }`}
                  >
                    {ev.type === "tts_complete"
                      ? `tts_complete: slide ${ev.slide} seg ${ev.segment}`
                      : `render_done: slide ${ev.slide}`}{" "}
                    <span className="text-gray-500">· {ev.at}</span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-gray-600">No events yet.</p>
              )}
            </div>
          </div>

          {/* Q&A Panel (S9) */}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
              Q&amp;A
            </p>

            {/* PTT Button */}
            <button
              onPointerDown={startRecording}
              onPointerUp={stopRecording}
              onPointerLeave={stopRecording}
              disabled={isTranscribing || isAnswering}
              className={`w-full select-none rounded-lg py-3 text-sm font-semibold transition-all ${
                isRecording
                  ? "animate-pulse bg-red-500 text-white"
                  : isTranscribing
                  ? "bg-amber-500/20 text-amber-300"
                  : isAnswering
                  ? "bg-indigo-500/20 text-indigo-300"
                  : "bg-white/10 text-gray-200 hover:bg-white/15 active:bg-white/25"
              } disabled:cursor-wait`}
            >
              {isRecording
                ? "🎙 Listening…"
                : isTranscribing
                ? "Transcribing…"
                : isAnswering
                ? "Answering…"
                : "Hold to Ask"}
            </button>

            {micError && (
              <p className="mt-1 text-xs text-red-400">{micError}</p>
            )}

            {/* Current Q&A result */}
            {qaTranscript && (
              <div className="mt-3 rounded-lg bg-white/5 p-3 space-y-2">
                <p className="text-xs text-gray-500">Question</p>
                <p className="text-xs text-white">{qaTranscript}</p>

                {qaAnswer && (
                  <>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${qtypeColor(qaAnswer.question_type)}`}>
                        {qaAnswer.question_type}
                      </span>
                      {qaAnswer.deferred && (
                        <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-xs text-amber-300">
                          ↪ deferred
                        </span>
                      )}
                      <span className="ml-auto text-xs text-gray-600">
                        {(qaAnswer.confidence * 100).toFixed(0)}% conf
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed text-gray-200">{qaAnswer.answer}</p>
                    {qaAnswer.citations.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {qaAnswer.citations.map((c, i) => (
                          <span key={i} className="text-xs text-gray-600">
                            📎 {c.source || c.kb_id}
                          </span>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Q&A history */}
            {qaHistory.length > 1 && (
              <div className="mt-3 space-y-1">
                <p className="text-xs text-gray-600">History</p>
                {qaHistory.slice(1).map((entry, i) => (
                  <div key={i} className="rounded bg-white/5 px-2 py-1">
                    <p className="text-xs text-gray-500 truncate">
                      Q: {entry.question}
                    </p>
                    <p className="text-xs text-gray-600 truncate">
                      {entry.answer.deferred ? "↪ deferred" : entry.answer.answer.slice(0, 60) + "…"}{" "}
                      <span className="text-gray-700">· {entry.at}</span>
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

        </aside>
      </main>
    </div>
  );
}
