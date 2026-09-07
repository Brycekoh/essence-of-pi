// The only file that knows the backend's URL shape.
//
// Everything runs in the browser. The backend is on the same machine and
// already allows this origin, and the progress stream is an EventSource --
// which only exists in the browser -- so a single client-side model is
// simpler than splitting fetches between server and client components.

import type {
  Concept,
  ExtractionResult,
  Job,
  JobEnd,
  JobEvent,
  Paper,
  PaperSummary,
} from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => body?.detail)
      .catch(() => undefined);
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message ?? `${response.status} ${response.statusText}`;
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// --- papers ---------------------------------------------------------------

export const listPapers = () => request<PaperSummary[]>("/api/papers");

export const getPaper = (id: string) => request<Paper>(`/api/papers/${id}`);

export function uploadPaper(file: File): Promise<Paper> {
  const body = new FormData();
  body.append("file", file);
  return request<Paper>("/api/papers", { method: "POST", body });
}

export const deletePaper = (id: string) =>
  request<void>(`/api/papers/${id}`, { method: "DELETE" });

// --- concepts -------------------------------------------------------------

export const listConcepts = (paperId: string) =>
  request<Concept[]>(`/api/papers/${paperId}/concepts`);

export const extractConcepts = (paperId: string) =>
  request<ExtractionResult>(`/api/papers/${paperId}/concepts`, {
    method: "POST",
  });

// --- video ----------------------------------------------------------------

export const videoUrl = (paperId: string, conceptId: string) =>
  `${API}/api/papers/${paperId}/concepts/${conceptId}/video`;

/** Returns 202 with a new job, or 200 with one already running. Either is a Job. */
export const startVideo = (paperId: string, conceptId: string) =>
  request<Job>(`/api/papers/${paperId}/concepts/${conceptId}/video`, {
    method: "POST",
  });

export const getJob = (jobId: string) => request<Job>(`/api/jobs/${jobId}`);

/**
 * Subscribe to a job's progress. Past events are replayed by the server
 * first, so a late subscriber still sees the whole build.
 *
 * Returns a function that closes the stream.
 */
export function watchJob(
  jobId: string,
  handlers: {
    onEvent: (event: JobEvent) => void;
    onEnd: (end: JobEnd) => void;
    onError?: () => void;
  },
): () => void {
  const source = new EventSource(`${API}/api/jobs/${jobId}/events`);

  source.addEventListener("progress", (e) => {
    handlers.onEvent(JSON.parse((e as MessageEvent).data));
  });
  source.addEventListener("end", (e) => {
    handlers.onEnd(JSON.parse((e as MessageEvent).data));
    source.close();
  });
  source.onerror = () => {
    // EventSource reconnects on its own; only surface it if the stream is
    // actually closed, which means the job is gone or the server is.
    if (source.readyState === EventSource.CLOSED) handlers.onError?.();
  };

  return () => source.close();
}
