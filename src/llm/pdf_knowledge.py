"""
PDF Knowledge Base — extracts, chunks, and retrieves FinOps best practices
from PDF documents in the /docs folder for LLM context enrichment.
=======================================================================
- Extracts text from PDFs using PyPDF2
- Chunks into ~500-char segments with overlap
- Keyword-based retrieval selects relevant chunks for a given architecture
- Caches extracted text in memory to avoid re-reading PDFs
- Caps total context to fit within Ollama 7B prompt budget
"""

import os
import logging
import hashlib
from typing import Dict, List, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Module-level cache: pdf_path -> list of text chunks ──
_chunk_cache: Dict[str, List[str]] = {}
_cache_loaded = False

# Directories to scan for PDFs (inside container)
DOCS_DIRS = [
    "/app/docs",
    os.path.join(os.path.dirname(__file__), "..", "..", "docs"),  # local dev
]

# Priority PDFs (most relevant for FinOps recommendations)
PRIORITY_PDFS = [
    "English-FinOps-Framework-2025.pdf",
    "wellarchitected-cost-optimization-pillar.pdf",
    "wellarchitected-framework.pdf",
    "cost-optimization-laying-the-foundation.pdf",
    "cost-management-guide.pdf",
    "compute-optimizer.pdf",
    "how-aws-pricing-works.pdf",
    "ebook-aws-cloud-financial-management-guide-032023.pdf",
    "Finout.pdf",
    "Flexera.pdf",
    "cloud .pdf",
    "romexsoft.pdf",
    "fig.io.pdf",
]

# Chunk configuration
CHUNK_SIZE = 500       # chars per chunk
CHUNK_OVERLAP = 80     # overlap between chunks
MAX_CHUNKS_PER_PDF = 150  # cap per PDF to avoid memory bloat
MAX_CONTEXT_CHARS = 2500  # max chars to inject into LLM prompt
MAX_PDF_SIZE_MB = 3.5  # skip PDFs larger than this (avoids slow extraction)
MAX_PDF_PAGES = 60     # only read first N pages per PDF
PDF_EXTRACT_TIMEOUT = 4  # seconds per PDF extraction


def _find_docs_dir() -> Optional[str]:
    """Find the docs directory (works in Docker and local dev)."""
    for d in DOCS_DIRS:
        p = os.path.abspath(d)
        if os.path.isdir(p):
            return p
    return None


def _extract_pdf_text(pdf_path: str) -> str:
    """Extract text from a PDF file using PyPDF2 with size, page, and time limits."""
    try:
        size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        if size_mb > MAX_PDF_SIZE_MB:
            logger.info("[PDF] Skipping %s (%.1fMB > %.1fMB limit)", pdf_path, size_mb, MAX_PDF_SIZE_MB)
            return ""

        import signal, PyPDF2

        def _timeout_handler(signum, frame):
            raise TimeoutError(f"PDF extraction timed out after {PDF_EXTRACT_TIMEOUT}s")

        # Set per-PDF alarm timeout
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(PDF_EXTRACT_TIMEOUT)
        try:
            text_parts = []
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                pages_to_read = min(len(reader.pages), MAX_PDF_PAGES)
                for i in range(pages_to_read):
                    try:
                        page_text = reader.pages[i].extract_text()
                        if page_text:
                            text_parts.append(page_text)
                    except Exception:
                        continue
            return "\n".join(text_parts)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except TimeoutError:
        logger.warning("[PDF] Extraction timed out for %s, skipping", pdf_path)
        return ""
    except Exception as e:
        logger.warning("[PDF] Failed to extract %s: %s", pdf_path, e)
        return ""


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks."""
    if not text or len(text) < 50:
        return []
    
    # Clean up whitespace
    text = " ".join(text.split())
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if len(chunk) >= 30:  # skip tiny chunks
            chunks.append(chunk)
        start += chunk_size - overlap
        if len(chunks) >= MAX_CHUNKS_PER_PDF:
            break
    
    return chunks


def load_pdf_chunks() -> Dict[str, List[str]]:
    """Load and chunk all PDFs from the docs directory. Cached after first call."""
    global _chunk_cache, _cache_loaded
    
    if _cache_loaded:
        return _chunk_cache
    
    docs_dir = _find_docs_dir()
    if not docs_dir:
        logger.warning("[PDF] No docs directory found")
        _cache_loaded = True
        return _chunk_cache
    
    # Collect all root-level PDFs, skip duplicates (files with # are variants)
    loaded_count = 0
    seen_bases = set()  # track base names to skip duplicates

    def _load_pdf(pdf_path: str, pdf_name: str):
        nonlocal loaded_count
        # Extract base name (before #) to detect duplicates
        base = pdf_name.split("#")[0].replace(".pdf", "").strip()
        if base in seen_bases:
            logger.info("[PDF] Skipping duplicate: %s (base=%s)", pdf_name, base)
            return
        seen_bases.add(base)

        text = _extract_pdf_text(pdf_path)
        chunks = _chunk_text(text)
        if chunks:
            clean_name = pdf_name.replace(".pdf", "").replace("#", "_").strip()
            _chunk_cache[clean_name] = chunks
            loaded_count += 1
            logger.info("[PDF] Loaded %s: %d chunks", clean_name, len(chunks))

    # First pass: priority PDFs
    for pdf_name in PRIORITY_PDFS:
        pdf_path = os.path.join(docs_dir, pdf_name)
        if os.path.isfile(pdf_path):
            _load_pdf(pdf_path, pdf_name)

    # Second pass: any other root-level PDFs
    try:
        for fname in sorted(os.listdir(docs_dir)):
            if fname.endswith(".pdf"):
                pdf_path = os.path.join(docs_dir, fname)
                if os.path.isfile(pdf_path):
                    _load_pdf(pdf_path, fname)
    except Exception as e:
        logger.warning("[PDF] Error scanning docs dir: %s", e)
    
    total_chunks = sum(len(c) for c in _chunk_cache.values())
    logger.info("[PDF] Knowledge base loaded: %d PDFs, %d total chunks", loaded_count, total_chunks)
    _cache_loaded = True
    return _chunk_cache


def _score_chunk(chunk: str, keywords: List[str]) -> int:
    """Score a chunk by how many keywords it contains."""
    chunk_lower = chunk.lower()
    return sum(1 for kw in keywords if kw.lower() in chunk_lower)


def retrieve_relevant_chunks(
    service_types: List[str],
    categories: List[str],
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """Retrieve the most relevant PDF chunks for given service types and categories.
    
    Args:
        service_types: e.g. ["RDS", "EKS", "ElastiCache", "VPC"]
        categories: e.g. ["security", "reliability", "performance", "cost"]
        max_chars: maximum total characters to return
    
    Returns:
        Formatted string of relevant best-practice chunks for LLM context.
    """
    all_chunks = load_pdf_chunks()
    if not all_chunks:
        return ""
    
    # Build keyword list from service types + categories + common FinOps terms
    keywords = []
    keywords.extend(service_types)
    keywords.extend(categories)
    # Add common FinOps terms that are always relevant
    keywords.extend([
        "cost optimization", "right-sizing", "reserved instance", "savings plan",
        "well-architected", "security", "reliability", "availability",
        "multi-az", "encryption", "backup", "disaster recovery",
        "performance", "scaling", "elasticity", "monitoring",
        "best practice", "recommendation", "pillar",
    ])
    
    # Score all chunks
    scored: List[Tuple[int, str, str]] = []  # (score, source, chunk)
    for source, chunks in all_chunks.items():
        for chunk in chunks:
            score = _score_chunk(chunk, keywords)
            if score >= 2:  # at least 2 keyword matches
                scored.append((score, source, chunk))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Build context string within budget
    parts = []
    total_len = 0
    sources_used = set()
    
    for score, source, chunk in scored:
        if total_len + len(chunk) + 50 > max_chars:
            break
        # Add source header if first chunk from this source
        if source not in sources_used:
            header = f"\n[Source: {source}]\n"
            parts.append(header)
            total_len += len(header)
            sources_used.add(source)
        parts.append(chunk)
        total_len += len(chunk)
    
    if not parts:
        return ""
    
    result = "\n".join(parts)
    logger.info(
        "[PDF] Retrieved %d chunks from %d sources (%d chars) for keywords: %s",
        len(parts) - len(sources_used),  # subtract headers
        len(sources_used),
        len(result),
        ", ".join(service_types[:5]),
    )
    return result


def get_best_practices_context(raw_graph_data: dict) -> str:
    """Build a best-practices context string from PDFs based on the architecture's services.
    
    This is the main entry point called from generate_recommendations().
    """
    if not raw_graph_data:
        return ""
    
    # Extract service types from graph data
    services = raw_graph_data.get("services", raw_graph_data.get("nodes", []))
    service_types = set()
    for s in services:
        svc_type = s.get("type", s.get("service_type", ""))
        if svc_type:
            service_types.add(svc_type.upper())
        # Also extract from name patterns
        name = s.get("name", s.get("id", "")).lower()
        for kw in ["rds", "eks", "ecs", "elasticache", "redis", "vpc", "nat", 
                    "ebs", "s3", "lambda", "ec2", "alb", "elb", "cloudfront",
                    "iam", "security_group", "kms", "waf"]:
            if kw in name:
                service_types.add(kw.upper())
    
    categories = ["security", "reliability", "performance", "cost optimization",
                   "right-sizing", "well-architected"]
    
    context = retrieve_relevant_chunks(
        service_types=list(service_types),
        categories=categories,
    )
    
    if context:
        return f"AWS & FinOps Best Practices (from reference documents):\n{context}\n"
    return ""
