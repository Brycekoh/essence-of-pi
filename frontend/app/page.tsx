import { PaperList } from "./components/paper-list";
import { Uploader } from "./components/uploader";

const STEPS = [
  {
    n: "01",
    title: "Read",
    body: "The PDF is parsed and the handful of ideas that actually matter are pulled out, ordered so prerequisites come first.",
  },
  {
    n: "02",
    title: "Write",
    body: "A model writes the narration, then Manim code to fit it. If a render fails, it gets its own traceback back and tries again.",
  },
  {
    n: "03",
    title: "Render",
    body: "Everything runs in a sandboxed container: animation, a local voice, ffmpeg. No key, no quota, no network.",
  },
];

export default function Home() {
  return (
    <div className="space-y-16">
      <section className="animate-rise pt-6 text-center sm:pt-12">
        <p className="mb-3 text-xs font-medium uppercase tracking-[0.2em] text-accent/80">
          research papers, distilled
        </p>
        <h1 className="wordmark mx-auto max-w-3xl text-4xl leading-[1.08] sm:text-6xl">
          Turn a paper into an explainer you&rsquo;d actually watch
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-base text-muted sm:text-lg">
          Upload a PDF. Get the core concepts back. Turn any of them into a
          short, narrated animation in the style of 3blue1brown.
        </p>
      </section>

      <section className="animate-rise mx-auto max-w-2xl" style={{ animationDelay: "120ms" }}>
        <Uploader />
      </section>

      <section
        className="animate-rise grid gap-4 sm:grid-cols-3"
        style={{ animationDelay: "220ms" }}
      >
        {STEPS.map((s) => (
          <div key={s.n} className="glass rounded-xl p-5">
            <p className="font-mono text-xs text-accent/70">{s.n}</p>
            <h3 className="mt-1 text-base font-semibold">{s.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{s.body}</p>
          </div>
        ))}
      </section>

      <section className="animate-rise" style={{ animationDelay: "320ms" }}>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-muted">
          Your papers
        </h2>
        <PaperList />
      </section>
    </div>
  );
}
