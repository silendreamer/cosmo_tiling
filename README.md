# Cosmopolitan Tile Order Converter

Python converter for turning Classica Homes and Saussy Burbank PDF selections
into structured Excel tile-order workbooks.

## Requirements

- Windows, macOS, or Linux
- Python 3.11+

Microsoft Word and Excel are not required. The project uses `pdfplumber` to
read PDFs and `openpyxl` to create `.xlsx` files.

## Setup and run with uv

From the repository root:

```powershell
uv sync
uv run python convert_tile_order.py pdf/classica/VendorOrder_PalosVerdeEstates7.pdf
```

The generated file is written to `output/<pdf-name>-TileOrder.xlsx`.

The formatted `Tile Order` sheet includes the project summary, colored room
sections, formula-driven order quantities, comments, and complete pattern
wording. The `Data` sheet retains measured quantities, room codes, and source
PDF text for auditing.

The selected JSON template identifies the PDF format and contains default and
project-specific business rules. These handle adjusted field measurements,
waste percentages, consolidated orders, Schluter quantities, and derived
accessories that are not stated directly in the PDF. The bundled Classica
template is `src/cosmo_tiling/config/templates/classica-template.json` and is used by default when
`--template` is omitted.

The Saussy template is `src/cosmo_tiling/config/templates/saussy-template.json`. It contains only the
reusable format settings used to parse the Tile section of any Saussy
design-selection PDF with the same layout. The three historical quantity sets
live separately in `src/cosmo_tiling/config/rules/saussy-reference-orders.json`;
they are optional
enrichments for the reference jobs because measured areas, waste, and shop notes
exist only in the completed order workbooks. A new project does not need a
`project_match` entry to parse. Its selections are exported with blank measured
and order quantities for review. For example:

```powershell
uv run python convert_tile_order.py "pdf/saussy/Eastland 104 Modern Luxe DSS 12.15.2025.pdf" --template src/cosmo_tiling/config/templates/saussy-template.json --output output/updated/Saussy-Tile-Order-Eastland-Yards-Lot-104.xlsx
```

Choose a different output path with:

```powershell
uv run python convert_tile_order.py input.pdf --template src/cosmo_tiling/config/templates/classica-template.json --output output/order.xlsx
```

Add `--debug-text` to save the extracted PDF text beside the workbook for
troubleshooting.

## Code layout

- `convert_tile_order.py` is a backward-compatible command-line launcher.
- `src/cosmo_tiling/converter.py` handles template loading, conversion
  orchestration, workbook generation, validation, and CLI behavior.
- `src/cosmo_tiling/parsers/classica.py` contains Classica metadata parsing, PDF row parsing,
  normalization, and order-rule application.
- `src/cosmo_tiling/parsers/saussy.py` contains Saussy metadata and Tile-section parsing,
  including the project-neutral fallback parser.
- `src/cosmo_tiling/parsers/common.py` contains the shared `OrderRow` model and text cleanup.
- `src/cosmo_tiling/config/` contains JSON templates and reference rules.

## Frontend prototype

The backend-free upload interface is in `frontend/`. Preview it locally with:

```powershell
uv run python -m http.server 8000 --directory frontend
```

Then open `http://localhost:8000`. The form currently handles PDF selection,
drag-and-drop validation, template selection, and the corrected option; the
Convert button intentionally stops at a frontend-only status message.

## Deployment direction

The current `frontend/` directory is a static site with no build step, so it can
be published directly on Cloudflare Pages or Netlify. When PDF conversion is
wired in, deploy the Python application as a web service (for example, Render)
and have the browser upload to that service. Generated workbooks should be
returned directly to the browser rather than retained on the application server.
