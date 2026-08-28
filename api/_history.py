from __future__ import annotations

import csv
import io
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import httpx
from vercel.blob import BlobClient, BlobNotFoundError

HISTORY_PATH = "history/conversions.csv"
HISTORY_FIELDS = (
    "id",
    "source_filename",
    "output_filename",
    "template",
    "status",
    "failure_reason",
    "row_count",
    "created_at_utc",
)
MAX_APPEND_ATTEMPTS = 5


class HistoryConflictError(RuntimeError):
    """The history changed between a read and conditional write."""


@dataclass(frozen=True)
class ConversionRecord:
    id: str
    source_filename: str
    output_filename: str
    template: str
    status: str
    failure_reason: str
    row_count: int | None
    created_at_utc: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class HistoryGateway(Protocol):
    def read(self) -> tuple[bytes | None, str | None]: ...

    def conditional_write(self, content: bytes, etag: str | None) -> None: ...


class VercelBlobGateway:
    def __init__(
        self,
        token: str | None = None,
        oidc_token: str | None = None,
        store_id: str | None = None,
    ) -> None:
        self.token = token or os.getenv("BLOB_READ_WRITE_TOKEN")
        self.oidc_token = oidc_token or os.getenv("VERCEL_OIDC_TOKEN")
        configured_store_id = store_id or os.getenv("BLOB_STORE_ID")
        self.store_id = (
            configured_store_id.removeprefix("store_") if configured_store_id else None
        )
        if not self.token and not (self.oidc_token and self.store_id):
            raise RuntimeError("Blob credentials are not available.")
        self.client = BlobClient(token=self.token) if self.token else None

    def _oidc_headers(self) -> dict[str, str]:
        if not self.oidc_token or not self.store_id:
            raise RuntimeError("OIDC Blob credentials are incomplete.")
        return {
            "Authorization": f"Bearer {self.oidc_token}",
            "x-vercel-blob-store-id": self.store_id,
        }

    def read(self) -> tuple[bytes | None, str | None]:
        if self.client is None:
            url = (
                f"https://{self.store_id}.private.blob.vercel-storage.com/"
                f"{HISTORY_PATH}"
            )
            response = httpx.get(
                url,
                params={"cache": "0"},
                headers=self._oidc_headers(),
                follow_redirects=True,
                timeout=30,
            )
            if response.status_code == 404:
                return None, None
            response.raise_for_status()
            return response.content, response.headers.get("etag")

        try:
            result = self.client.get(HISTORY_PATH, access="private", use_cache=False)
        except BlobNotFoundError:
            return None, None
        return result.content, result.etag or None

    def conditional_write(self, content: bytes, etag: str | None) -> None:
        api_url = (
            os.getenv("VERCEL_BLOB_API_URL")
            or os.getenv("NEXT_PUBLIC_VERCEL_BLOB_API_URL")
            or "https://vercel.com/api/blob"
        )
        headers = {
            "x-api-version": "12",
            "x-add-random-suffix": "0",
            "x-allow-overwrite": "1" if etag else "0",
            "x-cache-control-max-age": "60",
            "x-content-type": "text/csv; charset=utf-8",
            "x-vercel-blob-access": "private",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            headers.update(self._oidc_headers())
        if etag:
            headers["x-if-match"] = etag

        response = httpx.put(
            api_url,
            params={"pathname": HISTORY_PATH},
            headers=headers,
            content=content,
            timeout=30,
        )
        if response.status_code in {409, 412}:
            raise HistoryConflictError("The history changed during the write.")
        response.raise_for_status()


def new_conversion_record(
    *,
    source_filename: str,
    output_filename: str,
    template: str,
    status: str,
    failure_reason: str = "",
    row_count: int | None = None,
) -> ConversionRecord:
    return ConversionRecord(
        id=str(uuid4()),
        source_filename=source_filename,
        output_filename=output_filename,
        template=template,
        status=status,
        failure_reason=sanitize_failure_reason(failure_reason),
        row_count=row_count,
        created_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


def sanitize_failure_reason(reason: str) -> str:
    text = "".join(
        character
        for character in str(reason)
        if character in "\n\t" or ord(character) >= 32
    )
    text = re.sub(
        r"(?i)(token|authorization|password|secret)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        text,
    )
    text = re.sub(r"(?i)\b[A-Z]:\\[^\r\n]+", "[local path]", text)
    text = re.sub(r"(?<!\w)/(?:[^\s/]+/)+[^\s]+", "[local path]", text)
    return text.strip()[:1000]


def encode_records(records: list[ConversionRecord]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=HISTORY_FIELDS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        row = record.to_dict()
        row["row_count"] = "" if record.row_count is None else record.row_count
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def decode_records(content: bytes | None) -> list[ConversionRecord]:
    if not content:
        return []
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    records: list[ConversionRecord] = []
    for row in reader:
        if not row or not row.get("id"):
            continue
        count = (row.get("row_count") or "").strip()
        records.append(
            ConversionRecord(
                id=row["id"],
                source_filename=row.get("source_filename", ""),
                output_filename=row.get("output_filename", ""),
                template=row.get("template", ""),
                status=row.get("status", "failed"),
                failure_reason=row.get("failure_reason", ""),
                row_count=int(count) if count else None,
                created_at_utc=row.get("created_at_utc", ""),
            )
        )
    return records


class ConversionHistory:
    def __init__(
        self,
        gateway: HistoryGateway | None = None,
        *,
        oidc_token: str | None = None,
    ) -> None:
        self.gateway = gateway or VercelBlobGateway(oidc_token=oidc_token)

    def append(self, record: ConversionRecord) -> None:
        for attempt in range(MAX_APPEND_ATTEMPTS):
            content, etag = self.gateway.read()
            records = decode_records(content)
            records.append(record)
            try:
                self.gateway.conditional_write(encode_records(records), etag)
                return
            except HistoryConflictError:
                if attempt == MAX_APPEND_ATTEMPTS - 1:
                    raise
                time.sleep(0.025 * (2**attempt))

    def page(self, *, limit: int, offset: int) -> tuple[list[ConversionRecord], int]:
        content, _etag = self.gateway.read()
        records = decode_records(content)
        records.sort(key=lambda record: record.created_at_utc, reverse=True)
        return records[offset : offset + limit], len(records)


def safe_output_name(source_filename: str) -> str:
    name = safe_source_name(source_filename)
    if name.casefold().endswith(".pdf"):
        return f"{name[:-4]}.xlsx"
    return ""


def safe_source_name(source_filename: str) -> str:
    name = source_filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = "".join(character for character in name if ord(character) >= 32)
    return name if name and name not in {".", ".."} else "Unnamed PDF"
