import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

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
        <header className="border-b border-line">
          <div className="mx-auto flex max-w-4xl items-baseline gap-4 px-6 py-4">
            <Link href="/" className="text-lg font-semibold text-accent">
              Essence of Pi
            </Link>
            <span className="text-sm text-muted">
              research papers, distilled into explainer videos
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-4xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
