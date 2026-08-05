"""Layered SVG export designed for Cricut / Design Space workflows."""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any, Dict, List

import numpy as np

from pdf_generator import layout_piece_pages


PAGE_GAP_INCHES = 0.35


def _number(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".") or "0"


def _points(vertices: np.ndarray) -> str:
    return " ".join(f"{_number(point[0])},{_number(point[1])}" for point in vertices)


def _path(vertices: np.ndarray) -> str:
    if len(vertices) == 0:
        return ""
    commands = [f"M {_number(vertices[0, 0])} {_number(vertices[0, 1])}"]
    commands.extend(f"L {_number(point[0])} {_number(point[1])}" for point in vertices[1:])
    commands.append("Z")
    return " ".join(commands)


def create_cricut_svg(tiling: Dict[str, Any]) -> BytesIO:
    """Create one SVG containing stacked, individually grouped print pages.

    Every page contains an ``artwork`` group (fills + words) and a ``cut-lines``
    group (one closed path per physical piece).  The SVG viewBox uses inches as
    its logical unit, so the selected PDF tile-edge scale is preserved when the
    file is imported at 100% size.
    """
    settings = tiling["settings"]
    (page_w, page_h), pages = layout_piece_pages(tiling)
    page_count = len(pages)
    total_h = page_count * page_h + max(0, page_count - 1) * PAGE_GAP_INCHES
    cut_width = float(settings["cut_line_width_mm"]) / 25.4
    cut_color = settings["border_color"] if settings["border_color"] != "transparent" else "#000000"

    lines: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_number(page_w)}in" '
            f'height="{_number(total_h)}in" viewBox="0 0 {_number(page_w)} {_number(total_h)}">'
        ),
        "  <title>Penrose Word Match - Cricut cut sheets</title>",
        "  <desc>Page groups contain printable artwork and separate machine cut-line paths.</desc>",
    ]

    for page_index, placements in enumerate(pages):
        page_offset = page_index * (page_h + PAGE_GAP_INCHES)
        page_id = page_index + 1
        lines.append(f'  <g id="page-{page_id}" data-page="{page_id}" transform="translate(0 {_number(page_offset)})">')
        lines.append(f'    <g id="page-{page_id}-artwork" class="artwork">')
        prepared = []
        for tile, scale, translation in placements:
            source = np.asarray(tile["vertices"], dtype=float)
            placed = source * scale + translation
            # PDF geometry is y-up; SVG is y-down within each physical page.
            svg_vertices = np.column_stack((placed[:, 0], page_h - placed[:, 1]))
            prepared.append((tile, scale, translation, svg_vertices))
            fill = settings["acute_color"] if tile["type"] == "acute" else settings["obtuse_color"]
            fill_value = "none" if fill == "transparent" else fill
            lines.append(
                f'      <polygon id="piece-{tile["id"]}-art" class="piece-art" points="{_points(svg_vertices)}" '
                f'fill="{escape(fill_value)}" stroke="none"/>'
            )
            for edge in tile["edges"]:
                label = edge.get("label")
                if not label:
                    continue
                font_size = float(label["font_size"]) * scale
                if font_size * 72.0 < 3.5:
                    continue
                source_position = np.asarray(label["position"], dtype=float)
                placed_position = source_position * scale + translation
                x, y = float(placed_position[0]), page_h - float(placed_position[1])
                text = escape(str(label["text"]))
                lines.append(
                    f'      <text class="word-label" x="{_number(x)}" y="{_number(y)}" '
                    f'font-family="Arial, sans-serif" font-size="{_number(font_size)}" text-anchor="middle" '
                    f'dominant-baseline="central" fill="#172033" '
                    f'transform="rotate({_number(-float(label["angle"]))} {_number(x)} {_number(y)})">{text}</text>'
                )
        lines.append("    </g>")
        lines.append(
            f'    <g id="page-{page_id}-cut-lines" class="cut-lines" data-operation="cut" fill="none" '
            f'stroke="{escape(cut_color)}" stroke-width="{_number(cut_width)}" stroke-linejoin="round">'
        )
        for tile, _scale, _translation, svg_vertices in prepared:
            lines.append(
                f'      <path id="piece-{tile["id"]}-cut" class="cut-piece" data-piece-id="{tile["id"]}" '
                f'd="{_path(svg_vertices)}"/>'
            )
        lines.append("    </g>")
        lines.append("  </g>")

    lines.append("</svg>")
    data = ("\n".join(lines) + "\n").encode("utf-8")
    output = BytesIO(data)
    output.page_count = page_count  # type: ignore[attr-defined]
    output.piece_count = len(tiling["tiles"])  # type: ignore[attr-defined]
    output.seek(0)
    return output
