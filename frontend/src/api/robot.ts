const BASE = "/api/robot";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
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

export const robotApi = {
  getStatus: () => req<{ enabled: boolean }>("/status"),

  playAudio: (projectId: string, showFileId: string, audioPath: string) =>
    post<{ ok: boolean }>("/play-audio", {
      project_id: projectId,
      show_file_id: showFileId,
      audio_path: audioPath,
    }),
};
