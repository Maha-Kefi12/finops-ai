"""
Topology endpoint — LLM-generated 3D architecture topology.
The LLM decides the spatial layout: x,y,z coordinates for each node,
tier groupings, visual properties, risk levels, and connection metadata.
The frontend renders exactly what the LLM produces — no force-directed layout.
"""

from fastapi import APIRouter, HTTPException
import json
import os
import re
from pathlib import Path

router = APIRouter(prefix="/api", tags=["topology"])

SYNTHETIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "synthetic"


def _load_arch_data(req: dict):
    """Load architecture from file or DB."""
    if "architecture_file" in req:
        arch_path = SYNTHETIC_DIR / req["architecture_file"]
        if not arch_path.exists():
            raise HTTPException(404, f"Architecture file not found: {req['architecture_file']}")
        with open(arch_path) as f:
            return json.load(f), req["architecture_file"]

    if "architecture_id" in req:
        from src.storage.database import SessionLocal
        from src.graph.models import Architecture, Service, Dependency

        db = SessionLocal()
        try:
            arch = db.query(Architecture).filter(
                Architecture.id == req["architecture_id"]
            ).first()
            if not arch:
                raise HTTPException(404, f"Architecture not found: {req['architecture_id']}")

            services = db.query(Service).filter(Service.architecture_id == arch.id).all()
            deps = db.query(Dependency).filter(Dependency.architecture_id == arch.id).all()

            arch_data = {
                "metadata": {
                    "name": arch.name, "pattern": arch.pattern,
                    "complexity": arch.complexity,
                    "total_services": arch.total_services,
                    "total_cost_monthly": arch.total_cost_monthly,
                },
                "services": [
                    {"id": s.id, "name": s.name, "type": s.service_type,
                     "cost_monthly": s.cost_monthly, "owner": s.owner or "unknown"}
                    for s in services
                ],
                "dependencies": [
                    {"source": d.source, "target": d.target,
                     "type": d.dep_type, "weight": d.weight}
                    for d in deps
                ],
            }
            return arch_data, arch.name
        finally:
            db.close()

    raise HTTPException(400, "Provide 'architecture_file' or 'architecture_id'")


def _extract_json(text: str):
    """Extract JSON from LLM response."""
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    for start in range(len(text)):
        if text[start] == '{':
            for end in range(len(text), start, -1):
                if text[end - 1] == '}':
                    try:
                        return json.loads(text[start:end])
                    except json.JSONDecodeError:
                        continue
            break
    return None


@router.post("/topology/analyze")
async def analyze_topology(req: dict):
    """LLM generates full 3D topology: coordinates, tiers, risk coloring, annotations."""
    import networkx as nx

    arch_data, source_name = _load_arch_data(req)

    # Build graph for metrics
    G = nx.DiGraph()
    for svc in arch_data.get("services", []):
        G.add_node(svc["id"], name=svc["name"], type=svc["type"],
                   cost=svc["cost_monthly"])
    for dep in arch_data.get("dependencies", []):
        G.add_edge(dep["source"], dep["target"],
                   type=dep["type"], weight=dep.get("weight", 1.0))

    meta = arch_data.get("metadata", {})
    arch_name = meta.get("name", source_name)
    n_services = len(arch_data.get("services", []))
    n_deps = len(arch_data.get("dependencies", []))
    total_cost = sum(s.get("cost_monthly", 0) for s in arch_data.get("services", []))

    degree_cent = nx.degree_centrality(G) if G.number_of_nodes() > 0 else {}
    between_cent = nx.betweenness_centrality(G) if G.number_of_nodes() > 0 else {}
    try:
        pagerank = nx.pagerank(G)
    except Exception:
        pagerank = {}

    cycles = list(nx.simple_cycles(G)) if G.number_of_nodes() > 0 else []
    density = nx.density(G) if G.number_of_nodes() > 0 else 0

    # Build compact service list for prompt
    service_lines = []
    for svc in arch_data.get("services", []):
        sid = svc["id"]
        bc = between_cent.get(sid, 0)
        in_d = G.in_degree(sid) if sid in G else 0
        out_d = G.out_degree(sid) if sid in G else 0
        service_lines.append(
            f"  {svc['name']} | id={sid} | type={svc['type']} | cost=${svc['cost_monthly']:,.0f}/mo | "
            f"in={in_d} out={out_d} | betweenness={bc:.3f}"
        )

    dep_lines = []
    for dep in arch_data.get("dependencies", [])[:40]:
        dep_lines.append(f"  {dep['source']} -> {dep['target']} ({dep['type']})")

    # ── LLM CALL: Generate full 3D topology ──────────────────────────
    import httpx

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model_name = os.getenv("FINOPS_MODEL", "finops-aws")

    system = (
        "You are a senior AWS Solutions Architect creating a 3D architecture topology visualization. "
        "You MUST respond with valid JSON only. No text before or after the JSON. "
        "No emoji or special characters. Plain text only.\n\n"
        "You must assign SPATIAL 3D COORDINATES (x, y, z) to every service to create a clear "
        "layered architecture diagram that a CTO can immediately understand.\n\n"
        "LAYOUT RULES:\n"
        "- Group services into tiers: Ingress (z=0), API/Compute (z=-80), Data (z=-160), Storage/Cache (z=-240)\n"
        "- Spread services horizontally within each tier: x from -200 to 200\n"
        "- Use y=-20 to 20 for slight vertical variation within tiers\n"
        "- Place high-cost/high-risk services at prominent positions\n"
        "- Place tightly coupled services near each other on the x axis\n\n"
        "IMPORTANT: Each recommendation MUST be a plain text string.\n\n"
        "Respond with this JSON:\n"
        "{\n"
        '  "summary": "3-5 sentence architecture overview for a CTO",\n'
        '  "architecture_type": "microservices|monolith|event_driven|hybrid|serverless",\n'
        '  "nodes": [\n'
        "    {\n"
        '      "id": "exact service id from input",\n'
        '      "name": "service name",\n'
        '      "type": "service type",\n'
        '      "tier": "ingress|compute|data|storage|cache|queue|monitoring",\n'
        '      "aws_service": "the AWS managed service this maps to (e.g. ALB, EC2, RDS, S3, ElastiCache, SQS, Lambda, CloudWatch)",\n'
        '      "risk_level": "critical|high|moderate|low",\n'
        '      "role": "one sentence about what this service does",\n'
        '      "x": number between -200 and 200,\n'
        '      "y": number between -20 and 20,\n'
        '      "z": number (tier depth: 0, -80, -160, -240),\n'
        '      "size": number between 4 and 20 (bigger = higher cost or risk),\n'
        '      "color": "hex color based on risk: #ef4444 critical, #f59e0b high, #3b82f6 moderate, #22c55e low"\n'
        "    }\n"
        "  ],\n"
        '  "edges": [\n'
        "    {\n"
        '      "source": "source service id",\n'
        '      "target": "target service id",\n'
        '      "label": "short description of the connection",\n'
        '      "type": "sync|async|data_flow|event",\n'
        '      "color": "hex color: #ef4444 for critical paths, #94a3b8 for normal"\n'
        "    }\n"
        "  ],\n"
        '  "tiers": [\n'
        "    {\n"
        '      "name": "Tier name",\n'
        '      "z_position": number,\n'
        '      "role": "what this tier does",\n'
        '      "services": ["service names in this tier"]\n'
        "    }\n"
        "  ],\n"
        '  "critical_path": ["service1", "service2", "service3"],\n'
        '  "strengths": ["Architecture strength 1"],\n'
        '  "weaknesses": ["Architecture weakness 1"],\n'
        '  "recommendations": [\n'
        '    "Purchase 1-year Compute Savings Plan for the top 3 EC2 instances to cut On-Demand spend by 40 percent saving approximately 2400 dollars per year",\n'
        '    "Deploy ElastiCache Redis cluster in front of the RDS instances to offload 60 percent of read queries and reduce database costs by 800 dollars per month"\n'
        "  ]\n"
        "}"
    )

    # ── GraphRAG grounding: inject similar architecture context ────────
    rag_context = ""
    try:
        from src.rag.retrieval import GraphRAGRetriever
        retriever = GraphRAGRetriever()
        if retriever.load():
            rag_result = retriever.query(
                f"{arch_name} {meta.get('pattern', '')} topology cost ${total_cost:,.0f} services {n_services}",
                top_k=5,
            )
            rag_context = rag_result.get("context", "")
    except Exception:
        pass

    user_prompt = (
        f"Create a 3D architecture topology for this AWS infrastructure.\n\n"
        f"Architecture: {arch_name}\n"
        f"Pattern: {meta.get('pattern', 'unknown')}\n"
        f"Total services: {n_services}, Dependencies: {n_deps}\n"
        f"Monthly cost: ${total_cost:,.0f}\n"
        f"Graph density: {density:.4f}, Cycles: {len(cycles)}\n\n"
        f"SERVICES:\n" + "\n".join(service_lines) + "\n\n"
        f"DEPENDENCIES:\n" + "\n".join(dep_lines) + "\n\n"
        + (f"{rag_context}\n\n" if rag_context else "")
        + f"Assign 3D coordinates to every service. Group them into logical tiers. "
        f"Color-code by risk level. Size nodes by cost and importance. "
        f"Mark critical paths in red. Identify strengths, weaknesses, and give "
        f"specific AWS cost optimization recommendations with dollar estimates. "
        f"Include ALL {n_services} services in the nodes array with their exact IDs from the input."
    )

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 4000},
                },
            )

        if resp.status_code != 200:
            raise HTTPException(500, f"LLM error: {resp.text[:300]}")

        llm_text = resp.json().get("message", {}).get("content", "")

        try:
            from src.common.formatting import strip_symbols
            llm_text = strip_symbols(llm_text)
        except ImportError:
            pass

        parsed = _extract_json(llm_text)

        if not parsed:
            parsed = {"summary": llm_text, "raw": True, "nodes": [], "edges": [], "tiers": []}

        # Ensure all services have coordinates even if LLM missed some
        llm_node_ids = {n.get("id") for n in parsed.get("nodes", [])}

        # Coerce all node coordinates to numeric values
        for node in parsed.get("nodes", []):
            for key in ("x", "y", "z", "size"):
                try:
                    node[key] = float(node.get(key, 0))
                except (TypeError, ValueError):
                    node[key] = 0.0

        for i, svc in enumerate(arch_data.get("services", [])):
            if svc["id"] not in llm_node_ids:
                parsed.setdefault("nodes", []).append({
                    "id": svc["id"],
                    "name": svc["name"],
                    "type": svc["type"],
                    "tier": "compute",
                    "aws_service": svc["type"].upper(),
                    "risk_level": "moderate",
                    "role": f"{svc['type']} service",
                    "x": (i % 5) * 80 - 160,
                    "y": 0,
                    "z": -80,
                    "size": 8,
                    "color": "#3b82f6",
                })

        # Ensure all edges exist
        llm_edges = {(e.get("source"), e.get("target")) for e in parsed.get("edges", [])}
        for dep in arch_data.get("dependencies", []):
            key = (dep["source"], dep["target"])
            if key not in llm_edges:
                parsed.setdefault("edges", []).append({
                    "source": dep["source"],
                    "target": dep["target"],
                    "label": dep["type"],
                    "type": "sync",
                    "color": "#94a3b8",
                })

        # Flatten recommendations that are dicts
        recs = parsed.get("recommendations", [])
        clean_recs = []
        for r in recs:
            if isinstance(r, dict):
                clean_recs.append(next(
                    (r[k] for k in r if isinstance(r[k], str) and len(r[k]) > 20),
                    str(r),
                ))
            elif isinstance(r, str):
                clean_recs.append(r)
        parsed["recommendations"] = clean_recs

        # Add metadata
        parsed["architecture_name"] = arch_name
        parsed["n_services"] = n_services
        parsed["n_dependencies"] = n_deps
        parsed["total_cost_monthly"] = total_cost
        parsed["density"] = density
        parsed["cycles"] = len(cycles)

        return parsed

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Topology analysis failed: {str(e)}")
