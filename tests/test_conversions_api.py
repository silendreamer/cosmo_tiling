import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api._history import new_conversion_record
from api.conversions import app


class ConversionsApiTests(unittest.TestCase):
    @patch("api.conversions.ConversionHistory")
    def test_returns_pagination_state_and_records(self, mock_history):
        item = new_conversion_record(
            source_filename="Order.pdf",
            output_filename="Order.xlsx",
            template="saussy",
            status="success",
            row_count=2,
        )
        mock_history.return_value.page.return_value = ([item], 3)

        response = TestClient(app).get("/api/conversions?limit=1&offset=1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"][0]["id"], item.id)
        self.assertEqual(body["total"], 3)
        self.assertTrue(body["has_more"])

    @patch("api.conversions.ConversionHistory")
    def test_storage_outage_returns_safe_error(self, mock_history):
        mock_history.return_value.page.side_effect = RuntimeError("token=secret")

        response = TestClient(app).get("/api/conversions")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Conversion history is temporarily unavailable."},
        )
        self.assertNotIn("secret", response.text)

    def test_rejects_invalid_pagination(self):
        response = TestClient(app).get("/api/conversions?limit=101&offset=-1")

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
