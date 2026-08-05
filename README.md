#Vibe coded ;)
# Penrose Word Match

A self-contained Flask application that generates de Bruijn pentagrid Penrose
P3 rhomb tilings, assigns bilingual word pairs to shared tile edges, previews
the puzzle as SVG, and exports vector cut-out pieces to print-ready PDF pages.

The outer ring can be clipped into small edge pieces that complete an exact
decagon, pentagon, five-point-star, or square silhouette. Interior pieces remain
true P3 rhombi. A continuous outline pass keeps the assembled border visually
uniform, similar to classic bounded Penrose demos.

## Run locally

Python 3.9 or newer is required.

```bash
cd penrose_app
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>.

## Word input

Paste text or upload a `.txt`/`.csv` file. One pair belongs on each line and
may use either delimiter:

```text
Monday,Lunes
Tuesday|Martes
```

Shared edges are sorted by midpoint X and then Y. Pair halves are placed on
the two deterministic tile sides and the pair list cycles when necessary.
Boundary edges never receive labels.

## Printing and scale

The PDF exporter supports US Letter (default) and A4 paper. Choose a physical
tile-edge scale from 1 to 3 inches to pack many pieces onto each page. Every
full rhomb side uses that exact printed measurement, and clipped edge pieces
retain the same scale so they reconnect correctly. The auto-fit option keeps
the original one-piece-per-page behavior.

Cut-line thickness is set independently in millimeters. It controls the PDF
cut guides and Cricut SVG strokes without changing the thinner web-preview
border.

## Cricut SVG

`Export Cricut SVG` uses the same physical page packing and tile-edge scale as
the PDF. The single SVG contains one group per print page. Each page has an
`artwork` group (fills and word labels) and a separate `cut-lines` group with
exactly one closed machine-cut path per physical piece. Page groups are stacked
vertically with a small gap so they can be ungrouped and sent to Cricut Design
Space one sheet at a time.

## API

- `POST /generate` accepts `{ "settings": {...}, "word_pairs": [["Monday", "Lunes"]] }`.
- `POST /export_pdf` accepts the same body and downloads a PDF. Response
  headers report page count, piece count, and the maximum pieces on one page.
- `POST /export_svg` accepts the same body and downloads the layered Cricut SVG.
- `GET /health` returns a small readiness response.


<img width="1361" height="644" alt="{C68C2B36-2D8E-448A-89DA-3793266A4B20}" src="https://github.com/user-attachments/assets/d25f6bf9-2299-420a-97c7-a2284500b14e" />

<img width="810" height="471" alt="{D51757B3-3F7C-448B-A930-2CE07B718A72}" src="https://github.com/user-attachments/assets/eb9ce1e4-ef41-4add-b83a-c8c9600e0ad0" />
<img width="737" height="467" alt="{A115EF5E-F206-49E8-825E-FAD0F7FE4475}" src="https://github.com/user-attachments/assets/71b427c7-687a-4a1d-98cf-b414f6a55128" />
<img width="593" height="492" alt="{D01B4C96-45BF-41B5-8A4E-689350A158BF}" src="https://github.com/user-attachments/assets/fcc3c0aa-e495-4d1d-8b0b-34f7dba0e6d7" />

<img width="665" height="455" alt="{AB397150-CCE9-402E-8CFF-841ACDE0EC30}" src="https://github.com/user-attachments/assets/22da2cb5-392a-4de6-afd6-7d13a27f9fdc" />

<img width="897" height="418" alt="{809CFE9F-E97D-4C4A-A37E-BD4464F5654C}" src="https://github.com/user-attachments/assets/a0153979-6635-4bd3-a874-5986aa3f9149" />

