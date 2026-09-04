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

## Milestones 1-2, as built

```
backend/
├── app/
│   ├── main.py              FastAPI app, CORS, router wiring
│   ├── config.py            pydantic-settings; one cached Settings instance
│   ├── api/
│   │   ├── papers.py        the six paper routes
│   │   └── concepts.py      extract / list / read concepts
│   ├── models/
│   │   ├── paper.py         Paper, PageText, PaperText
│   │   └── concept.py       ConceptDraft (the LLM's schema) vs Concept (stored)
│   └── services/
│       ├── pdf_parser.py    pdfplumber, run off the event loop
│       ├── concepts.py      owns the prompt and the post-validation
│       ├── store.py         PaperStore — the seam Postgres slots into later
│       └── llm/
│           ├── base.py      LLMClient protocol — one method, `structured`
│           ├── gemini.py    response_schema + retry with backoff
│           └── stub.py      scripted double; tests never hit the network
└── tests/
    ├── pdf_fixture.py       hand-written PDF generator, no binary fixtures
    ├── test_papers.py       the ingestion API
    ├── test_concepts.py     the extraction API and service
    └── test_llm_gemini.py   schema compatibility, config errors, caching
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

**The two load-bearing seams**

- `PaperStore` — everything touching persistence goes through it. Swapping it
  for Postgres in milestone 8 should not require editing any router.
- `LLMClient` — one method, `structured(prompt, schema) -> schema`. Every later
  model call (scene splitting, Manim generation, narration) is that same shape,
  so the provider stays swappable and every test stays offline.
