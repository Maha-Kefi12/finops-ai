"""
FastAPI main application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.storage.database import init_db
from src.api.handlers.ingest import router as ingest_router
from src.api.handlers.graphs import router as graphs_router
from src.api.handlers.analyze import router as analyze_router
from src.api.handlers.topology import router as topology_router
from src.api.handlers.graphrag import router as graphrag_router
from src.api.handlers.docs import router as docs_router
from src.api.handlers.recommendations import router as recommendations_router
from src.api.handlers.export import router as export_router
from src.api.handlers.rag import router as rag_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database and RAG index on startup."""
    try:
        print("🚀 Initializing database...")
        init_db()
        print("✅ Database ready.")

        # ── RAG Auto-Init: one-time chunk + index from /docs ──
        _init_rag_index()

    except Exception as e:
        print(f"⚠️  Database unavailable (skipping): {e}")
        print("   Graph analysis and LLM features will work without a database.")
    yield


def _init_rag_index():
    """Check if doc_chunks are populated; if not, run the indexing pipeline once.

    This is idempotent: if chunks already exist in pgvector, it skips entirely.
    On first boot, it chunks all /docs PDFs and Markdown files, embeds them
    via TF-IDF, and stores them persistently in PostgreSQL for RAG retrieval.
    """
    import threading

    def _run_indexing():
        try:
            from src.storage.database import SessionLocal
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Check if doc_chunks table exists and has rows
                try:
                    result = db.execute(text("SELECT COUNT(*) FROM doc_chunks"))
                    count = result.scalar() or 0
                except Exception:
                    # Table might not exist yet — run setup first
                    print("📦 RAG: doc_chunks table not found, running setup...")
                    from src.rag.setup_vectordb import enable_pgvector_extension, create_vectordb_tables
                    enable_pgvector_extension()
                    create_vectordb_tables()
                    count = 0
                finally:
                    db.close()

                if count > 0:
                    print(f"✅ RAG index already populated ({count} chunks). Skipping indexing.")
                    return

                print("📚 RAG: No chunks found. Running one-time /docs indexing pipeline...")
                from src.rag.indexing_pipeline import index_all_documents
                stats = index_all_documents(mode='incremental')
                print(f"✅ RAG indexing complete: {stats.total_chunks_stored} chunks from "
                      f"{stats.total_files_indexed} files in {stats.duration_seconds():.1f}s")

            except Exception as e:
                # Don't let RAG init failures crash the database session
                try:
                    db.close()
                except Exception:
                    pass
                raise e

        except Exception as e:
            print(f"⚠️  RAG auto-init failed (non-fatal): {e}")
            print("   Recommendations will still work but without document-grounded context.")

    # Run in background thread so API starts immediately
    thread = threading.Thread(target=_run_indexing, name="rag-auto-init", daemon=True)
    thread.start()
    print("🔄 RAG auto-init started in background thread...")


app = FastAPI(
    title="FinOps AI Platform API",
    description="Graph-based cloud architecture analysis with AI-powered insights",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router)
app.include_router(graphs_router)
app.include_router(analyze_router)
app.include_router(topology_router)
app.include_router(graphrag_router)
app.include_router(docs_router)
app.include_router(recommendations_router)
app.include_router(export_router)
app.include_router(rag_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "finops-ai-platform"}


@app.get("/api/llm-status")
def llm_status():
    """Check if the LLM is connected and responding."""
    import os, requests as req
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    active_model = os.getenv("FINOPS_MODEL", "qwen2.5:7b")
    try:
        # Check Ollama is running
        r = req.get(f"{ollama_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        model_names = [m.get("name", "") for m in models]

        # Check if active model exists
        active_model_info = None
        for m in models:
            if active_model in m.get("name", ""):
                active_model_info = m
                break

        if active_model_info:
            return {
                "connected": True,
                "model_name": active_model,
                "base_model": "Qwen 2.5 7B Instruct",
                "size_gb": round(active_model_info.get("size", 0) / 1e9, 1),
                "quantization": active_model_info.get("details", {}).get("quantization_level", "Q4_K_M"),
                "parameters": active_model_info.get("details", {}).get("parameter_size", "7.6B"),
                "available_models": model_names,
                "ollama_url": ollama_url,
            }
        else:
            return {
                "connected": True,
                "model_name": active_model,
                "error": f"{active_model} model not found in Ollama",
                "available_models": model_names,
                "ollama_url": ollama_url,
            }
    except Exception as e:
        return {
            "connected": False,
            "model_name": None,
            "error": f"Cannot reach Ollama at {ollama_url}: {str(e)}",
            "ollama_url": ollama_url,
        }


@app.get("/")
def root():
    return {
        "message": "FinOps AI Platform API",
        "docs": "/docs",
        "health": "/health",
    }
