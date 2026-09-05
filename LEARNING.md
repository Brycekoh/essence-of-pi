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

## Milestone 3 — First render

**Built:** a `Renderer` seam, a Docker-backed manim renderer, a hand-written
scene template, and two endpoints. Twelve new tests, one of which renders for
real and skips itself when Docker is absent.

**Verified:** h264, 854x480, 15fps, 5.33s, 80 frames, 77 KB, rendered in 4.6s
at `-ql` inside a container with no network.

**Things I learned**

- **The toolchain problem answered the security question.** There is no manim,
  ffmpeg or LaTeX on this machine and installing them on Windows is grim, so
  rendering went into a container. That accidentally solved milestone 4's real
  problem: model-written Python now has a `--network none`, memory-capped,
  CPU-quotaed box to run in, and it exists before any model writes a line.
- **Killing `docker run` does not kill the container.** The daemon owns it. A
  timeout has to `docker kill` by name, which is why every container gets one.
- **`repr()`, not `json.dumps()`, for embedding text in generated Python.**
  JSON escapes astral-plane characters as UTF-16 surrogate pairs, so an emoji
  round-trips into Python as two lone surrogates rather than the character. A
  test caught this; I would not have.
- **Manim 0.19 ships no ffmpeg CLI.** It uses PyAV's bundled libav instead, so
  `ffmpeg`/`ffprobe` are simply not in the image. Milestone 5 muxes audio and
  cannot assume the CLI is there — either use PyAV or add ffmpeg to a derived
  image.
- **The image's PATH is not a login shell's PATH.** `docker run img sh -lc
  "manim --version"` reports "not found" because `/etc/profile` resets PATH and
  drops `/opt/venv/bin`. The direct invocation works fine. A probe that fails
  is not proof the thing is missing.
- **Rendering is fast at low quality and not at high.** 4.6s at `-ql` (480p15)
  versus minutes at `-qh`. Blocking the request is survivable today and will
  not be at milestone 5's clip counts.
- **`Text`, not `MathTex`.** Pango accepts any string; LaTeX falls over on the
  stray `%`, `&`, `_` and `$` that paper titles are full of.

**Open questions for later**

- Renders block the request. Fine for one 5-second card, untenable for a
  multi-scene video. This is the whole of milestone 6.
- Nothing caches. Re-rendering an unchanged concept costs a full container run;
  a content hash would make it free.
- The container mounts a host directory read-write. Milestone 4 should probably
  tighten that to a read-only source mount plus a separate output volume.

**Deliberate divergences from the reference project**

- Renders are sandboxed. The reference executes model-written Python directly
  on the host.
- The render path is a seam with a stub, so the API is testable without a
  2 GB image.
- Render failures map to 502/504 and the stderr is deliberately not returned to
  the client — it names host paths. From milestone 4 it becomes the model's
  correction prompt instead.

---

## Milestone 4 — Generated animation *(next)*

**Plan:** replace `build_scene()` with an LLM call, and add the correction
loop: render, and on failure feed the captured stderr back to the model as the
next prompt, up to N attempts. The seam is already in place — `RenderError`
carries `stderr` precisely for this.

**To find out:** how often the first attempt renders at all, whether the error
text is actually useful to the model, and whether constraining generation to a
small set of my own primitives beats letting it write raw Manim.
