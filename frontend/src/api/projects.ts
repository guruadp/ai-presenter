const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.blob();
}

function json<T>(path: string, method: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface ToneProfile {
  formality: string;
  pace: string;
  persona: string;
  dos: string[];
  donts: string[];
  language: string;
  voice_id: string | null;
}

export interface ProjectKnowledgeBase {
  kb_id: string;
  pinned_version: number;
  pinned_content_hash: string;
  attached_at: string;
}

export interface ProjectSlide {
  id: string;
  project_id: string;
  position: number;
  title: string | null;
  body: string;
  notes: string;
  image_path: string | null;
  vision_summary: string;
  generation_context: Record<string, unknown>;
  script: ProjectSlideScript | null;
  created_at: string;
}

export interface ProjectSlideScript {
  id: string;
  slide_id: string;
  status: string;
  narration: string;
  segments: ProjectScriptSegment[];
  citations: ProjectScriptCitation[];
  duration_seconds: number;
  delivery_style: Record<string, unknown>;
  running_summary: string;
  feedback: string | null;
  revision_history: ProjectScriptRevision[];
  tone_override: Record<string, unknown>;
  preview_config: Record<string, unknown>;
  stale_reasons: string[];
  version: number;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectScriptRevision {
  version: number;
  narration: string;
  status: string;
  duration_seconds: number;
  updated_at: string | null;
}

export interface ProjectScriptSegment {
  index: number;
  text: string;
  delivery: Record<string, unknown>;
  audio_tags: string[];
}

export interface ProjectScriptCitation {
  id: string;
  type: string;
  kb_id: string;
  kb_version: number | null;
  label: string;
  value: string;
  source: string;
}

export interface RegenerateScriptRequest {
  feedback?: string;
  make_shorter: boolean;
  more_energy: boolean;
  more_citations: boolean;
  tone_override?: Record<string, unknown>;
}

export interface ScriptReviewSettingsRequest {
  tone_override: Record<string, unknown>;
  preview_config: Record<string, unknown>;
}

export interface Project {
  id: string;
  name: string;
  owner: string;
  tone_profile: ToneProfile;
  knowledge_bases: ProjectKnowledgeBase[];
  slides: ProjectSlide[];
  show_files: ShowFile[];
  created_at: string;
  updated_at: string;
}

export interface ShowFile {
  id: string;
  project_id: string;
  version: number;
  status: string;
  manifest_path: string;
  bundle_path: string;
  manifest: Record<string, unknown>;
  validation_errors: string[];
  tts_provider: string;
  created_at: string;
}

export interface PackageGate {
  ok: boolean;
  errors: string[];
}

export interface TranscribeResponse {
  question: string;
  is_empty: boolean;
}

export interface AnswerCitation {
  source: string;
  kb_id: string;
  score: number;
}

export interface AnswerResponse {
  answer: string;
  question_type: string;
  citations: AnswerCitation[];
  confidence: number;
  deferred: boolean;
  deferred_reason: string | null;
}

export interface ProjectCreate {
  name: string;
  owner: string;
  kb_ids: string[];
  tone_profile: ToneProfile;
}

export const projectApi = {
  list: () => request<Project[]>("/projects"),
  get: (projectId: string) => request<Project>(`/projects/${projectId}`),
  create: (body: ProjectCreate) => json<Project>("/projects", "POST", body),
  delete: (projectId: string) =>
    request<void>(`/projects/${projectId}`, { method: "DELETE" }),
  uploadDeck: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Project>(`/projects/${projectId}/deck`, {
      method: "POST",
      body: form,
    });
  },
  generateScripts: (projectId: string) =>
    request<Project>(`/projects/${projectId}/scripts`, { method: "POST" }),
  packageGate: (projectId: string) =>
    request<PackageGate>(`/projects/${projectId}/package-gate`),
  listShowFiles: (projectId: string) =>
    request<ShowFile[]>(`/projects/${projectId}/show-files`),
  packageShowFile: (projectId: string) =>
    request<ShowFile>(`/projects/${projectId}/show-files`, { method: "POST" }),
  showFileDownloadUrl: (projectId: string, showFileId: string) =>
    `${BASE}/projects/${projectId}/show-files/${showFileId}/download`,
  getShowFile: (projectId: string, showFileId: string) =>
    request<ShowFile>(`/projects/${projectId}/show-files/${showFileId}`),
  showFileAssetUrl: (projectId: string, showFileId: string, assetPath: string) =>
    `${BASE}/projects/${projectId}/show-files/${showFileId}/assets/${assetPath}`,
  regenerateScript: (
    projectId: string,
    slideId: string,
    body: RegenerateScriptRequest
  ) =>
    json<ProjectSlideScript>(
      `/projects/${projectId}/slides/${slideId}/script/regenerate`,
      "POST",
      body
    ),
  editScript: (projectId: string, slideId: string, narration: string) =>
    json<ProjectSlideScript>(
      `/projects/${projectId}/slides/${slideId}/script`,
      "PATCH",
      { narration }
    ),
  approveScript: (projectId: string, slideId: string) =>
    request<ProjectSlideScript>(
      `/projects/${projectId}/slides/${slideId}/script/approve`,
      { method: "POST" }
    ),
  revertScript: (projectId: string, slideId: string) =>
    request<ProjectSlideScript>(
      `/projects/${projectId}/slides/${slideId}/script/revert`,
      { method: "POST" }
    ),
  updateReviewSettings: (
    projectId: string,
    slideId: string,
    body: ScriptReviewSettingsRequest
  ) =>
    json<ProjectSlideScript>(
      `/projects/${projectId}/slides/${slideId}/script/review-settings`,
      "PATCH",
      body
    ),
  previewSegmentAudio: (
    projectId: string,
    slideId: string,
    segmentIndex: number,
    previewConfig: Record<string, unknown>
  ) =>
    requestBlob(
      `/projects/${projectId}/slides/${slideId}/script/segments/${segmentIndex}/preview-audio`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preview_config: previewConfig }),
      }
    ),
  slideImageUrl: (projectId: string, slideId: string) =>
    `${BASE}/projects/${projectId}/slides/${slideId}/image`,
  transcribeAudio: (projectId: string, showFileId: string, audioBlob: Blob) => {
    const form = new FormData();
    form.append("audio", audioBlob, "recording.webm");
    return request<TranscribeResponse>(
      `/projects/${projectId}/show-files/${showFileId}/qa/transcribe`,
      { method: "POST", body: form }
    );
  },
  answerQuestion: (
    projectId: string,
    showFileId: string,
    question: string,
    slideContext: string | null,
    sessionId: string
  ) =>
    request<AnswerResponse>(
      `/projects/${projectId}/show-files/${showFileId}/qa/answer`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          slide_context: slideContext,
          session_id: sessionId,
        }),
      }
    ),
  synthesizeSpeech: (
    projectId: string,
    showFileId: string,
    text: string,
    voiceId: string | null
  ) =>
    requestBlob(`/projects/${projectId}/show-files/${showFileId}/tts/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice_id: voiceId }),
    }),
  exportVideo: (projectId: string, showFileId: string) =>
    requestBlob(`/projects/${projectId}/show-files/${showFileId}/export/video`, {
      method: "POST",
    }),
};
