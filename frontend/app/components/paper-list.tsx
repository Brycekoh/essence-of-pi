"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { API, listPapers } from "../lib/api";
import type { PaperSummary } from "../lib/types";

export function PaperList({ animate = true }: { animate?: boolean }) {
  const [papers, setPapers] = useState<PaperSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPapers()
      .then(setPapers)
      .catch(() => setError(`Can't reach the backend at ${API}. Is it running?`));
  }, []);

  if (error) return <p className="text-sm text-bad">{error}</p>;
  if (papers === null) return <p className="text-sm text-fg-3">Loading…</p>;
  if (papers.length === 0)
    return (
      <div className="card px-8 py-10 text-center">
        <p className="text-lg font-light">Nothing here yet.</p>
        <p className="mt-1 text-sm text-fg-3">
          The store is in memory, so a backend restart clears it.
        </p>
      </div>
    );

  return (
    <ul className="grid gap-5 sm:grid-cols-2">
      {papers.map((p, i) => (
        <li
          key={p.id}
          className={animate ? "animate-rise" : ""}
          style={animate ? { animationDelay: `${i * 80}ms` } : undefined}
        >
          <Link
            href={`/papers/${p.id}`}
            className="card card-hover flex h-full flex-col justify-between gap-6 p-7"
          >
            <span className="line-clamp-2 text-xl font-light leading-snug tracking-tight">
              {p.title ?? p.filename}
            </span>
            <span className="flex items-baseline justify-between text-xs text-fg-3">
              <span>{p.page_count} pages</span>
              <span>{new Date(p.uploaded_at).toLocaleDateString()}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
