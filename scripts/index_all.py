#!/usr/bin/env python3
"""
Index All Architectures — runs graph engine on every architecture file,
stores graph JSON output, and builds the full RAG index.

Usage:
    python scripts/index_all.py [data_dir] [rag_dir]
"""

import json
import os
import sys
import time
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.graph.engine import GraphEngine
from src.rag.embeddings import TFIDFEmbedder, architecture_to_text, graph_output_to_text
from src.rag.vector_store import VectorStore


def index_all(
    data_dir: str = None,
    rag_dir: str = None,
):
    """Process all architecture JSON files through graph engine and index into RAG."""

    data_path = Path(data_dir) if data_dir else PROJECT_ROOT / "data" / "synthetic"
    rag_path = Path(rag_dir) if rag_dir else PROJECT_ROOT / "data" / "rag_index"
    graph_output_path = rag_path / "graph_outputs"
    graph_output_path.mkdir(parents=True, exist_ok=True)

    print("━" * 60)
    print("  FinOps RAG Index Builder")
    print("━" * 60)
    print(f"  Data dir: {data_path}")
    print(f"  RAG dir:  {rag_path}")

    # ── 1. Find all architecture JSON files ──────────────────────
    arch_files = sorted(data_path.glob("*.json"))
    # Exclude summary files
    arch_files = [f for f in arch_files if "summary" not in f.name]
    print(f"\n📂 Found {len(arch_files)} architecture files\n")

    if not arch_files:
        print("❌ No architecture files found!")
        return

    # ── 2. Run graph engine on each and collect documents ────────
    arch_texts = []
    graph_texts = []
    arch_items = []
    graph_items = []
    errors = 0

    t0 = time.time()

    for i, arch_file in enumerate(arch_files):
        try:
            with open(arch_file) as f:
                arch_data = json.load(f)

            meta = arch_data.get("metadata", {})
            arch_name = meta.get("name", arch_file.stem)
            arch_id = meta.get("id", arch_file.stem)

            # Run graph engine
            engine = GraphEngine(arch_data)
            graph_json = engine.get_graph_json()

            # Save graph output
            graph_file = graph_output_path / f"{arch_file.stem}_graph.json"
            with open(graph_file, "w") as f:
                json.dump(graph_json, f)

            # Convert to text for embedding
            arch_text = architecture_to_text(arch_data)
            graph_text = graph_output_to_text(graph_json, arch_name)

            arch_texts.append(arch_text)
            graph_texts.append(graph_text)

            arch_items.append({
                "id": f"arch_{arch_id}",
                "text": arch_text,
                "metadata": {
                    "arch_id": arch_id,
                    "name": arch_name,
                    "filename": arch_file.name,
                    "pattern": meta.get("pattern", ""),
                    "complexity": meta.get("complexity", ""),
                    "region": meta.get("region", ""),
                    "cost_tier": meta.get("cost_tier", ""),
                    "services": meta.get("total_services", 0),
                    "cost": meta.get("total_cost_monthly", 0),
                },
            })

            graph_items.append({
                "id": f"graph_{arch_id}",
                "text": graph_text,
                "metadata": {
                    "arch_id": arch_id,
                    "name": arch_name,
                    "filename": arch_file.name,
                    "pattern": meta.get("pattern", ""),
                    "region": meta.get("region", ""),
                    "cost_tier": meta.get("cost_tier", ""),
                    "services": graph_json["metrics"].get("total_services", 0),
                    "cost": graph_json["metrics"].get("total_cost_monthly", 0),
                    "density": graph_json["metrics"].get("density", 0),
                    "is_dag": graph_json["metrics"].get("is_dag", True),
                    "critical_nodes": graph_json["metrics"].get("critical_nodes", []),
                },
            })

            if (i + 1) % 200 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (len(arch_files) - i - 1) / rate
                print(f"   📊 Processed {i + 1}/{len(arch_files)} "
                      f"({rate:.0f}/s, ETA: {eta:.0f}s)")

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"   ⚠️  Error processing {arch_file.name}: {e}")

    elapsed = time.time() - t0
    print(f"\n✅ Processed {len(arch_items)} architectures in {elapsed:.1f}s "
          f"({errors} errors)")

    # ── 3. Build TF-IDF embeddings ───────────────────────────────
    print(f"\n🔤 Building TF-IDF embeddings...")
    all_texts = arch_texts + graph_texts
    embedder = TFIDFEmbedder()
    embedder.fit(all_texts)
    print(f"   Vocabulary: {embedder.vocab_size} tokens")

    # Compute vectors
    print(f"   Embedding {len(arch_texts)} architecture docs...")
    arch_vectors = embedder.batch_transform(arch_texts)
    print(f"   Embedding {len(graph_texts)} graph docs...")
    graph_vectors = embedder.batch_transform(graph_texts)

    # ── 4. Build vector stores ───────────────────────────────────
    print(f"\n💾 Building vector stores...")
    arch_store = VectorStore(persist_dir=str(rag_path))
    graph_store = VectorStore(persist_dir=str(rag_path))

    for item, vec in zip(arch_items, arch_vectors):
        item["vector"] = vec
    arch_store.add_batch(arch_items)

    for item, vec in zip(graph_items, graph_vectors):
        item["vector"] = vec
    graph_store.add_batch(graph_items)

    # ── 5. Persist ───────────────────────────────────────────────
    print(f"\n📁 Saving to {rag_path}...")
    arch_store.save("arch_vectors.json")
    graph_store.save("graph_vectors.json")

    # Save embedder vocabulary for later reloading
    vocab_data = {
        "vocab": embedder.vocab,
        "idf": embedder.idf,
        "doc_count": embedder.doc_count,
    }
    with open(rag_path / "embedder_vocab.json", "w") as f:
        json.dump(vocab_data, f)

    # ── 6. Summary ───────────────────────────────────────────────
    arch_stats = arch_store.get_stats()
    graph_stats = graph_store.get_stats()

    print(f"\n{'━' * 60}")
    print(f"  ✅ RAG Index Built Successfully")
    print(f"{'━' * 60}")
    print(f"  Architectures indexed: {arch_stats['size']}")
    print(f"  Graph outputs indexed: {graph_stats['size']}")
    print(f"  Patterns: {len(arch_stats.get('patterns', []))}")
    print(f"  Regions:  {len(arch_stats.get('regions', []))}")
    print(f"  Cost tiers: {len(arch_stats.get('cost_tiers', []))}")
    print(f"  Vector dimension: {arch_stats.get('vector_dim', 0)}")
    print(f"  Vocabulary tokens: {embedder.vocab_size}")
    print(f"{'━' * 60}")

    # Save a readable summary
    summary = {
        "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "architectures_indexed": arch_stats["size"],
        "graph_outputs_indexed": graph_stats["size"],
        "patterns": arch_stats.get("patterns", []),
        "regions": arch_stats.get("regions", []),
        "cost_tiers": arch_stats.get("cost_tiers", []),
        "vocab_size": embedder.vocab_size,
        "vector_dim": arch_stats.get("vector_dim", 0),
        "processing_time_seconds": round(elapsed, 1),
        "errors": errors,
    }
    with open(rag_path / "index_summary.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else None
    rag_dir = sys.argv[2] if len(sys.argv) > 2 else None
    index_all(data_dir, rag_dir)
