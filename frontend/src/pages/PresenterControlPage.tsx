/**
 * EPIC 11 — Presenter Control Panel
 *
 * S11.1  Real-time FSM state (WebSocket), start/pause/stop, manual advance/prev.
 * S11.2  Q&A indicator + live transcript + last-answer + confidence + source.
 * S11.3  Pre-flight checklist (Show File, images, audio device, API) red/green.
 *
 * Architecture:
 *   - POSTs to /orchestrator/sessions to create a backend FSM session.
 *   - Connects WebSocket to receive typed events (state_changed, play_slide,
 *     play_audio, qa_gate_open, …).
 *   - Reacts to events: updates slide image, plays narration audio, runs Q&A
 *     pipeline, then sends completion commands back (slide_advanced,
 *     audio_complete, qa_answer_ready).
 */

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Circle,
  Loader2,
  Mic,
  MicOff,
  Pause,
  Play,
  RotateCcw,
  Square,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { OrchestratorEvent, orchestratorApi, OrchestratorCursor } from "../api/orchestrator";
import type { LogQARequest } from "../api/orchestrator";
import { AnswerResponse, projectApi } from "../api/projects";
import Spinner from "../components/ui/Spinner";
import { LaptopSpeaker } from "../services/audioOutput";

// ── Types ──────────────────────────────────────────────────────────────────────

type CheckState = "pending" | "ok" | "fail";

interface QAEntry {
  question: string;
  answer: AnswerResponse;
  at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function stateBadge(state: string) {
  const map: Record<string, string> = {
    IDLE: "bg-gray-500/20 text-gray-300",
    LOADING: "bg-blue-500/20 text-blue-300",
    READY: "bg-emerald-500/20 text-emerald-300",
    SPEAKING: "bg-indigo-500/20 text-indigo-300 animate-pulse",
    ADVANCING: "bg-cyan-500/20 text-cyan-300",
    PAUSED: "bg-amber-500/20 text-amber-300",
    QA_LISTENING: "bg-pink-500/20 text-pink-300 animate-pulse",
    QA_PROCESSING: "bg-purple-500/20 text-purple-300 animate-pulse",
    QA_ANSWERING: "bg-violet-500/20 text-violet-300 animate-pulse",
    ENDED: "bg-gray-500/20 text-gray-400",
    ERROR: "bg-red-500/20 text-red-400",
  };
  return map[state] ?? "bg-gray-500/20 text-gray-300";
}

function qtypeBadge(type: string) {
  const map: Record<string, string> = {
    "product-fact": "bg-blue-500/20 text-blue-300",
    feasibility: "bg-purple-500/20 text-purple-300",
    general: "bg-gray-500/20 text-gray-300",
    "sensitive-binding": "bg-amber-500/20 text-amber-300",
  };
  return map[type] ?? "bg-gray-500/20 text-gray-300";
}

function fmtSeconds(s: number) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

// ── Pre-flight row ────────────────────────────────────────────────────────────

function CheckRow({ label, state }: { label: string; state: CheckState }) {
  return (
    <div className="flex items-center gap-3 py-2">
      {state === "ok" ? (
        <CheckCircle size={16} className="text-emerald-400 shrink-0" />
      ) : state === "fail" ? (
        <XCircle size={16} className="text-red-400 shrink-0" />
      ) : (
        <Circle size={16} className="text-gray-600 shrink-0" />
      )}
      <span className={`text-sm ${state === "fail" ? "text-red-300" : state === "ok" ? "text-gray-200" : "text-gray-500"}`}>
        {label}
      </span>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function PresenterControlPage() {
  const { projectId, showFileId } = useParams<{ projectId: string; showFileId: string }>();
  const navigate = useNavigate();

  // ── Show file data ───────────────────────────────────────────────────────────
  const { data: showFile, isLoading } = useQuery({
    queryKey: ["show-file", projectId, showFileId],
    queryFn: () => projectApi.getShowFile(projectId!, showFileId!),
    enabled: !!projectId && !!showFileId,
  });

  const slides = useMemo(
    () => ((showFile?.manifest.slides as Array<Record<string, unknown>> | undefined) ?? []),
    [showFile]
  );

  const voiceId = useMemo(
    () => ((showFile?.manifest?.voice_config as Record<string, unknown> | undefined)?.voice_id as string | null) ?? null,
    [showFile]
  );

  // ── S11.3: Pre-flight checks ─────────────────────────────────────────────────
  const [checks, setChecks] = useState<Record<string, CheckState>>({
    showFile: "pending",
    images: "pending",
    audio: "pending",
    api: "pending",
  });
  const [launchError, setLaunchError] = useState<string | null>(null);
  const allPassed = Object.values(checks).every((v) => v === "ok");

  useEffect(() => {
    if (!showFile) return;

    // 1. Show File status
    setChecks((c) => ({ ...c, showFile: showFile.status === "ready" ? "ok" : "fail" }));

    // 2. Slide images
    const hasImages = slides.some((s) => s.image_path);
    setChecks((c) => ({ ...c, images: hasImages ? "ok" : "fail" }));

    // 3. Audio device (AudioContext availability)
    const hasAudio =
      typeof AudioContext !== "undefined" ||
      typeof (window as unknown as Record<string, unknown>).webkitAudioContext !== "undefined";
    setChecks((c) => ({ ...c, audio: hasAudio ? "ok" : "fail" }));

    // 4. API reachable
    fetch("/api/health")
      .then((r) => setChecks((c) => ({ ...c, api: r.ok ? "ok" : "fail" })))
      .catch(() => setChecks((c) => ({ ...c, api: "fail" })));
  }, [showFile, slides]);

  // ── S11.1: Session + WebSocket ───────────────────────────────────────────────
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [robotMode, setRobotMode] = useState(false);
  const robotModeRef = useRef(false);
  const [fsmState, setFsmState] = useState("IDLE");
  const [cursor, setCursor] = useState<OrchestratorCursor>({
    slide_index: 0, segment_index: 0, sentence_index: 0,
  });
  const [wsStatus, setWsStatus] = useState<"disconnected" | "connecting" | "connected">("disconnected");
  const [isLaunching, setIsLaunching] = useState(false);

  const sessionIdRef = useRef<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Audio
  const speakerRef = useRef(new LaptopSpeaker());
  const liveSpeakerRef = useRef(new LaptopSpeaker());

  // Slide display
  const [slideImagePath, setSlideImagePath] = useState<string | null>(null);
  const [slidePosition, setSlidePosition] = useState(1);
  const [slideSubtitle, setSlideSubtitle] = useState<string | null>(null);
  const pendingSlideAdvanceRef = useRef(false);

  // ── S11.2: Q&A state ─────────────────────────────────────────────────────────
  const [qaGateOpen, setQaGateOpen] = useState(false);
  const [qaTimeRemaining, setQaTimeRemaining] = useState(0);
  const qaTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessingQA, setIsProcessingQA] = useState(false);
  const [qaTranscript, setQaTranscript] = useState<string | null>(null);
  const [qaAnswer, setQaAnswer] = useState<AnswerResponse | null>(null);
  const [qaHistory, setQaHistory] = useState<QAEntry[]>([]);
  const [micError, setMicError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Stable refs for use inside WS callbacks
  const projectIdRef = useRef(projectId);
  const showFileIdRef = useRef(showFileId);
  const voiceIdRef = useRef(voiceId);
  const slidesRef = useRef(slides);
  const cursorRef = useRef(cursor);
  projectIdRef.current = projectId;
  showFileIdRef.current = showFileId;
  voiceIdRef.current = voiceId;
  slidesRef.current = slides;
  cursorRef.current = cursor;

  // ── Command sender (stable ref, always fresh session id) ─────────────────────
  const sendCommand = useCallback(
    async (type: string, payload: Record<string, unknown> = {}) => {
      const sid = sessionIdRef.current;
      if (!sid) return;
      try {
        await orchestratorApi.sendCommand(sid, type, payload);
      } catch (err) {
        console.error(`Command '${type}' failed:`, err);
      }
    },
    []
  );

  // ── Q&A timer helpers ─────────────────────────────────────────────────────────
  function startQATimer(seconds: number) {
    if (qaTimerRef.current) clearInterval(qaTimerRef.current);
    setQaTimeRemaining(Math.round(seconds));
    qaTimerRef.current = setInterval(() => {
      setQaTimeRemaining((t) => {
        if (t <= 1) { clearInterval(qaTimerRef.current!); return 0; }
        return t - 1;
      });
    }, 1000);
  }

  function stopQATimer() {
    if (qaTimerRef.current) { clearInterval(qaTimerRef.current); qaTimerRef.current = null; }
  }

  // ── Event handler (ref to avoid stale closures) ───────────────────────────────
  const handleEventRef = useRef((_: OrchestratorEvent) => {});
  handleEventRef.current = (event: OrchestratorEvent) => {
    const pid = projectIdRef.current;
    const sfid = showFileIdRef.current;
    const voice = voiceIdRef.current;

    switch (event.type) {
      // S11.1: state tracking
      case "state_changed":
        setFsmState(event.payload.state as string);
        setCursor(event.payload.cursor as OrchestratorCursor);
        break;

      case "play_slide": {
        const imgPath = event.payload.image_path as string;
        const pos = (event.payload.position as number) ?? ((event.payload.slide_index as number) + 1);
        pendingSlideAdvanceRef.current = true;
        setSlideImagePath(imgPath);
        setSlidePosition(pos);
        break;
      }

      case "play_audio": {
        // In robot mode the backend streams audio to the G1 speaker and
        // sends audio_complete itself — skip browser playback entirely.
        if (robotModeRef.current) break;

        const context = event.payload.context as string;
        if (context === "narration") {
          const audioPath = event.payload.audio_path as string;
          setSlideSubtitle((event.payload.text as string) ?? null);
          if (audioPath && pid && sfid) {
            const url = projectApi.showFileAssetUrl(pid, sfid, audioPath);
            speakerRef.current.play(url, () => {
              setSlideSubtitle(null);
              sendCommand("audio_complete", { sentence_index: 0 });
            });
          } else {
            sendCommand("audio_complete", { sentence_index: 0 });
          }
        } else if (context === "qa_answer") {
          const answerText = event.payload.answer as string;
          if (answerText && pid && sfid) {
            projectApi
              .synthesizeSpeech(pid, sfid, answerText, voice)
              .then((blob) => {
                const url = URL.createObjectURL(blob);
                liveSpeakerRef.current.play(url, () => {
                  URL.revokeObjectURL(url);
                  sendCommand("audio_complete");
                });
              })
              .catch(() => sendCommand("audio_complete"));
          } else {
            sendCommand("audio_complete");
          }
        }
        break;
      }

      case "stop_audio":
        speakerRef.current.stop();
        liveSpeakerRef.current.stop();
        setSlideSubtitle(null);
        break;

      // S11.2: Q&A gate
      case "qa_gate_open":
        setQaGateOpen(true);
        setQaTranscript(null);
        setQaAnswer(null);
        startQATimer((event.payload.budget_remaining_seconds as number) ?? 120);
        break;

      case "qa_gate_close":
        setQaGateOpen(false);
        stopQATimer();
        break;

      case "qa_time_expired":
        setQaGateOpen(false);
        stopQATimer();
        break;

      case "show_ended":
        setQaGateOpen(false);
        stopQATimer();
        speakerRef.current.stop();
        liveSpeakerRef.current.stop();
        break;

      case "error":
        console.error("Orchestrator error:", event.payload.message);
        break;
    }
  };

  // ── Launch session ───────────────────────────────────────────────────────────
  async function handleLaunch() {
    if (!projectId || !showFileId || !allPassed || isLaunching) return;
    setIsLaunching(true);
    setLaunchError(null);
    try {
      const resp = await orchestratorApi.createSession(projectId, showFileId);
      setSessionId(resp.session_id);
      sessionIdRef.current = resp.session_id;
      setFsmState(resp.state);
      setRobotMode(resp.robot_mode);
      robotModeRef.current = resp.robot_mode;

      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsEndpoint = `${proto}//${window.location.host}/api/orchestrator/sessions/${resp.session_id}/events`;
      const ws = new WebSocket(wsEndpoint);
      wsRef.current = ws;
      setWsStatus("connecting");

      ws.onopen = () => {
        setWsStatus("connected");
        orchestratorApi.sendCommand(resp.session_id, "start").catch((err) => {
          setLaunchError(err instanceof Error ? err.message : "Failed to start presentation");
        });
      };
      ws.onmessage = (msg) => {
        try {
          handleEventRef.current(JSON.parse(msg.data) as OrchestratorEvent);
        } catch { /* malformed message */ }
      };
      ws.onclose = () => setWsStatus("disconnected");
      ws.onerror = () => setWsStatus("disconnected");
    } catch (err) {
      setLaunchError(err instanceof Error ? err.message : "Failed to start session");
    } finally {
      setIsLaunching(false);
    }
  }

  // ── Cleanup on unmount ────────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      speakerRef.current.stop();
      liveSpeakerRef.current.stop();
      stopQATimer();
      const sid = sessionIdRef.current;
      if (sid) orchestratorApi.deleteSession(sid).catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── S11.2: Push-to-talk Q&A ──────────────────────────────────────────────────
  async function startRecording() {
    if (!qaGateOpen || isProcessingQA) return;
    setMicError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus" : "audio/webm";
      const mr = new MediaRecorder(stream, { mimeType });
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = handleRecordingStop;
      mediaRecorderRef.current = mr;
      mr.start();
      setIsRecording(true);
    } catch {
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
    const pid = projectIdRef.current;
    const sfid = showFileIdRef.current;
    if (!pid || !sfid) return;

    const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
    if (blob.size < 1000) { await sendCommand("qa_close"); return; }

    setIsProcessingQA(true);
    await sendCommand("qa_trigger");

    let transcribed: { question: string; is_empty: boolean };
    try {
      transcribed = await projectApi.transcribeAudio(pid, sfid, blob);
    } catch {
      setIsProcessingQA(false);
      await sendCommand("qa_close");
      return;
    }

    if (transcribed.is_empty || !transcribed.question.trim()) {
      setIsProcessingQA(false);
      await sendCommand("qa_close");
      return;
    }

    setQaTranscript(transcribed.question);
    const slideContext = (slidesRef.current[cursorRef.current.slide_index] as Record<string, unknown>)?.title as string | null ?? null;

    let answer: AnswerResponse;
    try {
      answer = await projectApi.answerQuestion(
        pid, sfid, transcribed.question, slideContext, sessionIdRef.current ?? ""
      );
    } catch {
      setIsProcessingQA(false);
      await sendCommand("qa_close");
      return;
    }

    setQaAnswer(answer);
    setQaHistory((h) => [
      { question: transcribed.question, answer, at: new Date().toLocaleTimeString() },
      ...h.slice(0, 9),
    ]);
    setIsProcessingQA(false);

    // S12.3: persist Q&A entry asynchronously (fire-and-forget)
    const sid = sessionIdRef.current;
    if (sid) {
      const logBody: LogQARequest = {
        question: transcribed.question,
        answer: answer.answer,
        question_type: answer.question_type,
        confidence: answer.confidence,
        deferred: answer.deferred,
        slide_index: cursorRef.current.slide_index,
        served_from_faq: answer.citations.length === 0 && answer.confidence === 1.0 && !answer.deferred,
      };
      orchestratorApi.logQA(sid, logBody).catch(() => {/* non-critical */});
    }

    await sendCommand("qa_answer_ready", {
      answer: answer.answer,
      question_type: answer.question_type,
      confidence: answer.confidence,
      deferred: answer.deferred,
    });
  }

  // ── Slide image load → send SLIDE_ADVANCED ───────────────────────────────────
  function handleSlideImageLoad() {
    if (pendingSlideAdvanceRef.current) {
      pendingSlideAdvanceRef.current = false;
      sendCommand("slide_advanced");
    }
  }

  // ── Loading state ─────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-950">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!showFile || !projectId || !showFileId) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-gray-950 text-white">
        <p className="text-red-400">Show File not found.</p>
        <button onClick={() => navigate("/projects")} className="text-sm text-indigo-400 underline">
          Back to Projects
        </button>
      </div>
    );
  }

  // ── S11.3: Pre-flight phase ───────────────────────────────────────────────────
  if (!sessionId) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-gray-950 text-white p-6">
        <div className="w-full max-w-md space-y-6">
          {/* Header */}
          <div>
            <button
              onClick={() => navigate(`/projects/${projectId}`)}
              className="mb-4 inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-white"
            >
              <ArrowLeft size={14} />
              Back to project
            </button>
            <h1 className="text-2xl font-bold">Pre-flight Check</h1>
            <p className="mt-1 text-sm text-gray-400">
              Show File v{showFile.version} — {slides.length} slides
            </p>
          </div>

          {/* Checklist */}
          <div className="rounded-xl border border-white/10 bg-gray-900 px-5 py-3 divide-y divide-white/5">
            <CheckRow
              label="Show File is ready"
              state={checks.showFile}
            />
            <CheckRow
              label="Slide images bundled"
              state={checks.images}
            />
            <CheckRow
              label="Audio device available"
              state={checks.audio}
            />
            <CheckRow
              label="API reachable"
              state={checks.api}
            />
          </div>

          {/* Errors */}
          {showFile.validation_errors.length > 0 && (
            <div className="rounded-lg bg-red-900/20 border border-red-500/20 px-4 py-3">
              <p className="text-xs font-medium text-red-400 mb-1">Validation errors:</p>
              {showFile.validation_errors.map((e) => (
                <p key={e} className="text-xs text-red-300">• {e}</p>
              ))}
            </div>
          )}

          {launchError && (
            <p className="text-sm text-red-400">{launchError}</p>
          )}

          {/* Launch button */}
          <button
            onClick={handleLaunch}
            disabled={!allPassed || isLaunching}
            className="w-full rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isLaunching ? (
              <><Loader2 size={15} className="animate-spin" /> Starting…</>
            ) : (
              <><Play size={15} /> Launch Presentation</>
            )}
          </button>
        </div>
      </div>
    );
  }

  // ── Active session ─────────────────────────────────────────────────────────────

  const isEnded = fsmState === "ENDED";
  const isPaused = fsmState === "PAUSED";
  const isSpeaking = fsmState === "SPEAKING" || fsmState === "ADVANCING";
  const inQA = fsmState.startsWith("QA_");

  // ── Ended state ───────────────────────────────────────────────────────────────
  if (isEnded) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-6 bg-gray-950 text-white">
        <div className="text-center space-y-2">
          <CheckCircle size={48} className="text-emerald-400 mx-auto" />
          <h2 className="text-2xl font-bold">Presentation Complete</h2>
          <p className="text-sm text-gray-400">
            Show File v{showFile.version} — {qaHistory.length} question{qaHistory.length !== 1 ? "s" : ""} answered
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/20"
          >
            <ArrowLeft size={14} />
            Back to Project
          </button>
        </div>
        {/* Q&A summary */}
        {qaHistory.length > 0 && (
          <div className="w-full max-w-lg space-y-2 mt-4 max-h-64 overflow-y-auto px-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Q&amp;A Log</p>
            {qaHistory.map((entry, i) => (
              <div key={i} className="rounded-lg bg-gray-900 px-3 py-2">
                <p className="text-xs text-gray-400 truncate">Q: {entry.question}</p>
                <p className="text-xs text-gray-500 truncate mt-0.5">
                  {entry.answer.deferred ? "↪ deferred" : entry.answer.answer.slice(0, 80) + "…"}
                  <span className="text-gray-700 ml-1">· {entry.at}</span>
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Running layout ─────────────────────────────────────────────────────────────
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gray-950 text-white">

      {/* S11.1: Header — state + cursor + stop */}
      <header className="flex items-center justify-between gap-4 border-b border-white/10 bg-black/40 px-4 py-2.5">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm text-gray-400 hover:bg-white/10 hover:text-white"
          >
            <ArrowLeft size={14} />
          </button>
          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${stateBadge(fsmState)}`}>
            {fsmState}
          </span>
          {robotMode && (
            <span className="rounded-full px-2.5 py-1 text-xs font-semibold bg-emerald-500/20 text-emerald-300">
              🤖 Robot
            </span>
          )}
          <span className="text-sm text-gray-400">
            Slide {slidePosition} of {slides.length}
          </span>
          {wsStatus !== "connected" && (
            <span className="text-xs text-amber-400">
              {wsStatus === "connecting" ? "Connecting…" : "WS disconnected"}
            </span>
          )}
        </div>

        {/* Transport controls */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => sendCommand("prev")}
            disabled={!isSpeaking}
            title="Previous slide"
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/10 disabled:opacity-30"
          >
            <ChevronLeft size={14} /> Prev
          </button>

          {isPaused ? (
            <button
              onClick={() => sendCommand("resume")}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
            >
              <Play size={13} /> Resume
            </button>
          ) : fsmState === "READY" ? (
            <button
              onClick={() => sendCommand("start")}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
            >
              <Play size={13} /> Start
            </button>
          ) : (
            <button
              onClick={() => sendCommand("pause")}
              disabled={!isSpeaking && !inQA}
              className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-30"
            >
              <Pause size={13} /> Pause
            </button>
          )}

          <button
            onClick={() => sendCommand("advance")}
            disabled={!isSpeaking}
            title="Next slide"
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/10 disabled:opacity-30"
          >
            Next <ChevronRight size={14} />
          </button>

          <button
            onClick={() => sendCommand("stop")}
            className="inline-flex items-center gap-1.5 rounded-lg bg-red-700/80 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-red-700"
          >
            <Square size={12} /> Stop
          </button>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_320px]">

        {/* Slide area */}
        <section className="relative flex min-h-0 flex-col items-center justify-center bg-black">
          {slideImagePath ? (
            <img
              key={slideImagePath}
              src={projectApi.showFileAssetUrl(projectId, showFileId, slideImagePath)}
              alt={`Slide ${slidePosition}`}
              onLoad={handleSlideImageLoad}
              className="max-h-full max-w-full object-contain shadow-2xl"
            />
          ) : (
            <div className="text-gray-700 text-sm">Waiting for slide…</div>
          )}
          {/* S11.1: Subtitle / narration text */}
          {slideSubtitle && (
            <div className="absolute bottom-0 left-0 right-0 bg-black/75 px-6 py-3 text-center">
              <p className="text-sm leading-relaxed text-white/90">{slideSubtitle}</p>
            </div>
          )}
        </section>

        {/* Sidebar: S11.1 state + S11.2 Q&A */}
        <aside className="min-h-0 overflow-y-auto border-l border-white/10 bg-gray-900 p-4 space-y-5">

          {/* Cursor info */}
          <div className="rounded-lg bg-white/5 px-3 py-2 space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-400">Position</span>
              <span className="text-xs text-gray-300">
                slide {cursor.slide_index + 1} · seg {cursor.segment_index}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-400">WS</span>
              <span className={`text-xs ${wsStatus === "connected" ? "text-emerald-400" : "text-amber-400"}`}>
                {wsStatus}
              </span>
            </div>
          </div>

          {/* Jump back (jump stack) */}
          <div>
            <button
              onClick={() => sendCommand("jump_return")}
              disabled={!isSpeaking}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-white/10 px-3 py-2 text-xs font-medium text-gray-200 hover:bg-white/20 disabled:opacity-30"
            >
              <RotateCcw size={12} /> Jump Back
            </button>
          </div>

          {/* S11.2: Q&A panel */}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
              Q&amp;A
            </p>

            {/* Gate indicator */}
            <div className={`mb-3 flex items-center gap-2 rounded-lg px-3 py-2 ${qaGateOpen ? "bg-pink-500/10 border border-pink-500/20" : "bg-white/5"}`}>
              <span className={`h-2 w-2 rounded-full ${qaGateOpen ? "bg-pink-400 animate-pulse" : "bg-gray-600"}`} />
              <span className={`text-xs font-medium ${qaGateOpen ? "text-pink-300" : "text-gray-500"}`}>
                {qaGateOpen ? `Gate open · ${fmtSeconds(qaTimeRemaining)}` : "Gate closed"}
              </span>
            </div>

            {/* Budget countdown bar */}
            {qaGateOpen && qaTimeRemaining > 0 && (
              <div className="mb-3 h-1 w-full rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-1 rounded-full bg-pink-400 transition-all duration-1000"
                  style={{ width: `${Math.min(100, (qaTimeRemaining / 120) * 100)}%` }}
                />
              </div>
            )}

            {/* PTT button */}
            <button
              onPointerDown={startRecording}
              onPointerUp={stopRecording}
              onPointerLeave={stopRecording}
              disabled={!qaGateOpen || isProcessingQA}
              className={`w-full select-none rounded-lg py-3 text-sm font-semibold transition-all ${
                isRecording
                  ? "animate-pulse bg-red-500 text-white"
                  : isProcessingQA
                  ? "bg-purple-500/20 text-purple-300"
                  : qaGateOpen
                  ? "bg-pink-500/20 text-pink-200 hover:bg-pink-500/30 active:bg-pink-500/40"
                  : "bg-white/5 text-gray-600 cursor-not-allowed"
              }`}
            >
              {isRecording ? (
                <span className="flex items-center justify-center gap-1.5"><Mic size={14} /> Listening…</span>
              ) : isProcessingQA ? (
                <span className="flex items-center justify-center gap-1.5"><Loader2 size={14} className="animate-spin" /> Processing…</span>
              ) : (
                <span className="flex items-center justify-center gap-1.5"><MicOff size={14} /> Hold to Ask</span>
              )}
            </button>
            {micError && <p className="mt-1 text-xs text-red-400">{micError}</p>}

            {/* Close gate button */}
            {qaGateOpen && !isRecording && !isProcessingQA && (
              <button
                onClick={() => sendCommand("qa_close")}
                className="mt-2 w-full rounded-lg bg-white/5 py-1.5 text-xs text-gray-400 hover:bg-white/10"
              >
                Close gate &amp; advance
              </button>
            )}
          </div>

          {/* S11.2: Current Q&A result */}
          {qaTranscript && (
            <div className="rounded-lg bg-white/5 p-3 space-y-2">
              <p className="text-xs text-gray-500">Question</p>
              <p className="text-xs text-white">{qaTranscript}</p>

              {qaAnswer && (
                <>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${qtypeBadge(qaAnswer.question_type)}`}>
                      {qaAnswer.question_type}
                    </span>
                    {qaAnswer.deferred && (
                      <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-xs text-amber-300">
                        ↪ deferred
                      </span>
                    )}
                    <span className="ml-auto text-xs text-gray-500">
                      {(qaAnswer.confidence * 100).toFixed(0)}% conf
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-gray-200">{qaAnswer.answer}</p>
                  {qaAnswer.citations.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {qaAnswer.citations.map((c, i) => (
                        <span key={i} className="text-xs text-gray-600">📎 {c.source || c.kb_id}</span>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* S11.2: Q&A history */}
          {qaHistory.length > 1 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-600">History</p>
              {qaHistory.slice(1).map((entry, i) => (
                <div key={i} className="rounded bg-white/5 px-2 py-1.5">
                  <p className="text-xs text-gray-500 truncate">Q: {entry.question}</p>
                  <p className="text-xs text-gray-600 truncate mt-0.5">
                    {entry.answer.deferred ? "↪ deferred" : entry.answer.answer.slice(0, 55) + "…"}
                    <span className="text-gray-700 ml-1">· {entry.at}</span>
                  </p>
                </div>
              ))}
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}
