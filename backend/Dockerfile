FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl libgl1 libglib2.0-0 libgomp1 \
    tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# FIX preload Docling : on force le téléchargement des modèles ML au build
# (layout detection, table structure) et pas au premier upload.
RUN python -c "\
from docling.document_converter import DocumentConverter, PdfFormatOption; \
from docling.datamodel.base_models import InputFormat; \
from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions; \
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend; \
opts = PdfPipelineOptions(); \
opts.do_ocr = True; \
opts.do_table_structure = True; \
opts.ocr_options = TesseractCliOcrOptions(lang=[\"fra\", \"eng\"]); \
dc = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts, backend=PyPdfiumDocumentBackend)}); \
print('Docling models preloaded OK with Tesseract')" \
|| echo "Docling preload skipped (réseau indisponible au build)"

COPY app/ ./app/

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
