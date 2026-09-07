import { PaperList } from "./components/paper-list";
import { SphereCanvas, type BackgroundVariant } from "./components/sphere-canvas";
import { Uploader } from "./components/uploader";

const FEATURES = [
  {
    title: "Concept distillation",
    body: "The handful of ideas that make the paper follow, ordered so prerequisites come first, each traced to its pages.",
  },
  {
    title: "Narrated animation",
    body: "A model writes the words, then Manim code to fit them. A failed render gets its own traceback back and tries again.",
  },
  {
    title: "Everything local",
    body: "Rendering, voice and ffmpeg run in a sandboxed container with no network. No key, no quota, no bill.",
  },
];

// Entrances are timed to land after the sphere has grown in (2.5s).
const AFTER_INTRO = 2.0;

const VARIANTS: BackgroundVariant[] = ["glass", "chrome", "smoke", "ring", "horizon"];

// `?bg=chrome` previews an alternative background without a code change.
// Reading searchParams makes this page dynamically rendered, which is fine:
// everything on it is client-fetched anyway.
export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ bg?: string }>;
}) {
  const { bg } = await searchParams;
  // Ring by default: a single glowing circle is the most 3blue1brown thing
  // to put behind the word "Pi", and it leaves the text easiest to read.
  const variant = VARIANTS.includes(bg as BackgroundVariant)
    ? (bg as BackgroundVariant)
    : "ring";

  return (
    <div className="relative min-h-screen overflow-hidden">
      <SphereCanvas introSeconds={2.5} variant={variant} />
      {/* Darkens the sphere where text sits, fading in once it has appeared. */}
      <div
        className="animate-fade pointer-events-none fixed inset-0 z-0 bg-gradient-to-b from-black/50 via-black/25 to-black/60"
        style={{ animationDelay: "1.5s", animationDuration: "1s" }}
      />

      <main className="relative z-10 px-6 pb-24 pt-36">
        <div className="mx-auto max-w-4xl space-y-16">
          <div
            className="animate-rise space-y-6 text-center"
            style={{ animationDelay: `${AFTER_INTRO}s` }}
          >
            <p className="eyebrow">Essence of Pi</p>
            <h1 className="text-[clamp(2.2rem,4.8vw,3.6rem)] font-light leading-[1.1] tracking-[-0.04em]">
              Research papers, distilled into{" "}
              <span className="font-normal">explainers you&rsquo;d actually watch</span>.
            </h1>
            <p className="mx-auto max-w-2xl text-lg text-fg-2">
              Upload a paper. Get its core ideas back. Turn any of them into a
              short, narrated animation in the style of 3blue1brown.
            </p>
          </div>

          <div className="animate-fade" style={{ animationDelay: `${AFTER_INTRO + 0.3}s` }}>
            <Uploader />
          </div>

          <div className="grid gap-6 md:grid-cols-3">
            {FEATURES.map((f, i) => (
              <div
                key={f.title}
                className="card card-hover animate-rise p-8 text-left"
                style={{ animationDelay: `${AFTER_INTRO + 0.6 + i * 0.15}s` }}
              >
                <p className="eyebrow mb-3 tracking-[0.3em]">
                  {String(i + 1).padStart(2, "0").split("").join(" ")}
                </p>
                <h3 className="mb-2 text-xl font-light">{f.title}</h3>
                <p className="text-sm leading-relaxed text-fg-2">{f.body}</p>
              </div>
            ))}
          </div>

          <div
            className="animate-rise"
            id="papers"
            style={{ animationDelay: `${AFTER_INTRO + 1.1}s` }}
          >
            <p className="eyebrow mb-4">Recent papers</p>
            <PaperList />
          </div>
        </div>
      </main>
    </div>
  );
}
