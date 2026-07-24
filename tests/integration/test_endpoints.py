"""Integration tests for FastAPI endpoints in app.py.

Covers Requirements 8.2, 8.3, 8.5:
  - /extract-text/ accepts PDF and image uploads, calls process_document()
  - /upload-and-ingest/ runs the full pipeline and calls MongoIngestor.insert()
  - Both endpoints accept both PDF and image file types
  - Errors from process_document() surface as 500 responses
"""
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)

FAKE_FILE = b"fake file content"

EXTRACT_URL = "/extract-text/"
INGEST_URL = "/upload-and-ingest/"


# ---------------------------------------------------------------------------
# /extract-text/ — PDF upload  (Requirement 8.2)
# ---------------------------------------------------------------------------

class TestExtractTextPdf:
    def test_pdf_upload_returns_200_with_extraction_result(self) -> None:
        mock_result = {"text": "extracted text", "tables": []}

        with patch("app.DocumentProcessor") as mock_dp_cls:
            mock_dp = MagicMock()
            mock_dp.process_document.return_value = mock_result
            mock_dp_cls.return_value = mock_dp

            response = client.post(
                EXTRACT_URL,
                files={"file": ("invoice.pdf", io.BytesIO(FAKE_FILE), "application/pdf")},
            )

        assert response.status_code == 200
        assert response.json() == mock_result

    def test_pdf_upload_calls_process_document(self) -> None:
        with patch("app.DocumentProcessor") as mock_dp_cls:
            mock_dp = MagicMock()
            mock_dp.process_document.return_value = {"text": "", "tables": []}
            mock_dp_cls.return_value = mock_dp

            client.post(
                EXTRACT_URL,
                files={"file": ("order.pdf", io.BytesIO(FAKE_FILE), "application/pdf")},
            )

        mock_dp.process_document.assert_called_once()


# ---------------------------------------------------------------------------
# /extract-text/ — image upload  (Requirement 8.5)
# ---------------------------------------------------------------------------

class TestExtractTextImage:
    @pytest.mark.parametrize("filename,content_type", [
        ("scan.jpg", "image/jpeg"),
        ("scan.jpeg", "image/jpeg"),
        ("scan.png", "image/png"),
    ])
    def test_image_upload_returns_200(self, filename: str, content_type: str) -> None:
        mock_result = {"text": "ocr text", "tables": []}

        with patch("app.DocumentProcessor") as mock_dp_cls:
            mock_dp = MagicMock()
            mock_dp.process_document.return_value = mock_result
            mock_dp_cls.return_value = mock_dp

            response = client.post(
                EXTRACT_URL,
                files={"file": (filename, io.BytesIO(FAKE_FILE), content_type)},
            )

        assert response.status_code == 200
        assert response.json() == mock_result

    def test_image_upload_calls_process_document(self) -> None:
        with patch("app.DocumentProcessor") as mock_dp_cls:
            mock_dp = MagicMock()
            mock_dp.process_document.return_value = {"text": "ocr result", "tables": []}
            mock_dp_cls.return_value = mock_dp

            client.post(
                EXTRACT_URL,
                files={"file": ("receipt.jpg", io.BytesIO(FAKE_FILE), "image/jpeg")},
            )

        mock_dp.process_document.assert_called_once()


# ---------------------------------------------------------------------------
# /extract-text/ — error handling  (Requirement 8.5)
# ---------------------------------------------------------------------------

class TestExtractTextErrors:
    def test_process_document_value_error_returns_500(self) -> None:
        with patch("app.DocumentProcessor") as mock_dp_cls:
            mock_dp = MagicMock()
            mock_dp.process_document.side_effect = ValueError("Unsupported file type: .xyz")
            mock_dp_cls.return_value = mock_dp

            response = client.post(
                EXTRACT_URL,
                files={"file": ("document.xyz", io.BytesIO(FAKE_FILE), "application/octet-stream")},
            )

        assert response.status_code == 500
        assert "Unsupported file type" in response.json()["detail"]

    def test_process_document_ioerror_returns_500(self) -> None:
        with patch("app.DocumentProcessor") as mock_dp_cls:
            mock_dp = MagicMock()
            mock_dp.process_document.side_effect = IOError("File not found: /tmp/missing.pdf")
            mock_dp_cls.return_value = mock_dp

            response = client.post(
                EXTRACT_URL,
                files={"file": ("missing.pdf", io.BytesIO(FAKE_FILE), "application/pdf")},
            )

        assert response.status_code == 500
        assert "File not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /upload-and-ingest/ — full pipeline  (Requirement 8.3)
# ---------------------------------------------------------------------------

class TestUploadAndIngest:
    def _mock_full_pipeline(
        self,
        *,
        extracted: dict | None = None,
        parsed: dict | None = None,
        normalized: dict | None = None,
    ):
        """Context manager that patches DocumentProcessor, MongoIngestor,
        parse_tables, and normalize_with_ai with sensible defaults."""
        extracted = extracted or {"text": "order text", "tables": []}
        parsed = parsed or {"order_id": "123", "products": []}
        normalized = normalized or {"order_id": "123", "products": []}

        mock_dp = MagicMock()
        mock_dp.process_document.return_value = extracted

        mock_mongo = MagicMock()

        return (
            patch("app.DocumentProcessor", return_value=mock_dp),
            patch("app.MongoIngestor", return_value=mock_mongo),
            patch("app.parse_tables", return_value=parsed),
            patch("app.normalize_with_ai", return_value=normalized),
            mock_dp,
            mock_mongo,
        )

    def test_pdf_upload_returns_200_with_success_message(self) -> None:
        mock_dp = MagicMock()
        mock_dp.process_document.return_value = {"text": "data", "tables": []}
        mock_mongo = MagicMock()

        with patch("app.DocumentProcessor", return_value=mock_dp), \
             patch("app.MongoIngestor", return_value=mock_mongo), \
             patch("app.parse_tables", return_value={}), \
             patch("app.normalize_with_ai", return_value={}):

            response = client.post(
                INGEST_URL,
                files={"file": ("purchase_order.pdf", io.BytesIO(FAKE_FILE), "application/pdf")},
            )

        assert response.status_code == 200
        body = response.json()
        assert "Data successfully ingested" in body["message"]

    def test_ingest_response_includes_filename(self) -> None:
        mock_dp = MagicMock()
        mock_dp.process_document.return_value = {"text": "data", "tables": []}
        mock_mongo = MagicMock()

        with patch("app.DocumentProcessor", return_value=mock_dp), \
             patch("app.MongoIngestor", return_value=mock_mongo), \
             patch("app.parse_tables", return_value={}), \
             patch("app.normalize_with_ai", return_value={}):

            response = client.post(
                INGEST_URL,
                files={"file": ("purchase_order.pdf", io.BytesIO(FAKE_FILE), "application/pdf")},
            )

        assert response.json()["file_name"] == "purchase_order.pdf"

    def test_mongo_insert_called_with_normalized_data(self) -> None:
        """MongoIngestor.insert() must receive the AI-normalized result and filename."""
        normalized = {"order_id": "PO-42", "products": [{"product_id": "X", "quantity": 5}]}
        mock_dp = MagicMock()
        mock_dp.process_document.return_value = {"text": "raw text", "tables": []}
        mock_mongo = MagicMock()

        with patch("app.DocumentProcessor", return_value=mock_dp), \
             patch("app.MongoIngestor", return_value=mock_mongo), \
             patch("app.parse_tables", return_value={"order_id": "PO-42", "products": []}), \
             patch("app.normalize_with_ai", return_value=normalized):

            client.post(
                INGEST_URL,
                files={"file": ("po.pdf", io.BytesIO(FAKE_FILE), "application/pdf")},
            )

        mock_mongo.insert.assert_called_once_with(normalized, "po.pdf")

    def test_ingest_error_returns_500(self) -> None:
        mock_dp = MagicMock()
        mock_dp.process_document.side_effect = RuntimeError("extraction failed")

        with patch("app.DocumentProcessor", return_value=mock_dp), \
             patch("app.MongoIngestor"):

            response = client.post(
                INGEST_URL,
                files={"file": ("broken.pdf", io.BytesIO(FAKE_FILE), "application/pdf")},
            )

        assert response.status_code == 500
        assert "extraction failed" in response.json()["detail"]
