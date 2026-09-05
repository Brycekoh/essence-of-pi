"""Measure how often the model's first attempt actually renders.

This is the number that tells you whether milestone 4 works. Everything else
about the generation loop is a guess until this has been run.

    cd backend
    .venv/Scripts/python.exe scripts/measure_generation.py path/to/paper.pdf

Costs, on the free tier: one request to extract concepts, then one to three per
concept. The free-tier quota is 20 requests per day *per model*, so a six
concept paper can exhaust a model in a single run -- which is why the client
rotates through LLM_FALLBACK_MODELS rather than retrying one model.

Add `--concepts N` to cap how many are animated.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.services.animation import animate_concept  # noqa: E402
from app.services.concepts import extract_concepts  # noqa: E402
from app.services.llm import build_llm  # noqa: E402
from app.services.pdf_parser import extract_pages  # noqa: E402
from app.services.render import ManimDockerRenderer  # noqa: E402
from app.models import Paper  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--concepts", type=int, default=3)
    parser.add_argument("--quality", default="-ql", help="-ql fast, -qm nicer")
    parser.add_argument("--out", type=Path, default=Path("storage/measure"))
    parser.add_argument(
        "--cache",
        type=Path,
        help="reuse concepts from this JSON file instead of paying for extraction",
    )
    args = parser.parse_args()

    settings = get_settings()
    llm = build_llm(settings.gemini_api_key, settings.llm_models_csv)
    renderer = ManimDockerRenderer(image=settings.renderer_image, quality=args.quality)
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"models  : {settings.llm_models_csv}")
    print(f"paper   : {args.pdf}")

    pages, title = await extract_pages(args.pdf)
    paper = Paper(
        id="measure",
        filename=args.pdf.name,
        size_bytes=args.pdf.stat().st_size,
        page_count=len(pages),
        char_count=sum(len(p.text) for p in pages),
        title=title,
    )
    print(f"pages   : {paper.page_count}  chars: {paper.char_count}\n")

    if args.cache and args.cache.exists():
        from app.models import Concept

        concepts = [
            Concept(**c) for c in json.loads(args.cache.read_text(encoding="utf-8"))
        ]
        print(f"concepts: {len(concepts)} (reused from {args.cache})\n")
    else:
        concepts, truncated = await extract_concepts(
            llm,
            paper,
            pages,
            max_concepts=settings.max_concepts,
            char_budget=settings.max_chars_to_model,
        )
        print(f"concepts: {len(concepts)} (truncated={truncated})\n")
        if args.cache:
            args.cache.write_text(
                json.dumps([c.model_dump() for c in concepts], indent=2),
                encoding="utf-8",
            )

    rows = []
    for i, concept in enumerate(concepts[: args.concepts], start=1):
        destination = args.out / f"{i:02d}-{concept.id[:8]}.mp4"
        started = time.monotonic()
        outcome = await animate_concept(
            llm,
            renderer,
            concept,
            destination,
            max_attempts=settings.max_render_attempts,
            timeout=settings.render_timeout_seconds,
        )
        elapsed = time.monotonic() - started
        steps = [a.outcome for a in outcome.attempts]

        print(f"[{i}] {concept.name}  ({elapsed:.0f}s)")
        if outcome.plan:
            print(f"    plan: {outcome.plan[:150]}")
        for attempt in outcome.attempts:
            detail = (attempt.detail or "").replace("\n", " | ")[:180]
            print(f"    {attempt.attempt}. {attempt.outcome}  {detail}")
        size = destination.stat().st_size if destination.exists() else 0
        print(f"    generated={outcome.generated}  {size} bytes -> {destination}\n")
        rows.append((concept.name, steps, outcome.generated))

    total = len(rows)
    if not total:
        print("No concepts animated.")
        return 1

    first_ok = sum(1 for _, steps, _ in rows if steps[:1] == ["rendered"])
    made = sum(1 for _, _, generated in rows if generated)
    blocked = sum(1 for _, steps, _ in rows if "llm-failed" in steps)

    print("=" * 64)
    print(f"first attempt rendered : {first_ok}/{total}")
    print(f"generated at all       : {made}/{total}")
    print(f"fell back to the card  : {total - made}/{total}")
    if blocked:
        print(f"blocked by the provider: {blocked}/{total}  (quota or capacity,")
        print("                         not a code-generation result)")
    print()
    for name, steps, _ in rows:
        print(f"  {name[:40]:42s} {' -> '.join(steps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
