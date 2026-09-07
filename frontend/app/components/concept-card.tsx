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
      className={`card animate-rise p-8 ${building ? "" : "card-hover"}`}
      style={{
        animationDelay: `${delay}ms`,
        ...(building ? { borderColor: "rgb(255 255 255 / 0.32)" } : {}),
      }}
    >
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0 space-y-2">
          <p className="eyebrow tracking-[0.3em]">
            {String(index).padStart(2, "0").split("").join(" ")}
            <span className="ml-4 normal-case tracking-normal">
              pages {concept.source_pages.join(", ") || "—"}
            </span>
          </p>
          <h3 className="text-2xl font-light leading-tight tracking-tight">{concept.name}</h3>
          <p className="text-fg-2">{concept.summary}</p>
          <button
            onClick={() => setOpen((o) => !o)}
            className="text-xs text-fg-3 transition-colors hover:text-fg"
          >
            {open ? "less ↑" : "more ↓"}
          </button>
          {open && (
            <div className="animate-fade space-y-2 border-l border-fg/15 pl-4 text-sm text-fg-2">
              <p>{concept.explanation}</p>
              {concept.prerequisites.length > 0 && (
                <p>
                  <span className="text-fg-3">Assumes </span>
                  {concept.prerequisites.join(", ")}
                </p>
              )}
              <p>
                <span className="text-fg-3">On screen </span>
                {concept.visual_hint}
              </p>
            </div>
          )}
        </div>

        <div className="shrink-0">
          {state.kind === "idle" && (
            <button onClick={build} className="btn-primary text-sm">
              Build video
            </button>
          )}
          {state.kind === "failed" && (
            <button onClick={build} className="btn-secondary text-sm">
              Try again
            </button>
          )}
          {state.kind === "done" && (
            <button onClick={build} className="btn-secondary text-xs" title="Generate a new version">
              Rebuild
            </button>
          )}
        </div>
      </div>

      {building && (
        <div className="mt-8">
          <Progress events={state.events} />
        </div>
      )}
      {state.kind === "failed" && (
        <p className="mt-6 inline-block rounded-full border border-bad/30 bg-bad/10 px-4 py-1 text-sm text-bad">
          {state.message}
        </p>
      )}
      {state.kind === "done" && (
        <video
          className="animate-fade mt-8 w-full"
          style={{ boxShadow: "0 30px 80px rgb(0 0 0 / 0.7)" }}
          controls
          preload="metadata"
          src={state.src}
        />
      )}
    </li>
  );
}
