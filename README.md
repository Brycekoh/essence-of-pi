# Essence of Pi

Research papers, distilled into 3blue1brown-style explainers.

Upload a paper, get back the handful of ideas that actually matter, and turn any
of them into a short narrated animation.

> **Status: milestone 7 of 8.** The whole pipeline works end to end, with a web
> UI in front of it. What's left is persistence — restart the backend and the
> paper list is empty. This is a learning build, in public, one milestone per
> commit; [LEARNING.md](LEARNING.md) is the running log, including the mistakes.

## How it works

```
PDF → pdfplumber → LLM concepts → split into scenes
                                        │
                    ┌───────────────────┴───────────────────┐
                    │  per scene:  narrate → MEASURE it     │
                    │              → animate to that length │
                    │              → render → mux audio     │
                    └───────────────────┬───────────────────┘
                                        └──► concatenate → mp4
```

Narration is synthesised **before** any animation code is written, and its
measured length becomes the animation's target — so the picture fits the words
rather than the words being padded to fit the picture.

A failed render hands its own stderr back to the model as the next prompt, up to
three attempts, then degrades to a title card carrying that scene's narration. A
scene that cannot be built is skipped rather than sinking the video.

Builds run off the request path: `POST` returns `202` with a job, and progress
streams to the browser over server-sent events.

**110 tests**, and all but three run with no API key, no network and no Docker.

## Run it

### 1. Build the two images (once)

Everything that renders, narrates or muxes runs in a container. Nothing is
installed on the host — no manim, no ffmpeg, no LaTeX, no speech model.

```bash
cd backend
docker pull manimcommunity/manim:stable
docker build -f Dockerfile.render -t essence-of-pi/render:latest .
docker build -f Dockerfile.kokoro -t essence-of-pi/tts:kokoro .
```

- **`essence-of-pi/render`** (~2.9 GB) adds ffmpeg and a Piper voice to the
  manim image. The upstream image has no ffmpeg *binary* — manim 0.21 renders
  through PyAV's bundled libav — so narration could not be muxed on it.
- **`essence-of-pi/tts:kokoro`** (~2.9 GB) is the default narrator. It needs
  torch and manim does not, so it is a separate image rather than another 3 GB
  on every render. Set `SPEECH_ENGINE=piper` to skip it, or `gtts` to skip both.

Both run with `--network none`; model weights and voices are baked in at build
time, because a container with no network cannot fetch them.

### 2. Backend

**Windows (PowerShell).** `&&` is not a valid statement separator in Windows
PowerShell 5.1, and activating a venv can trip the execution policy — so call
the venv's executables directly:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

**macOS / Linux:**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Copy `backend/.env.example` to `backend/.env` and add a `GEMINI_API_KEY`
([free from AI Studio](https://aistudio.google.com/apikey)). Without one the app
still boots and serves papers; the LLM routes return `503` explaining what to
set. Interactive API docs: <http://localhost:8000/docs>.

**Run a single worker.** Jobs live in the process's memory, so a second worker
would not see them.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Then <http://localhost:3000>. Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local`
if the backend is not on `localhost:8000`. The landing page's background can be
switched with `?bg=` — `ring` (default), `glass`, `chrome`, `smoke`, `horizon`.

### Tests

```bash
cd backend && pytest
```

`.\.venv\Scripts\pytest.exe` on Windows. Three tests run manim, ffmpeg and
Kokoro for real and skip themselves when Docker or an image is missing.

### Measuring the generation loop

The number that says whether milestone 4 works is how often the model's first
attempt renders. Nothing else about the loop is more than a guess without it:

```bash
cd backend
.venv/Scripts/python.exe scripts/measure_generation.py path/to/paper.pdf --concepts 2
```

It builds the real pipeline by default and prints which engine it used.
`--single-scene` isolates the raw generation loop.

## Free-tier reality check

Gemini's free tier allows **20 requests per day, per model**. Concept extraction
costs one; a video costs one to three *per scene*. The client therefore rotates
through `LLM_FALLBACK_MODELS` rather than retrying one model, since the quota is
per-model, and it remembers which models returned `429`.

`MAX_SCENES` is the main lever on how fast that budget disappears. Narration and
rendering cost nothing — they are local.

## API

| Method | Route | Does |
| --- | --- | --- |
| `POST` | `/api/papers` | Upload a PDF, extract its text, return metadata |
| `GET` | `/api/papers` | List uploaded papers, newest first |
| `GET` | `/api/papers/{id}` | Metadata for one paper |
| `GET` | `/api/papers/{id}/text` | Extracted text, per page (`?page=2` for one) |
| `GET` | `/api/papers/{id}/pdf` | The original file back |
| `DELETE` | `/api/papers/{id}` | Remove the paper, its file and its videos |
| `POST` | `/api/papers/{id}/concepts` | Extract concepts with an LLM (replaces any previous set) |
| `GET` | `/api/papers/{id}/concepts` | Concepts extracted so far |
| `GET` | `/api/papers/{id}/concepts/{cid}` | One concept |
| `POST` | `/api/papers/{id}/concepts/{cid}/video` | Queue a build; `202` and a job, or `200` joining one already running |
| `GET` | `/api/papers/{id}/concepts/{cid}/video` | Stream the rendered mp4 |
| `GET` | `/api/jobs` | Jobs in this process, newest first |
| `GET` | `/api/jobs/{job_id}` | Job status, stage and event history |
| `GET` | `/api/jobs/{job_id}/events` | Live progress as server-sent events |
| `GET` | `/health` | Liveness check |

Failures map deliberately: no API key → `503`, upstream refusal → `502`, render
timeout → `504`, readable PDF that yields nothing → `422`.

## Roadmap

- [x] **1 — Ingestion.** Upload, validate, extract text. No AI.
- [x] **2 — Concepts.** An LLM pulls the core ideas out of the paper, using
      structured output rather than parsing prose.
- [x] **3 — First render.** A hand-written Manim scene, rendered by the backend
      and served as an mp4.
- [x] **4 — Generated animation.** The LLM writes the Manim code; failed renders
      feed their own stderr back in for a correction pass.
- [x] **5 — Narration.** Concepts split into scenes; each is narrated, measured,
      animated to that measured length, muxed and concatenated.
- [x] **6 — Concurrency and progress.** Builds run off the request path, scenes
      render in parallel under a global cap, progress streams over SSE.
      *In-process, single worker* — see Design notes.
- [x] **7 — Frontend.** Next.js: upload, browse concepts, build with live
      progress, watch clips inline.
- [ ] **8 — Persistence and deploy.** Postgres behind `PaperStore`, and a single
      `docker compose up` that brings the whole thing up. The compose file in
      the repo root is a milestone-1 stub and does not yet do this.

## Design notes

**Input and storage**

- **Uploads are validated by their bytes, not their headers.** The `%PDF-` magic
  number is checked; the client-supplied `Content-Type` is ignored, because a
  client can claim anything.
- **PDF parsing runs off the event loop.** `pdfplumber` is synchronous and
  CPU-bound, so extraction goes through `asyncio.to_thread`. `async def` on the
  signature buys nothing if the body blocks.
- **Empty pages are kept, not dropped.** A scanned or figure-only page yields an
  empty string, so page numbers always match the source document.
- **Storage sits behind one interface.** `PaperStore` is in-memory today and
  loses everything on restart — a deliberate shortcut, and confining it to one
  class is what makes milestone 8 a swap rather than a rewrite.

**Talking to the model**

- **The model is constrained, not asked nicely.** `response_schema` makes the SDK
  decode straight into a pydantic model, so there is no "reply in JSON"
  instruction anywhere, no markdown fence to strip, and no regex to recover from
  a chatty answer.
- **A schema guarantees shape, not sense.** The model can still cite page 99 of a
  12-page paper or list a concept as its own prerequisite, so
  `services/concepts.py` validates meaning after the SDK has validated form.
- **The LLM sits behind one method.** `LLMClient.structured(prompt, schema)` is
  the entire provider interface; prompts live with the feature that owns them.
- **Retrying is not free when the quota counts requests.** Each model gets one
  retry, then the client moves to the next model — a generous retry policy spends
  the day's budget on a queue that is not moving.

**Generating and rendering**

- **Rendering happens in a container, from the first render.** `--network none`,
  a memory ceiling and a CPU quota, with a test asserting those flags. Milestone
  3's code was ours and harmless; milestone 4's is written by a model, and by
  then the sandbox already existed.
- **Concept text enters generated Python as a literal, never an expression.**
  `repr()`, not interpolation — so a concept named `"); import os` is inert data.
- **Static checks are a feedback loop, not a defence.** `compile()` plus an AST
  pass rejects unrenderable code in microseconds instead of paying for a
  container start. The container is what makes bad code *safe*; the AST pass only
  makes failure *fast*.
- **The error message is the correction prompt.** `RenderError` carries stderr
  precisely so the next attempt can be "here is your code, here is what it did".
  Correction runs at a lower temperature than generation.
- **Infrastructure failure is not the model's fault.** A Docker error raises
  `RenderUnavailable` and stops the loop, instead of spending model calls asking
  the model to fix a bad mount.
- **Failure degrades instead of erroring.** When every attempt fails, a
  hand-written card renders instead and the response says `generated: false`. On
  its first contact with reality that was the only thing that worked: the
  provider refused every generation request and 6/6 concepts still returned a
  playable video.

**Narration**

- **The narrator is local.** Kokoro by default, Piper as a lighter option. The
  scarce resource is model requests per day, and spending them on a voice would
  be a bad trade. Local is also deterministic — the same text gives the same
  audio, which a hosted API never does.
- **Narration is synthesised before the animation is written.** The reverse order
  produced 5.3s of video under 13.7s of speech, which meant holding a dead frame
  for eight seconds. Padding is the safety net, not the plan.
- **Pacing is a setting, and the text is a bigger one.** Sentence pauses and
  delivery speed are configurable, but asking the model for short single-idea
  sentences did more for smoothness than any parameter — a synthesised voice
  breathes at punctuation and nowhere else.

**Jobs and the API boundary**

- **Builds do not block the request.** A build is a split call plus up to three
  model calls and container starts *per scene* — minutes, on a connection no
  proxy would hold open.
- **The job registry is in-process, deliberately.** A restart loses jobs and a
  second worker would not see them. Redis plus a worker process is real
  infrastructure and milestone 8 rewrites persistence anyway; the swap is one
  class behind `JobRegistry`.
- **SSE, not a WebSocket.** Progress is one-way, needs no protocol upgrade, and
  browsers reconnect it for free. The stream replays a job's recorded events
  before live ones, so a late subscriber still sees the whole build.
- **Diagnostics stop at the API boundary.** Scene reports carry attempt
  *outcomes*; the detail behind them is distilled renderer stderr, written for
  the model and the server log, never for an HTTP client.

**Frontend**

- **Everything runs in the browser, on purpose.** The backend is local, already
  allows the origin, and the progress stream is an `EventSource` — which only
  exists in a browser.
- **Progress shows the stage, not a percentage.** The stages differ in length by
  an order of magnitude; "animating scene 2 of 3" says more than a bar stuck
  at 40%.
- **One shader, several looks.** The landing background is ~150 lines of GLSL on
  a single quad, with five variants behind `?bg=`. One still frame under
  `prefers-reduced-motion`, paused while the tab is hidden.

**Testing**

- **Tests never touch the network.** `StubLLM`, `StubRenderer`, `StubSpeech` and
  `StubMedia` are scripted per test, so the suite runs offline with no key and no
  Docker.
- **But a stub also replaces the check that the real thing can be built.** 105
  tests once passed over a `deps.py` reading five settings that did not exist.
  `tests/test_deps.py` now constructs every provider from real `Settings`.
- **Tests exist from commit one**, including a hand-rolled PDF writer in
  `tests/pdf_fixture.py` so the suite needs no binary fixtures.

## Note

Not affiliated with 3blue1brown or Grant Sanderson. Manim is a
community-maintained project; "3blue1brown-style" describes the visual idiom,
nothing more.

## License

MIT — see [LICENSE](LICENSE).
