from __future__ import annotations

_PDF_PAGE_WIDTH = 612
_PDF_PAGE_HEIGHT = 792
_PDF_MARGIN = 72
_PDF_LINE_HEIGHT = 14


def render_pdf_from_lines(lines: list[str]) -> bytes:
    """Render a lightweight PDF document from pre-wrapped lines."""

    lines_per_page = max(
        1,
        int((
            _PDF_PAGE_HEIGHT - 2 * _PDF_MARGIN
        ) // _PDF_LINE_HEIGHT),
    )
    if not lines:
        lines = [""]

    pages: list[list[str]] = []
    for index in range(0, len(lines), lines_per_page):
        pages.append(lines[index:index + lines_per_page])
    if not pages:
        pages = [[""]]

    page_streams = [_build_pdf_stream(page) for page in pages]
    return _assemble_pdf_document(page_streams)


def _build_pdf_stream(lines: list[str]) -> str:
    if not lines:
        lines = [""]

    stream_lines = [
        "BT",
        "/F1 12 Tf",
        f"{_PDF_LINE_HEIGHT} TL",
        f"1 0 0 1 {_PDF_MARGIN} {_PDF_PAGE_HEIGHT - _PDF_MARGIN} Tm",
    ]

    for line in lines:
        sanitized = _pdf_escape_text(line)
        stream_lines.append(f"({sanitized}) Tj")
        stream_lines.append("T*")

    stream_lines.append("ET")
    return "\n".join(stream_lines)


def _pdf_escape_text(text: str) -> str:
    safe_text = text.encode("latin-1", "replace").decode("latin-1")
    safe_text = safe_text.replace("\\", "\\\\")
    safe_text = safe_text.replace("(", "\\(")
    safe_text = safe_text.replace(")", "\\)")
    return safe_text


def _assemble_pdf_document(page_streams: list[str]) -> bytes:
    if not page_streams:
        page_streams = [_build_pdf_stream([""])]

    num_pages = len(page_streams)
    page_ids = [4 + index for index in range(num_pages)]
    content_ids = [4 + num_pages + index for index in range(num_pages)]

    objects: dict[int, str] = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    kids_entries = " ".join(f"{page_id} 0 R" for page_id in page_ids) or ""
    objects[2] = (
        "<< /Type /Pages /Kids ["
        f"{kids_entries}"
        "] /Count "
        f"{num_pages} >>"
    )

    for index, page_id in enumerate(page_ids):
        content_id = content_ids[index]
        page_dict = (
            "<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {_PDF_PAGE_WIDTH} {_PDF_PAGE_HEIGHT}] "
            "/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        objects[page_id] = page_dict

        stream = page_streams[index]
        stream_bytes = stream.encode("latin-1")
        content_object = (
            f"<< /Length {len(stream_bytes)} >>\n"
            f"stream\n{stream}\nendstream"
        )
        objects[content_id] = content_object

    max_object_id = max(objects)

    pdf_parts: list[str] = ["%PDF-1.4\n"]
    offsets: dict[int, int] = {}
    current_offset = len(pdf_parts[0].encode("latin-1"))

    for object_id in range(1, max_object_id + 1):
        content = objects.get(object_id)
        if content is None:
            continue
        serialized = f"{object_id} 0 obj\n{content}\nendobj\n"
        offsets[object_id] = current_offset
        encoded = serialized.encode("latin-1")
        pdf_parts.append(serialized)
        current_offset += len(encoded)

    xref_start = current_offset

    total_objects = max_object_id
    xref_lines = [
        "xref",
        f"0 {total_objects + 1}",
        "0000000000 65535 f ",
    ]
    for object_id in range(1, total_objects + 1):
        offset = offsets.get(object_id, 0)
        xref_lines.append(f"{offset:010} 00000 n ")

    xref_text = "\n".join(xref_lines) + "\n"
    pdf_parts.append(xref_text)
    current_offset += len(xref_text.encode("latin-1"))

    trailer = (
        "trailer\n"
        f"<< /Size {total_objects + 1} /Root 1 0 R >>\n"
        "startxref\n"
        f"{xref_start}\n"
        "%%EOF\n"
    )
    pdf_parts.append(trailer)

    return "".join(pdf_parts).encode("latin-1")


__all__ = [
    "render_pdf_from_lines",
]
