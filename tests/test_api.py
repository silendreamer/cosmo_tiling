import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.convert import MAX_UPLOAD_BYTES, create_workbook_response


class ApiTests(unittest.TestCase):
    @patch("api.convert.convert")
    def test_response_uses_pdf_name_with_xlsx_extension(self, mock_convert):
        def write_workbook(_input, output, **_kwargs):
            output.write_bytes(b"workbook")
            return [object(), object()]

        mock_convert.side_effect = write_workbook
        response = create_workbook_response(b"%PDF-1.7\ncontent", "Lot 104.pdf", "saussy")

        self.assertEqual(response.body, b"workbook")
        self.assertIn('filename="Lot 104.xlsx"', response.headers["content-disposition"])
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


if __name__ == "__main__":
    unittest.main()
