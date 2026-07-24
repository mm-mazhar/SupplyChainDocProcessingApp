"""Generate test fixture files for integration testing.

Uses raw PDF bytes (no reportlab) and Pillow for images.
Run with: uv run python scripts/generate_test_fixtures.py
"""

import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def _pdf_stream(content: bytes) -> bytes:
    """Wrap raw content bytes in a PDF stream object."""
    return b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"


def create_text_pdf(path: Path) -> None:
    """Create a minimal text-based PDF with a paragraph and a simple table."""
    # Build content stream: text + a hand-drawn table via lines
    content = (
        b"BT\n"
        b"/F1 14 Tf\n"
        b"50 750 Td\n"
        b"(Supply Chain Document - Invoice) Tj\n"
        b"0 -25 Td\n"
        b"/F1 10 Tf\n"
        b"(Vendor: Acme Corp   PO Number: PO-2024-001   Date: 2024-01-15) Tj\n"
        b"0 -15 Td\n"
        b"(Description: Industrial components for assembly line.) Tj\n"
        b"0 -30 Td\n"
        b"(--- Table: Line Items ---) Tj\n"
        b"0 -15 Td\n"
        b"(Item        Qty    Unit Price    Total) Tj\n"
        b"0 -15 Td\n"
        b"(Widget A    10     $5.00         $50.00) Tj\n"
        b"0 -15 Td\n"
        b"(Widget B    5      $12.00        $60.00) Tj\n"
        b"0 -15 Td\n"
        b"(Bolt Set    100    $0.50         $50.00) Tj\n"
        b"0 -30 Td\n"
        b"(Total: $160.00) Tj\n"
        b"ET\n"
    )

    stream = _pdf_stream(content)

    objects: list[bytes] = []

    # obj 1: catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # obj 2: pages
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    # obj 3: page
    objects.append(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R\n"
        b"   /MediaBox [0 0 612 792]\n"
        b"   /Contents 4 0 R\n"
        b"   /Resources << /Font << /F1 5 0 R >> >> >>\n"
        b"endobj\n"
    )
    # obj 4: content stream
    objects.append(b"4 0 obj\n" + stream + b"\nendobj\n")
    # obj 5: font
    objects.append(
        b"5 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        b"endobj\n"
    )

    _write_pdf(path, objects)


def create_scanned_pdf(path: Path) -> None:
    """Create a PDF that contains only an embedded image (no text layer).

    Simulates a scanned document — pdfplumber will extract no text,
    triggering the OCR fallback path in DocumentProcessor.
    """
    # Generate a small grayscale image with some marks to embed
    img = Image.new("L", (200, 100), color=240)
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 190, 90], outline=0, width=2)
    draw.line([10, 50, 190, 50], fill=0, width=1)
    draw.text((20, 20), "SCANNED", fill=0)
    draw.text((20, 55), "DOCUMENT", fill=0)

    # Convert image to raw RGB bytes for embedding in PDF
    img_rgb = img.convert("RGB")
    width, height = img_rgb.size
    raw_rgb = img_rgb.tobytes()

    img_stream = (
        b"<< /Type /XObject /Subtype /Image\n"
        b"   /Width " + str(width).encode() + b"\n"
        b"   /Height " + str(height).encode() + b"\n"
        b"   /ColorSpace /DeviceRGB\n"
        b"   /BitsPerComponent 8\n"
        b"   /Length " + str(len(raw_rgb)).encode() + b"\n"
        b">>\n"
        b"stream\n" + raw_rgb + b"\nendstream"
    )

    # Content stream: draw the image on the page
    content = (
        b"q\n"
        + str(width * 2).encode() + b" 0 0 " + str(height * 2).encode() + b" 50 400 cm\n"
        b"/Im1 Do\n"
        b"Q\n"
    )
    content_stream = _pdf_stream(content)

    objects: list[bytes] = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R\n"
        b"   /MediaBox [0 0 612 792]\n"
        b"   /Contents 4 0 R\n"
        b"   /Resources << /XObject << /Im1 5 0 R >> >> >>\n"
        b"endobj\n"
    )
    objects.append(b"4 0 obj\n" + content_stream + b"\nendobj\n")
    objects.append(b"5 0 obj\n" + img_stream + b"\nendobj\n")

    _write_pdf(path, objects)


def create_empty_pdf(path: Path) -> None:
    """Create a blank PDF with one empty page — no content whatsoever."""
    content = b""
    stream = _pdf_stream(content)

    objects: list[bytes] = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R\n"
        b"   /MediaBox [0 0 612 792]\n"
        b"   /Contents 4 0 R\n"
        b"   /Resources << >> >>\n"
        b"endobj\n"
    )
    objects.append(b"4 0 obj\n" + stream + b"\nendobj\n")

    _write_pdf(path, objects)


def _write_pdf(path: Path, objects: list[bytes]) -> None:
    """Assemble PDF objects with a proper cross-reference table and trailer."""
    header = b"%PDF-1.4\n"
    body = b""
    offsets: list[int] = []

    pos = len(header)
    for obj in objects:
        offsets.append(pos)
        body += obj
        pos += len(obj)

    xref_offset = len(header) + len(body)
    xref = b"xref\n"
    xref += b"0 " + str(len(objects) + 1).encode() + b"\n"
    xref += b"0000000000 65535 f \n"
    for off in offsets:
        xref += str(off).zfill(10).encode() + b" 00000 n \n"

    trailer = (
        b"trailer\n"
        b"<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n"
        + str(xref_offset).encode() + b"\n"
        b"%%EOF\n"
    )

    path.write_bytes(header + body + xref + trailer)


def create_receipt_jpg(path: Path) -> None:
    """Create a simple JPEG receipt image with readable text fields."""
    img = Image.new("RGB", (400, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, 399, 299], outline=(0, 0, 0), width=2)
    draw.text((20, 15), "RECEIPT", fill=(0, 0, 0))
    draw.line([0, 40, 400, 40], fill=(0, 0, 0), width=1)
    draw.text((20, 55), "Store: Supply Co.", fill=(0, 0, 0))
    draw.text((20, 75), "Date: 2024-01-15", fill=(0, 0, 0))
    draw.text((20, 95), "Trans #: 00123", fill=(0, 0, 0))
    draw.line([0, 120, 400, 120], fill=(0, 0, 0), width=1)
    draw.text((20, 135), "Item A         $10.00", fill=(0, 0, 0))
    draw.text((20, 155), "Item B          $5.50", fill=(0, 0, 0))
    draw.text((20, 175), "Item C          $3.25", fill=(0, 0, 0))
    draw.line([0, 200, 400, 200], fill=(0, 0, 0), width=1)
    draw.text((20, 215), "SUBTOTAL       $18.75", fill=(0, 0, 0))
    draw.text((20, 235), "TAX (8%)        $1.50", fill=(0, 0, 0))
    draw.text((20, 255), "TOTAL          $20.25", fill=(0, 0, 0))
    draw.line([0, 275, 400, 275], fill=(0, 0, 0), width=1)
    draw.text((120, 280), "Thank you!", fill=(0, 0, 0))

    img.save(path, format="JPEG", quality=90)


def create_invoice_png(path: Path) -> None:
    """Create a simple PNG invoice image with structured fields."""
    img = Image.new("RGB", (500, 400), color=(245, 245, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, 499, 399], outline=(50, 50, 150), width=3)
    draw.rectangle([0, 0, 499, 50], fill=(50, 50, 150))
    draw.text((180, 15), "INVOICE", fill=(255, 255, 255))
    draw.text((20, 70), "Invoice #: INV-2024-0042", fill=(0, 0, 0))
    draw.text((20, 90), "Date: 2024-01-15", fill=(0, 0, 0))
    draw.text((20, 110), "Due Date: 2024-02-14", fill=(0, 0, 0))
    draw.text((280, 70), "Bill To:", fill=(0, 0, 0))
    draw.text((280, 90), "ACME Corporation", fill=(0, 0, 0))
    draw.text((280, 110), "123 Main St, Anytown", fill=(0, 0, 0))
    draw.line([0, 145, 500, 145], fill=(50, 50, 150), width=2)
    draw.text((20, 155), "Description", fill=(0, 0, 80))
    draw.text((300, 155), "Qty", fill=(0, 0, 80))
    draw.text((360, 155), "Unit Price", fill=(0, 0, 80))
    draw.text((440, 155), "Total", fill=(0, 0, 80))
    draw.line([0, 175, 500, 175], fill=(200, 200, 200), width=1)
    draw.text((20, 185), "Industrial Widget", fill=(0, 0, 0))
    draw.text((310, 185), "50", fill=(0, 0, 0))
    draw.text((365, 185), "$2.50", fill=(0, 0, 0))
    draw.text((440, 185), "$125.00", fill=(0, 0, 0))
    draw.text((20, 205), "Steel Bolt M8", fill=(0, 0, 0))
    draw.text((305, 205), "200", fill=(0, 0, 0))
    draw.text((365, 205), "$0.15", fill=(0, 0, 0))
    draw.text((443, 205), "$30.00", fill=(0, 0, 0))
    draw.text((20, 225), "Assembly Kit", fill=(0, 0, 0))
    draw.text((315, 225), "10", fill=(0, 0, 0))
    draw.text((365, 225), "$8.00", fill=(0, 0, 0))
    draw.text((443, 225), "$80.00", fill=(0, 0, 0))
    draw.line([0, 255, 500, 255], fill=(50, 50, 150), width=2)
    draw.text((340, 265), "Subtotal:  $235.00", fill=(0, 0, 0))
    draw.text((340, 285), "Tax (10%):  $23.50", fill=(0, 0, 0))
    draw.text((340, 310), "TOTAL:     $258.50", fill=(0, 0, 80))

    img.save(path, format="PNG")


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = {
        "sample_text_pdf.pdf": create_text_pdf,
        "sample_scanned_pdf.pdf": create_scanned_pdf,
        "empty.pdf": create_empty_pdf,
        "sample_receipt.jpg": create_receipt_jpg,
        "sample_invoice.png": create_invoice_png,
    }

    for filename, creator in fixtures.items():
        fixture_path = FIXTURES_DIR / filename
        creator(fixture_path)
        size_kb = fixture_path.stat().st_size / 1024
        print(f"  created  {filename:30s}  ({size_kb:.1f} KB)")

    print(f"\nAll {len(fixtures)} fixtures written to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
