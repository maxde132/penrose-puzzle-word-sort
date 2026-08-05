"""Deterministic Penrose P3 rhomb tiling and word-assignment engine.

The implementation uses de Bruijn's pentagrid construction.  Five families of
parallel lines are intersected in the primal grid.  Every two-line crossing is
dual to one unit-edge rhomb whose sides point in two of the five star
directions.  The two possible acute angles are 36 and 72 degrees, which are the
thin (``acute`` here) and thick (``obtuse`` here) P3 rhombi.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from shapely.geometry import Polygon as ShapelyPolygon


PHI = (1.0 + math.sqrt(5.0)) / 2.0
DEFAULTS: Dict[str, Any] = {
    "density": 4,
    "border_width": 1.2,
    "border_color": "#203047",
    "acute_color": "#f2bd4b",
    "obtuse_color": "#69b9ad",
    "style": 0.5,
    "graphic_size": 1280,
    "rotation": 0,
    "edge_smoothing": True,
    "silhouette": "decagon",
    "paper_size": "letter",
    "pdf_scale": 1.5,
    "cut_line_width_mm": 0.4,
}
GRAPHIC_SIZES = (640, 1280, 2048, 4096, 8192)
ROTATIONS = (0, 90, 180, 270)
SILHOUETTES = ("decagon", "pentagon", "star", "square")
PAPER_SIZES = ("letter", "a4")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _number(value: Any, fallback: float) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback


def _color(value: Any, fallback: str) -> str:
    """Accept #RGB/#RRGGBB or the explicit transparent sentinel."""
    if value is None:
        return fallback
    if str(value).lower() in {"transparent", "none"}:
        return "transparent"
    candidate = str(value).strip()
    if len(candidate) in (4, 7) and candidate.startswith("#"):
        try:
            int(candidate[1:], 16)
            return candidate.lower()
        except ValueError:
            pass
    return fallback


def normalize_settings(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a safe, JSON-friendly settings object."""
    raw = raw or {}
    density = int(round(_number(raw.get("density"), DEFAULTS["density"])))
    graphic_size = int(round(_number(raw.get("graphic_size"), DEFAULTS["graphic_size"])))
    rotation = int(round(_number(raw.get("rotation"), DEFAULTS["rotation"])))
    if graphic_size not in GRAPHIC_SIZES:
        graphic_size = DEFAULTS["graphic_size"]
    if rotation not in ROTATIONS:
        rotation = DEFAULTS["rotation"]
    smoothing_value = raw.get("edge_smoothing", DEFAULTS["edge_smoothing"])
    if isinstance(smoothing_value, str):
        edge_smoothing = smoothing_value.strip().lower() not in {"0", "false", "no", "off"}
    else:
        edge_smoothing = bool(smoothing_value)
    silhouette = str(raw.get("silhouette", DEFAULTS["silhouette"])).lower()
    if silhouette not in SILHOUETTES:
        silhouette = DEFAULTS["silhouette"]
    paper_size = str(raw.get("paper_size", DEFAULTS["paper_size"])).lower()
    if paper_size not in PAPER_SIZES:
        paper_size = DEFAULTS["paper_size"]
    pdf_scale = _number(raw.get("pdf_scale"), DEFAULTS["pdf_scale"])
    # Zero is the backwards-compatible one-piece-per-page auto-fit mode.
    if abs(pdf_scale) < 1e-9:
        pdf_scale = 0.0
    else:
        pdf_scale = round(_clamp(pdf_scale, 0.75, 4.0), 2)
    cut_line_width_mm = round(
        _clamp(_number(raw.get("cut_line_width_mm"), DEFAULTS["cut_line_width_mm"]), 0.1, 2.0), 1
    )
    return {
        "density": int(_clamp(density, 1, 8)),
        "border_width": round(_clamp(_number(raw.get("border_width"), 1.2), 0.0, 5.0), 1),
        "border_color": _color(raw.get("border_color"), DEFAULTS["border_color"]),
        "acute_color": _color(raw.get("acute_color"), DEFAULTS["acute_color"]),
        "obtuse_color": _color(raw.get("obtuse_color"), DEFAULTS["obtuse_color"]),
        "style": round(_clamp(_number(raw.get("style"), 0.5), 0.1, 0.9), 2),
        "graphic_size": graphic_size,
        "rotation": rotation,
        "edge_smoothing": edge_smoothing,
        "silhouette": silhouette,
        "paper_size": paper_size,
        "pdf_scale": pdf_scale,
        "cut_line_width_mm": cut_line_width_mm,
    }


def parse_word_pairs(source: Any) -> List[Tuple[str, str]]:
    """Parse pairs supplied as nested arrays or comma/pipe-delimited text."""
    pairs: List[Tuple[str, str]] = []
    if isinstance(source, str):
        rows: Iterable[Any] = source.splitlines()
    elif isinstance(source, list):
        rows = source
    else:
        return pairs

    for row in rows:
        left = right = ""
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            left, right = str(row[0]), str(row[1])
        elif isinstance(row, dict):
            left = str(row.get("left", row.get("first", "")))
            right = str(row.get("right", row.get("second", "")))
        else:
            line = str(row).strip()
            if not line or line.startswith("#"):
                continue
            in_quotes = False
            has_unquoted_pipe = False
            for character in line:
                if character == '"':
                    in_quotes = not in_quotes
                elif character == "|" and not in_quotes:
                    has_unquoted_pipe = True
                    break
            separator = "|" if has_unquoted_pipe else ","
            if separator not in line:
                continue
            try:
                fields = next(csv.reader([line], delimiter=separator, skipinitialspace=True))
            except csv.Error:
                continue
            if len(fields) < 2:
                continue
            left, right = fields[0], fields[1]
        left, right = left.strip(), right.strip()
        if left and right:
            # Keep the UI/PDF responsive when somebody pastes a huge field.
            pairs.append((left[:120], right[:120]))
    return pairs[:10000]


def _signed_area(vertices: np.ndarray) -> float:
    x, y = vertices[:, 0], vertices[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - y * np.roll(x, -1)))


def _ensure_ccw(vertices: np.ndarray) -> np.ndarray:
    return vertices if _signed_area(vertices) > 0 else vertices[::-1].copy()


def _polygon_centroid(vertices: np.ndarray) -> np.ndarray:
    """Area-weighted centroid of a simple polygon."""
    cross = vertices[:, 0] * np.roll(vertices[:, 1], -1) - np.roll(vertices[:, 0], -1) * vertices[:, 1]
    area_six = 3.0 * float(np.sum(cross))
    if abs(area_six) < 1e-12:
        return vertices.mean(axis=0)
    return np.array(
        [
            float(np.sum((vertices[:, 0] + np.roll(vertices[:, 0], -1)) * cross)) / area_six,
            float(np.sum((vertices[:, 1] + np.roll(vertices[:, 1], -1)) * cross)) / area_six,
        ]
    )


def _outline_polygon(kind: str, radius: float) -> np.ndarray:
    """Return the selected clean clipping silhouette."""
    if kind == "square":
        # A slightly expanded half-side keeps square patches comparable in
        # area/tile count to the decagonal crop at the same density.
        half_side = radius * 0.88
        return np.asarray(
            [
                [-half_side, -half_side],
                [half_side, -half_side],
                [half_side, half_side],
                [-half_side, half_side],
            ],
            dtype=float,
        )
    count = 5 if kind == "pentagon" else 10
    points: List[List[float]] = []
    for index in range(count):
        angle = math.pi / 2.0 + 2.0 * math.pi * index / count
        point_radius = radius
        if kind == "star" and index % 2:
            point_radius *= 0.52
        points.append([point_radius * math.cos(angle), point_radius * math.sin(angle)])
    return _ensure_ccw(np.asarray(points, dtype=float))


def _cross_2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(first[0] * second[1] - first[1] * second[0])


def _clean_polygon(vertices: Sequence[np.ndarray]) -> np.ndarray:
    """Remove numerical duplicate and collinear vertices after clipping."""
    cleaned: List[np.ndarray] = []
    for point in vertices:
        point = np.asarray(point, dtype=float)
        if not cleaned or float(np.linalg.norm(point - cleaned[-1])) > 1e-8:
            cleaned.append(point)
    if len(cleaned) > 1 and float(np.linalg.norm(cleaned[0] - cleaned[-1])) <= 1e-8:
        cleaned.pop()
    changed = True
    while changed and len(cleaned) >= 3:
        changed = False
        for index in range(len(cleaned)):
            previous = cleaned[index - 1]
            current = cleaned[index]
            following = cleaned[(index + 1) % len(cleaned)]
            if abs(_cross_2d(current - previous, following - current)) <= 1e-9:
                cleaned.pop(index)
                changed = True
                break
    if len(cleaned) < 3:
        return np.empty((0, 2), dtype=float)
    return _ensure_ccw(np.vstack(cleaned))


def _clip_convex_polygon(subject: np.ndarray, clip_polygon: np.ndarray) -> np.ndarray:
    """Sutherland-Hodgman intersection of two CCW convex polygons."""
    output = [point.copy() for point in subject]
    for clip_index in range(len(clip_polygon)):
        clip_start = clip_polygon[clip_index]
        clip_end = clip_polygon[(clip_index + 1) % len(clip_polygon)]
        clip_vector = clip_end - clip_start
        input_points = output
        output = []
        if not input_points:
            break

        def inside(point: np.ndarray) -> bool:
            return _cross_2d(clip_vector, point - clip_start) >= -1e-9

        def intersection(start: np.ndarray, end: np.ndarray) -> np.ndarray:
            segment = end - start
            denominator = _cross_2d(segment, clip_vector)
            if abs(denominator) < 1e-12:
                return end.copy()
            amount = _cross_2d(clip_start - start, clip_vector) / denominator
            return start + amount * segment

        previous = input_points[-1]
        previous_inside = inside(previous)
        for current in input_points:
            current_inside = inside(current)
            if current_inside:
                if not previous_inside:
                    output.append(intersection(previous, current))
                output.append(current)
            elif previous_inside:
                output.append(intersection(previous, current))
            previous, previous_inside = current, current_inside
    return _clean_polygon(output)


def _clip_to_outline(subject: np.ndarray, outline: np.ndarray, kind: str) -> List[np.ndarray]:
    """Clip a rhomb to a convex outline or a concave five-point star."""
    if kind != "star":
        clipped = _clip_convex_polygon(subject, outline)
        return [clipped] if len(clipped) >= 3 else []

    intersection = ShapelyPolygon(subject).intersection(ShapelyPolygon(outline))
    if intersection.is_empty:
        return []
    geometries = [intersection] if intersection.geom_type == "Polygon" else list(intersection.geoms)
    fragments: List[np.ndarray] = []
    for geometry in geometries:
        if geometry.geom_type != "Polygon" or geometry.area < 1e-8:
            continue
        vertices = _clean_polygon(np.asarray(geometry.exterior.coords[:-1], dtype=float))
        if len(vertices) >= 3:
            fragments.append(vertices)
    return fragments


def _pentagrid_tiles(
    density: int, outline: Optional[np.ndarray] = None, outline_kind: str = "decagon"
) -> List[Dict[str, Any]]:
    """Create a cropped patch of the dual of a generic five-grid.

    ``gamma`` offsets avoid triple intersections.  At a crossing of line k in
    family i and line m in family j, the four surrounding pentagrid cells map
    to B, B+u_i, B+u_i+u_j and B+u_j.  Those are exactly one P3 rhomb.
    """
    directions = np.array(
        [[math.cos(2.0 * math.pi * j / 5.0), math.sin(2.0 * math.pi * j / 5.0)] for j in range(5)],
        dtype=float,
    )
    offsets = np.array([0.173, 0.337, -0.221, 0.119, -0.408], dtype=float)
    # The crop radius grows linearly; area (and therefore tile count) grows
    # approximately quadratically, keeping level 8 interactive and printable.
    radius = 1.8 + float(density)
    candidate_radius = radius if outline is None else float(np.max(np.linalg.norm(outline, axis=1))) + 1.1
    line_limit = int(math.ceil(2.0 * candidate_radius + 4.0))
    tiles: List[Dict[str, Any]] = []

    for i in range(5):
        for j in range(i + 1, 5):
            matrix = np.vstack((directions[i], directions[j]))
            inverse = np.linalg.inv(matrix)
            for line_i in range(-line_limit, line_limit + 1):
                for line_j in range(-line_limit, line_limit + 1):
                    crossing = inverse @ np.array(
                        [line_i + offsets[i], line_j + offsets[j]], dtype=float
                    )
                    cell: List[int] = []
                    for family in range(5):
                        if family == i:
                            cell.append(line_i - 1)
                        elif family == j:
                            cell.append(line_j - 1)
                        else:
                            value = float(np.dot(directions[family], crossing) - offsets[family])
                            cell.append(math.floor(value + 1e-9))
                    base = np.asarray(cell, dtype=float) @ directions
                    vertices = np.array(
                        [
                            base,
                            base + directions[i],
                            base + directions[i] + directions[j],
                            base + directions[j],
                        ],
                        dtype=float,
                    )
                    centroid = vertices.mean(axis=0)
                    if float(np.dot(centroid, centroid)) > candidate_radius * candidate_radius:
                        continue
                    vertices = _ensure_ccw(vertices)
                    original_area = abs(_signed_area(vertices))
                    if outline is not None:
                        fragments = _clip_to_outline(vertices, outline, outline_kind)
                    else:
                        fragments = [vertices]
                    acute_angle = math.degrees(
                        math.acos(_clamp(abs(float(np.dot(directions[i], directions[j]))), -1.0, 1.0))
                    )
                    for fragment in fragments:
                        clipped_area = abs(_signed_area(fragment))
                        if clipped_area < 1e-6:
                            continue
                        edge_piece = clipped_area < original_area - 1e-7
                        tiles.append(
                            {
                                "vertices": fragment,
                                "centroid": _polygon_centroid(fragment),
                                "type": "acute" if acute_angle < 54.0 else "obtuse",
                                "edge_piece": edge_piece,
                                "area_ratio": clipped_area / original_area,
                            }
                        )

    # A stable tile id is important because it defines Tile A versus Tile B.
    tiles.sort(
        key=lambda tile: (
            round(float(tile["centroid"][0]), 8),
            round(float(tile["centroid"][1]), 8),
            tile["type"],
        )
    )
    for tile_id, tile in enumerate(tiles):
        tile["id"] = tile_id
        tile["edge_words"] = [None] * len(tile["vertices"])
        tile["edge_internal"] = [False] * len(tile["vertices"])
    return tiles


def _point_key(point: Sequence[float]) -> Tuple[float, float]:
    return round(float(point[0]), 7), round(float(point[1]), 7)


def _edge_key(a: Sequence[float], b: Sequence[float]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    p, q = _point_key(a), _point_key(b)
    return (p, q) if p <= q else (q, p)


def _build_adjacency(tiles: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    buckets: Dict[Any, List[Tuple[int, int]]] = defaultdict(list)
    for tile in tiles:
        vertices = tile["vertices"]
        for edge_index in range(len(vertices)):
            buckets[_edge_key(vertices[edge_index], vertices[(edge_index + 1) % len(vertices)])].append(
                (tile["id"], edge_index)
            )

    internal: List[Dict[str, Any]] = []
    boundary_count = 0
    for key, owners in buckets.items():
        if len(owners) == 2:
            p, q = np.asarray(key[0]), np.asarray(key[1])
            internal.append(
                {
                    "midpoint": (p + q) / 2.0,
                    "owners": sorted(owners, key=lambda item: (item[0], item[1])),
                }
            )
            for tile_id, edge_index in owners:
                tiles[tile_id]["edge_internal"][edge_index] = True
        elif len(owners) == 1:
            boundary_count += 1
        else:
            raise RuntimeError("Pentagrid produced a non-manifold edge")
    internal.sort(
        key=lambda edge: (
            round(float(edge["midpoint"][0]), 8),
            round(float(edge["midpoint"][1]), 8),
        )
    )
    return internal, boundary_count


def _assign_words(
    tiles: List[Dict[str, Any]], internal_edges: List[Dict[str, Any]], pairs: List[Tuple[str, str]]
) -> None:
    """Assign pair halves to deterministic A/B sides of every shared edge."""
    if not pairs:
        return
    for index, shared in enumerate(internal_edges):
        first, second = pairs[index % len(pairs)]
        owner_a, owner_b = shared["owners"]
        tiles[owner_a[0]]["edge_words"][owner_a[1]] = first
        tiles[owner_b[0]]["edge_words"][owner_b[1]] = second


def _rotate(point: np.ndarray, degrees: int) -> np.ndarray:
    if degrees == 0:
        return point.copy()
    radians = math.radians(degrees)
    matrix = np.array(
        [[math.cos(radians), -math.sin(radians)], [math.sin(radians), math.cos(radians)]],
        dtype=float,
    )
    return point @ matrix.T


def _line_span(point: np.ndarray, direction: np.ndarray, polygon: np.ndarray) -> Tuple[float, float]:
    """Return signed intersections of an infinite line with a convex polygon."""
    hits: List[float] = []
    for index in range(len(polygon)):
        a = polygon[index]
        segment = polygon[(index + 1) % len(polygon)] - a
        denominator = direction[0] * segment[1] - direction[1] * segment[0]
        if abs(denominator) < 1e-10:
            continue
        delta = a - point
        distance = (delta[0] * segment[1] - delta[1] * segment[0]) / denominator
        along_segment = (delta[0] * direction[1] - delta[1] * direction[0]) / denominator
        if -1e-8 <= along_segment <= 1.0 + 1e-8:
            hits.append(float(distance))
    if not hits:
        return 0.0, 0.0
    return min(hits), max(hits)


def _readable_angle(vector: np.ndarray) -> float:
    angle = math.degrees(math.atan2(float(vector[1]), float(vector[0])))
    normalized = angle % 360.0
    if 90.0 < normalized <= 270.0:
        angle += 180.0
    return ((angle + 180.0) % 360.0) - 180.0


def _round_point(point: np.ndarray) -> List[float]:
    return [round(float(point[0]), 7), round(float(point[1]), 7)]


def _labels_overlap(first: Dict[str, Any], second: Dict[str, Any], scale: float) -> bool:
    """Conservative separating-axis test for two rotated text rectangles."""
    def box(label: Dict[str, Any]):
        angle = math.radians(float(label["angle"]))
        tangent = np.array([math.cos(angle), math.sin(angle)])
        normal = np.array([-tangent[1], tangent[0]])
        font_size = float(label["font_size"]) * scale
        width = min(float(label["max_width"]), 0.58 * len(label["text"]) * font_size)
        # A little breathing room makes real font metrics safer than the model.
        return np.asarray(label["position"], dtype=float), tangent, normal, width * 0.54, font_size * 0.60

    center_a, tangent_a, normal_a, half_w_a, half_h_a = box(first)
    center_b, tangent_b, normal_b, half_w_b, half_h_b = box(second)
    delta = center_b - center_a
    for axis in (tangent_a, normal_a, tangent_b, normal_b):
        reach_a = half_w_a * abs(float(np.dot(tangent_a, axis))) + half_h_a * abs(float(np.dot(normal_a, axis)))
        reach_b = half_w_b * abs(float(np.dot(tangent_b, axis))) + half_h_b * abs(float(np.dot(normal_b, axis)))
        if abs(float(np.dot(delta, axis))) >= reach_a + reach_b:
            return False
    return True


def _fit_tile_labels(edges: List[Dict[str, Any]]) -> None:
    """Uniformly shrink a tile's labels until their rotated boxes are disjoint."""
    labels = [edge["label"] for edge in edges if edge.get("label")]
    if len(labels) < 2:
        return

    def collides(scale: float) -> bool:
        for first_index in range(len(labels)):
            for second_index in range(first_index + 1, len(labels)):
                if _labels_overlap(labels[first_index], labels[second_index], scale):
                    return True
        return False

    if not collides(1.0):
        return
    low, high = 0.05, 1.0
    for _ in range(18):
        middle = (low + high) / 2.0
        if collides(middle):
            high = middle
        else:
            low = middle
    safe_scale = low * 0.94
    for label in labels:
        label["font_size"] = round(float(label["font_size"]) * safe_scale, 7)


def _serialize_tiles(
    tiles: List[Dict[str, Any]], settings: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], int, Dict[str, float]]:
    all_points = np.vstack([tile["vertices"] for tile in tiles])
    width = float(np.ptp(all_points[:, 0]))
    height = float(np.ptp(all_points[:, 1]))
    padding = 0.65
    scale_px = settings["graphic_size"] / max(width + 2 * padding, height + 2 * padding)
    skipped = 0
    result: List[Dict[str, Any]] = []

    for tile in tiles:
        vertices = tile["vertices"]
        centroid = _polygon_centroid(vertices)
        edges: List[Dict[str, Any]] = []
        for edge_index in range(len(vertices)):
            start = vertices[edge_index]
            end = vertices[(edge_index + 1) % len(vertices)]
            edge_vector = end - start
            edge_length = float(np.linalg.norm(edge_vector))
            tangent = edge_vector / edge_length
            midpoint = (start + end) / 2.0
            inward = np.array([-tangent[1], tangent[0]])
            if float(np.dot(inward, centroid - midpoint)) < 0:
                inward = -inward
            center_distance = max(0.0, float(np.dot(centroid - midpoint, inward)))
            # Map the style control to a practical 6.8%-13.2% of edge length,
            # then clamp before the centroid.  The default is exactly 10%,
            # matching the requested 10%-15% convention.  Staying below the
            # thin rhomb's inradius also keeps adjacent label anchors distinct.
            requested_distance = edge_length * (0.06 + 0.08 * settings["style"])
            inward_distance = min(requested_distance, center_distance * 0.90)
            text_position = midpoint + inward * inward_distance
            low_w, high_w = _line_span(text_position, tangent, vertices)
            low_h, high_h = _line_span(text_position, inward, vertices)
            safe_width = max(0.0, 2.0 * min(abs(low_w), abs(high_w)) * 0.86)
            safe_height = max(0.0, 2.0 * min(abs(low_h), abs(high_h)) * 0.72)
            word = tile["edge_words"][edge_index]
            # Requested typography increase: 10% over the original 0.15/0.55
            # sizing, with the existing polygon and collision constraints kept.
            font_size_units = min(edge_length * 0.165, safe_height * 0.605)
            render_full = bool(word)
            if word:
                estimated_fit = safe_width / max(1.0, 0.58 * len(word))
                font_size_units = min(font_size_units, estimated_fit)
            edge_data: Dict[str, Any] = {
                "index": edge_index,
                "start": _round_point(start),
                "end": _round_point(end),
                "midpoint": _round_point(midpoint),
                "unit_vector": _round_point(tangent),
                "length": round(edge_length, 7),
                "boundary": not tile["edge_internal"][edge_index],
                "label": None,
            }
            if word:
                edge_data["label"] = {
                    "text": word,
                    "position": _round_point(text_position),
                    "angle": round(_readable_angle(tangent), 5),
                    "inward_normal": _round_point(inward),
                    "max_width": round(safe_width, 7),
                    "font_size": round(font_size_units, 7),
                    "render_full_tiling": render_full,
                }
            edges.append(edge_data)
        _fit_tile_labels(edges)
        for edge in edges:
            label = edge.get("label")
            if label and label["font_size"] * scale_px < 4.5:
                label["render_full_tiling"] = False
                skipped += 1
        result.append(
            {
                "id": tile["id"],
                "type": tile["type"],
                "edge_piece": tile["edge_piece"],
                "area_ratio": round(float(tile["area_ratio"]), 6),
                "vertices": [_round_point(point) for point in vertices],
                "centroid": _round_point(centroid),
                "edges": edges,
            }
        )

    all_points = np.vstack([tile["vertices"] for tile in tiles])
    bounds = {
        "min_x": round(float(np.min(all_points[:, 0])) - padding, 7),
        "min_y": round(float(np.min(all_points[:, 1])) - padding, 7),
        "max_x": round(float(np.max(all_points[:, 0])) + padding, 7),
        "max_y": round(float(np.max(all_points[:, 1])) + padding, 7),
    }
    bounds["width"] = round(bounds["max_x"] - bounds["min_x"], 7)
    bounds["height"] = round(bounds["max_y"] - bounds["min_y"], 7)
    return result, skipped, bounds


def generate_tiling(raw_settings: Optional[Dict[str, Any]], word_source: Any = None) -> Dict[str, Any]:
    """Generate one complete API response."""
    settings = normalize_settings(raw_settings)
    pairs = parse_word_pairs(word_source)
    radius = 1.8 + float(settings["density"])
    outline = _outline_polygon(settings["silhouette"], radius) if settings["edge_smoothing"] else None
    tiles = _pentagrid_tiles(settings["density"], outline, settings["silhouette"])
    internal_edges, boundary_edges = _build_adjacency(tiles)
    _assign_words(tiles, internal_edges, pairs)

    if settings["rotation"]:
        for tile in tiles:
            tile["vertices"] = _rotate(tile["vertices"], settings["rotation"])
            tile["centroid"] = _polygon_centroid(tile["vertices"])
        if outline is not None:
            outline = _rotate(outline, settings["rotation"])

    serialized, skipped, bounds = _serialize_tiles(tiles, settings)
    acute_count = sum(tile["type"] == "acute" for tile in tiles)
    edge_piece_count = sum(bool(tile["edge_piece"]) for tile in tiles)
    warnings: List[str] = []
    if not pairs:
        warnings.append("No valid word pairs were supplied; the tiling was rendered without labels.")
    if skipped:
        warnings.append(
            f"{skipped} labels were hidden in the full-tiling preview because they would be too small; PDF tile pages still include them."
        )
    return {
        "settings": settings,
        "bounds": bounds,
        "outline": None if outline is None else [_round_point(point) for point in outline],
        "tiles": serialized,
        "stats": {
            "tiles": len(tiles),
            "acute_tiles": acute_count,
            "obtuse_tiles": len(tiles) - acute_count,
            "internal_edges": len(internal_edges),
            "boundary_edges": boundary_edges,
            "edge_pieces": edge_piece_count,
            "word_pairs": len(pairs),
            "skipped_preview_labels": skipped,
        },
        "warnings": warnings,
    }
