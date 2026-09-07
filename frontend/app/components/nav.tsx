"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// A floating pill, centred, over everything. It is the only chrome the app
// has -- there is no header bar -- so the content sits on black edge to edge.
export function Nav() {
  const path = usePathname();
  const on = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href);

  const link = (href: string, label: string) => (
    <Link
      href={href}
      className={`rounded-full px-4 py-1.5 text-sm transition-colors ${
        on(href) ? "text-fg" : "text-fg-2 hover:bg-fg/5 hover:text-fg"
      }`}
    >
      {label}
    </Link>
  );

  return (
    <div className="pointer-events-none fixed inset-x-0 top-6 z-50 flex justify-center">
      <nav
        className="animate-fade pointer-events-auto flex items-center gap-1 rounded-full border border-fg/15 bg-fg/5 px-3 py-2 backdrop-blur-2xl"
        style={{ boxShadow: "0 25px 80px rgb(0 0 0 / 0.65)" }}
      >
        <Link
          href="/"
          className="flex items-baseline gap-2 rounded-full px-4 py-1.5 text-sm tracking-tight text-fg transition-colors hover:bg-fg/5"
        >
          <span className="text-base leading-none">π</span>
          <span>Essence of Pi</span>
        </Link>
        <div className="mx-1 h-4 w-px bg-fg/20" />
        {link("/papers", "Library")}
        <Link
          href="/"
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition-all ${
            path === "/" ? "bg-fg text-bg" : "bg-fg/10 text-fg hover:bg-fg/20"
          }`}
        >
          Upload
        </Link>
      </nav>
    </div>
  );
}
