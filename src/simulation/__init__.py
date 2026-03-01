"""Simulation package — Monte Carlo engine, behaviour models, amplification analysis."""

from .behavior_models import ScalingModel, ScaleStrategy, get_model, MODELS
from .amplification import analyze_cascade, CascadeAnalysis, AmplificationResult
from .simulator import MonteCarloSimulator, MonteCarloReport, MonteCarloDistribution

__all__ = [
    "ScalingModel", "ScaleStrategy", "get_model", "MODELS",
    "analyze_cascade", "CascadeAnalysis", "AmplificationResult",
    "MonteCarloSimulator", "MonteCarloReport", "MonteCarloDistribution",
]
