"use client";

import { useEffect, useState } from "react";

import { ApiError, startVideo, videoUrl, watchJob } from "../lib/api";
import type { Concept, JobEvent } from "../lib/types";
import { Progress } from "./progress";

type State =
  | { kind: "idle" }
  | { kind: "building"; jobId: string; events: JobEvent[] }
  | { kind: "done"; src: string }
  | { kind: "failed"; message: string };

export function ConceptCard({
  index,
  concept,
  delay = 0,
}: {
  index: number;
  concept: Concept;
  delay?: number;
}) {
  const [state, setState] = useState<State>(
    // A concept that already has a video shows it straight away. The URL gets
    // a cache-buster so a rebuilt video is not served from the browser cache.
    concept.video_url
      ? { kind: "done", src: `${videoUrl(concept.paper_id, concept.id)}?v=${Date.now()}` }
      : { kind: "idle" },
  );
  const [open, setOpen] = useState(false);

  // Subscribe to progress for as long as a build is running. The cleanup
  // closes the stream when the card unmounts or the job changes.
  useEffect(() => {
    if (state.kind !== "building") return;
    const jobId = state.jobId;
    return watchJob(jobId, {
      onEvent: (event) =>
        setState((s) =>
          s.kind === "building" && s.jobId === jobId
            ? { ...s, events: [...s.events, event] }
            : s,
        ),
      onEnd: (end) =>
        setState(
          end.status === "succeeded" && end.video_url
            ? { kind: "done", src: `${videoUrl(concept.paper_id, concept.id)}?v=${Date.now()}` }
            : { kind: "failed", message: end.error ?? "The build failed." },
        ),
      onError: () =>
        setState({ kind: "failed", message: "Lost the connection to the build." }),
    });
    // `state.jobId` is the only part of state this effect depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.kind === "building" ? state.jobId : null]);

  async function build() {
    try {
      const job = await startVideo(concept.paper_id, concept.id);
      // The server replays past events on subscribe, so start from empty and
      // let the stream fill it -- even when joining a job already in flight.
      setState({ kind: "building", jobId: job.id, events: [] });
    } catch (e) {
      setState({
        kind: "failed",
        message: e instanceof ApiError ? e.message : "Couldn't start the build.",
      });
    }
  }

  const building = state.kind === "building";

  return (
    <li
      className={`glass animate-rise rounded-2xl p-5 transition-all duration-300
        ${building ? "border-accent/40" : "hover:border-accent/30"}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start gap-4">
        {/* Index badge: the ordering is meaningful, prerequisites come first. */}
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-accent-dim font-mono text-xs text-accent">
          {index}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h3 className="text-lg font-semibold leading-snug">{concept.name}</h3>
              <p className="mt-0.5 text-xs text-muted">
                pages {concept.source_pages.join(", ") || "—"}
              </p>
            </div>

            {state.kind === "idle" && (
              <button
                onClick={build}
                className="shrink-0 rounded-lg bg-accent px-3.5 py-1.5 text-sm font-medium text-bg transition hover:brightness-110"
              >
                Build video
              </button>
            )}
            {state.kind === "failed" && (
              <button
                onClick={build}
                className="shrink-0 rounded-lg border border-line px-3.5 py-1.5 text-sm text-muted transition hover:border-accent/40 hover:text-fg"
              >
                Try again
              </button>
            )}
            {state.kind === "done" && (
              <button
                onClick={build}
                className="shrink-0 text-xs text-muted transition hover:text-accent"
                title="Generate a new version"
              >
                rebuild
              </button>
            )}
          </div>

          <p className="mt-2 text-sm leading-relaxed text-fg/90">{concept.summary}</p>
          <button
            onClick={() => setOpen((o) => !o)}
            className="mt-1.5 text-xs text-muted transition hover:text-accent"
          >
            {open ? "less ↑" : "more ↓"}
          </button>
          {open && (
            <div className="animate-fade mt-3 space-y-2 border-l border-line pl-3 text-sm text-muted">
              <p>{concept.explanation}</p>
              {concept.prerequisites.length > 0 && (
                <p>
                  <span className="text-fg/70">Assumes: </span>
                  {concept.prerequisites.join(", ")}
                </p>
              )}
              <p>
                <span className="text-fg/70">On screen: </span>
                {concept.visual_hint}
              </p>
            </div>
          )}

          {building && (
            <div className="mt-4">
              <Progress events={state.events} />
            </div>
          )}
          {state.kind === "failed" && (
            <p className="mt-3 text-sm text-bad">{state.message}</p>
          )}
          {state.kind === "done" && (
            <video
              className="animate-fade mt-4 w-full shadow-2xl shadow-black/50"
              controls
              preload="metadata"
              src={state.src}
            />
          )}
        </div>
      </div>
    </li>
  );
}
