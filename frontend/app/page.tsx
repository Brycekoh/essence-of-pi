import { PaperList } from "./components/paper-list";
import { Uploader } from "./components/uploader";

export default function Home() {
  return (
    <div className="space-y-10">
      <section>
        <h1 className="mb-1 text-2xl font-semibold">Upload a paper</h1>
        <p className="mb-4 text-sm text-muted">
          It gets read, the handful of ideas that matter get pulled out, and
          each one can be turned into a short narrated animation.
        </p>
        <Uploader />
      </section>
      <section>
        <h2 className="mb-3 text-lg font-semibold">Your papers</h2>
        <PaperList />
      </section>
    </div>
  );
}
