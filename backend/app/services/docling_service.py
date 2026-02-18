# -*- coding: utf-8 -*-
"""
docling_service.py — Conversion de documents vers Markdown via Docling.

Pipeline : fichier → Docling → Markdown structuré → chunks sémantiques
Formats supportés : PDF, DOCX, DOC, DOTX, PPTX, PPT, XLSX, XLS,
                    ODT, ODS, ODP, HTML, HTM, CSV, MD, TXT, EPUB, AsciiDoc
"""
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.backend.pypdfium2_backend import PyPdfium2DocumentBackend
    _DOCLING_OK = True
except ImportError:
    _DOCLING_OK = False
    logger.error("Docling non installé — ajoutez 'docling' à requirements.txt")

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
        ".csv":      InputFormat.CSV,
        ".md":       InputFormat.MD,
        ".txt":      InputFormat.MD,
        ".asciidoc": InputFormat.ASCIIDOC,
        ".adoc":     InputFormat.ASCIIDOC,
        ".epub":     InputFormat.HTML,
    }


def _build_converter(ext: str) -> "DocumentConverter":
    if ext == ".pdf":
        opts = PdfPipelineOptions()
        opts.do_ocr = True
        opts.do_table_structure = True
        opts.table_structure_options.do_cell_matching = True
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=opts,
                    backend=PyPdfium2DocumentBackend,
                )
            }
        )
    return DocumentConverter()


def _chunk_markdown(markdown: str, filename: str, max_chars: int = 3000) -> List[Dict[str, Any]]:
    """
    Découpe le Markdown en sections sémantiques (par titres, puis par paragraphes).
    Retourne une liste de dicts {page, title, content, chunk_index}.
    """
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
            chunks.append({"page": len(chunks) + 1, "title": title,
                           "content": content, "chunk_index": len(chunks)})
        else:
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            buf = ""
            for para in paragraphs:
                if buf and len(buf) + len(para) + 2 > max_chars:
                    chunks.append({"page": len(chunks) + 1, "title": title,
                                   "content": buf.strip(), "chunk_index": len(chunks)})
                    buf = para + "\n\n"
                else:
                    buf += para + "\n\n"
            if buf.strip():
                chunks.append({"page": len(chunks) + 1, "title": title,
                               "content": buf.strip(), "chunk_index": len(chunks)})

    return chunks or [{"page": 1, "title": filename, "content": "(vide)", "chunk_index": 0}]


async def convert_document(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """
    Point d'entrée : bytes → chunks Markdown prêts pour l'embedding.
    Lève ValueError si format non supporté, RuntimeError si conversion échoue.
    """
    if not _DOCLING_OK:
        raise RuntimeError("Docling non installé")

    ext = Path(filename).suffix.lower()
    if ext not in EXT_TO_FORMAT:
        raise ValueError(
            f"Format non supporté : '{ext}'. "
            f"Acceptés : {', '.join(sorted(EXT_TO_FORMAT.keys()))}"
        )

    logger.info(f"[Docling] Conversion '{filename}' ({len(file_bytes):,} bytes)")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir="/tmp") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        converter = _build_converter(ext)
        result = converter.convert(tmp_path)
        markdown: str = result.document.export_to_markdown()

        if not markdown or not markdown.strip():
            logger.warning(f"[Docling] Markdown vide pour '{filename}'")
            return [{"page": 1, "title": filename, "content": "(document vide ou non lisible)", "chunk_index": 0}]

        chunks = _chunk_markdown(markdown, filename)
        logger.info(f"[Docling] {len(chunks)} chunks produits pour '{filename}'")
        return chunks

    except (ValueError, RuntimeError):
        raise
    except Exception as e:
        logger.error(f"[Docling] Erreur '{filename}': {e}", exc_info=True)
        raise RuntimeError(f"Erreur Docling pour '{filename}': {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
