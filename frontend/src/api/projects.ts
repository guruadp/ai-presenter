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
  version: number;
  created_at: string;
  updated_at: string;
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
}

export interface Project {
  id: string;
  name: string;
  owner: string;
  tone_profile: ToneProfile;
  knowledge_bases: ProjectKnowledgeBase[];
  slides: ProjectSlide[];
  created_at: string;
  updated_at: string;
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
  slideImageUrl: (projectId: string, slideId: string) =>
    `${BASE}/projects/${projectId}/slides/${slideId}/image`,
};
