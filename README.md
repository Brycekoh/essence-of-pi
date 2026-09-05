# Essence of Pi

Research papers, distilled into 3blue1brown-style explainers.

Upload a paper, get back the handful of ideas that actually matter, and watch
each one become a short animated video.

> **Status: milestone 4 of 8.** Papers go in, concepts come out, and a model
> writes the Manim for each one — retrying against its own error output when a
> render fails. No narration or multi-scene stitching yet. This is a learning build, in public, one milestone per
> commit — see [LEARNING.md](LEARNING.md) for the running log.

## What works today

```
PDF → pdfplumber → LLM concepts → LLM writes Manim → static check → render in Docker
                                        ▲                                │
                                        └──── the error, on failure ─────┘
```

| Method | Route | Does |
| --- | --- | --- |
| `POST` | `/api/papers` | Upload a PDF, extract its text, return metadata |
| `GET` | `/api/papers` | List uploaded papers, newest first |
| `GET` | `/api/papers/{id}` | Metadata for one paper |
| `GET` | `/api/papers/{id}/text` | Extracted text, per page (`?page=2` for one) |
| `GET` | `/api/papers/{id}/pdf` | The original file back |
| `DELETE` | `/api/papers/{id}` | Remove the paper and its file |
| `POST` | `/api/papers/{id}/concepts` | Extract concepts with an LLM (replaces any previous set) |
| `GET` | `/api/papers/{id}/concepts` | Concepts extracted so far |
| `GET` | `/api/papers/{id}/concepts/{cid}` | One concept |
| `POST` | `/api/papers/{id}/concepts/{cid}/video` | Model writes an animation; render it, correcting on failure |
| `GET` | `/api/papers/{id}/concepts/{cid}/video` | Stream the rendered mp4 |
| `GET` | `/health` | Liveness check |

The concept endpoints need `GEMINI_API_KEY` in `backend/.env` (a free key comes
from [AI Studio](https://aistudio.google.com/apikey)). Without one the app still
boots and serves papers; the concept routes return `503` explaining what to set.

**Free-tier reality check:** Gemini's free tier allows **20 requests per day,
per model**. Concept extraction costs one; each video costs one to three. The
client therefore rotates through `LLM_FALLBACK_MODELS` rather than retrying a
single model, since the quota is per-model. Measure the generation loop with:

```bash
.venv/Scripts/python.exe scripts/measure_generation.py path/to/paper.pdf
```

Rendering needs Docker running and the render image built once (~2 GB base
plus ffmpeg):

```bash
docker pull manimcommunity/manim:stable
cd backend && docker build -f Dockerfile.render -t essence-of-pi/render:latest .
```

The upstream manim image has **no ffmpeg binary** — manim 0.21 renders through
PyAV's bundled libav — so narration could not be muxed on it. The derived image
carries manim, LaTeX and ffmpeg, and is the sandbox for all three.

Nothing else is installed on the host — no manim, no ffmpeg, no LaTeX. If the
daemon is down the render route returns `502` saying so.

## Run it

**Windows (PowerShell).** `&&` is not a valid statement separator in Windows
PowerShell 5.1, and activating a venv can trip the execution policy -- so call
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

Interactive API docs: <http://localhost:8000/docs>

Tests -- `.\.venv\Scripts\pytest.exe` on Windows, `pytest` once activated
elsewhere:

```bash
cd backend && pytest
```

Or with Docker:

```bash
docker compose up --build
```

## Roadmap

- [x] **1 — Ingestion.** Upload, validate, extract text. No AI.
- [x] **2 — Concepts.** An LLM pulls the core ideas out of the paper, using
      structured output rather than parsing prose.
- [x] **3 — First render.** A hand-written Manim scene, rendered by the backend
      and served as an mp4.
- [x] **4 — Generated animation.** The LLM writes the Manim code; failed renders
      feed their own stderr back in for a correction pass.
- [~] **5 — Narration.** *In progress.* Speech and media seams built and
      tested against real ffmpeg; not yet wired to the endpoints. Scene timing
      from audio length is the remaining piece.
- [ ] **6 — Concurrency and progress.** A real job queue, parallel renders, live
      progress in the UI.
- [ ] **7 — Frontend.** Next.js: upload, browse concepts, watch clips.
- [ ] **8 — Persistence and deploy.** Postgres, object storage, auth, shipped.

## Design notes

Decisions made in milestone 1 that the later milestones depend on:

- **Uploads are validated by their bytes, not their headers.** The `%PDF-`
  magic number is checked; the client-supplied `Content-Type` is ignored,
  because a client can claim anything.
- **PDF parsing runs off the event loop.** `pdfplumber` is synchronous and
  CPU-bound, so extraction goes through `asyncio.to_thread`. A 60-page paper
  would otherwise stall every other request for the duration.
- **Storage sits behind one interface.** `PaperStore` is in-memory today and
  loses everything on restart. That's a deliberate milestone-1 shortcut, and
  confining it to one class is what makes milestone 8 a swap rather than a
  rewrite.
- **Empty pages are kept, not dropped.** A scanned or figure-only page yields
  an empty string, so page numbers always match the source document.
- **Tests exist from commit one**, including a hand-rolled PDF writer in
  `tests/pdf_fixture.py` so the suite needs no binary fixtures.
- **The model is constrained, not asked nicely.** `response_schema` makes the
  SDK decode straight into a pydantic model, so there is no "reply in JSON"
  instruction anywhere, no markdown fence to strip, and no regex to recover
  from a chatty answer.
- **A schema guarantees shape, not sense.** The model can still cite page 99 of
  a 12-page paper or list a concept as its own prerequisite, so
  `services/concepts.py` validates meaning after the SDK has validated form.
- **The LLM sits behind one method.** `LLMClient.structured(prompt, schema)` is
  the entire provider interface; prompts live with the feature that owns them.
  Swapping providers is a new module and one branch in `llm/__init__.py`.
- **Tests never touch the network.** `StubLLM` and `StubRenderer` are scripted
  per test, so the suite runs in ~1.5s with no key and no Docker. One test does
  run manim for real, and skips itself when Docker isn't available.
- **Rendering happens in a container, from the first render.** `--network none`,
  a memory ceiling and a CPU quota, with a test asserting those flags are
  present. Milestone 3's code is ours and harmless; milestone 4's is written by
  a model, and by then the sandbox already exists.
- **Concept text enters generated Python as a literal, never an expression.**
  `repr()`, not string interpolation — so a concept named `"); import os` is
  inert data.
- **Static checks are a feedback loop, not a defence.** `compile()` plus an AST
  pass rejects unrenderable code in microseconds instead of paying for a
  container start. The container is what makes bad code *safe*; the AST pass
  only makes failure *fast*. `services/codecheck.py` says so at the top.
- **The error message is the correction prompt.** `RenderError` carries stderr
  precisely so the next attempt can be "here is your code, here is what it
  did". Correction runs at a lower temperature than generation — a fix should
  be conservative.
- **Failure degrades instead of erroring.** When every attempt fails, the
  hand-written card from milestone 3 renders instead, and the response says
  `generated: false`. That is the reason milestone 3 built a template first.
  On its first contact with reality this was the only thing that worked: the
  provider refused every generation request, and 6/6 concepts still returned a
  playable video.
- **Retrying is not free when the quota counts requests.** At 20 requests per
  day per model, a generous retry policy spends the day's budget on a queue
  that is not moving. Each model gets one retry, then the client moves to the
  next model — and remembers which ones returned 429.

## Note

Not affiliated with 3blue1brown or Grant Sanderson. Manim is a
community-maintained project; "3blue1brown-style" describes the visual idiom,
nothing more.

## License

MIT — see [LICENSE](LICENSE).
