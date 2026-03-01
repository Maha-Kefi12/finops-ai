"""
Scaling behaviour models — each AWS service type has a distinct model
that controls how cost, CPU, latency, and memory respond when traffic
(pressure) changes.  Used by the simulator and the agents to reason
about *why* costs grow the way they do.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class ScaleStrategy(Enum):
    HORIZONTAL = "horizontal"  # can add instances (linear-ish)
    VERTICAL   = "vertical"    # must upgrade instance (step / exponential)


@dataclass
class ScalingModel:
    """Defines how a service type reacts to a traffic multiplier *p*."""
    name: str
    strategy: ScaleStrategy
    cost_exponent: float      # cost(p) = base_cost × p^cost_exponent
    latency_exponent: float   # lat(p)  = base_lat  × p^latency_exponent
    cpu_base: float           # resting CPU utilisation (0–1)
    mem_base: float           # resting memory utilisation (0–1)
    cpu_sensitivity: float    # how fast CPU rises with pressure
    mem_sensitivity: float
    capacity_limit: float     # max traffic mult before overload
    cold_start_penalty_ms: float  # extra latency on first call (serverless)

    def stressed_cost(self, base_cost: float, pressure: float) -> float:
        return base_cost * (pressure ** self.cost_exponent)

    def cpu(self, pressure: float) -> float:
        return min(1.0, self.cpu_base * (pressure ** self.cpu_sensitivity))

    def memory(self, pressure: float) -> float:
        return min(1.0, self.mem_base * (pressure ** self.mem_sensitivity))

    def latency(self, pressure: float) -> float:
        base = 5.0  # ms
        lat = base * (pressure ** self.latency_exponent)
        if pressure > self.capacity_limit:
            # degradation spike
            overshoot = pressure / self.capacity_limit
            lat *= overshoot ** 2
        return lat + (self.cold_start_penalty_ms if pressure < 0.2 else 0)

    def is_overloaded(self, pressure: float) -> bool:
        return (self.cpu(pressure) > 0.85 or
                self.memory(pressure) > 0.90 or
                pressure > self.capacity_limit)

    def amplification(self, pressure: float) -> float:
        """Cost amplification factor: how much cost grows relative to traffic."""
        if pressure <= 0.01:
            return 1.0
        cost_ratio = pressure ** self.cost_exponent
        return cost_ratio / pressure


# ─────────────────── pre-built models for every AWS service type ──────────

MODELS: Dict[str, ScalingModel] = {
    "service": ScalingModel(
        name="Compute (EC2 / ECS)",
        strategy=ScaleStrategy.HORIZONTAL,
        cost_exponent=1.0,
        latency_exponent=0.7,
        cpu_base=0.35, mem_base=0.40,
        cpu_sensitivity=0.8, mem_sensitivity=0.6,
        capacity_limit=4.0,
        cold_start_penalty_ms=0,
    ),
    "database": ScalingModel(
        name="Database (RDS / Aurora)",
        strategy=ScaleStrategy.VERTICAL,
        cost_exponent=1.6,
        latency_exponent=1.3,
        cpu_base=0.45, mem_base=0.55,
        cpu_sensitivity=0.9, mem_sensitivity=0.75,
        capacity_limit=2.5,
        cold_start_penalty_ms=0,
    ),
    "cache": ScalingModel(
        name="Cache (Redis / Memcached)",
        strategy=ScaleStrategy.HORIZONTAL,
        cost_exponent=1.1,
        latency_exponent=0.4,
        cpu_base=0.20, mem_base=0.60,
        cpu_sensitivity=0.5, mem_sensitivity=0.85,
        capacity_limit=5.0,
        cold_start_penalty_ms=0,
    ),
    "storage": ScalingModel(
        name="Storage (S3)",
        strategy=ScaleStrategy.HORIZONTAL,
        cost_exponent=1.0,
        latency_exponent=0.3,
        cpu_base=0.10, mem_base=0.15,
        cpu_sensitivity=0.3, mem_sensitivity=0.2,
        capacity_limit=10.0,
        cold_start_penalty_ms=0,
    ),
    "serverless": ScalingModel(
        name="Serverless (Lambda)",
        strategy=ScaleStrategy.HORIZONTAL,
        cost_exponent=1.0,
        latency_exponent=0.5,
        cpu_base=0.30, mem_base=0.30,
        cpu_sensitivity=0.6, mem_sensitivity=0.5,
        capacity_limit=8.0,
        cold_start_penalty_ms=150,
    ),
    "queue": ScalingModel(
        name="Queue (SQS)",
        strategy=ScaleStrategy.HORIZONTAL,
        cost_exponent=1.0,
        latency_exponent=0.2,
        cpu_base=0.10, mem_base=0.10,
        cpu_sensitivity=0.2, mem_sensitivity=0.15,
        capacity_limit=20.0,
        cold_start_penalty_ms=0,
    ),
    "load_balancer": ScalingModel(
        name="Load Balancer (ALB / NLB)",
        strategy=ScaleStrategy.HORIZONTAL,
        cost_exponent=1.0,
        latency_exponent=0.1,
        cpu_base=0.15, mem_base=0.10,
        cpu_sensitivity=0.3, mem_sensitivity=0.2,
        capacity_limit=15.0,
        cold_start_penalty_ms=0,
    ),
    "cdn": ScalingModel(
        name="CDN (CloudFront)",
        strategy=ScaleStrategy.HORIZONTAL,
        cost_exponent=0.9,
        latency_exponent=0.1,
        cpu_base=0.05, mem_base=0.05,
        cpu_sensitivity=0.1, mem_sensitivity=0.1,
        capacity_limit=50.0,
        cold_start_penalty_ms=0,
    ),
    "search": ScalingModel(
        name="Search (OpenSearch)",
        strategy=ScaleStrategy.VERTICAL,
        cost_exponent=1.4,
        latency_exponent=1.1,
        cpu_base=0.40, mem_base=0.50,
        cpu_sensitivity=0.85, mem_sensitivity=0.7,
        capacity_limit=3.0,
        cold_start_penalty_ms=0,
    ),
    "batch": ScalingModel(
        name="Batch (Step Functions / Fargate)",
        strategy=ScaleStrategy.HORIZONTAL,
        cost_exponent=1.2,
        latency_exponent=0.9,
        cpu_base=0.50, mem_base=0.45,
        cpu_sensitivity=0.75, mem_sensitivity=0.65,
        capacity_limit=4.0,
        cold_start_penalty_ms=0,
    ),
}


def get_model(service_type: str) -> ScalingModel:
    return MODELS.get(service_type, MODELS["service"])
