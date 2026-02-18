# -*- coding: utf-8 -*-
"""
chunker.py — Utilitaire de découpage Markdown.

Note : Ce module est conservé pour compatibilité mais le pipeline principal
utilise désormais le chunking intégré dans docling_service.py qui produit
des sections sémantiques directement depuis l'export Markdown de Docling.
"""
import re
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def chunk_markdown(
    markdown: str,
    chunk_size: int = 600,
    chunk_overlap: int = 50,
) -> List[Dict[str, Any]]:
    chunks = []
    current_title = "Introduction"
    current_page = 1

    sections = _split_by_headers(markdown)

    for section_title, section_content in sections:
        if section_title:
            current_title = section_title
        page_match = re.search(r"##\s*Page\s*(\d+)", section_title or "")
        if page_match:
            current_page = int(page_match.group(1))

        paragraphs = [p.strip() for p in re.split(r"\n{2,}", section_content) if p.strip()]
        current_chunk: List[str] = []
        current_size = 0

        for para in paragraphs:
            para_tokens = estimate_tokens(para)
            if current_size + para_tokens > chunk_size and current_chunk:
                chunks.append({
                    "content": "\n\n".join(current_chunk),
                    "title": current_title,
                    "page": current_page,
                    "chunk_index": len(chunks),
                })
                overlap: List[str] = []
                overlap_size = 0
                for p in reversed(current_chunk):
                    if overlap_size + estimate_tokens(p) <= chunk_overlap:
                        overlap.insert(0, p)
                        overlap_size += estimate_tokens(p)
                    else:
                        break
                current_chunk = overlap
                current_size = overlap_size
            current_chunk.append(para)
            current_size += para_tokens

        if current_chunk:
            chunks.append({
                "content": "\n\n".join(current_chunk),
                "title": current_title,
                "page": current_page,
                "chunk_index": len(chunks),
            })

    if not chunks and markdown.strip():
        chunks.append({"content": markdown[:3000], "title": "Document", "page": 1, "chunk_index": 0})

    return chunks


def _split_by_headers(markdown: str) -> List[tuple]:
    lines = markdown.split("\n")
    sections = []
    current_header = None
    current_lines: List[str] = []

    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.+)", line)
        if m:
            if current_lines:
                sections.append((current_header, "\n".join(current_lines)))
            current_header = m.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_header, "\n".join(current_lines)))

    return sections or [(None, markdown)]
