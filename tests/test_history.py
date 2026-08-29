import unittest
from unittest.mock import Mock, patch

from api._history import (
    ConversionHistory,
    HistoryConflictError,
    VercelBlobGateway,
    decode_records,
    encode_records,
    new_conversion_record,
    sanitize_failure_reason,
)


class FakeGateway:
    def __init__(self, content=None, conflicts=0):
        self.content = content
        self.etag = "etag-1" if content else None
        self.conflicts = conflicts
        self.writes = []

    def read(self):
        return self.content, self.etag

    def conditional_write(self, content, etag):
        if self.conflicts:
            self.conflicts -= 1
            self.etag = "etag-conflict"
            raise HistoryConflictError("conflict")
        if etag != self.etag:
            raise HistoryConflictError("stale etag")
        self.content = content
        self.etag = f"etag-{len(self.writes) + 2}"
        self.writes.append(content)


def record(name, created_at="2026-08-28T12:00:00Z", reason="", status="success"):
    item = new_conversion_record(
        source_filename=name,
        output_filename=name.removesuffix(".pdf") + ".xlsx",
        template="saussy",
        status=status,
        failure_reason=reason,
        row_count=3 if status == "success" else None,
    )
    return item.__class__(**{**item.to_dict(), "created_at_utc": created_at})


class HistoryTests(unittest.TestCase):
    def test_csv_round_trip_quotes_unicode_commas_and_multiline_reason(self):
        original = record(
            "Lót 12, phase 2.pdf",
            reason="First line, with comma\nSecond line",
            status="failed",
        )

        content = encode_records([original])
        restored = decode_records(content)

        self.assertEqual(restored, [original])

    def test_legacy_csv_defaults_to_new_order_metadata(self):
        legacy = (
            b"id,source_filename,output_filename,template,status,failure_reason,row_count,created_at_utc\n"
            b"1,order.pdf,order.xlsx,classica,success,,3,2026-01-01T00:00:00Z\n"
        )

        restored = decode_records(legacy)

        self.assertEqual(restored[0].order_type, "new")
        self.assertEqual(restored[0].original_filename, "")
        self.assertIsNone(restored[0].applied_change_count)

    def test_append_initializes_missing_csv_and_never_contains_file_bytes(self):
        gateway = FakeGateway()
        history = ConversionHistory(gateway)

        history.append(record("order.pdf"))

        self.assertEqual(len(decode_records(gateway.content)), 1)
        self.assertNotIn(b"%PDF-", gateway.content)
        self.assertNotIn(b"PK\x03\x04", gateway.content)

    def test_append_retries_after_etag_conflict(self):
        gateway = FakeGateway(conflicts=2)

        ConversionHistory(gateway).append(record("retry.pdf"))

        self.assertEqual(gateway.conflicts, 0)
        self.assertEqual(len(gateway.writes), 1)

    def test_page_is_newest_first_with_offset(self):
        gateway = FakeGateway(
            encode_records(
                [
                    record("old.pdf", "2026-01-01T00:00:00Z"),
                    record("new.pdf", "2026-08-28T00:00:00Z"),
                    record("middle.pdf", "2026-05-01T00:00:00Z"),
                ]
            )
        )

        page, total = ConversionHistory(gateway).page(limit=1, offset=1)

        self.assertEqual(total, 3)
        self.assertEqual(page[0].source_filename, "middle.pdf")

    def test_failure_reason_redacts_tokens_and_local_paths(self):
        reason = sanitize_failure_reason("token=abc123 at C:\\Users\\name\\secret.txt")

        self.assertNotIn("abc123", reason)
        self.assertNotIn("C:\\Users", reason)

    @patch("api._history.httpx.get")
    def test_oidc_read_uses_store_id_and_request_token(self, mock_get):
        response = Mock(status_code=404)
        mock_get.return_value = response

        gateway = VercelBlobGateway(
            oidc_token="short-lived-token",
            store_id="store_example123",
        )
        content, etag = gateway.read()

        self.assertIsNone(content)
        self.assertIsNone(etag)
        request = mock_get.call_args
        self.assertIn("example123.private.blob.vercel-storage.com", request.args[0])
        self.assertEqual(
            request.kwargs["headers"]["Authorization"],
            "Bearer short-lived-token",
        )
        self.assertEqual(
            request.kwargs["headers"]["x-vercel-blob-store-id"],
            "example123",
        )

    @patch("api._history.httpx.put")
    def test_oidc_conditional_write_includes_store_scope(self, mock_put):
        response = Mock(status_code=200)
        response.raise_for_status.return_value = None
        mock_put.return_value = response

        gateway = VercelBlobGateway(
            oidc_token="short-lived-token",
            store_id="store_example123",
        )
        gateway.conditional_write(b"csv", '"etag-1"')

        headers = mock_put.call_args.kwargs["headers"]
        self.assertEqual(headers["x-api-version"], "11")
        self.assertTrue(headers["x-api-blob-request-id"].startswith("example123:"))
        self.assertEqual(headers["x-api-blob-request-attempt"], "0")
        self.assertEqual(headers["x-if-match"], '"etag-1"')
        self.assertEqual(headers["x-vercel-blob-store-id"], "example123")


if __name__ == "__main__":
    unittest.main()
