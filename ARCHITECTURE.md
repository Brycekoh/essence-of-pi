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
                        │  concepts     │   ← milestone 2
                        │  LLM, struct- │
                        │  ured output  │
                        └───────┬───────┘
                                │ concept
                        ┌───────▼───────┐
                        │  scene split  │   ← milestone 4
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

## Milestone 1, as built

```
backend/
├── app/
│   ├── main.py              FastAPI app, CORS, router wiring
│   ├── config.py            pydantic-settings; one cached Settings instance
│   ├── api/papers.py        the six paper routes
│   ├── models/paper.py      Paper, PageText, PaperText — the wire contract
│   └── services/
│       ├── pdf_parser.py    pdfplumber, run off the event loop
│       └── store.py         PaperStore — the seam Postgres slots into later
└── tests/
    ├── pdf_fixture.py       hand-written PDF generator, no binary fixtures
    └── test_papers.py       ten tests over the whole API surface
```

**Request path for an upload**

1. `POST /api/papers` receives the file into memory.
2. Reject empty → 400. Over the size limit → 413. Missing `%PDF-` → 415.
3. Write the bytes to `storage/uploads/{uuid}.pdf`.
4. `extract_pages()` hands pdfplumber to a worker thread; a parse failure
   deletes the orphaned file and returns 422.
5. Build a `Paper`, store it alongside its pages, return 201.

**The one load-bearing seam:** everything that touches persistence goes
through `PaperStore`. Swapping it for Postgres in milestone 8 should not
require editing `api/papers.py`. If it does, the abstraction leaked.
