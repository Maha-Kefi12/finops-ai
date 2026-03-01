"""
Base Agent — provides the foundation for all 5 agents in the pipeline.
Each agent:
  1. Receives structured data (graph metrics, Monte Carlo results, cascade analysis)
  2. Builds a domain-specific prompt
  3. Calls the LLM (abocide/Qwen2.5-7B-Instruct-R1-forfinance via Ollama)
  4. Returns structured analysis

The base class handles LLM communication, prompt templating, and output parsing.
"""

from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from src.rag.indexing import get_knowledge_index
    HAS_RAG = True
except ImportError:
    HAS_RAG = False


@dataclass
class AgentOutput:
    """Standardised output from any agent."""
    agent_name: str
    agent_role: str
    analysis: str
    findings: List[Dict[str, Any]]
    risk_score: float               # 0-1
    confidence: float               # 0-1
    recommendations: List[str]
    raw_llm_response: Optional[str] = None
    execution_time_ms: int = 0


class BaseAgent(ABC):
    """Abstract base for all pipeline agents."""

    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    MODEL_NAME = os.getenv("FINOPS_MODEL", "finops-aws")

    def __init__(self):
        self.name = self.__class__.__name__
        self.role = "base"

    # ── LLM call ──────────────────────────────────────────────────────
    def _call_llm(self, system_prompt: str, user_prompt: str,
                  temperature: float = 0.3, max_tokens: int = 2048,
                  architecture_name: str = "") -> str:
        """Call the Ollama LLM with GraphRAG grounding.  Falls back to a
        structured deterministic analysis if Ollama is unavailable."""

        # GraphRAG grounding — inject factual context
        grounding = ""
        if HAS_RAG and architecture_name:
            try:
                idx = get_knowledge_index()
                ctx = idx.retrieve_context(architecture_name)
                grounding = idx.format_grounding_prompt(ctx)
            except Exception:
                pass

        grounded_system = system_prompt
        if grounding:
            grounded_system = (
                system_prompt + "\n\n"
                "CRITICAL INSTRUCTION: You are grounded by a GraphRAG knowledge index. "
                "You MUST only make claims supported by the ground truth data below. "
                "Do NOT hallucinate numbers, service names, or risk levels. "
                "If you are unsure, say 'insufficient data' rather than guessing.\n\n"
                + grounding
            )

        if not HAS_REQUESTS:
            return self._deterministic_fallback(user_prompt)

        try:
            resp = requests.post(
                f"{self.OLLAMA_URL}/api/chat",
                json={
                    "model": self.MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": grounded_system},
                        {"role": "user",   "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=120,
            )
            if resp.status_code == 200:
                return resp.json().get("message", {}).get("content", "")
        except Exception:
            pass

        return self._deterministic_fallback(user_prompt)

    def _deterministic_fallback(self, user_prompt: str) -> str:
        """When LLM is unavailable, produce a structured analysis
        purely from the data.  This ensures the pipeline is always usable."""
        return ""

    # ── JSON extraction helper ────────────────────────────────────────
    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """Try to extract JSON from LLM output."""
        # Try code-block JSON
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Try raw JSON
        for start in range(len(text)):
            if text[start] == '{':
                for end in range(len(text), start, -1):
                    if text[end - 1] == '}':
                        try:
                            return json.loads(text[start:end])
                        except json.JSONDecodeError:
                            continue
        return None

    # ── Abstract interface ────────────────────────────────────────────
    @abstractmethod
    def analyze(self, context: Dict[str, Any]) -> AgentOutput:
        """Run the agent's analysis on the given context."""
        ...

    def _build_output(self, analysis: str, findings: List[Dict],
                      risk_score: float, confidence: float,
                      recommendations: List[str],
                      raw: str = "", elapsed_ms: int = 0) -> AgentOutput:
        return AgentOutput(
            agent_name=self.name,
            agent_role=self.role,
            analysis=analysis,
            findings=findings,
            risk_score=min(max(risk_score, 0), 1),
            confidence=min(max(confidence, 0), 1),
            recommendations=recommendations,
            raw_llm_response=raw,
            execution_time_ms=elapsed_ms,
        )
