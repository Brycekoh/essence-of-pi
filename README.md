# Essence of Pi

Research papers, distilled into 3blue1brown-style explainers.

Upload a paper, get back the handful of ideas that actually matter, and turn any
of them into a short narrated animation.

> **Status: complete — all eight milestones done.** `docker compose up --build`
> brings up the whole thing, and papers, concepts and videos survive restarts.
> This is a learning build, in public, one milestone per commit;
> [LEARNING.md](LEARNING.md) is the running log, mistakes included.

**Contents** —
[Demo](#demo) ·
[How it works](#how-it-works) ·
[Tech stack](#tech-stack) ·
[Prerequisites](#prerequisites) ·
[Run it](#run-it) ·
[Configuration](#configuration) ·
[Free tier](#free-tier-reality-check) ·
[API](#api) ·
[Project structure](#project-structure) ·
[Troubleshooting](#troubleshooting) ·
[Known limitations](#known-limitations) ·
[Roadmap](#roadmap) ·
[Design notes](#design-notes)

## Demo

<div align="center">
  <a href="media/demo.mp4">
    <img src="media/demo.gif" alt="Internal Covariate Shift, generated from the Batch Normalization paper" width="640">
  </a>
  <br>
  <em><a href="media/demo.mp4">▶ Watch with sound</a> — the GIF is silent, and half the point is the narration.</em>
</div>

Generated from [Batch Normalization](https://arxiv.org/abs/1502.03167) (11 pages)
with no human input beyond dropping the PDF in: the model chose the concept,
split it into three scenes, wrote the narration, wrote the Manim, and all three
scenes rendered on the first attempt. 38 seconds of video, 110 seconds to build.

### The app

<p align="center">
  <img src="media/app-landing.png" alt="The landing page: a glowing ring behind the upload panel" width="49%">
  <img src="media/app-paper.png" alt="A paper's concepts, with a built video playing inline" width="49%">
</p>

Drop a PDF on the landing page, extract its concepts, and press **Build video** on
any of them. Progress streams in stage by stage, and the finished video plays
inline.

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
streams to the browser over server-sent events. Papers, pages and concepts live
in Postgres; PDFs and videos live in a Docker volume.

**159 tests**, including one suite run against three storage implementations.

## Tech stack

| Layer | What |
| --- | --- |
| Backend | Python, FastAPI, pydantic, SQLAlchemy 2, Alembic, pdfplumber |
| Database | Postgres 17 (in-memory store when no database is configured) |
| Model | Google Gemini on the free tier, via structured output |
| Animation | Manim Community 0.21 with LaTeX, in a Docker sandbox |
| Narration | Kokoro by default; Piper and gTTS as alternatives |
| Media | ffmpeg, in the same sandbox |
| Frontend | Next.js 16, React 19, Tailwind CSS 4, hand-written WebGL |
| Deployment | Docker Compose, on your own machine |

## Prerequisites

- **Docker Desktop**, or Docker Engine **26 or later** with Compose **2.24 or
  later**. The sandbox mounts need `volume-subpath` (Engine 26); the optional
  `.env` file needs Compose 2.24.
- **About 10 GB of free disk** for images. Build cache can take more;
  `docker builder prune` reclaims it.
- **A free Gemini API key** from [AI Studio](https://aistudio.google.com/apikey).
- For development on the host only: **Python 3.12+** and **Node.js 20.9+**.

## Run it

### With docker compose

```bash
cp backend/.env.example backend/.env    # then set GEMINI_API_KEY in it
docker compose up --build
```

Then open <http://localhost:3000>.

The first build takes a while — the render and narration images are ~3 GB each.
After that `docker compose up` starts in seconds, in dependency order: Postgres
becomes healthy, migrations run and exit, both sandbox images are confirmed, and
only then do the backend and frontend start.

Your data lives in two volumes. `docker compose down` keeps them;
`docker compose down -v` deletes every paper and video.

> **Security, stated plainly.** The backend mounts the Docker socket so it can
> start render containers, which gives it root-equivalent control of Docker on
> your machine. The containers it starts are still sandboxed — no network,
> capped memory and CPU, each seeing only its own scratch directory — but the
> backend itself is trusted. Fine on your own machine. Don't expose port 8000 to
> a network you don't control.

### On the host, for development

**1. Build the two sandbox images once.** Everything that renders, narrates or
muxes runs in a container; nothing is installed on the host.

```bash
cd backend
docker pull manimcommunity/manim:stable
docker build -f Dockerfile.render -t essence-of-pi/render:latest .
docker build -f Dockerfile.kokoro -t essence-of-pi/tts:kokoro .
```

- **`essence-of-pi/render`** adds ffmpeg and a Piper voice to the manim image.
  The upstream image has no ffmpeg *binary* — manim 0.21 renders through PyAV's
  bundled libav — so narration could not be muxed on it.
- **`essence-of-pi/tts:kokoro`** is the default narrator. It needs torch and
  manim does not, so it is a separate image. `SPEECH_ENGINE=piper` skips it.

**2. Backend.** On Windows PowerShell, call the venv's executables directly —
`&&` is not a statement separator in PowerShell 5.1, and activation can trip the
execution policy:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

macOS / Linux:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Without `DATABASE_URL` the backend uses an in-memory store — no setup, and a
restart forgets everything. To persist, point it at Postgres and create the
schema once:

```bash
export DATABASE_URL=postgresql+psycopg://eop:eop@localhost:5432/essence_of_pi
alembic upgrade head
```

**Run a single worker** either way: jobs live in the process's memory.

**3. Frontend.**

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend && pytest
```

On Windows: `.\.venv\Scripts\pytest.exe`. The storage contract suite and the
migration tests also run against a real Postgres when one is listening on
`TEST_DATABASE_URL` (default `localhost:55432`), and skip that leg otherwise:

```bash
docker run -d --name eop-pg-test -e POSTGRES_USER=eop -e POSTGRES_PASSWORD=eop \
  -e POSTGRES_DB=eop_test -p 55432:5432 postgres:17-alpine
```

A few tests run manim, ffmpeg and Kokoro for real, and skip themselves when
Docker or an image is missing.

### Measuring the generation loop

How often the model's first attempt renders is the number that says whether
generation works:

```bash
cd backend
.venv/Scripts/python.exe scripts/measure_generation.py path/to/paper.pdf --concepts 2
```

## Configuration

The backend reads environment variables, or `backend/.env`.
[`backend/.env.example`](backend/.env.example) lists every setting with its
default; only `GEMINI_API_KEY` is required. The ones you are most likely to want:

| Variable | Default | What it does |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | Required for concepts and videos. Without it those routes return `503`. |
| `MAX_SCENES` | `3` | Scenes per concept — the main lever on quota use |
| `MAX_CONCEPTS` | `6` | Concepts extracted per paper |
| `RENDER_QUALITY` | `-qm` | `-ql` 480p and fast, `-qm` 720p, `-qh` 1080p and slow |
| `MAX_PARALLEL_RENDERS` | `2` | Scenes rendering at once, across every job |
| `SPEECH_ENGINE` | `kokoro` | `kokoro`, `piper` (lighter), or `gtts` (needs network) |
| `KOKORO_VOICE` | `af_bella` | Also `af_heart`, `af_nicole`, `am_michael`, `am_adam`, `bf_emma` |
| `KOKORO_SPEED` | `0.92` | Below 1.0 is slower |
| `LLM_MODEL` | `gemini-3.8-flash` | Pinned rather than an alias, so results are comparable |
| `LLM_FALLBACK_MODELS` | `gemini-3.7-flash,…` | Tried in order when a model is busy or out of quota |
| `DATABASE_URL` | unset | Unset means in-memory. Compose sets it for you. |
| `MAX_UPLOAD_BYTES` | `26214400` | 25 MB |

The frontend has one setting, `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`). It is baked into the bundle at build time, so changing
it means rebuilding the frontend.

## Free-tier reality check

Gemini's free tier allows **20 requests per day, per model**. Concept extraction
costs one; a video costs one to three *per scene*. The client rotates through
`LLM_FALLBACK_MODELS` rather than retrying one model, since the quota is
per-model, and remembers which models returned `429`. In practice that is
roughly ten to twenty videos a day.

Narration, rendering and storage cost nothing — they are local.

## API

Interactive docs at <http://localhost:8000/docs>.

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

## Project structure

```
essence-of-pi/
├── backend/            FastAPI app, Alembic migrations, tests, three Dockerfiles
├── frontend/           Next.js app and its Dockerfile
├── media/              demo clip and screenshots for this README
├── docker-compose.yml  the whole stack
├── ARCHITECTURE.md     how the pieces fit, with diagrams
└── LEARNING.md         the milestone-by-milestone log
```

[ARCHITECTURE.md](ARCHITECTURE.md) has the full backend layout, the request path
for a video build, and a table of every seam and its implementations.

## Troubleshooting

**Every video fails, or the API says the Docker daemon is not running.** Start
Docker Desktop and confirm with `docker info`. Rendering, narration and muxing
all need it.

**Docker Desktop won't start, mentioning `dockerInference`.** Its Model Runner
failed to bind a socket. Turn off *Docker Model Runner* under Settings → AI, or
run `wsl --shutdown`, delete `%LOCALAPPDATA%\Docker\run`, and start it again.

**Concept extraction returns `503`.** `GEMINI_API_KEY` isn't set. Add it to
`backend/.env`, then recreate the backend so it picks the file up:
`docker compose up -d --force-recreate backend`.

**"No model answered", or `429` errors.** The free tier's daily quota is spent
on every model in the rotation. It resets daily (around midnight Pacific), or add
more models to `LLM_FALLBACK_MODELS`.

**The paper list is empty after a restart.** You're running on the host without
`DATABASE_URL`, so the backend used the in-memory store. Set it and run
`alembic upgrade head`. Under compose this can't happen.

**`Permission denied: '/work/media'` in the backend logs.** An older backend
image predates the scratch-directory fix. Rebuild: `docker compose up -d --build`.

**A port is already in use.** Something else holds 3000 or 8000 — often the
development servers. Stop them, or change the published ports in
`docker-compose.yml`.

**The frontend still calls an old API address.** `NEXT_PUBLIC_API_URL` is inlined
at build time. Rebuild it: `docker compose up -d --build frontend`.

**PowerShell reports a parse error on `&&`.** Windows PowerShell 5.1 has no `&&`.
Run the commands separately, or join them with `;`.

## Known limitations

- **Single user, no authentication.** It's a personal tool; don't expose it.
- **Builds in flight don't survive a restart.** The job registry lives in
  memory. Finished videos are safe in Postgres and the storage volume.
- **The correction loop only sees crashes.** A scene that renders cleanly but
  looks wrong — overlapping text, say — passes. Catching that would need
  something to look at the frames.
- **Long papers are truncated.** Extraction reads the first 30,000 characters,
  and says so in its response.
- **No OCR.** Scanned or image-only pages extract as empty text.
- **English only**, for both the prompts and the voices.
- **Free-tier throughput.** Roughly ten to twenty videos a day.

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
- [x] **7 — Frontend.** Next.js: upload, browse concepts, build with live
      progress, watch clips inline.
- [x] **8 — Persistence and deploy.** Postgres behind `PaperStore` with Alembic
      migrations, and one `docker compose up` for the whole stack. "Deploy"
      means your own machine, deliberately.

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

**Persistence and deployment**

- **The seam held.** Milestone 1 put every storage call behind `PaperStore` and
  promised that swapping in Postgres would change no router. It changed none.
- **The interface stayed synchronous, on purpose.** Moving pdfplumber off the
  event loop was about work that blocked for seconds. These are single-row
  lookups that take well under a millisecond against a local database.
- **One suite, three stores.** `tests/test_store_contract.py` runs identical
  tests against the in-memory store, SQLite and a real Postgres. On its first
  run it caught a bug in the *in-memory* store — pages came back in insertion
  order, and had since milestone 1.
- **Order is stored, not assumed.** Concepts are ordered so prerequisites come
  first. A table has no order, so there is a `position` column, and its test
  performs an `UPDATE` first — which moves a row to the end of a Postgres heap,
  so a missing `ORDER BY` fails rather than passing by coincidence.
- **Migrations are held to the code.** A test runs `alembic upgrade head` on an
  empty database and asks Alembic's autogenerate to diff the result against the
  code; the only passing answer is an empty diff.
- **A containerised backend cannot bind-mount its own paths.** Under compose,
  the paths the backend knows are inside *its* container, which the Docker
  daemon cannot see. Storage is a named volume, and each sandbox mounts only its
  own scratch directory with `volume-subpath`.
- **Widen the directory, never raise the sandbox's privileges.** The render
  image runs as uid 1000 and the backend as root, so a root-owned scratch
  directory was read-only to manim. The tempting fix was running render
  containers as root — that would run model-written code as root to dodge a
  `chmod`.

**Talking to the model**

- **The model is constrained, not asked nicely.** `response_schema` makes the SDK
  decode straight into a pydantic model — no "reply in JSON" instruction, no
  markdown fence to strip, no regex to recover from a chatty answer.
- **A schema guarantees shape, not sense.** The model can still cite page 99 of a
  12-page paper, so `services/concepts.py` validates meaning after the SDK has
  validated form.
- **The LLM sits behind one method.** `LLMClient.structured(prompt, schema)` is
  the entire provider interface; prompts live with the feature that owns them.
- **Retrying is not free when the quota counts requests.** Each model gets one
  retry, then the client moves to the next model.

**Generating and rendering**

- **Rendering happens in a container, from the first render.** `--network none`,
  a memory ceiling and a CPU quota, with a test asserting those flags.
- **Concept text enters generated Python as a literal, never an expression.**
  `repr()`, not interpolation — so a concept named `"); import os` is inert data.
- **Static checks are a feedback loop, not a defence.** An AST pass rejects
  unrenderable code in microseconds; the container is what makes bad code
  *safe*.
- **The error message is the correction prompt.** `RenderError` carries stderr
  so the next attempt can be "here is your code, here is what it did".
- **Infrastructure failure is not the model's fault.** A Docker error raises
  `RenderUnavailable` and stops the loop, instead of spending model calls on a
  bad mount.
- **Failure degrades instead of erroring.** When every attempt fails, a
  hand-written card renders and the response says `generated: false`.

**Narration**

- **The narrator is local.** Model requests are the scarce resource, and
  spending them on a voice would be a bad trade. Local is also deterministic.
- **Narration is synthesised before the animation is written.** The reverse order
  produced 5.3s of video under 13.7s of speech.
- **Pacing is a setting, and the text is a bigger one.** Short single-idea
  sentences did more for smoothness than any parameter — a synthesised voice
  breathes at punctuation and nowhere else.

**Jobs and the API boundary**

- **Builds do not block the request.** A build is minutes of model calls and
  container starts, on a connection no proxy would hold open.
- **SSE, not a WebSocket.** Progress is one-way, needs no protocol upgrade, and
  browsers reconnect it for free. The stream replays history before live events.
- **Diagnostics stop at the API boundary.** Clients see attempt *outcomes*; the
  renderer stderr behind them is for the model and the server log.

**Frontend**

- **Everything runs in the browser, on purpose.** The backend is local, allows
  the origin, and the progress stream is an `EventSource`.
- **Progress shows the stage, not a percentage.** Stages differ in length by an
  order of magnitude.
- **Reduced motion means no waiting either.** Under `prefers-reduced-motion`,
  animations are cut short *and* their delays cancelled, so content appears at
  once instead of after a staggered entrance.

**Testing**

- **Tests never touch the network.** Every external collaborator has a scripted
  stub, so the suite runs offline with no key.
- **But a stub also replaces the check that the real thing can be built.**
  `tests/test_deps.py` constructs every provider from real `Settings`.
- **Tests exist from commit one**, including a hand-rolled PDF writer so the
  suite needs no binary fixtures.

## Note

Not affiliated with 3blue1brown or Grant Sanderson. Manim is a
community-maintained project; "3blue1brown-style" describes the visual idiom,
nothing more.

## License

MIT — see [LICENSE](LICENSE).
