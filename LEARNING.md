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

## Milestone 4 — Generated animation

**Built:** the generate-check-render-correct loop, a static code checker, and a
degraded-but-not-failed fallback. Twenty new tests.

**Verified for real:** a deliberately broken scene rendered through the actual
container produced 3,455 characters of stderr, which distils to 1,341
characters ending on `AttributeError: Text object has no attribute 'nudge'`,
with a pointer at `/manim/scene.py:7`. That is genuinely fixable feedback. The
loop itself has still only been exercised against a scripted model -- there is
no API key on this machine.

**Things I learned**

- **Field order in a response schema is load-bearing.** `ManimScene` declares
  `plan` before `code`, and structured output is generated in declaration
  order, so the model commits to an approach in prose before it starts emitting
  Python. Putting `code` first means it starts typing before it has decided
  what it is animating.
- **The error text is the entire technique.** There is no clever prompt for
  "write correct Manim". There is a cheap loop that hands the model its own
  code and its own traceback. Everything hard is in making that traceback
  legible.
- **Rich-formatted tracebacks are mostly frame.** Manim's stderr is drawn in
  box characters around its own source. Stripping the decoration and leading
  with the final exception line cut the payload by 60% and guaranteed that the
  one useful line survives truncation. I only knew to do this because I ran a
  real failure and looked at the bytes.
- **Correct colder than you generate.** First attempt at 0.6, corrections at
  0.1. A fix should be conservative; a first draft can be creative.
- **Static checks are a feedback loop, not a security boundary.** `compile()`
  plus an AST pass rejects unrenderable code in microseconds rather than paying
  a container start. Any source-reading check can be evaded, which is precisely
  why the sandbox does not depend on one. The module docstring says this so
  nobody later mistakes it for defence.
- **Reject with instructions, not diagnoses.** Every `CodeRejected` message is
  written to be pasted straight into the next prompt: "the class is named X,
  but it must be named Y. Rename the class and keep everything else."
- **A duplicated FastAPI dependency is a silent test hole.** `dependency_overrides`
  is keyed on the function object, so defining `provide_llm` in two routers
  means a stub that only takes effect on half the routes. Consolidated into
  `api/deps.py`.

**Open questions for later**

- No idea what the real first-attempt success rate is. That needs a key and a
  golden set of concepts -- the obvious next measurement, and the thing that
  would turn prompt changes from guesswork into evidence.
- Three attempts is a guess. If most failures are LaTeX, constraining the model
  to `Text` entirely might beat correcting it.
- Every attempt regenerates from scratch. Sending the *previous* plan along
  with the error might keep more of what was working.
- Nothing caches. The same concept re-renders from zero every time.

**Deliberate divergences from the reference project**

- The reference sanitises model output with several hundred lines of regex
  before rendering. This corrects with the model instead of patching around it,
  and validates with an AST rather than string matching.
- Its generated code runs on the host. This runs in a container with no
  network.
- Its failures skip the scene silently. This degrades to a known-good card and
  reports `generated: false`, so a caller can tell the difference.

---

## Milestone 5 — Narration *(next)*

**Plan:** text-to-speech per scene, muxed to the video, with scene duration
driven by audio length rather than guessed.

**Known obstacle, found in milestone 3:** the manim image ships no ffmpeg CLI
-- it uses PyAV's bundled libav. So muxing means either using PyAV directly or
building a derived image with ffmpeg installed. Decide before writing code.
