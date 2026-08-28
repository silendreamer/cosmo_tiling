from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Request, Response

from api._history import ConversionHistory

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/conversions")
def get_conversions(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    try:
        records, total = ConversionHistory(
            oidc_token=request.headers.get("x-vercel-oidc-token")
        ).page(limit=limit, offset=offset)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Conversion history is temporarily unavailable.",
        ) from error

    response.headers["Cache-Control"] = "no-store"
    return {
        "items": [record.to_dict() for record in records],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(records) < total,
    }
