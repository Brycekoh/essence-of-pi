# Architecture

How Essence of Pi fits together, as of milestone 8. The *why* behind each
decision is in [README.md](README.md#design-notes) and, with the mistakes left
in, [LEARNING.md](LEARNING.md).

## The stack under docker compose

```
  browser ─────► frontend        Next.js production build          :3000
     │
     └─────────► backend         FastAPI, one worker               :8000
                    │    │
                    │    └─────► db            Postgres 17
                    │
                    │  /var/run/docker.sock
                    ▼
               host Docker daemon
                    │
                    ├─► essence-of-pi/render      manim, ffmpeg, Piper   uid 1000
                    └─► essence-of-pi/tts:kokoro  Kokoro                 root
                          sandboxes: --network none, capped memory and CPU,
                          each mounting only its own scratch directory
```

**Volumes.** `db` holds Postgres. `essence-of-pi-storage` is mounted into the
backend at `/data` and holds uploads, rendered videos and per-job scratch
directories.

**Startup order**, enforced by `depends_on`:

```
db healthy ──► migrate (alembic upgrade head) exits 0 ─┐
render-image exits 0 ──────────────────────────────────┼──► backend ──► frontend
tts-image exits 0 ─────────────────────────────────────┘
```

`render-image` and `tts-image` exist only so `docker compose up --build` builds
those images; the backend starts them itself with `docker run`.

## A video build, end to end

1. `POST /api/papers/{id}/concepts/{cid}/video` returns `202` with a job, or
   `200` with the job already running for that concept.
2. `JobRegistry` runs `build_explainer` as an asyncio task. Progress events fan
   out to any `GET /api/jobs/{id}/events` subscribers, which replay history
   first.
3. The model splits the concept into scenes.
4. Every scene's narration is synthesised concurrently, then **measured**.
5. Scenes animate in parallel under one global semaphore. For each: the model
   writes Manim to fit the measured length → AST check → render in a sandbox →
   on failure, the distilled stderr becomes the next prompt, up to three tries →
   title card if all fail.
6. Each clip is muxed with its narration, the clips are concatenated, and the mp4
   lands in the storage volume. `video_url` is written to Postgres.

## How a sandbox gets its files

| Where the backend runs | Mount | Why |
| --- | --- | --- |
| On the host | `-v <absolute path>:/work` | The path is the daemon's own |
| Under compose | `--mount type=volume,src=essence-of-pi-storage,dst=/work,volume-subpath=<scratch dir>` | The backend's paths are inside its container, invisible to the daemon |

`STORAGE_VOLUME` and `STORAGE_ROOT` select compose mode. A sandbox is refused a
mount of the whole volume, or of anything outside it. Scratch directories are
created `0o777` because the sandboxes do not share a uid with the backend.

## Backend layout

```
backend/
├── app/
│   ├── main.py, config.py
│   ├── api/            papers, concepts, videos, jobs, deps (every provider)
│   ├── models/         paper, concept, scene, job — the wire contract
│   ├── scenes/         title_card — the hand-written fallback scene
│   └── services/
│       ├── pdf_parser.py   pdfplumber, off the event loop
│       ├── concepts.py     extraction prompt and meaning checks
│       ├── explainer.py    split → narrate → measure → animate → mux → concat
│       ├── animation.py    generate → check → render → correct loop
│       ├── codecheck.py    AST checks: fast failure, not a defence
│       ├── jobs.py         in-process registry and SSE fan-out
│       ├── store.py        PaperStore protocol, in-memory implementation
│       ├── sql_store.py    Postgres implementation and table definitions
│       ├── container.py    sandbox argv, mounts, scratch dirs, timeouts
│       ├── llm/            Gemini client with model rotation; stub
│       ├── render/         manim in Docker; stub
│       ├── media/          ffmpeg in Docker; stub
│       └── speech/         Kokoro, Piper, gTTS; stub
├── alembic/            env.py, versions/0001_initial.py
├── scripts/            measure_generation.py
├── tests/              159 tests; contract suite runs on memory, SQLite, Postgres
├── Dockerfile          API server, with the docker CLI
├── Dockerfile.render   manim + LaTeX + ffmpeg + Piper
└── Dockerfile.kokoro   Kokoro on CPU-only torch
```

## The seams

Every collaborator that could plausibly change sits behind one small interface,
and every one has a stub so the suite runs offline.

| Seam | Contract | Implementations |
| --- | --- | --- |
| `PaperStore` | ten synchronous methods | in-memory, SQL (SQLite in tests, Postgres in compose) |
| `LLMClient` | `structured(prompt, schema)` | Gemini with model rotation, stub |
| `Renderer` | `render(code, scene_name, destination, timeout)` | manim in Docker, stub |
| `Speech` | `say(text, destination)` | Kokoro, Piper, gTTS, stub |
| `MediaTool` | `duration`, `mux`, `concat` | ffmpeg in Docker, stub |
| `JobRegistry` | create, submit, publish, subscribe | in-process only |

`JobRegistry` is the one still in memory: a restart loses a build in flight, but
not a finished video. It is the next seam to move into Postgres if that ever
matters.
