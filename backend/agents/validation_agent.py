"""Validation & Guardrail Agent: Verifies numerical grounding, blocks secret leaks, and checks claims."""

import re
from typing import Any
from backend.agents.schemas import CalculationStep, EvidenceItem


class ValidationAgent:
    """Strict guardrail agent ensuring safety, grounding, and provenance accuracy."""

    SECRET_PATTERNS = [
        re.compile(r"gsk_[a-zA-Z0-9]{20,}", re.IGNORECASE),
        re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
        re.compile(r"FIRMS_MAP_KEY\s*=\s*\S+", re.IGNORECASE),
        re.compile(r"(api[_-]?key|secret|password)\s*[:=]\s*['\"]?\w+['\"]?", re.IGNORECASE),
        re.compile(r"[A-Z]:\\[Users|Windows|System32]\\[\w\\]+", re.IGNORECASE),
    ]

    DISCLAIMER = "Detection counts describe observed hotspots, not burned area or unique wildfire events."

    def validate(
        self,
        draft_answer: str,
        evidence: list[EvidenceItem],
        calculations: list[CalculationStep] | None = None,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        """Verify the draft answer against evidence, scan for secrets, and enforce guardrails."""
        calcs = calculations or []
        limits = list(limitations or [])

        # 1. Secret leak check
        for pattern in self.SECRET_PATTERNS:
            if pattern.search(draft_answer):
                return {
                    "passed": False,
                    "answer": "Response intercepted by security guardrail: Detected potential credential or file path leakage.",
                    "evidence": [],
                    "calculations": [],
                    "limitations": ["Protected system credentials."],
                }

        # 2. Collect all grounded numbers from evidence and calculations
        # Pre-seed standard satellite domain constants (e.g. 375m VIIRS, 1000m MODIS resolution)
        grounded_numbers: set[float] = {375.0, 1000.0, 500.0}
        for ev in evidence:
            if isinstance(ev.value, (int, float)):
                v = float(ev.value)
                grounded_numbers.update([round(v, 1), round(v, 0), abs(round(v, 1)), abs(round(v, 0))])
            if isinstance(ev.metadata, dict):
                for val in ev.metadata.values():
                    if isinstance(val, (int, float)):
                        v = float(val)
                        grounded_numbers.update([round(v, 1), round(v, 0), abs(round(v, 1)), abs(round(v, 0))])

        for c in calcs:
            if isinstance(c.result, (int, float)):
                v = float(c.result)
                grounded_numbers.update([round(v, 1), round(v, 0), abs(round(v, 1)), abs(round(v, 0))])
            elif isinstance(c.result, str):
                for match in re.findall(r"[-+]?\d+\.?\d*", c.result):
                    try:
                        v = float(match)
                        grounded_numbers.update([round(v, 1), round(v, 0), abs(round(v, 1)), abs(round(v, 0))])
                    except ValueError:
                        pass

        # 3. Detect ungrounded numerical claims (large numbers > 10 not representing calendar years)
        words = draft_answer.replace(",", "")
        cited_numbers = re.findall(r"\b\d+\.?\d*\b", words)
        for num_str in cited_numbers:
            try:
                num = float(num_str)
                # Ignore calendar years (1900 - 2030), days (1-31), small counts (< 4)
                if (1900 <= num <= 2030) or (1 <= num <= 31):
                    continue
                rounded = round(num, 1)
                rounded_int = round(num, 0)
                if rounded not in grounded_numbers and rounded_int not in grounded_numbers and evidence:
                    # Flag ungrounded claim
                    draft_answer += f" [Note: The cited figure {num_str} is unverified against local evidence]."
            except ValueError:
                pass

        # 4. Check for misrepresentation of estimated data as observed
        for ev in evidence:
            if ev.status == "estimated" and "observed" in draft_answer.lower() and "estimated" not in draft_answer.lower():
                draft_answer = draft_answer.replace("observed", "estimated")

        # 5. Missing data cannot be represented as zero
        for ev in evidence:
            if ev.status == "unavailable" and " 0 " in draft_answer:
                draft_answer = (
                    "Data is unavailable for this period due to missing satellite partitions. "
                    "Missing data is fundamentally distinct from zero observed detections."
                )

        # 6. Ensure mandatory scientific limitation
        if any(w in draft_answer.lower() for w in ("detection", "hotspot", "fire activity")) and self.DISCLAIMER not in draft_answer:
            draft_answer += f" {self.DISCLAIMER}"

        if self.DISCLAIMER not in limits:
            limits.append(self.DISCLAIMER)

        return {
            "passed": True,
            "answer": draft_answer.strip(),
            "evidence": evidence,
            "calculations": calcs,
            "limitations": limits,
        }
