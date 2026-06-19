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
  created_at: string;
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
};
