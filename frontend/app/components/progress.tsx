"use client";

import type { JobEvent } from "../lib/types";

// The stages in the order the pipeline runs them. Progress is shown as which
// stage we are on rather than a percentage: the stages differ in length by
// an order of magnitude, and a bar that sits at 40% for two minutes says less
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

  const scene = events
    .filter((e) => e.stage === "animate" && e.scene)
    .reduce((max, e) => Math.max(max, e.scene ?? 0), 0);
  const total = latest?.total_scenes ?? null;

  return (
    <div className="space-y-3">
      <ol className="flex gap-1.5">
        {STAGES.map((stage, i) => {
          const failed = current === "failed";
          const state = failed
            ? i <= reached ? "bad" : "idle"
            : i < reached ? "done" : i === reached ? "active" : "idle";
          return (
            <li
              key={stage}
              title={LABELS[stage]}
              className={`relative h-px flex-1 overflow-hidden rounded-full transition-colors duration-500 ${
                state === "done" ? "bg-fg" : state === "bad" ? "bg-bad" : "bg-fg/15"
              }`}
            >
              {state === "active" && (
                <span className="animate-sweep absolute inset-y-0 left-0 bg-fg" />
              )}
            </li>
          );
        })}
      </ol>
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-light">
          {LABELS[current] ?? current}
          {current === "animate" && total ? (
            <span className="text-fg-3"> — scene {scene || 1} of {total}</span>
          ) : null}
        </span>
        <span className="eyebrow text-[10px]">
          {reached < 0 ? "" : `${reached + 1} / ${STAGES.length}`}
        </span>
      </div>
    </div>
  );
}
