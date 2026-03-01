"""Agents package — 5-agent pipeline for architecture risk analysis."""

from .base_agent import BaseAgent, AgentOutput
from .architect_agent import TopologyAnalystAgent
from .behavior_agent import BehaviorScientistAgent
from .economist_agent import CostEconomistAgent
from .detective_agent import RiskDetectiveAgent
from .synthesizer_agent import ExecutiveSynthesizerAgent
from .orchestrator import AgentOrchestrator

__all__ = [
    "BaseAgent", "AgentOutput",
    "TopologyAnalystAgent", "BehaviorScientistAgent",
    "CostEconomistAgent", "RiskDetectiveAgent",
    "ExecutiveSynthesizerAgent", "AgentOrchestrator",
]
