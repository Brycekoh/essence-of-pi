"""A tiny PDF writer, so the tests don't need a binary fixture checked in.

This builds a genuinely valid single- or multi-page PDF with real text objects,
including a correct cross-reference table. It exists to make the test suite
self-contained; nothing in the app uses it.
"""


def make_pdf(page_texts: list[str]) -> bytes:
    """Return the bytes of a PDF containing one page per string."""
    n = len(page_texts)
    if n == 0:
        raise ValueError("A PDF needs at least one page.")

    # Object numbering: 1 catalog, 2 page tree, 3 font,
    # then a (page, content) pair per page starting at 4.
    page_ids = [4 + 2 * i for i in range(n)]
    content_ids = [5 + 2 * i for i in range(n)]

    bodies: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [{}] /Count {} >>".format(
            " ".join(f"{pid} 0 R" for pid in page_ids), n
        ).encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    for page_id, content_id, text in zip(page_ids, content_ids, page_texts):
        bodies[page_id] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode()

        escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        stream = f"BT /F1 24 Tf 72 700 Td ({escaped}) Tj ET".encode()
        bodies[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in sorted(bodies):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + bodies[num] + b"\nendobj\n"

    # Cross-reference table: byte offset of every object, in order.
    xref_start = len(out)
    count = max(bodies) + 1
    out += f"xref\n0 {count}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, count):
        out += f"{offsets[num]:010d} 00000 n \n".encode()

    out += f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_start}\n".encode()
    out += b"%%EOF\n"
    return bytes(out)
