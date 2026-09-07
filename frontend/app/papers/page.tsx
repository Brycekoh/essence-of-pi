import { PaperList } from "../components/paper-list";

export default function LibraryPage() {
  return (
    <main className="relative z-10 px-6 pb-24 pt-36">
      <div className="mx-auto max-w-4xl space-y-10">
        <div className="animate-rise space-y-3">
          <p className="eyebrow">Library</p>
          <h1 className="text-[clamp(2rem,3.5vw,3rem)] font-light leading-tight tracking-[-0.03em]">
            Every paper you&rsquo;ve uploaded.
          </h1>
          <p className="text-fg-2">
            Open one to extract its concepts and build videos from them.
          </p>
        </div>
        <div className="animate-rise" style={{ animationDelay: "150ms" }}>
          <PaperList animate={false} />
        </div>
      </div>
    </main>
  );
}
