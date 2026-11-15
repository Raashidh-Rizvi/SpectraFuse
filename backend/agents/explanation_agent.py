"""Explanation Agent: Explains scientific concepts, sensor physics, and methodology."""

from typing import Any
from backend.agents.knowledge_base import read_doc_section
from backend.agents.schemas import EvidenceItem


class ExplanationAgent:
    """Specialist agent responsible for explaining scientific methodology and limitations."""

    def explain(self, topic: str, region: str = "sri-lanka") -> dict[str, Any]:
        """Provide a concise, scientifically accurate explanation of a methodology concept."""
        explanation_text = read_doc_section(topic)

        evidence = [
            EvidenceItem(
                source="project_methodology_documentation",
                product=None,
                metric="documentation_concept",
                value=topic,
                status="verified_reference",
            )
        ]

        limitations = [
            "Detection counts describe observed satellite thermal hotspots, not burned area or unique wildfire events.",
            "Satellite observations are subject to cloud cover, smoke attenuation, and diurnal overpass timing.",
        ]

        return {
            "answer": explanation_text,
            "evidence": evidence,
            "limitations": limitations,
            "period": None,
        }
