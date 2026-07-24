"""Unit tests for DocumentProcessor file-type routing.

Covers Requirements 6.3, 6.4, 6.5:
  - ValueError for unsupported extensions
  - IOError for non-existent file paths
  - Case-insensitive extension routing
"""
from unittest.mock import MagicMock, patch

import pytest

from doc_processing import DocumentProcessor


@pytest.fixture()
def processor() -> DocumentProcessor:
    return DocumentProcessor()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exists_and_route(target_method: str):
    """Return a context-manager pair: os.path.exists=True + patched target."""
    return (
        patch("doc_processing.os.path.exists", return_value=True),
        patch.object(DocumentProcessor, target_method, return_value={"text": "", "tables": []}),
    )


# ---------------------------------------------------------------------------
# PDF routing
# ---------------------------------------------------------------------------

class TestPdfRouting:
    def test_pdf_extension_calls_process_pdf(self, processor: DocumentProcessor) -> None:
        # Arrange
        with patch("doc_processing.os.path.exists", return_value=True), \
             patch.object(DocumentProcessor, "_process_pdf", return_value={"text": "hello", "tables": []}) as mock_pdf:
            # Act
            result = processor.process_document("invoice.pdf")

        # Assert
        mock_pdf.assert_called_once_with("invoice.pdf")
        assert result == {"text": "hello", "tables": []}

    def test_pdf_routing_does_not_call_process_image(self, processor: DocumentProcessor) -> None:
        with patch("doc_processing.os.path.exists", return_value=True), \
             patch.object(DocumentProcessor, "_process_pdf", return_value={"text": "", "tables": []}), \
             patch.object(DocumentProcessor, "_process_image") as mock_img:
            processor.process_document("doc.pdf")

        mock_img.assert_not_called()


# ---------------------------------------------------------------------------
# Image routing
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]


class TestImageRouting:
    @pytest.mark.parametrize("ext", IMAGE_EXTENSIONS)
    def test_image_extension_calls_process_image(
        self, processor: DocumentProcessor, ext: str
    ) -> None:
        file_path = f"scan{ext}"

        with patch("doc_processing.os.path.exists", return_value=True), \
             patch.object(DocumentProcessor, "_process_image", return_value={"text": "ocr", "tables": []}) as mock_img:
            result = processor.process_document(file_path)

        mock_img.assert_called_once_with(file_path)
        assert result == {"text": "ocr", "tables": []}

    @pytest.mark.parametrize("ext", IMAGE_EXTENSIONS)
    def test_image_routing_does_not_call_process_pdf(
        self, processor: DocumentProcessor, ext: str
    ) -> None:
        with patch("doc_processing.os.path.exists", return_value=True), \
             patch.object(DocumentProcessor, "_process_image", return_value={"text": "", "tables": []}), \
             patch.object(DocumentProcessor, "_process_pdf") as mock_pdf:
            processor.process_document(f"scan{ext}")

        mock_pdf.assert_not_called()


# ---------------------------------------------------------------------------
# Unsupported extension → ValueError  (Requirement 6.3)
# ---------------------------------------------------------------------------

class TestUnsupportedExtension:
    @pytest.mark.parametrize("file_path", [
        "report.txt",
        "spreadsheet.docx",
        "archive.zip",
        "data.csv",
        "image.gif",
    ])
    def test_unsupported_extension_raises_value_error(
        self, processor: DocumentProcessor, file_path: str
    ) -> None:
        with patch("doc_processing.os.path.exists", return_value=True):
            with pytest.raises(ValueError, match="Unsupported file type"):
                processor.process_document(file_path)

    def test_value_error_message_includes_extension(self, processor: DocumentProcessor) -> None:
        with patch("doc_processing.os.path.exists", return_value=True):
            with pytest.raises(ValueError) as exc_info:
                processor.process_document("notes.txt")

        assert ".txt" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Non-existent file → IOError  (Requirement 6.4)
# ---------------------------------------------------------------------------

class TestNonExistentFile:
    def test_missing_file_raises_ioerror(self, processor: DocumentProcessor) -> None:
        with patch("doc_processing.os.path.exists", return_value=False):
            with pytest.raises(IOError, match="File not found"):
                processor.process_document("/no/such/file.pdf")

    def test_ioerror_message_includes_path(self, processor: DocumentProcessor) -> None:
        missing = "/ghost/path/invoice.pdf"
        with patch("doc_processing.os.path.exists", return_value=False):
            with pytest.raises(IOError) as exc_info:
                processor.process_document(missing)

        assert missing in str(exc_info.value)

    def test_ioerror_checked_before_extension_routing(self, processor: DocumentProcessor) -> None:
        """IOError must be raised for unsupported extension when file also doesn't exist."""
        with patch("doc_processing.os.path.exists", return_value=False):
            with pytest.raises(IOError):
                processor.process_document("/ghost/path/report.txt")


# ---------------------------------------------------------------------------
# Case-insensitive extension matching  (Requirement 6.5)
# ---------------------------------------------------------------------------

class TestCaseInsensitiveRouting:
    @pytest.mark.parametrize("file_path", [
        "invoice.PDF",
        "invoice.Pdf",
        "invoice.pDf",
    ])
    def test_uppercase_pdf_routes_to_process_pdf(
        self, processor: DocumentProcessor, file_path: str
    ) -> None:
        with patch("doc_processing.os.path.exists", return_value=True), \
             patch.object(DocumentProcessor, "_process_pdf", return_value={"text": "", "tables": []}) as mock_pdf:
            processor.process_document(file_path)

        mock_pdf.assert_called_once_with(file_path)

    @pytest.mark.parametrize("file_path,ext", [
        ("photo.PNG", ".png"),
        ("photo.JPG", ".jpg"),
        ("photo.JPEG", ".jpeg"),
        ("photo.TIFF", ".tiff"),
        ("photo.BMP", ".bmp"),
        ("photo.Png", ".png"),
    ])
    def test_uppercase_image_routes_to_process_image(
        self, processor: DocumentProcessor, file_path: str, ext: str
    ) -> None:
        with patch("doc_processing.os.path.exists", return_value=True), \
             patch.object(DocumentProcessor, "_process_image", return_value={"text": "", "tables": []}) as mock_img:
            processor.process_document(file_path)

        mock_img.assert_called_once_with(file_path)


# ---------------------------------------------------------------------------
# pdfplumber integration  (Requirements 2.2, 2.3, 2.4, 2.5)
# ---------------------------------------------------------------------------

def _make_page(text: str | None, tables: list) -> MagicMock:
    """Build a mock pdfplumber page with fixed extract_text / extract_tables."""
    page = MagicMock()
    page.extract_text.return_value = text
    page.extract_tables.return_value = tables
    return page


def _make_pdf_ctx(*pages: MagicMock) -> MagicMock:
    """Return a mock context manager whose __enter__ yields a PDF with .pages."""
    pdf = MagicMock()
    pdf.pages = list(pages)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=pdf)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestPdfplumberIntegration:
    """Unit tests for _process_pdf() using mocked pdfplumber.

    Covers Requirements 2.2, 2.3, 2.4, 2.5.
    """

    # ------------------------------------------------------------------
    # Req 2.2: multi-page text is concatenated with newline separators
    # ------------------------------------------------------------------

    def test_multipage_text_concatenated_with_newline(
        self, processor: DocumentProcessor
    ) -> None:
        page1 = _make_page("Page one text", [])
        page2 = _make_page("Page two text", [])
        pdf_ctx = _make_pdf_ctx(page1, page2)

        with patch("doc_processing.pdfplumber.open", return_value=pdf_ctx):
            result = processor._process_pdf("dummy.pdf")

        assert result["text"] == "Page one text\nPage two text"

    def test_empty_page_text_is_excluded_from_concatenation(
        self, processor: DocumentProcessor
    ) -> None:
        """None / empty results from extract_text must not add blank lines."""
        page1 = _make_page("Real content", [])
        page2 = _make_page(None, [])  # blank page
        pdf_ctx = _make_pdf_ctx(page1, page2)

        with patch("doc_processing.pdfplumber.open", return_value=pdf_ctx):
            result = processor._process_pdf("dummy.pdf")

        assert result["text"] == "Real content"

    # ------------------------------------------------------------------
    # Req 2.3 / 5.4: tables are extracted and normalized to cell-dict format
    # ------------------------------------------------------------------

    def test_table_extraction_produces_cell_dict_format(
        self, processor: DocumentProcessor
    ) -> None:
        raw_table = [
            ["Header A", "Header B"],
            ["Row 1 A",  "Row 1 B"],
        ]
        page = _make_page("Some text", [raw_table])
        pdf_ctx = _make_pdf_ctx(page)

        with patch("doc_processing.pdfplumber.open", return_value=pdf_ctx):
            result = processor._process_pdf("dummy.pdf")

        assert len(result["tables"]) == 1
        cells = result["tables"][0]
        # 2 rows × 2 cols = 4 cells
        assert len(cells) == 4

        cell_00 = next(c for c in cells if c["row_index"] == 0 and c["column_index"] == 0)
        assert cell_00 == {"row_index": 0, "column_index": 0, "content": "Header A"}

        cell_11 = next(c for c in cells if c["row_index"] == 1 and c["column_index"] == 1)
        assert cell_11 == {"row_index": 1, "column_index": 1, "content": "Row 1 B"}

    def test_none_cell_values_become_empty_string(
        self, processor: DocumentProcessor
    ) -> None:
        """Req 5.5: None cell values must be represented as empty string."""
        raw_table = [["Value", None]]
        page = _make_page("text", [raw_table])
        pdf_ctx = _make_pdf_ctx(page)

        with patch("doc_processing.pdfplumber.open", return_value=pdf_ctx):
            result = processor._process_pdf("dummy.pdf")

        cells = result["tables"][0]
        none_cell = next(c for c in cells if c["column_index"] == 1)
        assert none_cell["content"] == ""

    def test_tables_collected_across_all_pages(
        self, processor: DocumentProcessor
    ) -> None:
        """Req 2.3: tables from every page are merged into the output list."""
        table_p1 = [["A", "B"]]
        table_p2 = [["C", "D"]]
        page1 = _make_page("text p1", [table_p1])
        page2 = _make_page("text p2", [table_p2])
        pdf_ctx = _make_pdf_ctx(page1, page2)

        with patch("doc_processing.pdfplumber.open", return_value=pdf_ctx):
            result = processor._process_pdf("dummy.pdf")

        assert len(result["tables"]) == 2

    # ------------------------------------------------------------------
    # Req 2.4: if at least one page has text, OCR must NOT be invoked
    # ------------------------------------------------------------------

    def test_ocr_not_called_when_text_extracted(
        self, processor: DocumentProcessor
    ) -> None:
        page = _make_page("Extractable text", [])
        pdf_ctx = _make_pdf_ctx(page)

        with patch("doc_processing.pdfplumber.open", return_value=pdf_ctx), \
             patch.object(DocumentProcessor, "_fallback_to_ocr") as mock_ocr:
            processor._process_pdf("dummy.pdf")

        mock_ocr.assert_not_called()

    # ------------------------------------------------------------------
    # Req 2.5: text-based PDF with no tables returns empty tables list
    # ------------------------------------------------------------------

    def test_pdf_with_text_but_no_tables_returns_empty_tables(
        self, processor: DocumentProcessor
    ) -> None:
        page = _make_page("Some text, no tables", [])
        pdf_ctx = _make_pdf_ctx(page)

        with patch("doc_processing.pdfplumber.open", return_value=pdf_ctx):
            result = processor._process_pdf("dummy.pdf")

        assert result["text"] == "Some text, no tables"
        assert result["tables"] == []

    # ------------------------------------------------------------------
    # Req 3.1: empty PDF (no text, no tables) triggers OCR fallback
    # ------------------------------------------------------------------

    def test_empty_pdf_triggers_ocr_fallback(
        self, processor: DocumentProcessor
    ) -> None:
        page = _make_page(None, [])  # all pages return no text
        pdf_ctx = _make_pdf_ctx(page)
        ocr_result = {"text": "ocr extracted text", "tables": []}

        with patch("doc_processing.pdfplumber.open", return_value=pdf_ctx), \
             patch.object(
                 DocumentProcessor, "_fallback_to_ocr", return_value=ocr_result
             ) as mock_ocr:
            result = processor._process_pdf("dummy.pdf")

        mock_ocr.assert_called_once_with("dummy.pdf")
        assert result == ocr_result

    def test_empty_pdf_multi_blank_pages_triggers_ocr_fallback(
        self, processor: DocumentProcessor
    ) -> None:
        """Multiple blank pages — all None — must still route to OCR."""
        pages = [_make_page(None, []) for _ in range(3)]
        pdf_ctx = _make_pdf_ctx(*pages)
        ocr_result = {"text": "", "tables": []}

        with patch("doc_processing.pdfplumber.open", return_value=pdf_ctx), \
             patch.object(
                 DocumentProcessor, "_fallback_to_ocr", return_value=ocr_result
             ) as mock_ocr:
            result = processor._process_pdf("dummy.pdf")

        mock_ocr.assert_called_once_with("dummy.pdf")
        assert result == {"text": "", "tables": []}


# ---------------------------------------------------------------------------
# Table normalization helper tests (Requirement 5.4, 5.5)
# ---------------------------------------------------------------------------

class TestNormalizePdfplumberTables:
    """Unit tests for _normalize_pdfplumber_tables() helper method.

    Covers Requirements 5.4, 5.5.
    """

    def test_empty_input_returns_empty_list(self, processor: DocumentProcessor) -> None:
        """Empty table list should return empty result."""
        result = processor._normalize_pdfplumber_tables([])
        assert result == []

    def test_single_2x2_table_with_string_values(
        self, processor: DocumentProcessor
    ) -> None:
        """2×2 table with all strings produces correct cell dicts."""
        raw_table = [
            ["A", "B"],
            ["C", "D"],
        ]
        result = processor._normalize_pdfplumber_tables([raw_table])

        assert len(result) == 1
        cells = result[0]
        assert len(cells) == 4

        # Verify cell format
        assert cells[0] == {"row_index": 0, "column_index": 0, "content": "A"}
        assert cells[1] == {"row_index": 0, "column_index": 1, "content": "B"}
        assert cells[2] == {"row_index": 1, "column_index": 0, "content": "C"}
        assert cells[3] == {"row_index": 1, "column_index": 1, "content": "D"}

    def test_table_with_none_values_become_empty_string(
        self, processor: DocumentProcessor
    ) -> None:
        """None values in cells must be converted to empty string."""
        raw_table = [
            ["Value", None],
            [None, "Another"],
        ]
        result = processor._normalize_pdfplumber_tables([raw_table])

        cells = result[0]
        assert len(cells) == 4

        # Check None cells converted to empty string
        none_cell_1 = next(c for c in cells if c["row_index"] == 0 and c["column_index"] == 1)
        assert none_cell_1["content"] == ""

        none_cell_2 = next(c for c in cells if c["row_index"] == 1 and c["column_index"] == 0)
        assert none_cell_2["content"] == ""

    def test_ragged_table_all_cells_present(
        self, processor: DocumentProcessor
    ) -> None:
        """Ragged table (rows with different lengths) must still produce all cells."""
        raw_table = [
            ["A", "B", "C"],  # 3 columns
            ["D", "E"],       # 2 columns
            ["F"],            # 1 column
        ]
        result = processor._normalize_pdfplumber_tables([raw_table])

        cells = result[0]
        # Total cells: 3 + 2 + 1 = 6
        assert len(cells) == 6

        # Verify indices are correct
        assert cells[0] == {"row_index": 0, "column_index": 0, "content": "A"}
        assert cells[1] == {"row_index": 0, "column_index": 1, "content": "B"}
        assert cells[2] == {"row_index": 0, "column_index": 2, "content": "C"}
        assert cells[3] == {"row_index": 1, "column_index": 0, "content": "D"}
        assert cells[4] == {"row_index": 1, "column_index": 1, "content": "E"}
        assert cells[5] == {"row_index": 2, "column_index": 0, "content": "F"}

    def test_multiple_tables_normalized_separately(
        self, processor: DocumentProcessor
    ) -> None:
        """Multiple tables must each be normalized independently."""
        table1 = [["A", "B"]]
        table2 = [["X"], ["Y"]]
        result = processor._normalize_pdfplumber_tables([table1, table2])

        assert len(result) == 2

        # First table: 1 row × 2 cols = 2 cells
        assert len(result[0]) == 2
        assert result[0][0]["content"] == "A"
        assert result[0][1]["content"] == "B"

        # Second table: 2 rows × 1 col = 2 cells
        assert len(result[1]) == 2
        assert result[1][0]["content"] == "X"
        assert result[1][1]["content"] == "Y"


# ---------------------------------------------------------------------------
# PaddleOCR integration tests  (Requirements 7.1, 7.2, 7.3, 7.5)
# ---------------------------------------------------------------------------

class TestPaddleOCRIntegration:
    """Unit tests for _process_image() and lazy PaddleOCR initialization.

    Covers Requirements 7.1, 7.2, 7.3, 7.5.
    """

    # ------------------------------------------------------------------
    # Req 7.1: PaddleOCR NOT initialized at __init__ time
    # ------------------------------------------------------------------

    def test_paddleocr_not_initialized_on_instantiation(self) -> None:
        with patch("doc_processing.PaddleOCR") as mock_cls:
            DocumentProcessor()
            mock_cls.assert_not_called()

    # ------------------------------------------------------------------
    # Req 7.2: First image call initializes PaddleOCR with correct args
    # ------------------------------------------------------------------

    def test_first_image_call_initializes_paddleocr_once(self) -> None:
        with patch("doc_processing.PaddleOCR") as mock_cls, \
             patch("doc_processing.os.path.exists", return_value=True):
            mock_instance = MagicMock()
            mock_instance.ocr.return_value = [[[ [[0,0],[1,0],[1,1],[0,1]], ["extracted text", 0.99] ]]]
            mock_cls.return_value = mock_instance

            proc = DocumentProcessor()
            proc.process_document("scan.jpg")

            mock_cls.assert_called_once_with(use_angle_cls=True, lang="en", show_log=False)

    def test_paddleocr_initialized_with_custom_lang(self) -> None:
        with patch("doc_processing.PaddleOCR") as mock_cls, \
             patch("doc_processing.os.path.exists", return_value=True):
            mock_instance = MagicMock()
            mock_instance.ocr.return_value = [[[ [[0,0],[1,0],[1,1],[0,1]], ["text", 0.99] ]]]
            mock_cls.return_value = mock_instance

            proc = DocumentProcessor(lang="ch")
            proc.process_document("scan.jpg")

            mock_cls.assert_called_once_with(use_angle_cls=True, lang="ch", show_log=False)

    # ------------------------------------------------------------------
    # Req 7.3: Second image call reuses existing PaddleOCR instance
    # ------------------------------------------------------------------

    def test_second_image_call_reuses_ocr_instance(self) -> None:
        with patch("doc_processing.PaddleOCR") as mock_cls, \
             patch("doc_processing.os.path.exists", return_value=True):
            mock_instance = MagicMock()
            mock_instance.ocr.return_value = [[[ [[0,0],[1,0],[1,1],[0,1]], ["line", 0.95] ]]]
            mock_cls.return_value = mock_instance

            proc = DocumentProcessor()
            proc.process_document("scan1.png")
            proc.process_document("scan2.png")

            mock_cls.assert_called_once()

    # ------------------------------------------------------------------
    # Req 4.2: Text lines joined with newlines
    # ------------------------------------------------------------------

    def test_image_ocr_text_extracted_and_joined(self) -> None:
        ocr_result = [[
            [ [[0,0],[1,0],[1,1],[0,1]], ["first line", 0.99] ],
            [ [[0,1],[1,1],[1,2],[0,2]], ["second line", 0.95] ],
        ]]
        with patch("doc_processing.PaddleOCR") as mock_cls, \
             patch("doc_processing.os.path.exists", return_value=True):
            mock_instance = MagicMock()
            mock_instance.ocr.return_value = ocr_result
            mock_cls.return_value = mock_instance

            proc = DocumentProcessor()
            result = proc.process_document("photo.jpg")

        assert result["text"] == "first line\nsecond line"
        assert result["tables"] == []

    # ------------------------------------------------------------------
    # Req 9.2: None OCR result → empty text, empty tables
    # ------------------------------------------------------------------

    def test_none_ocr_result_returns_empty(self) -> None:
        with patch("doc_processing.PaddleOCR") as mock_cls, \
             patch("doc_processing.os.path.exists", return_value=True):
            mock_instance = MagicMock()
            mock_instance.ocr.return_value = None
            mock_cls.return_value = mock_instance

            proc = DocumentProcessor()
            result = proc.process_document("blank.png")

        assert result == {"text": "", "tables": []}

    # ------------------------------------------------------------------
    # Req 9.2: Empty result[0] → empty text, empty tables
    # ------------------------------------------------------------------

    def test_empty_result_list_returns_empty(self) -> None:
        with patch("doc_processing.PaddleOCR") as mock_cls, \
             patch("doc_processing.os.path.exists", return_value=True):
            mock_instance = MagicMock()
            mock_instance.ocr.return_value = [[]]   # result[0] is empty list
            mock_cls.return_value = mock_instance

            proc = DocumentProcessor()
            result = proc.process_document("blank.jpg")

        assert result == {"text": "", "tables": []}

    # ------------------------------------------------------------------
    # Req 4.3: Image processing always returns empty tables list
    # ------------------------------------------------------------------

    def test_image_processing_always_returns_empty_tables(self) -> None:
        with patch("doc_processing.PaddleOCR") as mock_cls, \
             patch("doc_processing.os.path.exists", return_value=True):
            mock_instance = MagicMock()
            mock_instance.ocr.return_value = [[[ [[0,0],[1,0],[1,1],[0,1]], ["some text", 0.99] ]]]
            mock_cls.return_value = mock_instance

            proc = DocumentProcessor()
            result = proc.process_document("invoice.tiff")

        assert result["tables"] == []

    # ------------------------------------------------------------------
    # Req 7.5: PDF-only workflow never initializes PaddleOCR
    # ------------------------------------------------------------------

    def test_pdf_only_workflow_never_initializes_paddleocr(self) -> None:
        page = _make_page("Extractable PDF text", [])
        pdf_ctx = _make_pdf_ctx(page)

        with patch("doc_processing.PaddleOCR") as mock_cls, \
             patch("doc_processing.pdfplumber.open", return_value=pdf_ctx), \
             patch("doc_processing.os.path.exists", return_value=True):

            proc = DocumentProcessor()
            result = proc.process_document("document.pdf")

        mock_cls.assert_not_called()
        assert result["text"] == "Extractable PDF text"

    # ------------------------------------------------------------------
    # Req 3.2: Scanned PDF fallback invokes OCR
    # ------------------------------------------------------------------

    def test_scanned_pdf_fallback_invokes_ocr(self) -> None:
        page = _make_page(None, [])   # no extractable text → scanned PDF
        pdf_ctx = _make_pdf_ctx(page)

        with patch("doc_processing.PaddleOCR") as mock_cls, \
             patch("doc_processing.pdfplumber.open", return_value=pdf_ctx), \
             patch("doc_processing.os.path.exists", return_value=True):
            mock_instance = MagicMock()
            mock_instance.ocr.return_value = [[[ [[0,0],[1,0],[1,1],[0,1]], ["ocr from pdf", 0.98] ]]]
            mock_cls.return_value = mock_instance

            proc = DocumentProcessor()
            result = proc.process_document("scanned.pdf")

        mock_cls.assert_called_once()
        mock_instance.ocr.assert_called_once_with("scanned.pdf", cls=True)
        assert result["text"] == "ocr from pdf"
        assert result["tables"] == []
