from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from api._history import new_conversion_record, safe_source_name
from api.convert import (
    MAX_RESPONSE_BYTES,
    MAX_UPLOAD_BYTES,
    TEMPLATE_PATHS,
    XLSX_MEDIA_TYPE,
    _content_disposition,
    _safe_client_filename,
    _save_history,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cosmo_tiling.corrections import (
    CorrectionAnalysis,
    analyze_correction,
    generate_corrected_workbook,
)

MAX_COMBINED_UPLOAD_BYTES = 4 * 1024 * 1024

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


async def _read_pdf(upload: UploadFile, label: str) -> tuple[bytes, str]:
    filename = upload.filename or ""
    contents = await upload.read(MAX_UPLOAD_BYTES + 1)
    await upload.close()
    if not filename:
        raise HTTPException(status_code=400, detail=f"The {label} PDF needs a valid filename.")
    _safe_client_filename(filename)
    if not filename.casefold().endswith(".pdf"):
        raise HTTPException(status_code=400, detail=f"Choose a PDF file for {label}.")
    if not contents:
        raise HTTPException(status_code=400, detail=f"The {label} PDF is empty.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"The {label} PDF exceeds the 4 MB limit.")
    if not contents.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail=f"The {label} file is not a valid PDF.")
    return contents, filename


def _validate_request(
    original_bytes: bytes,
    corrected_bytes: bytes,
    template: str,
) -> Path:
    template_path = TEMPLATE_PATHS.get(template)
    if template_path is None:
        raise HTTPException(
            status_code=400,
            detail="Choose the Classica template for corrected orders. Saussy support is awaiting a revised-order sample.",
        )
    if template != "classica":
        raise HTTPException(
            status_code=400,
            detail="Corrected Saussy orders are not enabled yet.",
        )
    if len(original_bytes) + len(corrected_bytes) > MAX_COMBINED_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The two corrected-order PDFs exceed the 4 MB combined limit.",
        )
    return template_path


def _write_inputs(
    directory: str,
    original_bytes: bytes,
    corrected_bytes: bytes,
) -> tuple[Path, Path]:
    work_dir = Path(directory)
    original_path = work_dir / "original.pdf"
    corrected_path = work_dir / "corrected.pdf"
    original_path.write_bytes(original_bytes)
    corrected_path.write_bytes(corrected_bytes)
    return original_path, corrected_path


def _corrected_output_name(filename: str) -> str:
    safe_name = _safe_client_filename(filename)
    stem = safe_name[:-4] if safe_name.casefold().endswith(".pdf") else safe_name
    return f"{stem}-Corrected.xlsx"


@app.post("/api/corrections/analyze")
async def analyze_corrected_order(
    original_pdf: Annotated[UploadFile, File()],
    corrected_pdf: Annotated[UploadFile, File()],
    template: Annotated[str, Form()],
) -> JSONResponse:
    original_bytes, _original_name = await _read_pdf(original_pdf, "original order")
    corrected_bytes, _corrected_name = await _read_pdf(corrected_pdf, "corrected order")
    template_path = _validate_request(original_bytes, corrected_bytes, template)
    with tempfile.TemporaryDirectory() as directory:
        original_path, corrected_path = _write_inputs(directory, original_bytes, corrected_bytes)
        try:
            analysis, _original, _corrected = analyze_correction(
                original_path,
                corrected_path,
                template_path,
                template_name=template,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=422,
                detail="The corrected order could not be analyzed. Check both PDFs and try again.",
            ) from error
    return JSONResponse(
        content=analysis.model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/corrections/generate")
async def generate_corrected_order(
    request: Request,
    original_pdf: Annotated[UploadFile, File()],
    corrected_pdf: Annotated[UploadFile, File()],
    template: Annotated[str, Form()],
    analysis: Annotated[str, Form()],
    decisions: Annotated[str, Form()],
) -> Response:
    original_bytes, original_name = await _read_pdf(original_pdf, "original order")
    corrected_bytes, corrected_name = await _read_pdf(corrected_pdf, "corrected order")
    template_path = _validate_request(original_bytes, corrected_bytes, template)
    try:
        expected_analysis = CorrectionAnalysis.model_validate_json(analysis)
        decision_values = json.loads(decisions)
        if not isinstance(decision_values, dict) or not all(
            isinstance(key, str) and value in {"apply", "ignore"}
            for key, value in decision_values.items()
        ):
            raise ValueError("Invalid decisions")
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=400,
            detail="The correction analysis or review decisions are invalid. Analyze the PDFs again.",
        ) from error

    output_name = _corrected_output_name(corrected_name)
    with tempfile.TemporaryDirectory() as directory:
        original_path, corrected_path = _write_inputs(directory, original_bytes, corrected_bytes)
        output_path = Path(directory) / output_name
        try:
            final_analysis, resolved_actions, rows = generate_corrected_workbook(
                original_path,
                corrected_path,
                output_path,
                template_path,
                decision_values,
                template_name=template,
                expected_analysis=expected_analysis,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=422,
                detail="The corrected workbook could not be generated. Analyze the PDFs again and review all warnings.",
            ) from error
        workbook = output_path.read_bytes()

    if len(workbook) > MAX_RESPONSE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The generated workbook is too large to download through Vercel.",
        )

    applied_count = sum(
        action.status in {"applied", "already_current"} for action in resolved_actions
    )
    warning_count = len(final_analysis.warnings) + sum(
        len(action.warnings) for action in resolved_actions
    )
    record = new_conversion_record(
        source_filename=safe_source_name(corrected_name),
        output_filename=output_name,
        template=template,
        order_type="corrected",
        original_filename=safe_source_name(original_name),
        corrected_filename=safe_source_name(corrected_name),
        status="success",
        row_count=len(rows),
        applied_change_count=applied_count,
        warning_count=warning_count,
    )
    saved, history_error = _save_history(
        record,
        request.headers.get("x-vercel-oidc-token"),
    )
    headers = {
        "Cache-Control": "no-store",
        "Content-Disposition": _content_disposition(output_name),
        "X-Order-Row-Count": str(len(rows)),
        "X-Applied-Change-Count": str(applied_count),
        "X-Warning-Count": str(warning_count),
        "X-Conversion-Id": record.id,
        "X-Conversion-Created-At": record.created_at_utc,
        "X-History-Saved": str(saved).lower(),
    }
    if history_error:
        headers["X-History-Error"] = history_error
    return Response(
        content=workbook,
        media_type=XLSX_MEDIA_TYPE,
        headers=headers,
    )
