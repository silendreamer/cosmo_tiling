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
sections, order quantities where available, comments, and complete pattern
wording. The `Data` sheet retains measured quantities, room codes, and source
PDF text for auditing.

Classica uploads use the deterministic parser used by
`scripts/extract_classica_room.py`. Room codes and applications come from the PDF;
the template contains optional wording aliases, with no project matching.
Drain riser plugs follow every shower drain (1 EA), and the shared caulk, sealer,
niche, and accessory rules apply. Other quantities remain blank. The `Source`
sheet preserves extracted columns, and unresolved instructions appear in
`Change Review`. The app flags content requiring review.
The bundled template is `src/cosmo_tiling/config/templates/classica-template.json`
and is used by default when `--template` is omitted.

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
- `src/cosmo_tiling/parsers/classica_columns.py` contains the shared Classica
  column extraction and row rules; `classica_app.py` adapts them to app workbooks.
- `src/cosmo_tiling/parsers/classica_changes.py` handles supported PDF change instructions.
- `src/cosmo_tiling/parsers/classica.py` retains metadata parsing and legacy helpers.
- `src/cosmo_tiling/parsers/saussy.py` contains Saussy metadata and Tile-section parsing,
  including the project-neutral fallback parser.
- `src/cosmo_tiling/parsers/common.py` contains the shared `OrderRow` model and text cleanup.
- `src/cosmo_tiling/config/` contains JSON templates and reference rules.

## Web app

The static upload interface is in `frontend/` and posts PDFs to the FastAPI
function in `api/convert.py`. The function converts the PDF in temporary
storage and returns the generated workbook directly to the browser. The
download keeps the PDF filename and changes its extension to `.xlsx`.

Corrected Classica PDFs use the same single-file upload. Because the corrected
PDF contains the original selections and its correction instructions, the
converter applies supported instructions from that PDF directly and records
unresolved instructions in the workbook for review.

Shared conversion metadata is exposed by `api/conversions.py` and stored in a
private Vercel Blob object at `history/conversions.csv`. Only filenames,
order/template type, status, failure reason, row/change/warning counts, ID, and timestamp are retained;
uploaded PDFs and generated workbooks are never written to Blob. The newest
50 records are loaded initially and older records can be requested in pages.

Install the project and Vercel CLI, then preview the complete app locally with:

```powershell
uv sync
vercel dev
```

The web converter accepts PDFs up to 4 MB so the upload and generated workbook
remain below Vercel's 4.5 MB function payload limit.

## Vercel deployment

Import the repository with the project root set to the repository root (not
`frontend/`). `vercel.json` publishes `frontend/` as the static site and deploys
the Python API functions.

Before deploying, connect a **private Vercel Blob store** to the project. New
connections use Vercel's short-lived OIDC credentials and add `BLOB_STORE_ID`;
legacy connections may provide `BLOB_READ_WRITE_TOKEN`. Pull the updated
development environment for local `vercel dev` runs with:

```powershell
vercel env pull .env.local
```

If Blob is unavailable, workbook conversion and download still succeed, but
the page warns that the conversion was not added to shared history.
