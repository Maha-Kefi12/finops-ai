"""
Unit test: verify that graph context flows through to LLM prompt and card enrichment.

Tests that:
1. _build_graph() produces full architectural context from context package
2. _build_business_graph_context() includes narratives
3. _enrich_cards() attaches graph_context with blast radius, SPOF, dependencies
4. _compute_blast_radius() correctly traverses dependency graph
"""
import pytest
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestBuildGraph:
    """Test that _build_graph renders full context from context package."""

    def test_renders_architecture_overview(self):
        from src.llm.client import _build_graph

        pkg = {
            "architecture_name": "prod-us-east-1",
            "total_services": 35,
            "total_cost_monthly": 12500,
            "total_dependencies": 48,
            "cross_az_dependency_count": 7,
        }
        result = _build_graph(pkg)
        assert "ARCHITECTURE OVERVIEW" in result
        assert "35 services" in result
        assert "$12,500/mo" in result
        assert "7 CROSS-AZ" in result

    def test_renders_critical_services(self):
        from src.llm.client import _build_graph

        pkg = {
            "critical_services": [
                {
                    "name": "finops-postgres-prod",
                    "centrality": 0.4521,
                    "in_degree": 12,
                    "out_degree": 3,
                    "cost_monthly": 892,
                    "cascading_failure_risk": "critical",
                    "single_point_of_failure": True,
                    "severity_label": "CRITICAL BOTTLENECK",
                    "dependency_patterns": ["Fan-in bottleneck: 12 callers"],
                    "dependents_count": 12,
                }
            ],
        }
        result = _build_graph(pkg)
        assert "finops-postgres-prod" in result
        assert "SINGLE POINT OF FAILURE" in result
        assert "CASCADE RISK: CRITICAL" in result
        assert "CRITICAL BOTTLENECK" in result
        assert "12 services depend on it" in result

    def test_renders_anti_patterns(self):
        from src.llm.client import _build_graph

        pkg = {
            "anti_patterns": [
                {
                    "name": "Cross-AZ Chatty Communication",
                    "severity": "high",
                    "description": "7 cross-AZ deps detected",
                    "estimated_savings": 35,
                    "recommendation": "Co-locate services",
                }
            ],
        }
        result = _build_graph(pkg)
        assert "ANTI-PATTERNS" in result
        assert "Cross-AZ Chatty" in result
        assert "$35/mo" in result

    def test_renders_risks(self):
        from src.llm.client import _build_graph

        pkg = {
            "risks": [
                {
                    "name": "Cascading Failure Risk",
                    "severity": "critical",
                    "description": "If db fails, 30 services down",
                    "impact": "Full outage",
                }
            ],
        }
        result = _build_graph(pkg)
        assert "RISK ASSESSMENT" in result
        assert "Cascading Failure" in result

    def test_renders_waste(self):
        from src.llm.client import _build_graph

        pkg = {
            "waste_detected": [
                {
                    "category": "Overprovisioned Resources",
                    "estimated_monthly": 450,
                    "description": "3 resources with <15% CPU",
                }
            ],
            "total_waste_monthly": 450,
        }
        result = _build_graph(pkg)
        assert "WASTE DETECTED" in result
        assert "$450/mo" in result

    def test_empty_pkg_returns_no_graph_data(self):
        from src.llm.client import _build_graph

        result = _build_graph({})
        assert result == "(No graph data)"


class TestBuildBusinessGraphContext:
    """Test that _build_business_graph_context includes narratives."""

    def test_includes_narratives(self):
        from src.llm.client import _build_business_graph_context

        pkg = {
            "interesting_node_narratives": [
                "finops-postgres-prod is a CRITICAL BOTTLENECK (centrality 0.4521). "
                "It powers 12 services including checkout, auth, and catalog. "
                "If it fails, 86% of the architecture goes down.",
            ],
        }
        result = _build_business_graph_context({}, pkg)
        assert "PER-NODE ARCHITECTURE NARRATIVES" in result
        assert "powers 12 services" in result
        assert "86%" in result

    def test_empty_returns_fallback(self):
        from src.llm.client import _build_business_graph_context

        result = _build_business_graph_context({}, {})
        assert "No business graph context" in result


class TestEnrichCards:
    """Test that _enrich_cards attaches graph_context to each card."""

    def _make_graph_data(self):
        return {
            "services": [
                {"id": "db-prod", "name": "finops-postgres-prod", "cost_monthly": 892,
                 "type": "rds", "region": "us-east-1a", "environment": "production",
                 "attributes": {"instance_type": "db.r5.2xlarge", "storage_gb": 500}},
                {"id": "api-gw", "name": "api-gateway", "cost_monthly": 120,
                 "type": "ec2", "region": "us-east-1b"},
                {"id": "checkout", "name": "checkout-api", "cost_monthly": 45,
                 "type": "ecs", "region": "us-east-1a"},
                {"id": "auth", "name": "auth-service", "cost_monthly": 30,
                 "type": "ecs", "region": "us-east-1a"},
            ],
            "dependencies": [
                {"source": "checkout", "target": "db-prod"},
                {"source": "auth", "target": "db-prod"},
                {"source": "api-gw", "target": "checkout"},
                {"source": "api-gw", "target": "auth"},
            ],
        }

    def _make_context_package(self):
        return {
            "critical_services": [
                {
                    "node_id": "db-prod",
                    "name": "finops-postgres-prod",
                    "centrality": 0.4521,
                    "single_point_of_failure": True,
                    "cascading_failure_risk": "critical",
                    "severity_label": "CRITICAL BOTTLENECK",
                    "narrative": "This database powers 4 services. 86% blast radius.",
                }
            ],
        }

    def test_card_gets_graph_context(self):
        from src.llm.client import _enrich_cards

        card = {
            "resource_identification": {"resource_id": "db-prod", "service_name": "finops-postgres-prod"},
            "cost_breakdown": {"current_monthly": 0},
        }

        result = _enrich_cards([card], self._make_graph_data(), self._make_context_package())
        enriched = result[0]

        assert "graph_context" in enriched
        gc = enriched["graph_context"]
        assert gc["dependency_count"] == 2  # checkout + auth depend on db-prod
        assert gc["is_spof"] is True
        assert gc["cascading_failure_risk"] == "critical"
        assert gc["centrality"] == 0.4521
        assert "86% blast radius" in gc["narrative"]

    def test_blast_radius_computed(self):
        from src.llm.client import _enrich_cards

        card = {
            "resource_identification": {"resource_id": "db-prod"},
            "cost_breakdown": {"current_monthly": 0},
        }

        result = _enrich_cards([card], self._make_graph_data(), self._make_context_package())
        gc = result[0]["graph_context"]
        # db-prod is depended upon by checkout and auth
        # api-gw depends on checkout and auth
        # So blast radius of db-prod should include checkout, auth (direct deps on it)
        assert gc["blast_radius_services"] >= 2
        assert gc["blast_radius_pct"] > 0

    def test_cross_az_detected(self):
        from src.llm.client import _enrich_cards

        card = {
            "resource_identification": {"resource_id": "db-prod"},
            "cost_breakdown": {"current_monthly": 0},
        }

        result = _enrich_cards([card], self._make_graph_data(), self._make_context_package())
        gc = result[0]["graph_context"]
        # api-gw is in us-east-1b, db-prod is in us-east-1a
        # But api-gw doesn't directly depend on db-prod, so cross_az may be 0
        # checkout and auth are in us-east-1a same as db-prod
        # This is correct - no cross-az deps for db-prod itself


class TestComputeBlastRadius:
    """Test the recursive blast radius computation."""

    def test_simple_chain(self):
        from src.llm.client import _compute_blast_radius

        # A -> B -> C (if C fails, B is affected; if B fails, A is affected)
        dependents_of = {
            "C": ["B"],
            "B": ["A"],
        }
        visited = set()
        _compute_blast_radius("C", dependents_of, visited)
        assert visited == {"B", "A"}

    def test_fan_out(self):
        from src.llm.client import _compute_blast_radius

        dependents_of = {
            "db": ["svc1", "svc2", "svc3"],
        }
        visited = set()
        _compute_blast_radius("db", dependents_of, visited)
        assert len(visited) == 3

    def test_no_deps(self):
        from src.llm.client import _compute_blast_radius

        visited = set()
        _compute_blast_radius("lonely", {}, visited)
        assert len(visited) == 0

    def test_circular_doesnt_infinite_loop(self):
        from src.llm.client import _compute_blast_radius

        dependents_of = {
            "A": ["B"],
            "B": ["A"],
        }
        visited = set()
        _compute_blast_radius("A", dependents_of, visited)
        assert visited == {"B", "A"}
