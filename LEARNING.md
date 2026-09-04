# Learning log

Why this repo exists: to rebuild a paper→animation pipeline from scratch,
one working milestone at a time, and understand every layer rather than
inherit it. Each entry records what got built, what surprised me, and what I
chose to do differently from the project that inspired it.

---

## Milestone 1 — Ingestion

**Built:** FastAPI service that accepts a PDF, validates it, extracts text
per page with pdfplumber, and exposes it over a small JSON API. Ten tests.

**Things I learned**

- `pdfplumber` is fully synchronous. An `async def` endpoint that calls it
  directly still blocks the event loop for the whole parse — `async` on the
  signature buys nothing if the body is CPU-bound. `asyncio.to_thread` moves
  it to a worker thread and keeps the server responsive.
- Content-type headers on uploads are client-supplied and worthless for
  validation. The first five bytes of the file (`%PDF-`) are not.
- FastAPI's `dependency_overrides` makes tests isolated without monkeypatching
  module globals — each test gets a fresh store and a temp upload directory.
- A valid PDF is a short, readable format: a handful of objects, a
  cross-reference table of byte offsets, and a trailer. `tests/pdf_fixture.py`
  writes one by hand, which was faster than adding a PDF-generation dependency
  and taught me more.

**Open questions for later**

- Scanned PDFs extract as empty pages. OCR fallback, or refuse them politely?
- Two-column academic layouts confuse naive text extraction — does reading
  order actually survive pdfplumber, or does milestone 2 need layout-aware
  extraction to get usable input?
- The in-memory store dies on restart. Fine now, breaks the moment renders
  take minutes.

**Deliberate divergences from the reference project**

- Tests from the first commit. The original has none.
- Magic-byte validation and an explicit size limit before parsing.
- Extraction off the event loop.
- Storage behind a single interface instead of module-level dicts plus JSON
  files plus a database, three ways at once.

---

## Milestone 2 — Concepts

**Built:** an LLM layer with one method, a concept-extraction service that owns
the prompt, and three endpoints. Fifteen new tests, none of which touch the
network.

**Things I learned**

- **Structured output is a decoding constraint, not a prompt.** Passing
  `response_schema=ConceptExtraction` to the google-genai SDK makes it decode
  into that pydantic model directly — `response.parsed` is the instance. There
  is no "reply only in JSON" line in any prompt in this repo, and nothing
  strips markdown fences. The reference project spends several hundred lines of
  regex recovering from malformed model output; that entire failure mode is
  designed out rather than patched.
- **But a schema constrains form, not meaning.** The model still cited a page
  that did not exist and listed a concept as its own prerequisite. `_clean()`
  fixes exactly those, and there is a test for each. Validating twice — the SDK
  for shape, me for sense — is the actual lesson.
- **Field descriptions are prompt.** The model reads the `Field(description=...)`
  text on the response schema, so `visual_hint`'s description is doing as much
  work as the prompt template is.
- **Retry only what retrying can fix.** `ServerError` gets exponential backoff
  with jitter; a malformed request or a bad key fails identically every time,
  so it raises immediately.
- **`store.list()` shadowed the builtin.** A method named `list` in a class body
  means a later `list[Concept]` annotation in that same class resolves to the
  method — `TypeError: 'function' object is not subscriptable` at import time.
  Renamed to `list_papers`.
- **A protocol plus a stub beats mocking.** `LLMClient` is a `Protocol`, so
  `StubLLM` implements it without inheriting anything, and tests assert on the
  prompt that was actually built.

**Open questions for later**

- Truncation at 60k chars is crude. Papers put their contribution in the
  abstract and their mechanism in the middle; a section-aware selection would
  probably beat "first 60k characters".
- Nothing measures extraction quality yet. A golden set of five papers with
  expected concepts would turn "looks good" into a number.
- Re-extraction silently replaces the previous set and costs another call.
  Caching on a hash of (text, model, prompt version) would make re-runs free.
- `visual_hint` is a guess at what milestone 4 will need. It may be the wrong
  shape entirely, and I will not know until the renderer exists.

**Deliberate divergences from the reference project**

- Structured output instead of prose parsing.
- One provider-agnostic method instead of a Gemini-specific service class.
- Concepts carry `source_pages`, so every claim is traceable to a page.
- Upstream failure returns 502, not 500 — we are the client of a service that
  let us down, and the status code should say so.

---

## Milestone 3 — First render *(next)*

**Plan:** a hand-written Manim scene, rendered by the backend as a subprocess,
served as an mp4. No LLM involved — the point is to learn the render pipeline
and its failure modes before adding a model that writes the code.

**To find out:** how slow a render actually is, what manim needs installed
(LaTeX is the painful one), and whether this has to move off the request path
immediately or can wait for milestone 6.
