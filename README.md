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

## Web app

The static upload interface is in `frontend/` and posts PDFs to the FastAPI
function in `api/convert.py`. The function converts the PDF in temporary
storage and returns the generated workbook directly to the browser. The
download keeps the PDF filename and changes its extension to `.xlsx`.

The **Corrected order** flow accepts an original and revised Classica PDF. It
analyzes deterministic selection differences, requests review for uncertain
prose instructions, and returns a single `-Corrected.xlsx` workbook with a
`Revision Report` audit sheet. Each PDF may be up to 4 MB, while the pair must
be 4 MB or smaller in total. Corrected Saussy orders remain disabled until a
real original/revised fixture is available. See
[`docs/corrected-order-workflow.md`](docs/corrected-order-workflow.md) for the
behavior and acceptance contract.

Shared conversion metadata is exposed by `api/conversions.py` and stored in a
private Vercel Blob object at `history/conversions.csv`. Only filenames,
order/template type, status, failure reason, row/change/warning counts, ID, and timestamp are retained;
uploaded PDFs and generated workbooks are never written to Blob. The newest
50 records are loaded initially and older records can be requested in pages.

Optional correction-prose interpretation uses the OpenAI Responses API. Set
`OPENAI_API_KEY` on the server and optionally override the default model with
`OPENAI_CORRECTION_MODEL` (default `gpt-5.6-terra`). Only redacted correction
snippets and candidate rows are sent; raw PDFs are not sent. If the key or API
is unavailable, deterministic analysis continues and unmatched instructions
are sent to user review.

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
