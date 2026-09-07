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

## Interlude — first contact with a real provider

Ran the whole pipeline against Gemini for the first time, on the Batch
Normalization paper (arXiv 1502.03167, 11 pages, 42k characters).

**What worked.** Concept extraction, and well: six concepts, correctly ordered
so prerequisites come first, with page citations that check out. Not a
restatement of the abstract. It took 56 seconds for one call.

**What did not.** Zero of six concepts got an animation generated. Not because
the model wrote bad Manim -- because it never wrote any. Every attempt failed
at the provider: two on 503 "high demand", four on 429.

```
quotaId: GenerateRequestsPerDayPerProjectPerModel
quotaValue: 20
```

**Twenty requests per day, per model.** That single fact invalidated a design
decision I had made an hour earlier.

**Things I learned**

- **Know which resource is scarce before designing a retry policy.** I had just
  lengthened the backoff to 2s/6s/18s to survive demand spikes -- correct if
  latency is the constraint, actively harmful when the quota counts *requests*.
  Combined with a fallback model, one logical call became up to eight requests.
  Six concepts consumed roughly forty requests against a budget of twenty.
- **The fix is rotation, not persistence.** The quota is per-model and the
  account has a dozen flash models. Retrying one model harder buys nothing;
  trying a different model buys a whole fresh budget. Now: one retry per model,
  then move on, and remember which models returned 429 so no request is ever
  spent rediscovering that.
- **429 is not retryable and never was.** It is the one error where trying
  again is guaranteed to fail *and* costs the thing you are short of.
- **The fallback path justified itself immediately.** Every generation request
  failed and 6/6 concepts still returned a playable video, with
  `generated: false` so the caller can tell. That was written as a nicety in
  milestone 4 and turned out to be the only reason the endpoint worked at all
  on its first real day.
- **Model availability is not what the docs say.** `gemini-2.0-flash` and
  `gemini-2.5-flash` both 404 despite being listed; `3.6-flash` was down while
  `3.8-flash` answered in 1.6s; `3.7-flash` took 49s for a one-word reply.
  Capacity moves minute to minute. Ask the API, not the documentation.
- **A one-line prompt succeeded while a 60k-character prompt to the same model
  in the same minute got 503.** Capacity is refused per request, not per model.

**Still unmeasured:** the first-attempt render rate, which is the entire point
of milestone 4. `scripts/measure_generation.py` exists to answer it the moment
there is quota to spend.

---

## Milestone 5 — Narration

**Built so far:** the LLM-free half. A `Speech` seam with gTTS behind it, a
`MediaTool` seam with ffmpeg behind it (probe, mux, concat), a derived Docker
image carrying manim *and* ffmpeg, and a shared container helper both the
renderer and ffmpeg now use.

**Verified for real:** a 3s test video plus 5s of audio muxes to 5.0s with the
last frame held; two clips concatenate to 10s. Then end to end on real content
-- two Batch Normalization concepts rendered, narrated with gTTS, muxed and
stitched into 26.9 seconds of video with sound.

**The obstacle from milestone 3, resolved.** The manim image has no ffmpeg
binary; manim 0.21 renders through PyAV's bundled libav. Rather than rewrite
muxing in PyAV, `Dockerfile.render` adds ffmpeg to the base image. It builds in
7 seconds on top of the 2 GB base and means one sandbox does rendering, probing,
muxing and concatenation.

**Things I learned**

- **The narration is 2.5x longer than the animation.** Measured: 5.3s of video
  against 13.7s of speech. Padding the video holds a dead frame for eight
  seconds. So the order has to invert -- synthesise narration first, measure
  it, then tell the scene how long to run. Padding is the safety net, not the
  plan. I would have designed this the wrong way round without rendering one.
- **`--workdir` is not optional.** Moving the mount from `/manim` to a shared
  `/work` broke rendering instantly, because the image's own WORKDIR won and
  `scene.py` resolved somewhere the mounted files were not. There is now a test
  asserting the flag.
- **Two callers made the container helper worth extracting.** Timeout handling,
  kill-by-name and the sandbox flags were about to be written a second time for
  ffmpeg. One helper, one place to get the security flags right.
- **A test can synthesise its own media.** `ffmpeg -f lavfi -i testsrc` and
  `anullsrc` produce real video and audio on demand, so the integration tests
  need no checked-in fixtures -- the same instinct as the hand-written PDF
  writer in milestone 1.

### Part 2 — the ordering

Scene splitting, narration-driven timing, and the endpoint.

- **The order is the design.** A concept is split into scenes, every scene's
  narration is synthesised and measured *first*, and only then is animation
  code written — with the measured length in the prompt. Part 1 proved why:
  animation-then-narration gave 5.3s of video under 13.7s of speech.
- **Narration is generated concurrently, animation is not.** TTS is
  network-bound and independent per scene; rendering is the slow part and
  competes for the same CPU.
- **A failed scene is skipped, not fatal.** One scene that will not render
  should not lose the other three. Its fallback card carries that scene's own
  narration, so the video still *says* the right thing even when it cannot
  show it.
- **A test caught a leak I had claimed did not exist.** Since milestone 4 the
  502 body serialised whole attempt objects, and `detail` is distilled renderer
  stderr — paths and all. I had asserted "stderr never reaches the client" in
  milestone 3, dropped that assertion when rewriting the test for milestone 4,
  and the leak walked in behind it. Scene reports now carry outcomes only, and
  the assertion is back. Deleting a test is how a guarantee quietly stops being
  one.
- **Quota is now the design constraint, not an annoyance.** One split call plus
  up to three per scene means a three-scene video can cost ten requests against
  a twenty-per-day-per-model budget. `max_scenes` is the main lever.

**Deliberate divergences from the reference project**

- The reference shells out to ffmpeg on the host. Here ffmpeg runs in the same
  network-isolated container as the renderer.
- Narration sits behind a `Speech` protocol, so gTTS is a starting point rather
  than a commitment.

---

## Milestone 4, revisited

Went back to the generation prompt once milestone 5 was wired up. Three
changes, separated by how well justified each one is -- two are evidence, one
is a guess, and the difference matters.

**A real bug, and mine.** Milestone 5 left two contradictory length
instructions in the same prompt: the system prompt said "keep the whole
animation between 10 and 25 seconds" while the per-scene block said "must last
about 7 seconds, because that is how long the narration takes". A model given
both is given neither. Exactly one now reaches it -- the measured narration
length when narration exists, a default range when it does not -- and a test
asserts `"seconds" not in SYSTEM` so it cannot drift back.

**The correction prompt was missing the point of the scene.** It carried the
error and the code but never said what the code was *for*, which leaves a "fix"
free to quietly animate something else. It now carries the plan the model wrote
on its first attempt.

**A prior, not a measurement.** I added a short list of known-good manim classes
and methods to the system prompt. Hallucinated methods are the classic failure
mode for generated manim, and the reference project ships a cheat sheet for
exactly this -- but nothing in *my* runs has yet shown that this is what fails
here. It is a reasonable guess dressed as a fix, and labelling it as one matters
more than being right about it.

**Things I learned**

- **Wiring a later milestone can silently corrupt an earlier one.** Nothing
  failed when milestone 5 introduced the contradiction. No test covered "how
  many length instructions does the model receive", because until there were
  two sources of that instruction the question was meaningless. New
  collaborators create new invariants, and the old tests do not know about them.
- **`str.format` ignores extra keyword arguments.** A botched edit left
  `CORRECT.format(plan=...)` pointing at a template with no `{plan}` in it.
  That is not an error, it is a silent no-op -- a change that looks applied,
  passes every test, and does nothing.
- **Measure before and after on the same input.** The baseline run was launched
  before these edits, so it holds the old prompt against the same paper and the
  same cached concepts: one variable. Without that, prompt changes are just
  opinions with a diff attached.

### Measured, finally

**2/2 concepts rendered on the first attempt.** Batch Normalization paper,
`gemini-3.8-flash`, 36s and 59s end to end, 19.4s and 14.1s of video. No
corrections, no fallbacks.

Getting that number took four attempts, and the last two failures were mine,
not the provider's:

- **A relative path in a bind mount is a named volume, not a path.** The
  measure script passed `--out storage/measure`, so `docker run -v
  storage\measure\...:/work` asked for a *volume called* `storage\measure...`
  and was refused. Every render failed before manim started. No test caught it
  because pytest's `tmp_path` is always absolute -- the fixture that makes
  tests convenient also made them unrepresentative.
- **Infrastructure failures were being treated as the model's fault.** All
  three attempts re-prompted the model to fix a Docker configuration error:
  three model calls, three identical failures, quota gone. There is now a
  `RenderUnavailable` for "the container could not start", and the loop stops
  on it instead of arguing with the model about a bad mount.

**What the videos actually look like.** Better than expected: real diagrams,
LaTeX formulas rendering correctly via `MathTex`, axes with labelled point
clouds, a decision boundary that moves. Not a title card with a formula pasted
on it.

**The defect the loop cannot see.** Both videos have overlapping text -- a
label written on top of another label. The render succeeds, exits zero, and
produces a valid mp4, so nothing in the correction loop notices. The loop only
ever sees crashes. Catching a *visual* defect needs a different mechanism
entirely: rendering a frame and having something look at it. That is the honest
ceiling on this design, and it took seeing the output to find it.


---

## Milestone 6 — Concurrency and progress

**Built:** a job registry, builds moved off the request path, scenes rendering
in parallel under a global cap, and progress over server-sent events. Twelve
new tests.

**The scoping decision, stated plainly.** The roadmap said "a real job queue",
meaning Redis and a worker process. I built it in-process instead. Jobs live in
this process's memory: a restart loses them, and a second uvicorn worker would
not see them. That is a stopping point I chose, not one I missed, and the README
says so next to the feature rather than in a footnote.

**Things I learned**

- **202 is the whole milestone.** A build is one split call plus up to three
  model calls and container starts per scene. Holding an HTTP connection open
  for that is not slow, it is wrong -- proxies close it, retries duplicate the
  work, and the client has nothing to show meanwhile.
- **SSE beats a WebSocket for one-way progress.** No protocol upgrade, plain
  HTTP, and browsers reconnect automatically. The reference project used a
  WebSocket and then had to hand-write keepalives and reconnection logic for a
  stream that never carries a message from the client.
- **Replay before you subscribe.** A client that connects a second after the
  job starts would otherwise join midway and never learn what it missed. The
  stream sends the recorded events first, then live ones.
- **A publisher must never be blocked by a subscriber.** `publish` uses
  `put_nowait` and drops on a full queue. A browser tab that stops reading must
  not be able to stall the render pipeline reporting to it -- there is a test
  that fires 500 events at a full queue and asserts all 500 are still recorded.
- **The semaphore belongs around the whole generate-render cycle, not the
  render.** Releasing between the model call and the container start just lets
  everything pile up at the container.
- **Fixtures do not cross module boundaries.** `rendered` lived in
  `test_video.py`; the moment a second module needed it, it had to move to
  `conftest.py`. Importing a fixture does not register it.

**Open questions for later**

- Jobs are lost on restart. Milestone 8 territory.
- Nothing cancels a running job.
- Parallel scenes mean parallel model calls, which burns the free-tier quota
  faster and invites the 503s from the interlude. `max_parallel_renders` is
  the lever and it defaults to 2.


---

## Interlude — the measurement tool was measuring the past

Sent two generated videos over as evidence that milestone 4 works. The reply:
"I cannot hear the narration?"

There was no narration. `ffprobe` on both files: one stream, video. No audio
track at all.

**What had happened.** `scripts/measure_generation.py` was written during
milestone 4 and calls `animate_concept` -- the single-scene loop, no narration,
no mux. Milestone 5 added `build_explainer` and made that the product. The
script was never updated, so it kept exercising a code path that had stopped
being the thing the API builds two milestones earlier.

Every number it produced about the *generation loop* was still true. The claim
it implied -- "this is what the system makes" -- was not.

**Things I learned**

- **A measurement tool not wired to the product measures the past.** It fails
  silently, because it still runs, still passes, still prints a number. The
  test suite cannot catch this: both code paths work, they are just not the
  same path.
- **Ship the artefact, not the summary.** The gap survived a green suite, a
  passing integration test and my own review. It did not survive someone
  pressing play. When the deliverable is a file, look at the file.
- **The fix is a default, not a flag.** The script now runs the real pipeline
  by default, with `--single-scene` to isolate the generation loop. Making the
  product path opt-in is how it drifted in the first place.

**Verified after the fix:** Internal Covariate Shift, 2 scenes, 32.7s, h264
plus aac, both scenes generated first attempt, 144 seconds to build.


---

## Interlude — a better voice

gTTS sounded like a satnav, so the narrator got replaced. Piper, running in the
render image.

**Why not the obvious answers.** *Whisper* is speech-to-text -- the opposite
direction, and a common mix-up worth naming. *Kokoro* sounds better than Piper
and pulls in torch, which would have taken a 2 GB image past 5 GB; for a
container that gets rebuilt often that is the deciding fact, not the audio.
*Gemini TTS* was tempting because the key already exists, but it draws on the
same twenty-requests-per-day quota as code generation -- narration would have
competed with the thing that actually needs the quota.

**What Piper cost:** 260 MB. ONNX, no torch, one voice baked in at build time
because the container runs with `--network none` and cannot fetch anything.

**Things I learned**

- **Pacing is a setting.** `--sentence-silence 0.45` puts a real breath between
  sentences and `--length-scale` slows delivery. gTTS ran everything together;
  for an explainer that is as damaging as a robotic timbre, and no amount of
  better voice model fixes it if the pauses are not there.
- **A local engine is deterministic, and that compounds.** The same text gives
  the same audio, so builds are reproducible and a future cache can key on the
  narration text. A hosted voice can change under you between runs.
- **The seam paid for itself exactly as intended.** Adding an engine was one
  new module and one branch in `build_speech`. Nothing in the explainer, the
  API, or any test above that layer changed. That is the second time a
  protocol written in an earlier milestone made a later one cheap.
- **Narration gets the same sandbox as rendering.** There is no reason a
  text-to-speech process needs network access either, and a test asserts the
  flags rather than trusting that.

### Smoothing it

The first voice was picked by me and rejected by the person listening, which is
the correct order for that decision. Downloading five alternatives and playing
them side by side cost nothing -- a Piper voice is a file, and swapping one is
a config line.

Four knobs, in ascending order of how much they mattered:

1. `--length-scale 1.12`. TTS defaults are tuned for assistants answering
   questions, not for explaining something. Almost everything sounds better
   12% slower.
2. `--sentence-silence 0.6`. The gap between ideas is where understanding
   happens.
3. `--noise-scale` / `--noise-w-scale`. Counterintuitive: *lower* is smoother.
   Left at the voice's own defaults, exposed as config for later.
4. **The narration text itself** -- and this is not a Piper setting at all. A
   synthesised voice breathes at punctuation, so three long sentences give it
   three places to breathe. Asking the model for short single-idea sentences
   did more for smoothness than any parameter, costs nothing, and improves
   every future video rather than one.

The generalisable bit: when output quality disappoints, check whether the
*input* is the problem before tuning the engine. I reached for parameters
first, and they were the smaller half.


---

## Interlude — Kokoro, and two bugs I wrote while adding it

Piper was good; Kokoro is better, and the voice was chosen by ear again
(`af_bella`). It costs a separate 2.88 GB image -- torch, which manim does not
need, so layering it onto the render image would make every render carry a
speech model. I had earlier called this "a few hundred megabytes", which was
wrong: the CPU-only torch wheel is far smaller than the CUDA default but not
small.

**Bug one: the pause did nothing.** Kokoro has no `--sentence-silence`, so I
padded between the pipeline's own chunks. Measured, a three-sentence line came
back as *one* chunk, so the padding sat between one thing and nothing. Fixed by
splitting sentences before synthesis: 12.8s to 14.65s on the same line, which
is the pause becoming real.

**Bug two: CRLF, and a suite that could not see it.** Several config edits used
Python string replacement matching `
` against files with CRLF endings. They
matched nothing, changed nothing, and reported success. The result was
`deps.py` reading `settings.speech_engine`, `settings.kokoro_voice` and three
other attributes that did not exist on `Settings` at all.

**And 105 tests passed.** Every test overrides `provide_speech`, `provide_llm`,
`provide_renderer` and `provide_media` with stubs -- which is exactly what
keeps the suite offline and fast, and exactly why nothing ever tried to build
the real thing. A real video request would have raised `AttributeError` and
returned a 500.

**Things I learned**

- **A test double that replaces a collaborator also replaces the check that the
  collaborator can be built.** Stubs bought speed and offline tests, and quietly
  sold the wiring. `tests/test_deps.py` now constructs every provider from real
  `Settings` and asserts every attribute `deps.py` reads exists.
- **Verify edits applied, do not trust that they did.** A replacement that
  matches nothing is silent. Every edit in this project should assert on its
  match; the ones that did caught their failures immediately, the ones that did
  not caused this.
- **Line endings are a correctness issue, not a formatting one.** On a Windows
  checkout, matching `
` against CRLF fails invisibly.
- **The same class of bug appeared twice in one session** -- the measurement
  script hardcoded `GttsSpeech` after I had just fixed it for hardcoding the
  wrong pipeline. Anything that constructs a collaborator directly, instead of
  going through the factory the app uses, will drift. It now builds from config
  and prints which engine it used.


---

## Milestone 7 — Frontend

**Built:** a Next.js app. Upload a PDF, open a paper, extract concepts, click
Build on a concept, watch the stages go by, play the result inline.

**Verified in a browser, not just compiled:** uploaded the Batch Norm paper,
extracted six concepts, built one, watched "Narrating 3 scenes" become
"Animating scene 3 of 3" become a video player at 0:38. The pipeline behind
that was already tested; what this proved is that the wiring to a real
`EventSource` and a real `<video>` element works.

**Things I learned**

- **Read the bundled docs.** This Next.js version ships its documentation in
  `node_modules` and a note saying the framework has changed from what a model
  was trained on. It had: `params` is now a Promise you await. Ten minutes of
  reading beat an hour of debugging a stale mental model.
- **Everything runs in the browser, on purpose.** The backend is local, it
  already allows this origin, and the progress stream is an `EventSource` --
  which only exists in a browser. One client-side model was simpler than
  splitting fetches between server and client components for no gain.
- **Show the stage, not a percentage.** The stages are wildly different
  lengths. A bar that sits at 40% for two minutes says less than "animating
  scene 2 of 3".
- **Replay makes late subscribers free.** Because the server replays a job's
  recorded events before streaming live ones, the card can subscribe from an
  empty list every time -- including when it joins a build that is already
  half done.
- **A UI would have caught the silent-audio bug on day one.** It has a
  `<video>` element and nowhere to hide a missing track. The measurement
  script could print "generated=True" over a silent file for days; a person
  pressing play in a browser cannot be fooled the same way.

**Types are kept by hand.** Six interfaces mirroring the pydantic models.
Reading them is faster than reading a generator's output, and they drift only
when the API does -- which is when a person should be looking anyway.

### The design pass

The first cut was functional and plain, and the reaction was "why not make
it really cool like the original". Fair. A second pass added a hand-written
WebGL shader background, a landing page, glass panels and staggered
entrances.

- **Function first, then form -- in that order, verified.** The plain version
  was tested end to end in a browser (upload, extract, build with live
  progress, play) and committed *before* any styling. A pretty UI over a
  broken pipe is worse than an ugly one over a working pipe, because it hides
  the break.
- **The shader is ~80 lines of GLSL, not a library.** Domain-warped value
  noise in the palette the videos use, plus the faint coordinate grid every
  3blue1brown scene sits on. Rendered at 75% resolution, one still frame
  under `prefers-reduced-motion`, paused when the tab is hidden. The CSS
  background underneath is the fallback if WebGL is missing.
- **No animation library.** Two CSS keyframes and an inline `animation-delay`
  per card do the staggered entrances. The reference project pulled in
  framer-motion for the same effect; that is a dependency for a `transform`.
- **Low contrast is the point.** The background sits behind text on every
  page. It has to read as texture, not content, so every colour is mixed at
  10 to 35 percent.

### Second design pass: match the reference, not my taste

The first pass was teal-and-indigo with a drifting noise field. The reaction
was "it just looks ugly, do something similar to the repo I sent". Fair, and
I had not actually looked at the reference before styling -- I had read its
CSS and guessed.

Looking at its landing screenshot settled it in one glance: **monochrome**.
Near-black, white light-weight Geist, wide-tracked uppercase eyebrows, glass
panels lit from inside by white glow, pill buttons, a floating pill nav
instead of a header bar -- and a single glowing refractive sphere behind the
upload panel that fades and grows in over the first two seconds.

- **Look at the thing before imitating it.** Reading the reference's Tailwind
  config told me its colours were white-on-black; it did not tell me the
  sphere was the whole design. A screenshot did in a second.
- **The sphere is a disc, not a raymarch.** Its surface normal is
  reconstructed from the radius, which is all the lighting needs: a key light,
  a fresnel rim, a specular dot, and a texture sampled at a warped position so
  it reads as bent by glass. Three samples with a small offset give the
  chromatic split at the edge. ~90 lines of GLSL, my own.
- **Own implementation, borrowed look.** The reference has no licence file,
  so nothing of its shader or components was read for reuse. Layout, palette
  and timing were taken from the screenshot; every line of code is new.
- **The interior had to be dimmed after the first screenshot.** Text and
  panels sit on the sphere; the rim is what should read, not the body.

### Choosing the background

Asked for alternatives, I built five looks into one shader behind a `?bg=`
switch and screenshotted each, the same way the voices were compared: make
the options real, let a person choose by eye, then make the choice the
default. *Ring* won -- a single glowing circle with a chromatic edge and a
slow bright arc. It keeps what makes the reference feel expensive, drops the
busy interior so text reads, and a circle is the most 3blue1brown thing to
put behind the word "Pi". The other four stay reachable by query parameter,
which costs nothing and means the next opinion can be tested in a URL.

One bug worth remembering: a backtick inside a GLSL comment ended the
JavaScript template literal early. TypeScript reported the error on a line
that looked like perfectly good GLSL, because from its point of view the
string had already closed.
