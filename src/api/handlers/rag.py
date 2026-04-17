"""
RAG API Endpoints

Endpoints:
- GET /api/rag/search?q=<query> - Search for documents
- GET /api/rag/documents - List indexed documents
- GET /api/rag/stats - Retrieval statistics
- POST /api/rag/incremental-index - Run incremental indexing
- PUT /api/rag/chunks/{chunk_id}/boost - Update relevance boost
- GET /api/rag/performance - Performance metrics
"""

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from typing import List, Dict, Any
from datetime import datetime

from src.rag.rag_integration import (
    get_rag_integration,
    retrieve_context,
    get_rag_stats,
)
from src.rag.monitoring import (
    detect_new_documents,
    index_incremental,
    update_relevance_boost,
    get_performance_metrics,
)
from src.rag.retrieval_service import get_retrieval_service, retrieve

router = APIRouter(prefix="/api/rag", tags=["RAG"])


@router.get("/search")
def search_documents(q: str = Query(..., min_length=3, max_length=1000)) -> Dict[str, Any]:
    """
    Search for documents using vector similarity.
    
    Args:
        q: Search query
        top_k: Number of results (default: 5)
    
    Returns:
        Retrieved chunks with scores
    """
    try:
        results = retrieve(q, top_k=5)
        
        return {
            'query': q,
            'results': [
                {
                    'chunk_id': r.chunk_id,
                    'text': r.text[:500],  # Truncate for API response
                    'source_file': r.source_file,
                    'source_type': r.source_type,
                    'section_hierarchy': r.section_hierarchy,
                    'score': round(r.score, 4),
                    'relevance_score': round(r.relevance_score, 4),
                }
                for r in results
            ],
            'count': len(results),
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/documents")
def list_documents() -> Dict[str, Any]:
    """List all indexed documents."""
    try:
        rag = get_rag_integration()
        sources = rag.get_document_sources()
        
        return {
            'documents': sources,
            'total_documents': len(sources),
            'total_chunks': sum(d['chunk_count'] for d in sources),
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.get("/stats")
def retrieval_stats() -> Dict[str, Any]:
    """Get retrieval statistics."""
    try:
        rag = get_rag_integration()
        stats = rag.get_stats()
        
        return {
            'stats': stats,
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/incremental-index")
def run_incremental_indexing(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Run incremental indexing to detect and index new/modified files.
    """
    try:
        result = index_incremental()
        
        return {
            'status': result['status'],
            'new_files': len(result['new_files']),
            'chunks_added': result.get('chunks_added', 0),
            'duplicates_skipped': result.get('duplicates_skipped', 0),
            'failed_files': result.get('failed_files', []),
            'details': result,
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Incremental indexing failed: {str(e)}")


@router.put("/chunks/{chunk_id}/boost")
def update_chunk_relevance(chunk_id: str, boost: float = Query(..., ge=0.1, le=10.0)) -> Dict[str, Any]:
    """
    Update relevance boost for a chunk.
    
    Args:
        chunk_id: Chunk ID
        boost: Relevance boost factor (0.1 to 10.0)
    
    Returns:
        Update confirmation
    """
    try:
        success = update_relevance_boost(chunk_id, boost)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Chunk not found: {chunk_id}")
        
        return {
            'chunk_id': chunk_id,
            'boost': boost,
            'updated_at': datetime.utcnow().isoformat(),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update boost: {str(e)}")


@router.get("/performance")
def performance_metrics() -> Dict[str, Any]:
    """Get comprehensive performance metrics."""
    try:
        metrics = get_performance_metrics()
        
        return {
            'metrics': metrics,
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/check-new-documents")
def check_new_documents() -> Dict[str, Any]:
    """Check for new/modified documents without indexing."""
    try:
        new_docs = detect_new_documents()
        
        return {
            'new_documents': new_docs,
            'count': len(new_docs),
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check documents: {str(e)}")
