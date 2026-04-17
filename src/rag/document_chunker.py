"""
Phase 2: Document Chunker Service

Intelligent chunking for MD and PDF files from /docs.
- Markdown: Split by headers (H1→H2→H3), preserve hierarchy, 200-2000 char chunks, 100 char overlap
- PDF: Extract text, split by pages/sections, same overlap/size rules
- Features: Content hash (SHA-256), metadata extraction, quality validation, logging
"""

import os
import re
import hashlib
import logging
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A document chunk with metadata."""
    text: str
    chunk_number: int
    source_file: str
    source_type: str  # 'markdown' | 'pdf'
    section_hierarchy: Optional[str]  # Breadcrumb path for MD headers
    content_hash: str  # SHA-256
    chunk_size_chars: int


class MarkdownChunker:
    """Chunks Markdown files by header hierarchy."""
    
    MIN_CHUNK_SIZE = 200
    MAX_CHUNK_SIZE = 2000
    OVERLAP_SIZE = 100
    
    @staticmethod
    def _compute_hash(text: str) -> str:
        """Compute SHA-256 hash of text."""
        return hashlib.sha256(text.encode()).hexdigest()
    
    @staticmethod
    def _extract_headers(md_text: str) -> List[tuple]:
        """Extract header hierarchy from markdown.
        
        Returns: List of (level, text, position)
        """
        pattern = r'^(#{1,6})\s+(.+?)$'
        headers = []
        for match in re.finditer(pattern, md_text, re.MULTILINE):
            level = len(match.group(1))
            text = match.group(2).strip()
            headers.append((level, text, match.start(), match.end()))
        return headers
    
    @staticmethod
    def _build_hierarchy(level: int, current: List[str], headers: List[tuple], 
                        header_idx: int) -> List[str]:
        """Build header hierarchy breadcrumb."""
        # Adjust hierarchy list based on header level
        while len(current) > 0 and current[0][0] >= level:
            current.pop(0)
        
        # Find current header
        if header_idx < len(headers):
            h_level, h_text, _, _ = headers[header_idx]
            current.insert(0, (h_level, h_text))
        
        return current
    
    @classmethod
    def chunk(cls, file_path: str) -> List[Chunk]:
        """Chunk a markdown file by header hierarchy."""
        chunks = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                md_text = f.read()
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return []
        
        if not md_text.strip():
            logger.debug(f"Empty markdown file: {file_path}")
            return []
        
        headers = cls._extract_headers(md_text)
        
        # If no headers, treat as single chunk
        if not headers:
            return cls._chunk_single_section(md_text, file_path, "markdown")
        
        # Split by header sections
        chunk_texts = []
        current_hierarchy = []
        
        for i, (level, h_text, h_start, h_end) in enumerate(headers):
            current_hierarchy = cls._build_hierarchy(level, current_hierarchy, headers, i)
            
            # Get section text (from header end to next header start, or end of doc)
            section_start = h_end
            if i + 1 < len(headers):
                section_end = headers[i + 1][2]
            else:
                section_end = len(md_text)
            
            section_text = md_text[section_start:section_end].strip()
            hierarchy_path = " > ".join([h[1] for h in reversed(current_hierarchy)])
            
            # If section is too small, skip
            if len(section_text) < cls.MIN_CHUNK_SIZE:
                continue
            
            # Sub-chunk if section is too large
            if len(section_text) > cls.MAX_CHUNK_SIZE:
                sub_chunks = cls._sub_chunk(section_text, hierarchy_path)
                chunk_texts.extend(sub_chunks)
            else:
                chunk_texts.append((section_text, hierarchy_path))
        
        # Convert to Chunk objects
        source_file = os.path.basename(file_path)
        for chunk_num, (text, hierarchy) in enumerate(chunk_texts):
            content_hash = cls._compute_hash(text)
            chunk = Chunk(
                text=text,
                chunk_number=chunk_num,
                source_file=source_file,
                source_type="markdown",
                section_hierarchy=hierarchy,
                content_hash=content_hash,
                chunk_size_chars=len(text)
            )
            chunks.append(chunk)
        
        logger.info(f"Chunked {file_path}: {len(chunks)} chunks")
        return chunks
    
    @classmethod
    def _chunk_single_section(cls, text: str, file_path: str, 
                             source_type: str) -> List[Chunk]:
        """Chunk a section without headers."""
        chunks = []
        source_file = os.path.basename(file_path)
        
        if len(text) <= cls.MAX_CHUNK_SIZE:
            content_hash = cls._compute_hash(text)
            chunk = Chunk(
                text=text,
                chunk_number=0,
                source_file=source_file,
                source_type=source_type,
                section_hierarchy=None,
                content_hash=content_hash,
                chunk_size_chars=len(text)
            )
            chunks.append(chunk)
            return chunks
        
        # Split into overlapping chunks
        chunk_num = 0
        i = 0
        while i < len(text):
            chunk_end = min(i + cls.MAX_CHUNK_SIZE, len(text))
            chunk_text = text[i:chunk_end]
            
            # Skip if chunk too small (except last chunk)
            if len(chunk_text) >= cls.MIN_CHUNK_SIZE or chunk_end == len(text):
                content_hash = cls._compute_hash(chunk_text)
                chunk = Chunk(
                    text=chunk_text,
                    chunk_number=chunk_num,
                    source_file=source_file,
                    source_type=source_type,
                    section_hierarchy=None,
                    content_hash=content_hash,
                    chunk_size_chars=len(chunk_text)
                )
                chunks.append(chunk)
                chunk_num += 1
            
            # Move by (chunk size - overlap)
            i += cls.MAX_CHUNK_SIZE - cls.OVERLAP_SIZE
        
        return chunks
    
    @classmethod
    def _sub_chunk(cls, text: str, hierarchy_path: str) -> List[tuple]:
        """Sub-chunk a large section into overlapping chunks."""
        chunks = []
        i = 0
        
        while i < len(text):
            chunk_end = min(i + cls.MAX_CHUNK_SIZE, len(text))
            chunk_text = text[i:chunk_end].strip()
            
            if len(chunk_text) >= cls.MIN_CHUNK_SIZE or chunk_end == len(text):
                chunks.append((chunk_text, hierarchy_path))
            
            i += cls.MAX_CHUNK_SIZE - cls.OVERLAP_SIZE
        
        return chunks


class PDFChunker:
    """Chunks PDF files by page/section."""
    
    MIN_CHUNK_SIZE = 200
    MAX_CHUNK_SIZE = 2000
    OVERLAP_SIZE = 100
    
    @staticmethod
    def _compute_hash(text: str) -> str:
        """Compute SHA-256 hash of text."""
        return hashlib.sha256(text.encode()).hexdigest()
    
    @classmethod
    def chunk(cls, file_path: str) -> List[Chunk]:
        """Chunk a PDF file."""
        chunks = []
        
        if PyPDF2 is None:
            logger.warning(f"PyPDF2 not installed, skipping PDF: {file_path}")
            return []
        
        try:
            pdf_reader = PyPDF2.PdfReader(open(file_path, 'rb'))
            num_pages = len(pdf_reader.pages)
        except Exception as e:
            logger.warning(f"Failed to read PDF {file_path}: {e}")
            return []
        
        source_file = os.path.basename(file_path)
        chunk_num = 0
        
        # Extract text from each page
        for page_num in range(num_pages):
            try:
                pdf_file = open(file_path, 'rb')
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                pdf_file.close()
                
                if not text or not text.strip():
                    logger.debug(f"Empty page {page_num} in {file_path}")
                    continue
                
                # Split page text into chunks if needed
                if len(text) <= cls.MAX_CHUNK_SIZE:
                    content_hash = cls._compute_hash(text)
                    chunk = Chunk(
                        text=text,
                        chunk_number=chunk_num,
                        source_file=source_file,
                        source_type="pdf",
                        section_hierarchy=f"Page {page_num + 1}",
                        content_hash=content_hash,
                        chunk_size_chars=len(text)
                    )
                    chunks.append(chunk)
                    chunk_num += 1
                else:
                    # Sub-chunk large pages
                    sub_chunks = cls._sub_chunk_page(text, page_num)
                    for sub_text in sub_chunks:
                        content_hash = cls._compute_hash(sub_text)
                        chunk = Chunk(
                            text=sub_text,
                            chunk_number=chunk_num,
                            source_file=source_file,
                            source_type="pdf",
                            section_hierarchy=f"Page {page_num + 1}",
                            content_hash=content_hash,
                            chunk_size_chars=len(sub_text)
                        )
                        chunks.append(chunk)
                        chunk_num += 1
                        
            except Exception as e:
                logger.warning(f"Failed to extract text from page {page_num} in {file_path}: {e}")
                continue
        
        if chunks:
            logger.info(f"Chunked {file_path}: {len(chunks)} chunks from {num_pages} pages")
        else:
            logger.warning(f"No text extracted from {file_path}")
        
        return chunks
    
    @classmethod
    def _sub_chunk_page(cls, text: str, page_num: int) -> List[str]:
        """Sub-chunk a large page into overlapping chunks."""
        chunks = []
        i = 0
        
        while i < len(text):
            chunk_end = min(i + cls.MAX_CHUNK_SIZE, len(text))
            chunk_text = text[i:chunk_end].strip()
            
            if len(chunk_text) >= cls.MIN_CHUNK_SIZE or chunk_end == len(text):
                chunks.append(chunk_text)
            
            i += cls.MAX_CHUNK_SIZE - cls.OVERLAP_SIZE
        
        return chunks


def chunk_markdown(file_path: str) -> List[Chunk]:
    """Chunk a markdown file."""
    return MarkdownChunker.chunk(file_path)


def chunk_pdf(file_path: str) -> List[Chunk]:
    """Chunk a PDF file."""
    return PDFChunker.chunk(file_path)


def chunk_document(file_path: str) -> List[Chunk]:
    """Chunk a document (auto-detect format)."""
    if file_path.endswith('.md'):
        return chunk_markdown(file_path)
    elif file_path.endswith('.pdf'):
        return chunk_pdf(file_path)
    else:
        logger.warning(f"Unknown file format: {file_path}")
        return []
