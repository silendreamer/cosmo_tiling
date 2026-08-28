from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cosmo_tiling.converter import convert  # noqa: E402


MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TEMPLATE_PATHS = {
    "classica": SOURCE_ROOT / "cosmo_tiling" / "config" / "templates" / "classica-template.json",
    "saussy": SOURCE_ROOT / "cosmo_tiling" / "config" / "templates" / "saussy-template.json",
}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _safe_client_filename(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="The uploaded PDF needs a valid filename.")
    return name


def _output_filename(pdf_filename: str) -> str:
    name = _safe_client_filename(pdf_filename)
    if not name.casefold().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Choose a file with a .pdf extension.")
    return f"{name[:-4]}.xlsx"


def _content_disposition(filename: str) -> str:
    fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", filename).replace('"', "_")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


def create_workbook_response(pdf_bytes: bytes, filename: str, template: str) -> Response:
    output_name = _output_filename(filename)
    template_path = TEMPLATE_PATHS.get(template)
    if template_path is None:
        raise HTTPException(status_code=400, detail="Choose either the Saussy or Classica template.")
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The PDF exceeds the 4 MB upload limit.")
    if not pdf_bytes.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The selected file is not a valid PDF.")

    with tempfile.TemporaryDirectory() as directory:
        work_dir = Path(directory)
        input_path = work_dir / "upload.pdf"
        output_path = work_dir / output_name
        input_path.write_bytes(pdf_bytes)
        try:
            rows = convert(input_path, output_path, template_path=template_path)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=f"The PDF could not be converted: {error}",
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=422,
                detail="The PDF could not be read with the selected template. Check the template and try again.",
            ) from error

        workbook = output_path.read_bytes()

    if len(workbook) > MAX_RESPONSE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The generated workbook is too large to download through Vercel.",
        )

    return Response(
        content=workbook,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": _content_disposition(output_name),
            "X-Order-Row-Count": str(len(rows)),
        },
    )


@app.post("/api/convert")
async def convert_pdf(
    pdf: UploadFile = File(...),
    template: str = Form(...),
) -> Response:
    contents = await pdf.read(MAX_UPLOAD_BYTES + 1)
    await pdf.close()
    return create_workbook_response(contents, pdf.filename or "", template)
