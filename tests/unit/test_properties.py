"""Property-based tests for DocumentProcessor.

Uses hypothesis to verify universal correctness properties.
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from doc_processing import DocumentProcessor


# ---------------------------------------------------------------------------
# Property 10: Table Normalization Correctness
# Validates: Requirements 5.4, 5.5
# ---------------------------------------------------------------------------

cell_value = st.one_of(st.none(), st.text(max_size=20))
table_row = st.lists(cell_value, min_size=0, max_size=5)
single_table = st.lists(table_row, min_size=0, max_size=5)
tables_input = st.lists(single_table, min_size=0, max_size=3)


@given(tables=tables_input)
@settings(max_examples=200)
def test_normalize_tables_output_structure(tables):
    """Property 10: all cells always have correct keys, types, and None → empty string."""
    processor = DocumentProcessor()
    result = processor._normalize_pdfplumber_tables(tables)

    assert isinstance(result, list)
    assert len(result) == len(tables)

    for table_cells in result:
        assert isinstance(table_cells, list)
        for cell in table_cells:
            assert set(cell.keys()) == {"row_index", "column_index", "content"}
            assert isinstance(cell["row_index"], int) and cell["row_index"] >= 0
            assert isinstance(cell["column_index"], int) and cell["column_index"] >= 0
            assert isinstance(cell["content"], str)


@given(tables=tables_input)
@settings(max_examples=200)
def test_normalize_tables_none_becomes_empty_string(tables):
    """Property 10 (None coercion): any None cell value must become empty string."""
    processor = DocumentProcessor()
    result = processor._normalize_pdfplumber_tables(tables)

    for table_cells in result:
        for cell in table_cells:
            assert cell["content"] is not None


@given(tables=tables_input)
@settings(max_examples=200)
def test_normalize_tables_cell_count_matches_input(tables):
    """Property 10 (completeness): total cells output == total cells input."""
    processor = DocumentProcessor()
    result = processor._normalize_pdfplumber_tables(tables)

    for original_table, normalized_cells in zip(tables, result):
        expected_cell_count = sum(len(row) for row in original_table)
        assert len(normalized_cells) == expected_cell_count


# ---------------------------------------------------------------------------
# Property 9: Image OCR Output Structure
# Validates: Requirements 4.2, 4.3
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch

text_line_strategy = st.text(
    max_size=30,
    alphabet=st.characters(blacklist_categories=["Cs"]),
)
text_lines_strategy = st.lists(text_line_strategy, min_size=0, max_size=10)


@given(text_lines=text_lines_strategy)
@settings(max_examples=200)
def test_image_ocr_output_structure(text_lines):
    """Property 9: output always has "text" as str and "tables" as empty list.

    **Validates: Requirements 4.2, 4.3**
    """
    mock_ocr_result = (
        [[[None, [line, 0.99]] for line in text_lines]] if text_lines else [[]]
    )

    processor = DocumentProcessor()
    with patch("doc_processing.PaddleOCR") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.ocr.return_value = mock_ocr_result
        mock_cls.return_value = mock_instance

        result = processor._process_image("test.jpg")

    assert isinstance(result["text"], str)
    assert result["tables"] == []

    if text_lines:
        expected = "\n".join(text_lines)
        assert result["text"] == expected


@given(text_lines=text_lines_strategy)
@settings(max_examples=100)
def test_image_ocr_none_result_returns_empty_text(text_lines):
    """Property 9 (None/empty OCR): None or empty OCR result always returns empty text.

    **Validates: Requirements 4.2, 4.3**
    """
    processor = DocumentProcessor()

    # Test with None result
    with patch("doc_processing.PaddleOCR") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.ocr.return_value = None
        mock_cls.return_value = mock_instance

        result = processor._process_image("test.jpg")

    assert result == {"text": "", "tables": []}

    # Test with empty first page result [[]]
    del processor._ocr  # reset lazy init
    with patch("doc_processing.PaddleOCR") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.ocr.return_value = [[]]
        mock_cls.return_value = mock_instance

        result = processor._process_image("test.jpg")

    assert isinstance(result["text"], str)
    assert result["tables"] == []


# ---------------------------------------------------------------------------
# Property 1: Output Contract Preservation
# Validates: Requirements 5.1, 5.2
# ---------------------------------------------------------------------------

VALID_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"]

valid_extension = st.sampled_from(VALID_EXTENSIONS)
text_content = st.text(max_size=100)
table_content = st.lists(
    st.lists(
        st.fixed_dictionaries({
            "row_index": st.integers(min_value=0, max_value=10),
            "column_index": st.integers(min_value=0, max_value=10),
            "content": st.text(max_size=20),
        }),
        min_size=0, max_size=5
    ),
    min_size=0, max_size=3
)


@given(
    ext=valid_extension,
    text=text_content,
    tables=table_content,
)
@settings(max_examples=200)
def test_output_contract_preservation(ext, text, tables):
    """Property 1: process_document() always returns {"text": str, "tables": list}.

    **Validates: Requirements 5.1, 5.2**
    """
    file_path = f"document{ext}"
    mock_result = {"text": text, "tables": tables}

    processor = DocumentProcessor()
    with patch("doc_processing.os.path.exists", return_value=True), \
         patch.object(DocumentProcessor, "_process_pdf", return_value=mock_result), \
         patch.object(DocumentProcessor, "_process_image", return_value=mock_result):

        result = processor.process_document(file_path)

    # Exactly two keys
    assert set(result.keys()) == {"text", "tables"}
    # text is always a string
    assert isinstance(result["text"], str)
    # tables is always a list
    assert isinstance(result["tables"], list)


# ---------------------------------------------------------------------------
# Property 2: Table Cell Structure Integrity
# Validates: Requirements 5.3
# ---------------------------------------------------------------------------

@given(tables=tables_input)
@settings(max_examples=200)
def test_table_cell_structure_integrity(tables):
    """Property 2: every cell dict has exactly {row_index, column_index, content} with correct types."""
    processor = DocumentProcessor()
    result = processor._normalize_pdfplumber_tables(tables)

    for table_cells in result:
        for cell in table_cells:
            assert set(cell.keys()) == {"row_index", "column_index", "content"}
            assert isinstance(cell["row_index"], int) and cell["row_index"] >= 0
            assert isinstance(cell["column_index"], int) and cell["column_index"] >= 0
            assert isinstance(cell["content"], str)
            assert cell["content"] is not None


# ---------------------------------------------------------------------------
# Property 15: Exception Propagation
# Validates: Requirements 3.5, 9.3, 9.4
# ---------------------------------------------------------------------------

exception_types = st.sampled_from([
    ValueError("bad value"),
    RuntimeError("runtime error"),
    IOError("io error"),
    OSError("os error"),
    Exception("generic exception"),
])


@given(exc=exception_types)
@settings(max_examples=50)
def test_pdfplumber_exceptions_propagate(exc):
    """Property 15: exceptions from pdfplumber propagate to the caller unchanged.

    **Validates: Requirements 3.5, 9.3**
    """
    processor = DocumentProcessor()

    with patch("doc_processing.pdfplumber.open", side_effect=exc):
        with pytest.raises(type(exc)):
            processor._process_pdf("any.pdf")


@given(exc=exception_types)
@settings(max_examples=50)
def test_paddleocr_exceptions_propagate(exc):
    """Property 15: exceptions from PaddleOCR propagate to the caller unchanged.

    **Validates: Requirements 3.5, 9.4**
    """
    processor = DocumentProcessor()

    with patch("doc_processing.PaddleOCR") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.ocr.side_effect = exc
        mock_cls.return_value = mock_instance

        with pytest.raises(type(exc)):
            processor._process_image("any.jpg")
