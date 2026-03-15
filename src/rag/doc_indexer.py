"""
Document Indexer — Graph RAG over FinOps documentation.

Parses PDF and Markdown files from /docs, chunks them, indexes via
TF-IDF + VectorStore, and provides semantic search for grounding
LLM recommendations with real AWS best-practice knowledge.
"""

from __future__ import annotations

import logging
import os
import signal
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .embeddings import TFIDFEmbedder
from .vector_store import VectorStore

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
CHUNK_SIZE = 500       # words per chunk
CHUNK_OVERLAP = 100    # overlapping words


class DocIndexer:
    """Indexes FinOps documentation for Graph RAG retrieval.

    Scans /docs for PDF and Markdown files, chunks them, embeds via
    TF-IDF, and stores in a VectorStore for cosine-similarity search.
    """

    def __init__(self, docs_dir: Optional[str] = None):
        self.docs_dir = Path(docs_dir) if docs_dir else DOCS_DIR
        self.embedder = TFIDFEmbedder()
        self.store = VectorStore()
        self.documents: List[Dict[str, Any]] = []  # raw parsed docs
        self._indexed = False

    # ── Scanning & Parsing ──────────────────────────────────────────

    def scan_and_index(self, timeout_seconds: int = 30) -> int:
        """Scan /docs, parse all files, chunk, and index. Returns chunk count.

        Has a per-file timeout to prevent hanging on large PDFs.
        """
        if self._indexed:
            return self.store.size

        all_chunks: List[Dict[str, Any]] = []

        if not self.docs_dir.exists():
            logger.warning("Docs directory not found: %s", self.docs_dir)
            return 0

        for filepath in sorted(self.docs_dir.iterdir()):
            if filepath.is_dir():
                continue

            try:
                if filepath.suffix.lower() == ".pdf":
                    text = self._parse_pdf_safe(filepath, timeout=30)
                elif filepath.suffix.lower() == ".md":
                    text = self._parse_markdown(filepath)
                else:
                    continue

                if not text or len(text.strip()) < 50:
                    continue

                # Store raw document
                self.documents.append({
                    "filename": filepath.name,
                    "type": filepath.suffix.lower(),
                    "size_bytes": filepath.stat().st_size,
                    "text_length": len(text),
                })

                # Chunk the document
                chunks = self._chunk_text(text, filepath.name)
                all_chunks.extend(chunks)
                logger.info("Parsed %s: %d chars → %d chunks",
                            filepath.name, len(text), len(chunks))

            except Exception as e:
                logger.warning("Failed to parse %s: %s", filepath.name, e)
                continue

        if not all_chunks:
            logger.warning("No document chunks found in %s", self.docs_dir)
            return 0

        # Build TF-IDF index from all chunk texts
        chunk_texts = [c["text"] for c in all_chunks]
        self.embedder.fit(chunk_texts)

        # Embed and store each chunk
        for i, chunk in enumerate(all_chunks):
            vector = self.embedder.transform(chunk["text"])
            self.store.add(
                doc_id=f"doc-{i}",
                text=chunk["text"],
                vector=vector,
                metadata={
                    "source": chunk["source"],
                    "chunk_index": chunk["chunk_index"],
                    "category": self._categorize(chunk["source"]),
                },
            )

        self._indexed = True
        logger.info("Indexed %d chunks from %d documents",
                     self.store.size, len(self.documents))
        return self.store.size

    def _parse_pdf_safe(self, filepath: Path, timeout: int = 10) -> str:
        """Extract text from a PDF file with a timeout to prevent hanging."""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            logger.warning("PyPDF2 not available, skipping PDF: %s", filepath.name)
            return ""

        def _timeout_handler(signum, frame):
            raise TimeoutError(f"PDF parsing timed out for {filepath.name}")

        old_handler = None
        try:
            # Set alarm-based timeout (Unix only)
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
        except (ValueError, AttributeError):
            pass  # Not on main thread or not Unix

        try:
            reader = PdfReader(str(filepath))
            pages = []
            for page in reader.pages[:50]:  # Cap at 50 pages
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
        except TimeoutError:
            logger.warning("PDF timed out after %ds: %s", timeout, filepath.name)
            return ""
        except Exception as e:
            logger.warning("PDF parse error for %s: %s", filepath.name, e)
            return ""
        finally:
            try:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            except (ValueError, AttributeError):
                pass

    def _parse_markdown(self, filepath: Path) -> str:
        """Read a markdown file as plain text."""
        try:
            return filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning("Markdown read error for %s: %s", filepath.name, e)
            return ""

    def _chunk_text(self, text: str, source: str) -> List[Dict[str, Any]]:
        """Split text into overlapping word-level chunks."""
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        words = text.split()

        if len(words) <= CHUNK_SIZE:
            return [{"text": text, "source": source, "chunk_index": 0}]

        chunks = []
        start = 0
        idx = 0
        while start < len(words):
            end = min(start + CHUNK_SIZE, len(words))
            chunk_text = " ".join(words[start:end])
            chunks.append({
                "text": chunk_text,
                "source": source,
                "chunk_index": idx,
            })
            start += CHUNK_SIZE - CHUNK_OVERLAP
            idx += 1

        return chunks

    def _categorize(self, filename: str) -> str:
        """Categorize a document by filename."""
        fn = filename.lower()
        if "well" in fn and "architect" in fn:
            return "well-architected"
        if "cost" in fn:
            return "cost-optimization"
        if "pricing" in fn:
            return "aws-pricing"
        if "finops" in fn or "framework" in fn:
            return "finops-framework"
        if "compute" in fn or "optimizer" in fn:
            return "compute-optimizer"
        if "cloud" in fn:
            return "cloud-strategy"
        return "general"

    # ── Query ───────────────────────────────────────────────────────

    def query_docs(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search indexed documents by semantic similarity.

        Returns list of {text, source, category, score}.
        """
        if not self._indexed:
            self.scan_and_index()

        if self.store.size == 0:
            return []

        query_vec = self.embedder.transform(query)
        results = self.store.search(query_vec, top_k=top_k)
        return [
            {
                "text": r["text"][:800],
                "source": r["metadata"].get("source", "unknown"),
                "category": r["metadata"].get("category", "general"),
                "chunk_index": r["metadata"].get("chunk_index", 0),
                "score": round(r["score"], 4),
            }
            for r in results
        ]

    def get_best_practices_context(self, query_terms: List[str],
                                   top_k: int = 5) -> str:
        """Query docs for best practices and format as LLM context."""
        if not self._indexed:
            self.scan_and_index()

        combined_query = " ".join(query_terms)
        results = self.query_docs(combined_query, top_k=top_k)

        if not results:
            return ""

        lines = ["AWS & FINOPS BEST PRACTICES (from documentation):"]
        for i, r in enumerate(results, 1):
            lines.append(f"\n[Source: {r['source']} | Category: {r['category']}]")
            lines.append(r["text"])

        return "\n".join(lines)

    # ── Stats ───────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return indexing statistics."""
        if not self._indexed:
            self.scan_and_index()

        categories = {}
        for doc in self.store.documents:
            cat = doc.get("metadata", {}).get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_documents": len(self.documents),
            "total_chunks": self.store.size,
            "categories": categories,
            "documents": [
                {
                    "filename": d["filename"],
                    "type": d["type"],
                    "size_bytes": d["size_bytes"],
                    "text_length": d["text_length"],
                }
                for d in self.documents
            ],
        }

    def list_documents(self) -> List[Dict[str, Any]]:
        """List all indexed documents."""
        if not self._indexed:
            self.scan_and_index()
        return self.documents


# ── Singleton ────────────────────────────────────────────────────────
_doc_index: Optional[DocIndexer] = None


def get_doc_index() -> DocIndexer:
    """Get or create the singleton DocIndexer instance.

    Lazy: does not block if indexing fails or times out.
    """
    global _doc_index
    if _doc_index is None:
        _doc_index = DocIndexer()
        try:
            _doc_index.scan_and_index(timeout_seconds=120)
        except Exception as e:
            logger.warning("DocIndexer scan failed (will use fallback): %s", e)
    return _doc_index
