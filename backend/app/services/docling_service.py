# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    _DOCLING_OK = True
    logger.info("Docling chargé avec succès")
except Exception as e:
    _DOCLING_OK = False
    logger.error(f"Docling import échoué: {e}")

EXT_TO_FORMAT: Dict[str, Any] = {}
if _DOCLING_OK:
    EXT_TO_FORMAT = {
        ".pdf":      InputFormat.PDF,
        ".docx":     InputFormat.DOCX,
        ".dotx":     InputFormat.DOCX,
        ".doc":      InputFormat.DOCX,
        ".pptx":     InputFormat.PPTX,
        ".ppt":      InputFormat.PPTX,
        ".xlsx":     InputFormat.XLSX,
        ".xls":      InputFormat.XLSX,
        ".odt":      InputFormat.DOCX,
        ".html":     InputFormat.HTML,
        ".htm":      InputFormat.HTML,
        ".md":       InputFormat.MD,
        ".txt":      InputFormat.MD,
        ".epub":     InputFormat.HTML,
    }
else:
    EXT_TO_FORMAT = {
        ".txt": "txt", ".md": "txt", ".csv": "txt",
        ".html": "txt", ".htm": "txt",
        ".pdf": "pdf", ".docx": "docx",
    }


def _build_converter(ext: str) -> "DocumentConverter":
    if ext == ".pdf":
        opts = PdfPipelineOptions()
        opts.do_ocr = False
        opts.do_table_structure = True
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=opts,
                    backend=PyPdfiumDocumentBackend,
                )
            }
        )
    return DocumentConverter()


def _chunk_markdown(markdown: str, filename: str, max_chars: int = 3000) -> List[Dict[str, Any]]:
    heading_re = re.compile(r"^(#{1,6}\s.+)$", re.MULTILINE)
    parts = heading_re.split(markdown)

    sections: List[Dict[str, str]] = []
    current_heading = Path(filename).stem
    buffer = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if heading_re.match(part):
            if buffer.strip():
                sections.append({"heading": current_heading, "content": buffer.strip()})
            current_heading = part.lstrip("#").strip()
            buffer = part + "\n"
        else:
            buffer += part + "\n"
    if buffer.strip():
        sections.append({"heading": current_heading, "content": buffer.strip()})

    if not sections:
        sections = [{"heading": Path(filename).stem, "content": markdown}]

    chunks: List[Dict[str, Any]] = []
    for section in sections:
        content = section["content"]
        title = f"{Path(filename).stem} — {section['heading']}"
        if len(content) <= max_chars:
            chunks.append({
                "page": len(chunks) + 1,
                "title": title,
                "content": content,
                "chunk_index": len(chunks),
            })
        else:
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            buf = ""
            for para in paragraphs:
                if buf and len(buf) + len(para) + 2 > max_chars:
                    chunks.append({
                        "page": len(chunks) + 1,
                        "title": title,
                        "content": buf.strip(),
                        "chunk_index": len(chunks),
                    })
                    buf = para + "\n\n"
                else:
                    buf += para + "\n\n"
            if buf.strip():
                chunks.append({
                    "page": len(chunks) + 1,
                    "title": title,
                    "content": buf.strip(),
                    "chunk_index": len(chunks),
                })

    return chunks or [{"page": 1, "title": filename, "content": "(vide)", "chunk_index": 0}]


def _fallback_parse(file_bytes: bytes, filename: str) -> str:
    """Parser de secours sans Docling."""
    ext = Path(filename).suffix.lower()

    if ext in (".txt", ".md", ".csv", ".html", ".htm"):
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                return file_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return file_bytes.decode("utf-8", errors="replace")

    if ext == ".pdf":
        try:
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            pages = [p.extract_text() for p in reader.pages if p.extract_text()]
            return "\n\n".join(pages) if pages else "(PDF vide ou non lisible)"
        except Exception:
            try:
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(file_bytes)
                pages = [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
                return "\n\n".join(pages)
            except Exception as e2:
                raise RuntimeError(f"Impossible de lire le PDF: {e2}")

    if ext == ".docx":
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            raise RuntimeError(f"Impossible de lire le DOCX: {e}")

    raise ValueError(f"Format non supporté en mode fallback: {ext}")


def _convert_sync(tmp_path: str, ext: str, filename: str) -> List[Dict[str, Any]]:
    """Conversion synchrone via Docling — exécutée dans un thread."""
    converter = _build_converter(ext)
    result = converter.convert(tmp_path)
    markdown: str = result.document.export_to_markdown()
    if not markdown or not markdown.strip():
        logger.warning(f"[Docling] Markdown vide pour '{filename}'")
        return [{"page": 1, "title": filename, "content": "(document vide ou non lisible)", "chunk_index": 0}]
    return _chunk_markdown(markdown, filename)


async def convert_document(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Point d'entrée : bytes → chunks prêts pour l'embedding."""
    ext = Path(filename).suffix.lower()

    if _DOCLING_OK and ext in EXT_TO_FORMAT:
        logger.info(f"[Docling] Conversion '{filename}' ({len(file_bytes):,} bytes)")
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir="/tmp") as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            chunks = await asyncio.to_thread(_convert_sync, tmp_path, ext, filename)
            logger.info(f"[Docling] {len(chunks)} chunks produits pour '{filename}'")
            return chunks
        except Exception as e:
            logger.error(f"[Docling] Erreur '{filename}': {e}", exc_info=True)
            raise RuntimeError(f"Erreur Docling pour '{filename}': {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
    else:
        # Fallback pour CSV et formats non supportés par Docling
        logger.info(f"[Fallback] Conversion '{filename}'")
        try:
            text = _fallback_parse(file_bytes, filename)
            chunks = _chunk_markdown(text, filename)
            logger.info(f"[Fallback] {len(chunks)} chunks pour '{filename}'")
            return chunks
        except Exception as e:
            raise RuntimeError(f"Erreur conversion '{filename}': {e}")
