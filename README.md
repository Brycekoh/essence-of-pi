# Essence of Pi

Research papers, distilled into 3blue1brown-style explainers.

Upload a paper, get back the handful of ideas that actually matter, and watch
each one become a short animated video.

> **Status: milestone 1 of 8.** The PDF ingestion layer works and is tested.
> Nothing generates video yet. This is a learning build, in public, one
> milestone per commit — see [LEARNING.md](LEARNING.md) for the running log.

## What works today

```
PDF upload  →  validation  →  pdfplumber text extraction  →  JSON API
```

| Method | Route | Does |
| --- | --- | --- |
| `POST` | `/api/papers` | Upload a PDF, extract its text, return metadata |
| `GET` | `/api/papers` | List uploaded papers, newest first |
| `GET` | `/api/papers/{id}` | Metadata for one paper |
| `GET` | `/api/papers/{id}/text` | Extracted text, per page (`?page=2` for one) |
| `GET` | `/api/papers/{id}/pdf` | The original file back |
| `DELETE` | `/api/papers/{id}` | Remove the paper and its file |
| `GET` | `/health` | Liveness check |

## Run it

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Interactive API docs: <http://localhost:8000/docs>

Tests:

```bash
cd backend && pytest
```

Or with Docker:

```bash
docker compose up --build
```

## Roadmap

- [x] **1 — Ingestion.** Upload, validate, extract text. No AI.
- [ ] **2 — Concepts.** An LLM pulls the core ideas out of the paper, using
      structured output rather than parsing prose.
- [ ] **3 — First render.** A hand-written Manim scene, rendered by the backend
      and served as an mp4.
- [ ] **4 — Generated animation.** The LLM writes the Manim code; failed renders
      feed their own stderr back in for a correction pass.
- [ ] **5 — Narration.** Text-to-speech per scene, muxed to video, scene timing
      driven by audio length.
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

## Credit

Inspired by [clarifai](https://github.com/) *(← replace with the original repo
URL)*, which demonstrated the paper→Manim pipeline. This is an independent
reimplementation written from scratch to learn the stack; no code was copied,
and the architecture diverges deliberately (see [LEARNING.md](LEARNING.md)).
Not affiliated with that project, with 3blue1brown, or with Grant Sanderson.

Manim is a community-maintained project; "3blue1brown-style" describes the
visual idiom, nothing more.

## License

MIT — see [LICENSE](LICENSE).
