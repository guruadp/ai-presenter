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

export interface KB {
  id: string;
  name: string;
  owner: string;
  version: number;
  content_hash: string;
  created_at: string;
  updated_at: string;
}

export interface KBDocument {
  id: string;
  kb_id: string;
  filename: string;
  content_type: string;
  content_hash: string;
  chunk_count: number;
  tags: string[];
  ingested_at: string;
}

export interface KBFact {
  id: string;
  kb_id: string;
  key: string;
  value: string;
  source: string | null;
  created_at: string;
}

export interface KBLimitation {
  id: string;
  kb_id: string;
  description: string;
  created_at: string;
}

export const kbApi = {
  list: () => request<KB[]>("/kbs"),
  get: (id: string) => request<KB>(`/kbs/${id}`),
  create: (body: { name: string; owner: string }) =>
    json<KB>("/kbs", "POST", body),
  update: (id: string, body: { name?: string }) =>
    json<KB>(`/kbs/${id}`, "PATCH", body),
  delete: (id: string) => request<void>(`/kbs/${id}`, { method: "DELETE" }),

  listDocuments: (kbId: string) =>
    request<KBDocument[]>(`/kbs/${kbId}/documents`),
  uploadDocument: (kbId: string, file: File, tags: string[]) => {
    const form = new FormData();
    form.append("file", file);
    form.append("tags", tags.join(","));
    return request<KBDocument>(`/kbs/${kbId}/documents`, {
      method: "POST",
      body: form,
    });
  },

  listFacts: (kbId: string) => request<KBFact[]>(`/kbs/${kbId}/facts`),
  addFact: (
    kbId: string,
    body: { key: string; value: string; source?: string }
  ) => json<KBFact>(`/kbs/${kbId}/facts`, "POST", body),
  deleteFact: (kbId: string, factId: string) =>
    request<void>(`/kbs/${kbId}/facts/${factId}`, { method: "DELETE" }),

  listLimitations: (kbId: string) =>
    request<KBLimitation[]>(`/kbs/${kbId}/limitations`),
  addLimitation: (kbId: string, body: { description: string }) =>
    json<KBLimitation>(`/kbs/${kbId}/limitations`, "POST", body),
  deleteLimitation: (kbId: string, limId: string) =>
    request<void>(`/kbs/${kbId}/limitations/${limId}`, { method: "DELETE" }),
};

export function ago(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString("en", {
    month: "short",
    day: "numeric",
  });
}
