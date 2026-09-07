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
      <p className="text-sm text-muted">
        Nothing yet. The store is in memory, so a backend restart clears it.
      </p>
    );

  return (
    <ul className="divide-y divide-line rounded-lg border border-line bg-panel">
      {papers.map((p) => (
        <li key={p.id}>
          <Link
            href={`/papers/${p.id}`}
            className="flex items-baseline justify-between gap-4 px-4 py-3 hover:bg-panel-2"
          >
            <span className="truncate">{p.title ?? p.filename}</span>
            <span className="shrink-0 text-xs text-muted">
              {p.page_count} pages
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
