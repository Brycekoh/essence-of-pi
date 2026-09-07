"use client";

import type { JobEvent } from "../lib/types";

// The stages in the order the pipeline runs them. Progress is shown as which
// stage we are on rather than a percentage, because the stages are wildly
// different lengths and a bar that sits at 40% for two minutes tells you less
// than "animating scene 2 of 3".
const STAGES = ["split", "narrate", "animate", "stitch", "done"] as const;

const LABELS: Record<string, string> = {
  split: "Splitting into scenes",
  narrate: "Narrating",
  animate: "Animating",
  stitch: "Stitching",
  done: "Done",
  failed: "Failed",
};

export function Progress({ events }: { events: JobEvent[] }) {
  const latest = events[events.length - 1];
  const current = latest?.stage ?? "split";
  const reached = STAGES.indexOf(current as (typeof STAGES)[number]);

  // The furthest scene reported so far, for "scene 2 of 3".
  const scene = events
    .filter((e) => e.stage === "animate" && e.scene)
    .reduce((max, e) => Math.max(max, e.scene ?? 0), 0);
  const total = latest?.total_scenes ?? null;

  return (
    <div className="space-y-2">
      <ol className="flex gap-1">
        {STAGES.map((stage, i) => {
          const state =
            current === "failed"
              ? i <= reached
                ? "bad"
                : "idle"
              : i < reached
                ? "done"
                : i === reached
                  ? "active"
                  : "idle";
          return (
            <li
              key={stage}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                state === "done"
                  ? "bg-accent"
                  : state === "active"
                    ? "animate-pulse bg-accent"
                    : state === "bad"
                      ? "bg-bad"
                      : "bg-line"
              }`}
              title={LABELS[stage]}
            />
          );
        })}
      </ol>
      <p className="text-sm text-muted">
        {LABELS[current] ?? current}
        {current === "animate" && total ? ` — scene ${scene || 1} of ${total}` : ""}
        {latest?.message && current !== "animate" ? ` — ${latest.message}` : ""}
      </p>
    </div>
  );
}
