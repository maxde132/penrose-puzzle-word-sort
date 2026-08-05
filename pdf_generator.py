"""Vector PDF output with one-piece and paper-saving packed layouts."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Polygon


PAGE_SIZES = {
    "letter": (8.5, 11.0),
    "a4": (8.2677, 11.6929),
}


def _paint(value: str) -> str:
    return "none" if value == "transparent" else value


def _one_piece_pages(
    tiles: List[Dict[str, Any]], page_size: Tuple[float, float]
) -> List[List[Tuple[Dict[str, Any], float, np.ndarray]]]:
    """Place exactly one piece on each page, scaled into an 80% fitting box."""
    page_w, page_h = page_size
    pages: List[List[Tuple[Dict[str, Any], float, np.ndarray]]] = []
    for tile in tiles:
        source = np.asarray(tile["vertices"], dtype=float)
        low, high = source.min(axis=0), source.max(axis=0)
        extent = high - low
        scale = min((page_w * 0.80) / max(extent[0], 1e-9), (page_h * 0.80) / max(extent[1], 1e-9))
        target_center = np.array([page_w / 2.0, page_h / 2.0])
        translation = target_center - ((low + high) / 2.0) * scale
        pages.append([(tile, scale, translation)])
    return pages


def _packed_pages(
    tiles: List[Dict[str, Any]], page_size: Tuple[float, float], edge_inches: float
) -> List[List[Tuple[Dict[str, Any], float, np.ndarray]]]:
    """First-fit decreasing shelf packing at an exact physical edge scale.

    Pentagrid rhombs use unit-length sides, so ``edge_inches`` is directly the
    printed length of an unclipped tile edge.  Edge fragments preserve the same
    scale and therefore reconnect physically with their neighboring pieces.
    """
    page_w, page_h = page_size
    margin, gutter = 0.30, 0.11
    usable_w, usable_h = page_w - 2.0 * margin, page_h - 2.0 * margin
    items = []
    for tile in tiles:
        source = np.asarray(tile["vertices"], dtype=float)
        low, high = source.min(axis=0), source.max(axis=0)
        extent = high - low
        packed_w = float(extent[0]) * edge_inches + 2.0 * gutter
        packed_h = float(extent[1]) * edge_inches + 2.0 * gutter
        if packed_w > usable_w + 1e-9 or packed_h > usable_h + 1e-9:
            raise ValueError(
                f"The {edge_inches:g} inch scale is too large for {page_w:g} x {page_h:g} inch paper."
            )
        items.append(
            {
                "tile": tile,
                "low": low,
                "width": packed_w,
                "height": packed_h,
            }
        )

    # Large pieces establish shelves first; small clipped boundary pieces fill
    # the remaining gaps instead of consuming whole pages.
    items.sort(key=lambda item: (-item["height"], -item["width"], item["tile"]["id"]))
    page_states: List[Dict[str, Any]] = []

    def place_on_shelf(page: Dict[str, Any], item: Dict[str, Any], shelf: Dict[str, float]) -> None:
        x = shelf["x"]
        y = shelf["y"]
        shelf["x"] += item["width"]
        content_origin = np.array([margin + x + gutter, margin + y + gutter])
        translation = content_origin - item["low"] * edge_inches
        page["placements"].append((item["tile"], edge_inches, translation))

    for item in items:
        placed = False
        for page in page_states:
            candidates = [
                shelf
                for shelf in page["shelves"]
                if item["height"] <= shelf["height"] + 1e-9
                and shelf["x"] + item["width"] <= usable_w + 1e-9
            ]
            if candidates:
                shelf = min(candidates, key=lambda candidate: usable_w - candidate["x"] - item["width"])
                place_on_shelf(page, item, shelf)
                placed = True
                break
            if page["height_used"] + item["height"] <= usable_h + 1e-9:
                shelf = {"x": 0.0, "y": page["height_used"], "height": item["height"]}
                page["shelves"].append(shelf)
                page["height_used"] += item["height"]
                place_on_shelf(page, item, shelf)
                placed = True
                break
        if not placed:
            page = {"placements": [], "shelves": [], "height_used": 0.0}
            shelf = {"x": 0.0, "y": 0.0, "height": item["height"]}
            page["shelves"].append(shelf)
            page["height_used"] = item["height"]
            place_on_shelf(page, item, shelf)
            page_states.append(page)

    return [page["placements"] for page in page_states]


def _draw_piece(
    axes: Any,
    tile: Dict[str, Any],
    settings: Dict[str, Any],
    scale: float,
    translation: np.ndarray,
) -> None:
    source = np.asarray(tile["vertices"], dtype=float)
    vertices = source * scale + translation
    fill = settings["acute_color"] if tile["type"] == "acute" else settings["obtuse_color"]
    border = _paint(settings["border_color"])
    # Matplotlib line widths are points; convert the dedicated physical cut
    # thickness from millimeters so printouts are predictable at every scale.
    line_width = settings["cut_line_width_mm"] * 72.0 / 25.4 if border != "none" else 0.0
    axes.add_patch(
        Polygon(
            vertices,
            closed=True,
            facecolor=_paint(fill),
            edgecolor=border,
            linewidth=line_width,
            joinstyle="miter",
        )
    )

    for edge in tile["edges"]:
        label = edge.get("label")
        if not label:
            continue
        source_position = np.asarray(label["position"], dtype=float)
        position = source_position * scale + translation
        maximum_points = label["max_width"] * scale * 72.0
        base_points = label["font_size"] * scale * 72.0
        fit_points = maximum_points / max(1.0, 0.58 * len(label["text"]))
        # The cap is 10% larger than the previous 26 pt maximum.
        font_size = min(28.6, base_points, fit_points)
        if font_size < 3.5:
            continue
        axes.text(
            position[0],
            position[1],
            label["text"],
            ha="center",
            va="center",
            rotation=label["angle"],
            rotation_mode="anchor",
            fontsize=font_size,
            color="#172033",
            clip_on=True,
        )


def layout_piece_pages(
    tiling: Dict[str, Any]
) -> Tuple[Tuple[float, float], List[List[Tuple[Dict[str, Any], float, np.ndarray]]]]:
    """Return the physical page size and piece placements used by PDF/SVG."""
    settings = tiling["settings"]
    page_size = PAGE_SIZES[settings["paper_size"]]
    edge_inches = float(settings["pdf_scale"])
    if edge_inches <= 0.0:
        pages = _one_piece_pages(tiling["tiles"], page_size)
    else:
        pages = _packed_pages(tiling["tiles"], page_size, edge_inches)
    return page_size, pages


def create_tiles_pdf(tiling: Dict[str, Any]) -> BytesIO:
    """Render cut-out pieces to vector PDF pages using the selected scale."""
    output = BytesIO()
    settings = tiling["settings"]
    page_size, pages = layout_piece_pages(tiling)

    with PdfPages(output, metadata={"Title": "Penrose word-matching pieces", "Creator": "Penrose Word Match"}) as pdf:
        for placements in pages:
            page_w, page_h = page_size
            figure = plt.figure(figsize=page_size)
            axes = figure.add_axes([0.0, 0.0, 1.0, 1.0])
            axes.set_xlim(0.0, page_w)
            axes.set_ylim(0.0, page_h)
            axes.set_aspect("equal", adjustable="box")
            axes.axis("off")
            for tile, scale, translation in placements:
                _draw_piece(axes, tile, settings, scale, translation)
            pdf.savefig(figure, dpi=144, facecolor="white")
            plt.close(figure)

    output.seek(0)
    output.page_count = len(pages)  # type: ignore[attr-defined]
    output.piece_count = len(tiling["tiles"])  # type: ignore[attr-defined]
    output.max_pieces_per_page = max((len(page) for page in pages), default=0)  # type: ignore[attr-defined]
    return output
