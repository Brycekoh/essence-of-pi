import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { ShaderBackground } from "./components/shader-background";

export const metadata: Metadata = {
  title: "Essence of Pi",
  description: "Research papers, distilled into 3blue1brown-style explainers.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <ShaderBackground />
        <header className="sticky top-0 z-20 border-b border-line/60 bg-bg/60 backdrop-blur-md">
          <div className="mx-auto flex max-w-5xl items-baseline gap-4 px-6 py-3.5">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-xl leading-none text-accent">π</span>
              <span className="wordmark text-lg">Essence of Pi</span>
            </Link>
            <span className="hidden text-sm text-muted sm:inline">
              papers → concepts → explainer videos
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
        <footer className="mx-auto max-w-5xl px-6 pb-10 pt-6 text-xs text-muted/70">
          Built with manim, ffmpeg and Kokoro, all running locally. Concepts by Gemini.
        </footer>
      </body>
    </html>
  );
}
