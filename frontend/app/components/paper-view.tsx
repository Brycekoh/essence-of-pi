"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, extractConcepts, getPaper, listConcepts } from "../lib/api";
import type { Concept, Paper } from "../lib/types";
import { ConceptCard } from "./concept-card";

export function PaperView({ paperId }: { paperId: string }) {
  const [paper, setPaper] = useState<Paper | null>(null);
  const [concepts, setConcepts] = useState<Concept[] | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getPaper(paperId), listConcepts(paperId)])
      .then(([p, c]) => {
        setPaper(p);
        setConcepts(c);
      })
      .catch((e) =>
        setError(
          e instanceof ApiError && e.status === 404
            ? "This paper isn't in the store any more. The backend was probably restarted."
            : "Couldn't load this paper.",
        ),
      );
  }, [paperId]);

  async function extract() {
    setExtracting(true);
    setError(null);
    setNote(null);
    try {
      const result = await extractConcepts(paperId);
      setConcepts(result.concepts);
      setNote(
        `${result.concepts.length} concepts from ${result.model}` +
          (result.truncated
            ? " — the paper was longer than the model budget, so only the start was read."
            : ""),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Extraction failed.");
    } finally {
      setExtracting(false);
    }
  }

  if (error && !paper)
    return (
      <div className="glass rounded-xl p-6">
        <p className="text-bad">{error}</p>
        <Link href="/" className="mt-3 inline-block text-sm text-accent">
          ← back to papers
        </Link>
      </div>
    );
  if (!paper || concepts === null) return <p className="text-muted">Loading…</p>;

  return (
    <div className="space-y-10">
      <header className="animate-rise">
        <Link href="/" className="text-xs text-muted hover:text-accent">
          ← papers
        </Link>
        <h1 className="wordmark mt-2 text-3xl leading-tight sm:text-4xl">
          {paper.title ?? paper.filename}
        </h1>
        <p className="mt-2 text-sm text-muted">
          {paper.page_count} pages · {Math.round(paper.char_count / 1000)}k characters
        </p>
      </header>

      <section className="animate-rise" style={{ animationDelay: "100ms" }}>
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 className="text-sm font-medium uppercase tracking-wider text-muted">
            Concepts
          </h2>
          <button
            onClick={extract}
            disabled={extracting}
            className="rounded-lg bg-accent px-3.5 py-1.5 text-sm font-medium text-bg transition hover:brightness-110 disabled:opacity-50"
          >
            {extracting
              ? "Asking the model…"
              : concepts.length
                ? "Extract again"
                : "Extract concepts"}
          </button>
        </div>
        {note && <p className="mb-4 text-sm text-muted">{note}</p>}
        {error && <p className="mb-4 text-sm text-bad">{error}</p>}

        {concepts.length === 0 ? (
          <div className="glass rounded-xl p-8 text-center">
            <p className="text-fg">No concepts yet.</p>
            <p className="mt-1 text-sm text-muted">
              Extraction is one model call and takes about a minute.
            </p>
          </div>
        ) : (
          <ol className="space-y-4">
            {concepts.map((c, i) => (
              <ConceptCard key={c.id} index={i + 1} concept={c} delay={i * 70} />
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
