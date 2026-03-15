"""
Docs API — search and query the FinOps documentation index.

Exposes the DocIndexer's Graph RAG capabilities for documentation
search and best-practices retrieval.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["docs"])


class DocSearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5


@router.post("/docs/search")
async def search_docs(req: DocSearchRequest):
    """Search FinOps documentation via Graph RAG semantic search."""
    try:
        from src.rag.doc_indexer import get_doc_index
        idx = get_doc_index()
        results = idx.query_docs(req.query, top_k=req.top_k or 5)
        return {
            "query": req.query,
            "results": results,
            "total_results": len(results),
        }
    except Exception as e:
        logger.error("Doc search failed: %s", e)
        return {"query": req.query, "results": [], "error": str(e)}


@router.get("/docs/stats")
async def get_docs_stats():
    """Return documentation index statistics."""
    try:
        from src.rag.doc_indexer import get_doc_index
        idx = get_doc_index()
        return idx.get_stats()
    except Exception as e:
        logger.error("Doc stats failed: %s", e)
        return {"error": str(e), "total_documents": 0, "total_chunks": 0}
