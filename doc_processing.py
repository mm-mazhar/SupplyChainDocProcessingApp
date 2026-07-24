import os
import json
import yaml
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

import pdfplumber
from paddleocr import PaddleOCR

# Load environment variables from .env file
load_dotenv()

from pymongo import MongoClient

# AI imports
from google import genai
from google.genai import types as genai_types
from openai import OpenAI


def load_model_config(path: str = "config.yml") -> dict:
    """Load AI model configuration from a YAML file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


# Load once at module level so all functions share the same config
_model_config = load_model_config()


_SUPPORTED_PDF_EXTENSIONS = {".pdf"}
_SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}


class DocumentProcessor:

    def __init__(self, lang: str = "en"):
        self.lang = lang

    def process_document(self, file_path: str) -> dict:
        """Process a document file (PDF or image) and extract text and tables.

        Args:
            file_path: Path to the document file.

        Returns:
            dict: {"text": str, "tables": list[list[dict]]}

        Raises:
            IOError: If the file does not exist.
            ValueError: If the file extension is not supported.
        """
        if not os.path.exists(file_path):
            raise IOError(f"File not found: {file_path}")

        ext = Path(file_path).suffix.lower()

        if ext in _SUPPORTED_PDF_EXTENSIONS:
            return self._process_pdf(file_path)

        if ext in _SUPPORTED_IMAGE_EXTENSIONS:
            return self._process_image(file_path)

        raise ValueError(f"Unsupported file type: {ext}")

    def _process_pdf(self, file_path: str) -> dict:
        """Extract text and tables from a PDF using pdfplumber."""
        with pdfplumber.open(file_path) as pdf:
            page_texts: list[str] = []
            raw_tables: list = []

            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    page_texts.append(page_text)

                page_tables = page.extract_tables()
                if page_tables:
                    raw_tables.extend(page_tables)

            if not page_texts:
                return self._fallback_to_ocr(file_path)

            return {
                "text": "\n".join(page_texts),
                "tables": self._normalize_pdfplumber_tables(raw_tables),
            }

    def _normalize_pdfplumber_tables(
        self, tables: list[list[list[str | None]]]
    ) -> list[list[dict]]:
        """Convert pdfplumber tables to cell-dict format.

        Args:
            tables: Outer list = tables, middle = rows, inner = cell values.

        Returns:
            Each table as a flat list of cell dicts with row_index, column_index, content.
        """
        normalized: list[list[dict]] = []
        for table in tables:
            cells: list[dict] = []
            for row_index, row in enumerate(table):
                for col_index, cell in enumerate(row):
                    cells.append({
                        "row_index": row_index,
                        "column_index": col_index,
                        "content": cell if cell is not None else "",
                    })
            normalized.append(cells)
        return normalized

    def _fallback_to_ocr(self, file_path: str) -> dict:
        """Fall back to OCR for scanned PDFs."""
        return self._process_image(file_path)

    def _process_image(self, file_path: str) -> dict:
        """Extract text from an image using PaddleOCR."""
        if not hasattr(self, '_ocr'):
            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=False)

        result = self._ocr.ocr(file_path, cls=True)

        if not result or not result[0]:
            return {"text": "", "tables": []}

        text_lines: list[str] = []
        for line in result[0]:
            if line and len(line) > 1:
                text_lines.append(line[1][0])

        return {"text": "\n".join(text_lines), "tables": []}


class MongoIngestor:

    def __init__(self):
        connection_string = os.getenv("MONGO_CONNECTION_STRING")
        db_name = os.getenv("MONGO_DB_NAME")
        collection_name = os.getenv("MONGO_COLLECTION_NAME")

        self.client = MongoClient(connection_string)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def insert(self, document: dict, file_name: str):
        mongo_doc = {
            "source_file": file_name,
            "data": document,
            "created_at": datetime.utcnow()
        }
        result = self.collection.insert_one(mongo_doc)
        print("Inserted ID:", result.inserted_id)


def parse_tables(result: dict) -> dict:
    tables = result.get("tables", [])

    if len(tables) < 2:
        return {"error": "Insufficient tables"}

    # -------- ORDER TABLE --------
    order_table = tables[0]
    headers, values = {}, {}

    for cell in order_table:
        if cell["row_index"] == 0:
            headers[cell["column_index"]] = cell["content"].strip().lower().replace(" ", "_")
        elif cell["row_index"] == 1:
            values[cell["column_index"]] = cell["content"].strip()

    order_data = {headers[i]: values.get(i) for i in headers}

    # -------- PRODUCT TABLE --------
    product_table = tables[1]
    product_headers = {}

    for cell in product_table:
        if cell["row_index"] == 0:
            product_headers[cell["column_index"]] = (
                cell["content"].replace(":", "").strip().lower().replace(" ", "_")
            )

    rows = {}
    for cell in product_table:
        if cell["row_index"] > 0:
            row = rows.setdefault(cell["row_index"], {})
            key = product_headers.get(cell["column_index"])
            row[key] = cell["content"].strip()

    products = []
    for row in rows.values():
        products.append({
            "product_id": row.get("product_id"),
            "product_name": row.get("product"),
            "quantity": int(row.get("quantity")) if row.get("quantity") else None,
            "unit_price": float(row.get("unit_price")) if row.get("unit_price") else None
        })

    return {
        "order_id": order_data.get("order_id"),
        "order_date": order_data.get("order_date"),
        "customer_name": order_data.get("customer_name"),
        "products": products
    }


def clean_json_response(raw_text: str) -> str:
    """Helper function to strip markdown JSON block wrappers sometimes returned by Open-Source models."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def normalize_with_ai(parsed_data: dict, raw_text: str) -> dict:
    norm_cfg = _model_config["ai"]["normalization"]
    primary_cfg = norm_cfg["primary"]
    fallback_cfg = norm_cfg["fallback"]
    system_prompt = norm_cfg["system_prompt"]

    prompt = f"""
    Normalize the following purchase order data.

    Ensure:
    - Correct field names
    - Correct data types
    - No hallucinations

    Return ONLY JSON. Do not wrap in markdown formatting.

    Schema:
    {{
      "order_id": string,
      "order_date": string,
      "customer_name": string,
      "products": [
        {{
          "product_id": string,
          "product_name": string,
          "quantity": number,
          "unit_price": number
        }}
      ]
    }}

    Extracted Data:
    {parsed_data}

    OCR Text:
    {raw_text}
    """

    # --- 1. PRIMARY AI (configured in models.yml) ---
    try:
        print(f"⏳ Attempting normalization with {primary_cfg['provider']} / {primary_cfg['model']}...")
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        response = client.models.generate_content(
            model=primary_cfg["model"],
            contents=f"{system_prompt}\n\n{prompt}",
            config=genai_types.GenerateContentConfig(
                response_mime_type=primary_cfg["response_mime_type"],
                temperature=primary_cfg["temperature"],
            ),
        )
        return json.loads(response.text)

    except Exception as e:
        print(f"⚠️ {primary_cfg['provider']} failed: {e}. Falling back to {fallback_cfg['provider']}...")

        # --- 2. FALLBACK AI (configured in models.yml) ---
        try:
            openrouter_client = OpenAI(
                base_url=fallback_cfg["base_url"],
                api_key=os.getenv("OPENROUTER_API_KEY")
            )

            response = openrouter_client.chat.completions.create(
                model=fallback_cfg["model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=fallback_cfg["temperature"]
            )

            raw_json = response.choices[0].message.content
            cleaned_json = clean_json_response(raw_json)
            return json.loads(cleaned_json)

        except Exception as fallback_e:
            print(f"❌ {fallback_cfg['provider']} fallback also failed: {fallback_e}")
            return parsed_data  # Return unnormalized data if both AIs fail


if __name__ == "__main__":
    processor = DocumentProcessor()

    # Step 1: Document extraction (pdfplumber / PaddleOCR)
    print("⏳ Running document extraction...")
    result = processor.process_document("data/PurchaseOrders/purchase_orders_10248.pdf")

    # Step 2: Deterministic parsing
    parsed = parse_tables(result)
    print("\nParsed:\n", parsed)

    # Step 3: AI normalization (Gemini -> OpenRouter)
    final_data = normalize_with_ai(parsed, result["text"])
    print("\nFinal Data:\n", json.dumps(final_data, indent=2))

    # Step 4: Mongo insert
    print("\n⏳ Saving to MongoDB Atlas...")
    mongo = MongoIngestor()
    mongo.insert(final_data, "purchase_orders_10248.pdf")
    print("✅ Process Complete.")