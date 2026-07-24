import os
from pathlib import Path
from fastapi import FastAPI, File, Request, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import uvicorn
from doc_processing import DocumentProcessor, parse_tables, normalize_with_ai, MongoIngestor
from tempfile import NamedTemporaryFile

from dotenv import load_dotenv
load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/extract-text/")
async def extract_text(file: UploadFile = File(...)):
    """Extract text and tables from a PDF or image file."""
    temp_file_path: str | None = None
    try:
        processor = DocumentProcessor()

        with NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
            temp_file.write(file.file.read())
            temp_file_path = temp_file.name

        result = processor.process_document(temp_file_path)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file_path is not None:
            os.unlink(temp_file_path)


@app.post("/upload-and-ingest/")
async def upload_and_ingest(file: UploadFile = File(...)):
    """Upload a PDF or image, run the full pipeline, and insert into MongoDB."""
    temp_file_path: str | None = None
    try:
        processor = DocumentProcessor()
        mongo = MongoIngestor()

        with NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
            temp_file.write(file.file.read())
            temp_file_path = temp_file.name

        result = processor.process_document(temp_file_path)
        parsed_data = parse_tables(result)
        final_data = normalize_with_ai(parsed_data, result["text"])
        mongo.insert(final_data, file.filename)

        return JSONResponse(content={
            "message": "Data successfully ingested into the database.",
            "file_name": file.filename,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file_path is not None:
            os.unlink(temp_file_path)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
