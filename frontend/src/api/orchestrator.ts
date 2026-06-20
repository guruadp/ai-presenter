const BASE = "/api/orchestrator";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

function post<T>(path: string, body: unknown): Promise<T> {
  return req<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface OrchestratorCursor {
  slide_index: number;
  segment_index: number;
  sentence_index: number;
}

export interface CreateSessionResponse {
  session_id: string;
  state: string;
}

export interface SessionStateResponse {
  session_id: string;
  state: string;
  cursor: OrchestratorCursor;
  jump_stack_depth: number;
}

export interface CommandResponse {
  state: string;
  cursor: OrchestratorCursor;
}

export interface OrchestratorEvent {
  type: string;
  payload: Record<string, unknown>;
}

export interface LogQARequest {
  question: string;
  answer: string;
  question_type: string;
  confidence: number;
  deferred: boolean;
  slide_index: number;
  served_from_faq: boolean;
}

export interface QAEntryOut {
  id: string;
  session_id: string;
  project_id: string;
  question: string;
  answer_text: string;
  question_type: string;
  confidence: number;
  deferred: boolean;
  slide_index: number;
  served_from_faq: boolean;
  created_at: string;
}

function wsUrl(sessionId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/orchestrator/sessions/${sessionId}/events`;
}

export const orchestratorApi = {
  createSession: (projectId: string, showFileId: string, qaBudgetSeconds = 120) =>
    post<CreateSessionResponse>("/sessions", {
      project_id: projectId,
      show_file_id: showFileId,
      qa_budget_seconds: qaBudgetSeconds,
    }),

  getSession: (sessionId: string) =>
    req<SessionStateResponse>(`/sessions/${sessionId}`),

  sendCommand: (sessionId: string, type: string, payload: Record<string, unknown> = {}) =>
    post<CommandResponse>(`/sessions/${sessionId}/command`, { type, payload }),

  deleteSession: (sessionId: string) =>
    req<void>(`/sessions/${sessionId}`, { method: "DELETE" }),

  openEventsSocket: (sessionId: string): WebSocket =>
    new WebSocket(wsUrl(sessionId)),

  logQA: (sessionId: string, body: LogQARequest) =>
    post<QAEntryOut>(`/sessions/${sessionId}/qa-log`, body),
};
