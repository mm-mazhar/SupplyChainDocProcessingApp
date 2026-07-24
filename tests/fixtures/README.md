# Test Fixtures

Minimal synthetic files used by the integration test suite. All files are
generated programmatically by `scripts/generate_test_fixtures.py` — no
external downloads required.

| File | Type | Purpose |
|------|------|---------|
| `sample_text_pdf.pdf` | Text-based PDF | Exercises pdfplumber text + table extraction. Contains a one-page invoice with a line-items table. pdfplumber should return non-empty text and at least one table. |
| `sample_scanned_pdf.pdf` | Image-only PDF | Simulates a scanned document. Has no text layer, so pdfplumber returns empty text on every page, triggering the OCR fallback path in `DocumentProcessor`. |
| `empty.pdf` | Blank PDF | Edge case: a valid one-page PDF with no content. `DocumentProcessor` should return `{"text": "", "tables": []}` without raising. |
| `sample_receipt.jpg` | JPEG image | Exercises the image OCR path. Contains receipt-style text fields (store, date, items, totals). `DocumentProcessor` should route it through PaddleOCR. |
| `sample_invoice.png` | PNG image | Exercises the image OCR path with a more structured layout (header, table columns, totals). `DocumentProcessor` should route it through PaddleOCR. |

## Regenerating

```bash
uv run python scripts/generate_test_fixtures.py
```

No extra dependencies beyond what is already in `pyproject.toml` (Pillow is a
transitive dependency of paddleocr; raw PDF bytes need no additional library).
