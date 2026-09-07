"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { API, listPapers } from "../lib/api";
import type { PaperSummary } from "../lib/types";

export function PaperList() {
  const [papers, setPapers] = useState<PaperSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPapers()
      .then(setPapers)
      .catch(() => setError(`Can't reach the backend at ${API}. Is it running?`));
  }, []);

  if (error) return <p className="text-sm text-bad">{error}</p>;
  if (papers === null) return <p className="text-sm text-muted">Loading…</p>;
  if (papers.length === 0)
    return (
      <p className="glass rounded-xl px-4 py-3 text-sm text-muted">
        Nothing yet. The store is in memory, so a backend restart clears it.
      </p>
    );

  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {papers.map((p, i) => (
        <li
          key={p.id}
          className="animate-rise"
          style={{ animationDelay: `${i * 60}ms` }}
        >
          <Link
            href={`/papers/${p.id}`}
            className="glass group flex h-full flex-col justify-between gap-3 rounded-xl p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40"
          >
            <span className="line-clamp-2 leading-snug group-hover:text-accent">
              {p.title ?? p.filename}
            </span>
            <span className="flex items-baseline justify-between text-xs text-muted">
              <span>{p.page_count} pages</span>
              <span>{new Date(p.uploaded_at).toLocaleDateString()}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
