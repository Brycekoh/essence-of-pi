// Mirrors the backend's pydantic models. Kept by hand rather than generated:
// there are six of them, and reading this file is faster than reading an
// OpenAPI generator's output.

export interface PaperSummary {
  id: string;
  filename: string;
  page_count: number;
  char_count: number;
  title: string | null;
  uploaded_at: string;
}

export interface Paper extends PaperSummary {
  size_bytes: number;
}

export interface Concept {
  id: string;
  paper_id: string;
  name: string;
  summary: string;
  explanation: string;
  prerequisites: string[];
  visual_hint: string;
  source_pages: number[];
  video_url: string | null;
}

export interface ExtractionResult {
  paper_id: string;
  concepts: Concept[];
  truncated: boolean;
  model: string;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface JobEvent {
  at: string;
  stage: string;
  message: string;
  scene: number | null;
  total_scenes: number | null;
  fraction?: number | null;
}

export interface Job {
  id: string;
  paper_id: string;
  concept_id: string;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  events: JobEvent[];
  video_url: string | null;
  error: string | null;
}

export interface JobEnd {
  status: JobStatus;
  video_url: string | null;
  error: string | null;
}
