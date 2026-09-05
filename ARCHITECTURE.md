# Architecture

The shape of the finished system, and how much of it exists so far.

```
                        ┌───────────────┐
   PDF ──upload──▶      │  ingestion    │   ← milestone 1 (DONE)
                        │  validate     │
                        │  extract text │
                        └───────┬───────┘
                                │ text
                        ┌───────▼───────┐
                        │  concepts     │   ← milestone 2 (DONE)
                        │  LLM, struct- │
                        │  ured output  │
                        └───────┬───────┘
                                │ concept
                        ┌───────▼───────┐
                        │  animation    │   ← milestone 4 (DONE)
                        └───────┬───────┘
                                │ scenes
              ┌─────────────────┼─────────────────┐
              │                 │                 │
      ┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐
      │ generate     │  │ narrate      │  │ ...          │  ← milestone 5
      │ Manim code   │  │ (TTS)        │  │              │
      │      │       │  └───────┬──────┘  └──────────────┘
      │   render     │          │
      │      │       │          │
      │  fail? feed  │          │
      │  stderr back │          │
      │  and retry   │          │
      └───────┬──────┘          │
              └────────┬────────┘
                       │ mux + concat (ffmpeg)
               ┌───────▼───────┐
               │  final video  │   ← milestone 6 adds queue + progress
               └───────┬───────┘
                       │
               ┌───────▼───────┐
               │  Next.js UI   │   ← milestone 7
               └───────────────┘
```

## Milestones 1-4, as built

```
backend/
├── app/
│   ├── main.py              FastAPI app, CORS, router wiring
│   ├── config.py            pydantic-settings; one cached Settings instance
│   ├── api/
│   │   ├── papers.py        the six paper routes
│   │   ├── concepts.py      extract / list / read concepts
│   │   └── videos.py        render a concept, stream the mp4
│   ├── models/
│   │   ├── paper.py         Paper, PageText, PaperText
│   │   └── concept.py       ConceptDraft (the LLM's schema) vs Concept (stored)
│   └── services/
│       ├── pdf_parser.py    pdfplumber, run off the event loop
│       ├── concepts.py      owns the prompt and the post-validation
│       ├── store.py         PaperStore — the seam Postgres slots into later
│       ├── animation.py  the generate-check-render-correct loop
│       ├── codecheck.py  AST checks: fast feedback, NOT the sandbox
│       ├── llm/
│       │   ├── base.py      LLMClient protocol — one method, `structured`
│       │   ├── gemini.py    response_schema + retry with backoff
│       │   └── stub.py      scripted double; tests never hit the network
│       └── render/
│           ├── base.py      Renderer protocol; RenderError carries stderr
│           ├── manim_docker.py  sandboxed container run, killed on timeout
│           └── stub.py      writes a placeholder mp4, no Docker needed
│   └── scenes/
│       └── title_card.py    the hand-written scene, replaced in milestone 4
└── tests/
    ├── pdf_fixture.py       hand-written PDF generator, no binary fixtures
    ├── test_papers.py       the ingestion API
    ├── test_concepts.py     the extraction API and service
    ├── test_llm_gemini.py   schema compatibility, config errors, caching
    ├── test_video.py        render API, scene generation, sandbox flags
    └── test_animation.py    the correction loop and the static checks
```

**Request path for an upload**

1. `POST /api/papers` receives the file into memory.
2. Reject empty → 400. Over the size limit → 413. Missing `%PDF-` → 415.
3. Write the bytes to `storage/uploads/{uuid}.pdf`.
4. `extract_pages()` hands pdfplumber to a worker thread; a parse failure
   deletes the orphaned file and returns 422.
5. Build a `Paper`, store it alongside its pages, return 201.

**Request path for a concept extraction**

1. `POST /api/papers/{id}/concepts` resolves the paper and its pages, or 404s.
2. `build_document()` joins non-blank pages with `[page N]` markers up to a
   character budget, reporting whether it had to truncate.
3. `LLMClient.structured(prompt, schema=ConceptExtraction)` — the SDK decodes
   directly into the pydantic model; transient server errors retry with
   backoff, bad requests do not.
4. `_clean()` drops out-of-range page citations, self-referential
   prerequisites, and duplicate names, then the list is trimmed to
   `max_concepts`.
5. Concepts get server-assigned ids, are stored against the paper, returned 201.

Failures map to status codes deliberately: no API key → 503, upstream failure →
502, readable PDF that yields nothing → 422.

**Request path for a render**

1. `POST .../concepts/{cid}/video` resolves the concept, or 404s.
2. `build_scene()` produces Manim source, embedding concept text via `repr()`
   so it can only ever be data.
3. The source is written to a scratch directory, which is bind-mounted into a
   container run with `--network none`, `--memory`, `--cpus` and a name.
4. On timeout the container is killed by name — killing the `docker run`
   client would leave it running.
5. The mp4 is located by glob (the resolution directory depends on the quality
   flag), moved to `storage/videos/{concept_id}.mp4`, and the URL is attached
   to the concept.

Failures map deliberately: render failure → 502, timeout → 504, daemon down →
502 with instructions. Captured stderr is never returned to the client; it
names host paths, and from milestone 4 it becomes the correction prompt.

**The correction loop (milestone 4)**

```
   ask the model for a scene  ──▶  compile() + AST check  ──▶  render in Docker
             ▲                            │                          │
             │                            │ rejected                 │ failed
             └──── distilled error ◀──────┴──────────────────────────┘
                    (max 3 attempts, then the milestone-3 card)
```

The static check exists to fail in microseconds instead of seconds; the
container exists to fail *safely*. They are not the same mechanism and the code
says so.

**The three load-bearing seams**

- `PaperStore` — everything touching persistence goes through it. Swapping it
  for Postgres in milestone 8 should not require editing any router.
- `LLMClient` — one method, `structured(prompt, schema) -> schema`. Every later
  model call (scene splitting, Manim generation, narration) is that same shape,
  so the provider stays swappable and every test stays offline.
- `Renderer` — one method, `render(code, scene_name, destination, timeout)`.
  Milestone 3 feeds it code we wrote; milestone 4 feeds it code a model wrote.
  Nothing else changes, which is the point of building it now.
