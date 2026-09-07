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
        `${result.concepts.length} concepts, from ${result.model}` +
          (result.truncated
            ? ". The paper was longer than the model budget, so only the start was read."
            : "."),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Extraction failed.");
    } finally {
      setExtracting(false);
    }
  }

  const shell = (children: React.ReactNode) => (
    <main className="relative z-10 px-6 pb-24 pt-36">
      <div className="mx-auto max-w-4xl">{children}</div>
    </main>
  );

  if (error && !paper)
    return shell(
      <div className="card px-10 py-12 text-center">
        <p className="text-lg font-light">{error}</p>
        <Link href="/papers" className="btn-secondary mt-6">
          ← Library
        </Link>
      </div>,
    );
  if (!paper || concepts === null)
    return shell(<p className="text-fg-3">Loading…</p>);

  return shell(
    <div className="space-y-14">
      <header className="animate-rise space-y-5">
        <Link href="/papers" className="btn-secondary text-xs">
          ← Library
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="min-w-0 space-y-2">
            <p className="eyebrow">Paper</p>
            <h1 className="text-[clamp(2rem,3.5vw,3.4rem)] font-light leading-tight tracking-[-0.03em]">
              {paper.title ?? paper.filename}
            </h1>
            <p className="text-fg-3">
              {paper.page_count} pages · {Math.round(paper.char_count / 1000)}k characters
            </p>
          </div>
          <button onClick={extract} disabled={extracting} className="btn-primary">
            {extracting
              ? "Asking the model…"
              : concepts.length
                ? "Extract again"
                : "Extract concepts"}
          </button>
        </div>
        {note && <p className="text-sm text-fg-2">{note}</p>}
        {error && <p className="text-sm text-bad">{error}</p>}
      </header>

      <section className="animate-rise space-y-6" style={{ animationDelay: "150ms" }}>
        <p className="eyebrow">Concepts</p>
        {concepts.length === 0 ? (
          <div className="card px-10 py-14 text-center">
            <p className="text-xl font-light">No concepts yet.</p>
            <p className="mt-2 text-fg-2">
              Extraction is a single model call and takes about a minute.
            </p>
          </div>
        ) : (
          <ol className="space-y-6">
            {concepts.map((c, i) => (
              <ConceptCard key={c.id} index={i + 1} concept={c} delay={i * 90} />
            ))}
          </ol>
        )}
      </section>
    </div>,
  );
}
