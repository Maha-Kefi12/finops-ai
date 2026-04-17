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
    """Initialize the database on startup (optional — skipped if DB unavailable)."""
    try:
        print("🚀 Initializing database...")
        init_db()
        print("✅ Database ready.")
    except Exception as e:
        print(f"⚠️  Database unavailable (skipping): {e}")
        print("   Graph analysis and LLM features will work without a database.")
    yield


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
