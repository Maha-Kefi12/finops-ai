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


@app.get("/health")
def health():
    return {"status": "ok", "service": "finops-ai-platform"}


@app.get("/api/llm-status")
def llm_status():
    """Check if the FinOps LLM (finops-aws) is connected and responding."""
    import os, requests as req
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        # Check Ollama is running
        r = req.get(f"{ollama_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        model_names = [m.get("name", "") for m in models]

        # Check if finops-aws exists
        finops_model = None
        for m in models:
            if "finops-aws" in m.get("name", ""):
                finops_model = m
                break

        if finops_model:
            return {
                "connected": True,
                "model_name": "finops-aws",
                "base_model": "abocide/Qwen2.5-7B-Instruct-R1-forfinance",
                "size_gb": round(finops_model.get("size", 0) / 1e9, 1),
                "quantization": finops_model.get("details", {}).get("quantization_level", "Q4_K_M"),
                "parameters": finops_model.get("details", {}).get("parameter_size", "7.6B"),
                "available_models": model_names,
                "ollama_url": ollama_url,
            }
        else:
            return {
                "connected": True,
                "model_name": None,
                "error": "finops-aws model not found. Run: ollama create finops-aws -f Modelfile",
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
