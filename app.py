"""Flask entry point for the Penrose Word Match application."""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request, send_file

from pdf_generator import create_tiles_pdf
from penrose_engine import generate_tiling
from svg_generator import create_cricut_svg


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {}
    return data


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/generate")
def generate():
    data = _payload()
    word_source = data.get("word_pairs", data.get("word_text", ""))
    return jsonify(generate_tiling(data.get("settings", data), word_source))


@app.post("/export_pdf")
def export_pdf():
    data = _payload()
    word_source = data.get("word_pairs", data.get("word_text", ""))
    tiling = generate_tiling(data.get("settings", data), word_source)
    document = create_tiles_pdf(tiling)
    response = send_file(
        document,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="penrose_word_pieces.pdf",
        max_age=0,
    )
    response.headers["X-Penrose-Page-Count"] = str(getattr(document, "page_count", 0))
    response.headers["X-Penrose-Piece-Count"] = str(getattr(document, "piece_count", 0))
    response.headers["X-Penrose-Max-Per-Page"] = str(getattr(document, "max_pieces_per_page", 0))
    return response


@app.post("/export_svg")
def export_svg():
    data = _payload()
    word_source = data.get("word_pairs", data.get("word_text", ""))
    tiling = generate_tiling(data.get("settings", data), word_source)
    document = create_cricut_svg(tiling)
    response = send_file(
        document,
        mimetype="image/svg+xml",
        as_attachment=True,
        download_name="penrose_cricut_pieces.svg",
        max_age=0,
    )
    response.headers["X-Penrose-Page-Count"] = str(getattr(document, "page_count", 0))
    response.headers["X-Penrose-Piece-Count"] = str(getattr(document, "piece_count", 0))
    return response


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "The request is larger than the 2 MB local safety limit."}), 413


@app.errorhandler(Exception)
def handle_error(error):
    app.logger.exception("Request failed")
    return jsonify({"error": str(error) or "Generation failed."}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
