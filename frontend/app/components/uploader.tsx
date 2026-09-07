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
        className={`cursor-pointer rounded-lg border-2 border-dashed p-10 text-center transition
          ${dragging ? "border-accent bg-panel-2" : "border-line bg-panel hover:border-accent-dim"}
          ${busy ? "pointer-events-none opacity-60" : ""}`}
      >
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
          <p className="text-muted">Reading the PDF…</p>
        ) : (
          <>
            <p className="text-fg">Drop a PDF here, or click to choose one</p>
            <p className="mt-1 text-sm text-muted">Up to 25 MB</p>
          </>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-bad">{error}</p>}
    </div>
  );
}
