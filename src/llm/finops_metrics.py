"""
FinOps Metrics Extractor
========================
Unified extraction of P95, CPU, IOPS, latency, and other finops metrics
from graph nodes and edges. Used by both engine and LLM recommendation generation.

Ensures consistent hardening of metrics across all recommendations.
"""

from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class FinOpsMetricsExtractor:
    """Extract and normalize finops metrics from graph nodes and edges."""

    @staticmethod
    def extract_node_metrics(node: Dict[str, Any], edges: List[Dict] = None) -> Dict[str, Any]:
        """Extract all finops metrics for a single node.

        Returns a normalized metrics dict with:
        - cpu_utilization_percent: float
        - memory_utilization_percent: float
        - iops: float (total IOPS)
        - read_iops: float
        - write_iops: float
        - latency_ms: float (p50)
        - latency_p95_ms: float (p95)
        - latency_p99_ms: float (p99)
        - error_rate: float (%)
        - throughput_qps: float
        - throughput_rps: float
        - network_in_mbps: float
        - network_out_mbps: float
        - cost_monthly: float
        - cost_p95_monthly: float (peak 95th percentile)
        - health_score: float (0-100)
        - observation: str (human-readable summary)
        """
        node_id = node.get("node_id") or node.get("id", "")

        # Extract CPU
        cpu_util = FinOpsMetricsExtractor._extract_cpu(node)

        # Extract memory
        mem_util = FinOpsMetricsExtractor._extract_memory(node)

        # Extract IOPS (for storage/database services)
        iops = FinOpsMetricsExtractor._extract_iops(node)
        read_iops, write_iops = FinOpsMetricsExtractor._extract_read_write_iops(node, iops)

        # Extract latency (from edges if available, or node attributes)
        latency_p50, latency_p95, latency_p99 = FinOpsMetricsExtractor._extract_latencies(node, edges or [])

        # Extract error rate
        error_rate = FinOpsMetricsExtractor._extract_error_rate(node, edges or [])

        # Extract throughput (QPS/RPS)
        throughput_qps, throughput_rps = FinOpsMetricsExtractor._extract_throughput(node, edges or [])

        # Extract network metrics
        network_in_mbps, network_out_mbps = FinOpsMetricsExtractor._extract_network(node, edges or [])

        # Extract cost metrics
        cost_monthly = float(node.get("cost_monthly", 0))
        cost_p95_monthly = FinOpsMetricsExtractor._estimate_cost_p95(node, cost_monthly)

        # Health/risk score
        health_score = FinOpsMetricsExtractor._extract_health_score(node)

        # Build observation text
        observation = FinOpsMetricsExtractor._build_observation_text(
            node, cpu_util, mem_util, iops, latency_p95, error_rate, throughput_qps
        )

        return {
            "node_id": node_id,
            "cpu_utilization_percent": cpu_util,
            "memory_utilization_percent": mem_util,
            "iops": iops,
            "read_iops": read_iops,
            "write_iops": write_iops,
            "latency_p50_ms": latency_p50,
            "latency_p95_ms": latency_p95,
            "latency_p99_ms": latency_p99,
            "error_rate_percent": error_rate,
            "throughput_qps": throughput_qps,
            "throughput_rps": throughput_rps,
            "network_in_mbps": network_in_mbps,
            "network_out_mbps": network_out_mbps,
            "cost_monthly": cost_monthly,
            "cost_p95_monthly": cost_p95_monthly,
            "health_score": health_score,
            "observation": observation,
        }

    @staticmethod
    def _extract_cpu(node: Dict[str, Any]) -> Optional[float]:
        """Extract CPU utilization percentage."""
        # Try different paths
        paths = [
            "cpu_utilization",
            "cpu_utilization_percent",
            "performance_metrics.CPUUtilization.value",
            "attributes.cpu_utilization",
            "metrics.cpu_utilization",
            "utilization_score",
        ]

        for path in paths:
            val = FinOpsMetricsExtractor._get_nested(node, path)
            if val is not None and val > 0:
                # Normalize to 0-100
                if val > 100:
                    val = min(val, 100)  # Cap at 100
                return float(val)

        return None

    @staticmethod
    def _extract_memory(node: Dict[str, Any]) -> Optional[float]:
        """Extract memory utilization percentage."""
        paths = [
            "memory_utilization",
            "memory_utilization_percent",
            "performance_metrics.MemoryUtilization.value",
            "attributes.memory_utilization",
            "metrics.memory_utilization",
        ]

        for path in paths:
            val = FinOpsMetricsExtractor._get_nested(node, path)
            if val is not None and val > 0:
                if val > 100:
                    val = min(val, 100)
                return float(val)

        return None

    @staticmethod
    def _extract_iops(node: Dict[str, Any]) -> Optional[float]:
        """Extract total IOPS."""
        paths = [
            "iops",
            "performance_metrics.IOPS.value",
            "attributes.iops",
            "metrics.iops",
            "cost_properties.iops",
        ]

        for path in paths:
            val = FinOpsMetricsExtractor._get_nested(node, path)
            if val is not None and val > 0:
                return float(val)

        return None

    @staticmethod
    def _extract_read_write_iops(node: Dict[str, Any], total_iops: Optional[float]) -> tuple:
        """Extract read/write IOPS separately."""
        read_iops = None
        write_iops = None

        # Try to find read IOPS
        read_paths = ["read_iops", "performance_metrics.ReadIOPS.value", "attributes.read_iops"]
        for path in read_paths:
            val = FinOpsMetricsExtractor._get_nested(node, path)
            if val is not None and val > 0:
                read_iops = float(val)
                break

        # Try to find write IOPS
        write_paths = ["write_iops", "performance_metrics.WriteIOPS.value", "attributes.write_iops"]
        for path in write_paths:
            val = FinOpsMetricsExtractor._get_nested(node, path)
            if val is not None and val > 0:
                write_iops = float(val)
                break

        # If both found, verify they sum reasonably with total
        if read_iops and write_iops and total_iops:
            sum_iops = read_iops + write_iops
            if sum_iops > total_iops * 1.1:  # Allow 10% variance
                # Redistribute to match total
                ratio = total_iops / sum_iops if sum_iops > 0 else 1
                read_iops *= ratio
                write_iops *= ratio

        return read_iops, write_iops

    @staticmethod
    def _extract_latencies(node: Dict[str, Any], edges: List[Dict]) -> tuple:
        """Extract p50, p95, p99 latencies in ms."""
        latency_p50 = None
        latency_p95 = None
        latency_p99 = None

        # Try node-level latency
        for key in ["latency", "average_latency_ms", "latency_ms", "p50_latency"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None and val >= 0:
                latency_p50 = float(val)
                break

        # Try performance metrics
        if not latency_p50:
            val = FinOpsMetricsExtractor._get_nested(node, "performance_metrics.LatencyMs.value")
            if val is not None and val >= 0:
                latency_p50 = float(val)

        # Try p95/p99 specific
        for key in ["p95_latency", "latency_p95", "p95_latency_ms"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None and val >= 0:
                latency_p95 = float(val)
                break

        for key in ["p99_latency", "latency_p99", "p99_latency_ms"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None and val >= 0:
                latency_p99 = float(val)
                break

        # Try to estimate from edges if not found
        if not latency_p50 and edges:
            edge_latencies = []
            node_id = node.get("node_id") or node.get("id", "")
            for edge in edges:
                if edge.get("target") == node_id:
                    val = FinOpsMetricsExtractor._get_nested(edge, "traffic_properties.average_latency_ms")
                    if val is not None and val >= 0:
                        edge_latencies.append(float(val))

            if edge_latencies:
                latency_p50 = sum(edge_latencies) / len(edge_latencies)
                latency_p95 = sorted(edge_latencies)[int(len(edge_latencies) * 0.95)] if len(edge_latencies) > 1 else latency_p50
                latency_p99 = sorted(edge_latencies)[int(len(edge_latencies) * 0.99)] if len(edge_latencies) > 1 else latency_p50

        # Estimate p95/p99 from p50 if available
        if latency_p50 and not latency_p95:
            latency_p95 = latency_p50 * 1.5  # Rough estimate
        if latency_p50 and not latency_p99:
            latency_p99 = latency_p50 * 2.0  # Rough estimate

        return latency_p50, latency_p95, latency_p99

    @staticmethod
    def _extract_error_rate(node: Dict[str, Any], edges: List[Dict]) -> Optional[float]:
        """Extract error rate as percentage."""
        # Try node-level
        for key in ["error_rate", "error_rate_percent", "error_percentage", "errors"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None and val >= 0:
                rate = float(val)
                # Normalize to 0-100
                if rate > 100:
                    rate = rate / 1000 if rate > 1000 else 0.1  # Assume it was per 1M
                return rate

        # Try edges
        if edges:
            error_counts = []
            node_id = node.get("node_id") or node.get("id", "")
            for edge in edges:
                if edge.get("target") == node_id:
                    val = FinOpsMetricsExtractor._get_nested(edge, "behavior_properties.error_rate")
                    if val is not None and val >= 0:
                        error_counts.append(float(val))

            if error_counts:
                return sum(error_counts) / len(error_counts)

        return None

    @staticmethod
    def _extract_throughput(node: Dict[str, Any], edges: List[Dict]) -> tuple:
        """Extract QPS and RPS."""
        qps = None
        rps = None

        # Try direct metrics
        for key in ["qps", "queries_per_second", "q_per_sec"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None and val > 0:
                qps = float(val)
                break

        for key in ["rps", "requests_per_second", "r_per_sec"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None and val > 0:
                rps = float(val)
                break

        # Try from edges if not found
        if not qps and edges:
            node_id = node.get("node_id") or node.get("id", "")
            qps_values = []
            for edge in edges:
                if edge.get("target") == node_id:
                    val = FinOpsMetricsExtractor._get_nested(edge, "traffic_properties.queries_per_second")
                    if val is not None and val > 0:
                        qps_values.append(float(val))
            if qps_values:
                qps = sum(qps_values)

        if not rps and edges:
            node_id = node.get("node_id") or node.get("id", "")
            rps_values = []
            for edge in edges:
                if edge.get("target") == node_id:
                    val = FinOpsMetricsExtractor._get_nested(edge, "traffic_properties.requests_per_second")
                    if val is not None and val > 0:
                        rps_values.append(float(val))
            if rps_values:
                rps = sum(rps_values)

        # Use RPS as fallback for QPS if not found
        if qps is None and rps is not None:
            qps = rps

        return qps, rps

    @staticmethod
    def _extract_network(node: Dict[str, Any], edges: List[Dict]) -> tuple:
        """Extract network in/out in Mbps."""
        network_in = None
        network_out = None

        # Try direct metrics
        for key in ["network_in_mbps", "network_in", "bytes_in_per_sec"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None and val > 0:
                network_in = float(val)
                break

        for key in ["network_out_mbps", "network_out", "bytes_out_per_sec"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None and val > 0:
                network_out = float(val)
                break

        # Try from edges
        if not network_in and edges:
            node_id = node.get("node_id") or node.get("id", "")
            net_in_values = []
            for edge in edges:
                if edge.get("target") == node_id:
                    val = FinOpsMetricsExtractor._get_nested(edge, "network_properties.bytes_in_per_second")
                    if val is not None and val > 0:
                        net_in_values.append(float(val) / (1024 * 1024))  # Convert to Mbps
            if net_in_values:
                network_in = sum(net_in_values)

        return network_in, network_out

    @staticmethod
    def _estimate_cost_p95(node: Dict[str, Any], cost_monthly: float) -> float:
        """Estimate 95th percentile cost from base cost and volatility."""
        # Try to get explicit p95 cost
        for key in ["cost_p95", "cost_p95_monthly", "peak_cost"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None and val > 0:
                return float(val)

        # Estimate based on cost volatility if available
        volatility = FinOpsMetricsExtractor._get_nested(node, "cost_volatility")
        if volatility is not None and volatility > 0:
            # Assume normal distribution: p95 ≈ mean + 1.645 * std_dev
            # volatility likely represents a 1-sigma std_dev
            return cost_monthly * 1.645 * float(volatility)

        # Default estimate: assume 1.3x variance at p95
        return cost_monthly * 1.3

    @staticmethod
    def _extract_health_score(node: Dict[str, Any]) -> float:
        """Extract or compute health score (0-100)."""
        for key in ["health_score", "health", "is_healthy"]:
            val = FinOpsMetricsExtractor._get_nested(node, key)
            if val is not None:
                score = float(val)
                # Normalize boolean to score
                if val is True:
                    return 100.0
                elif val is False:
                    return 0.0
                # Cap to 0-100
                return max(0.0, min(100.0, score))

        # Estimate from resource state
        status = node.get("status", "").lower()
        if status in ("running", "active"):
            return 85.0
        elif status in ("stopped", "terminated"):
            return 20.0

        # Default to good health if no data
        return 75.0

    @staticmethod
    def _build_observation_text(node: Dict[str, Any], cpu: Optional[float], mem: Optional[float],
                               iops: Optional[float], latency_p95: Optional[float],
                               error_rate: Optional[float], qps: Optional[float]) -> str:
        """Build human-readable observation text from metrics."""
        parts = []

        if cpu is not None:
            if cpu < 10:
                parts.append(f"CPU very low ({cpu:.1f}%)")
            elif cpu > 80:
                parts.append(f"CPU high ({cpu:.1f}%)")
            else:
                parts.append(f"CPU {cpu:.1f}%")

        if mem is not None:
            if mem > 80:
                parts.append(f"Memory near limit ({mem:.1f}%)")
            elif mem > 50:
                parts.append(f"Memory {mem:.1f}%")

        if iops is not None:
            parts.append(f"IOPS {iops:.0f}")

        if latency_p95 is not None and latency_p95 > 10:
            parts.append(f"P95 latency {latency_p95:.0f}ms")

        if error_rate is not None and error_rate > 0.1:
            parts.append(f"Error rate {error_rate:.2f}%")

        if qps is not None:
            parts.append(f"Throughput {qps:.0f} qps")

        return " | ".join(parts) if parts else "No anomalies detected"

    @staticmethod
    def _get_nested(obj: Dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation."""
        try:
            keys = path.split(".")
            val = obj
            for key in keys:
                if isinstance(val, dict):
                    val = val.get(key)
                else:
                    return None
            return val
        except Exception:
            return None


__all__ = ["FinOpsMetricsExtractor"]
