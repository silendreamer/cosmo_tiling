import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.convert import MAX_UPLOAD_BYTES, app, create_workbook_response


class ApiTests(unittest.TestCase):
    @patch("api.convert.convert")
    def test_response_uses_pdf_name_with_xlsx_extension(self, mock_convert):
        def write_workbook(_input, output, **_kwargs):
            output.write_bytes(b"workbook")
            return [object(), object()]

        mock_convert.side_effect = write_workbook
        response = create_workbook_response(
            b"%PDF-1.7\ncontent", "Lot 104.pdf", "saussy"
        )

        self.assertEqual(response.body, b"workbook")
        self.assertIn(
            'filename="Lot 104.xlsx"', response.headers["content-disposition"]
        )
        self.assertEqual(response.headers["x-order-row-count"], "2")

    def test_rejects_unknown_template(self):
        with self.assertRaises(HTTPException) as context:
            create_workbook_response(b"%PDF-1.7", "order.pdf", "unknown")
        self.assertEqual(context.exception.status_code, 400)

    def test_rejects_non_pdf_content(self):
        with self.assertRaises(HTTPException) as context:
            create_workbook_response(b"not a pdf", "order.pdf", "classica")
        self.assertEqual(context.exception.status_code, 400)

    def test_rejects_oversized_upload(self):
        with self.assertRaises(HTTPException) as context:
            create_workbook_response(
                b"%PDF-" + b"x" * MAX_UPLOAD_BYTES,
                "order.pdf",
                "classica",
            )
        self.assertEqual(context.exception.status_code, 413)

    @patch("api.convert._save_history", return_value=False)
    @patch("api.convert.convert")
    def test_success_survives_history_outage_and_returns_metadata_headers(
        self,
        mock_convert,
        _mock_save_history,
    ):
        def write_workbook(_input, output, **_kwargs):
            output.write_bytes(b"workbook")
            return [object()]

        mock_convert.side_effect = write_workbook
        response = TestClient(app).post(
            "/api/convert",
            files={"pdf": ("Order.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
            data={"template": "saussy"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"workbook")
        self.assertEqual(response.headers["x-history-saved"], "false")
        self.assertTrue(response.headers["x-conversion-id"])
        self.assertTrue(response.headers["x-conversion-created-at"].endswith("Z"))

    @patch("api.convert._save_history", return_value=True)
    def test_failed_conversion_returns_saved_record(self, _mock_save_history):
        response = TestClient(app).post(
            "/api/convert",
            files={"pdf": ("bad.pdf", b"not a pdf", "application/pdf")},
            data={"template": "classica"},
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertTrue(body["history_saved"])
        self.assertEqual(body["conversion"]["source_filename"], "bad.pdf")
        self.assertEqual(body["conversion"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
