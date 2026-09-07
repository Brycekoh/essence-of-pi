"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { ApiError, uploadPaper } from "../lib/api";

export function Uploader() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(file: File) {
    setBusy(true);
    setError(null);
    try {
      const paper = await uploadPaper(file);
      router.push(`/papers/${paper.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed.");
      setBusy(false);
    }
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files[0];
          if (file) send(file);
        }}
        className={`glass group relative cursor-pointer rounded-2xl p-10 text-center transition-all duration-300
          ${dragging ? "scale-[1.01] border-accent/70" : "hover:border-accent/40"}
          ${busy ? "pointer-events-none" : ""}`}
      >
        {/* Dashed inner ring, so it reads as a drop target without a heavy border. */}
        <div
          className={`pointer-events-none absolute inset-3 rounded-xl border border-dashed transition-colors
            ${dragging ? "border-accent/70" : "border-line group-hover:border-accent-dim"}`}
        />
        <input
          ref={input}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) send(file);
          }}
        />
        {busy ? (
          <div className="space-y-2">
            <p className="animate-glow text-accent">Reading the PDF…</p>
            <p className="text-xs text-muted">text extraction, a few seconds</p>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-3xl leading-none text-accent/80">↑</p>
            <p className="text-base">
              Drop a PDF here, or <span className="text-accent">choose one</span>
            </p>
            <p className="text-xs text-muted">Research papers work best · up to 25 MB</p>
          </div>
        )}
      </div>
      {error && <p className="mt-3 text-center text-sm text-bad">{error}</p>}
    </div>
  );
}
