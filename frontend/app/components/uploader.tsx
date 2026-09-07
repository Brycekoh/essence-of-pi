"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, uploadPaper } from "../lib/api";

export function Uploader() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(file: File | undefined) {
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("That isn't a PDF.");
      return;
    }
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
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        send(e.dataTransfer.files[0]);
      }}
      className={`card group relative p-14 transition-all duration-300
        ${dragging ? "scale-[0.99] border-fg/50 bg-black/50" : "hover:border-fg/30 hover:bg-black/50"}
        ${busy ? "pointer-events-none" : "cursor-pointer"}`}
      style={dragging ? { boxShadow: "0 0 80px rgb(255 255 255 / 0.12)" } : undefined}
    >
      {/* A sheen from the top-left corner that brightens on hover. */}
      <div className="pointer-events-none absolute inset-0 rounded-3xl bg-gradient-to-br from-fg/20 via-transparent to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-60" />

      {/* The whole panel is the file input. */}
      <input
        type="file"
        accept="application/pdf"
        disabled={busy}
        onChange={(e) => send(e.target.files?.[0])}
        className="absolute inset-0 z-30 h-full w-full cursor-pointer opacity-0"
        aria-label="Upload a PDF"
      />

      <div className="pointer-events-none relative flex flex-col items-center gap-6 text-center">
        <div
          className={`rounded-full border border-fg/20 bg-black/30 p-6 backdrop-blur-xl transition-transform duration-300 ${
            dragging ? "scale-110" : ""
          }`}
          style={{ boxShadow: "0 0 40px rgb(255 255 255 / 0.15)" }}
        >
          {busy ? (
            <div className="animate-spin-slow h-14 w-14 rounded-full border-4 border-fg/15 border-t-fg" />
          ) : (
            <UploadIcon />
          )}
        </div>
        <div>
          <p className="text-2xl font-light tracking-tight">
            {busy ? "Reading the paper…" : "Drop your PDF or click to browse"}
          </p>
          <p className="mt-2 text-fg-2">
            {busy
              ? "Extracting the text. A few seconds."
              : "Research papers work best. Up to 25 MB."}
          </p>
        </div>
        {error && (
          <p className="animate-fade rounded-full border border-bad/30 bg-bad/10 px-4 py-1 text-sm text-bad">
            {error}
          </p>
        )}
      </div>

      {busy && (
        <div className="animate-sweep absolute bottom-0 left-0 h-px bg-gradient-to-r from-transparent via-fg to-transparent" />
      )}
    </div>
  );
}

function UploadIcon() {
  return (
    <svg
      className="h-14 w-14 text-fg/70"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 16V4" />
      <path d="M7 9l5-5 5 5" />
      <path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2" />
    </svg>
  );
}
