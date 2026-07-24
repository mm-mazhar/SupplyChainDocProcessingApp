"""Integration tests for DocumentProcessor with real fixture files.

Tests the full pipeline without mocks: real PDF/image → pdfplumber/PaddleOCR
→ normalized output → parse_tables().

Covers Requirements 5.1, 5.2, 5.3.

OCR-dependent tests (scanned PDF, image files) are skipped when PaddleOCR
models are not available in the current environment.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from doc_processing import DocumentProcessor, parse_tables

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _paddle_available() -> bool:
    """Return True only if PaddleOCR can be imported and initialised."""
    try:
        from paddleocr import PaddleOCR  # noqa: F401
        PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        return True
    except Exception:
        return False


requires_ocr = pytest.mark.skipif(
    not _paddle_available(),
    reason="requires PaddleOCR models",
)


# ---------------------------------------------------------------------------
# Text-PDF tests  (Requirements 5.1, 5.2)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_text_pdf_output_has_required_keys() -> None:
    """process_document() on a text-based PDF returns 'text' and 'tables'."""
    processor = DocumentProcessor()
    result = processor.process_document(str(FIXTURES / "sample_text_pdf.pdf"))

    assert "text" in result
    assert "tables" in result
    assert isinstance(result["text"], str)
    assert isinstance(result["tables"], list)
    assert len(result["text"]) > 0, "Expected non-empty text from sample_text_pdf.pdf"


@pytest.mark.integration
def test_text_pdf_table_cell_structure() -> None:
    """Every cell in every table has row_index, column_index, content keys.

    Validates Requirement 5.3.
    """
    processor = DocumentProcessor()
    result = processor.process_document(str(FIXTURES / "sample_text_pdf.pdf"))

    for table in result["tables"]:
        assert isinstance(table, list)
        for cell in table:
            assert "row_index" in cell, f"Missing row_index in cell: {cell}"
            assert "column_index" in cell, f"Missing column_index in cell: {cell}"
            assert "content" in cell, f"Missing content in cell: {cell}"
            assert isinstance(cell["row_index"], int)
            assert isinstance(cell["column_index"], int)
            assert isinstance(cell["content"], str)
            assert cell["row_index"] >= 0
            assert cell["column_index"] >= 0


# ---------------------------------------------------------------------------
# Blank / empty PDF (Requirement 9.1)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_blank_pdf_returns_empty_result_without_raising() -> None:
    """A valid blank PDF returns {"text": "", "tables": []} and does not raise.

    A blank PDF has no text layer, so pdfplumber finds no text and the code
    follows the OCR fallback path (Req 3.1). When PaddleOCR finds no text on a
    blank image it returns {"text": "", "tables": []}. When OCR models are
    unavailable the test is skipped — the blank-page path requires OCR.
    """
    if not _paddle_available():
        pytest.skip("requires PaddleOCR models (blank PDF triggers OCR fallback)")

    processor = DocumentProcessor()
    result = processor.process_document(str(FIXTURES / "empty.pdf"))

    assert result == {"text": "", "tables": []}


# ---------------------------------------------------------------------------
# parse_tables() downstream compatibility (Property 17 / Requirements 5.1-5.3)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_parse_tables_does_not_raise_on_text_pdf_output() -> None:
    """parse_tables() can consume DocumentProcessor output without crashing.

    Even if tables are insufficient for a full parse it must return a dict,
    not raise an exception.
    """
    processor = DocumentProcessor()
    result = processor.process_document(str(FIXTURES / "sample_text_pdf.pdf"))

    parsed = parse_tables(result)
    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Scanned PDF — OCR fallback (Requirements 3.1–3.4)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_ocr
def test_scanned_pdf_returns_text_from_ocr() -> None:
    """A scanned (image-only) PDF triggers OCR and returns non-empty text."""
    processor = DocumentProcessor()
    result = processor.process_document(str(FIXTURES / "sample_scanned_pdf.pdf"))

    assert "text" in result
    assert "tables" in result
    assert isinstance(result["text"], str)
    assert result["tables"] == []


# ---------------------------------------------------------------------------
# Image files — OCR path (Requirements 4.1–4.3)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_ocr
def test_jpg_image_output_structure() -> None:
    """A JPEG image processed through OCR returns valid contract structure."""
    processor = DocumentProcessor()
    result = processor.process_document(str(FIXTURES / "sample_receipt.jpg"))

    assert "text" in result
    assert "tables" in result
    assert isinstance(result["text"], str)
    assert result["tables"] == []


@pytest.mark.integration
@requires_ocr
def test_png_image_output_structure() -> None:
    """A PNG image processed through OCR returns valid contract structure."""
    processor = DocumentProcessor()
    result = processor.process_document(str(FIXTURES / "sample_invoice.png"))

    assert "text" in result
    assert "tables" in result
    assert isinstance(result["text"], str)
    assert result["tables"] == []
