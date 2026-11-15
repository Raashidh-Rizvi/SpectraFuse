"""Application service layer orchestrating Chat requests, session memory, and telemetry."""

import logging
import re
import time
import uuid
from typing import Any

from fastapi import HTTPException

from backend.agents.memory import SessionMemory, get_session_store
from backend.agents.orchestrator import OrchestratorAgent
from backend.agents.schemas import ChatRequest, ChatResponse, EvidenceItem, UIAction, DownloadItem
from backend.agents.web_explanation import explain
from backend.fire import data_directory

logger = logging.getLogger("spectrafuse.agents")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [agents] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class AgentService:
    """Production service coordinating multi-turn chat sessions, reasoning, and guardrails."""

    VALID_REGIONS = {"sri-lanka", "demo", "101,14,102,15", "79.5,5.8,82,10"}
    MAX_MESSAGE_LENGTH = 4000

    FOLLOW_UP_EXPLAIN_PATTERNS = [
        re.compile(r"\b(explain\s+(above|that|this)|tell\s+me\s+more|why\s+is\s+that|why\s+did\s+that\s+happen|why\s+was\s+it\s+(so\s+)?(high|low)|more\s+details(\s+on\s+that)?)\b", re.IGNORECASE),
    ]

    FOLLOW_UP_MAP_PATTERNS = [
        re.compile(r"\b(show\s+(that\s+)?on\s+(the\s+)?map|visualize\s+(that|this)|map\s+(that|this))\b", re.IGNORECASE),
    ]

    FOLLOW_UP_DOWNLOAD_PATTERNS = [
        re.compile(r"\b(download\s+(that|this|it|csv)|export\s+(that|this|it|csv))\b", re.IGNORECASE),
    ]

    def __init__(self, orchestrator: OrchestratorAgent | None = None):
        self.orchestrator = orchestrator or OrchestratorAgent()
        self.session_store = get_session_store()

    def process_chat(self, request: ChatRequest | dict[str, Any], *, monthly_evidence=None) -> ChatResponse:
        """Process incoming chat request with validation, session continuity, and telemetry."""
        if isinstance(request, dict):
            raw_msg = request.get("message") or request.get("question") or ""
            if len(raw_msg) > self.MAX_MESSAGE_LENGTH:
                raise HTTPException(
                    status_code=422,
                    detail=f"Message exceeds maximum allowed length of {self.MAX_MESSAGE_LENGTH} characters (received {len(raw_msg)})."
                )
            request = ChatRequest(**request)

        start_time = time.time()
        req_id = f"req_{uuid.uuid4().hex[:12]}"

        # 1. Input validation: Maximum message length
        msg = (request.message or "").strip()
        if len(msg) > self.MAX_MESSAGE_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"Message exceeds maximum allowed length of {self.MAX_MESSAGE_LENGTH} characters (received {len(msg)})."
            )

        if not msg:
            raise HTTPException(
                status_code=422,
                detail="Message cannot be empty."
            )

        # 2. Input validation: Region resolution
        region = request.region or "sri-lanka"
        if region not in self.VALID_REGIONS:
            # Check if bbox format
            bbox_match = re.match(r"^-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*$", region)
            if not bbox_match:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown region '{region}'. Supported regions are 'sri-lanka', 'demo', or bounding box coordinates (e.g., '101,14,102,15')."
                )

        # 3. Retrieve or create session memory (Short-Term Memory)
        session = self.session_store.get_or_create(request.session_id)
        if request.context:
            session.update_context_from_filter(request.context)

        # 4. Check for follow-up reasoning over Short-Term Memory (STM)
        follow_up_response = self._handle_follow_up(msg, session, req_id)
        if follow_up_response is not None:
            if monthly_evidence is not None:
                follow_up_response = explain(request, session, follow_up_response, monthly_evidence)
            session.add_turn(msg, follow_up_response)
            duration_ms = round((time.time() - start_time) * 1000, 2)
            self._log_telemetry(req_id, session.session_id, follow_up_response.intent, duration_ms, ["stm_memory_reasoner"])
            return follow_up_response

        # 5. Enrich request with session context if missing explicit entities
        enriched_request = self._enrich_request_from_memory(request, session)

        # 6. Process via Orchestrator
        response = self.orchestrator.process(enriched_request)
        if monthly_evidence is not None:
            response = explain(request, session, response, monthly_evidence)
        response.request_id = req_id
        response.session_id = session.session_id

        # 7. Record turn into session memory
        session.add_turn(msg, response)

        # 8. Telemetry audit logging
        duration_ms = round((time.time() - start_time) * 1000, 2)
        tools_used = [ev.source for ev in response.evidence]
        self._log_telemetry(req_id, session.session_id, response.intent, duration_ms, tools_used)

        return response

    def _handle_follow_up(self, message: str, session: SessionMemory, req_id: str) -> ChatResponse | None:
        """Resolve follow-up questions referencing previous conversation turns."""
        last_turn = session.get_last_substantive_turn()
        if not last_turn:
            return None

        low = message.lower().strip()

        # Follow-up: "Explain above" / "Why did that happen?" / "Tell me more"
        is_explain_followup = any(p.search(low) for p in self.FOLLOW_UP_EXPLAIN_PATTERNS)
        if is_explain_followup:
            return self._build_contextual_explanation(last_turn, session, req_id)

        # Follow-up: "Show that on the map" / "Visualize that"
        is_map_followup = any(p.search(low) for p in self.FOLLOW_UP_MAP_PATTERNS)
        if is_map_followup:
            return self._build_map_followup(last_turn, session, req_id)

        # Follow-up: "Download that" / "Export that CSV"
        is_dl_followup = any(p.search(low) for p in self.FOLLOW_UP_DOWNLOAD_PATTERNS)
        if is_dl_followup:
            return self._build_download_followup(last_turn, session, req_id)

        return None

    def _build_contextual_explanation(self, last_turn: Any, session: SessionMemory, req_id: str) -> ChatResponse:
        """Deep contextual reasoning for 'explain above' based on last turn evidence."""
        region = last_turn.region or session.active_region
        year = last_turn.target_year or session.active_year
        month = last_turn.target_month or session.active_month
        detections = last_turn.detections
        intent = last_turn.intent

        # If previous turn was a monthly activity query (e.g. August 2021)
        if intent == "monthly_summary" or detections is not None:
            month_str = f"{year:04d}-{month:02d}" if year and month else "the queried period"
            count_str = f"{detections:,.0f}" if detections is not None else "the reported"
            status_desc = "observed by VIIRS S-NPP at 375 m resolution" if last_turn.status == "observed" else "estimated from MODIS calibrated data"

            # Contextual domain knowledge for Sri Lanka seasonality
            seasonal_explanation = ""
            if region == "sri-lanka" and month in (7, 8, 9):
                seasonal_explanation = (
                    "In Sri Lanka, July through August represents the peak of the secondary fire season during the Southwest Monsoon (Yala dry period). "
                    "While the southwestern wet zone receives heavy rain, the North-Central and Eastern dry zones experience arid, windy conditions. "
                    "Agricultural land clearing (chena cultivation) and scrub burning typically concentrate in this window, producing sharp seasonal peaks. "
                )
            elif region == "sri-lanka" and month in (2, 3):
                seasonal_explanation = (
                    "In Sri Lanka, February and March mark the primary dry season between the Northeast and Southwest monsoons. "
                    "High temperatures and low relative humidity in the dry and intermediate zones facilitate rapid agricultural burning and scrub fires. "
                )
            else:
                seasonal_explanation = (
                    f"Fire activity in {region} during {month_str} is driven by local agricultural cycles, seasonal dryness, "
                    "and climatic factors regulating vegetative fuel moisture. "
                )

            answer = (
                f"Regarding the {month_str} fire activity in {region} ({count_str} detections, {status_desc}):\n\n"
                f"{seasonal_explanation}\n\n"
                "Scientific context:\n"
                "• Satellite thermal detections capture active hotspots at the time of overpass (approximately 13:30 local solar time).\n"
                "• Detection counts represent distinct thermal pixels and do NOT equate to total burned area or the number of individual wildfire incidents.\n"
                "• Satellite observations can be attenuated by cloud cover or heavy smoke plumes."
            )

            return ChatResponse(
                request_id=req_id,
                session_id=session.session_id,
                intent="followup_explanation",
                answer=answer,
                region=region,
                period=last_turn.period,
                evidence=last_turn.evidence,
                calculations=last_turn.calculations,
                limitations=[
                    "Detection counts describe observed satellite thermal hotspots, not burned area or unique wildfire events.",
                    "Satellite observations are subject to cloud cover, smoke attenuation, and diurnal overpass timing.",
                ],
                ui_actions=[],
                downloads=[],
            )

        # If previous turn was an anomaly explanation
        elif intent == "anomaly_explanation":
            answer = (
                f"Regarding the historical anomaly previously calculated for {region}:\n\n"
                "• The seasonal departure is calculated relative to the historical median for that specific calendar month across all available prior years in the archive.\n"
                "• Using the median rather than the arithmetic mean provides robustness against extreme episodic fire years (outliers).\n"
                "• Large negative departures typically correlate with extended monsoonal rainfall, unseasonal precipitation suppressing fuels, or altered agricultural burning schedules.\n"
                "• Detection counts describe observed satellite thermal hotspots, not burned area or unique wildfire events."
            )

            return ChatResponse(
                request_id=req_id,
                session_id=session.session_id,
                intent="followup_explanation",
                answer=answer,
                region=region,
                period=last_turn.period,
                evidence=last_turn.evidence,
                calculations=last_turn.calculations,
                limitations=["Detection counts describe observed satellite thermal hotspots, not burned area or unique wildfire events."],
                ui_actions=[],
                downloads=[],
            )

        # Default contextual explanation
        else:
            answer = (
                f"Continuing from our previous discussion regarding {region}:\n\n"
                f"{last_turn.agent_answer}\n\n"
                "In SpectraFuse, all satellite time-series are harmonized to the VIIRS 375 m observational scale. "
                "Detection counts describe observed satellite thermal hotspots, not burned area or unique wildfire events."
            )
            return ChatResponse(
                request_id=req_id,
                session_id=session.session_id,
                intent="followup_explanation",
                answer=answer,
                region=region,
                period=last_turn.period,
                evidence=last_turn.evidence,
                calculations=last_turn.calculations,
                limitations=["Detection counts describe observed satellite thermal hotspots, not burned area or unique wildfire events."],
                ui_actions=[],
                downloads=[],
            )

    def _build_map_followup(self, last_turn: Any, session: SessionMemory, req_id: str) -> ChatResponse:
        """Resolve 'show that on the map' using date bounds and region from previous turn."""
        region = last_turn.region or session.active_region
        start_date = "2022-03-01"
        end_date = "2022-03-10"

        if last_turn.period and "start" in last_turn.period:
            start_date = last_turn.period["start"]
            end_date = last_turn.period.get("end", start_date)
        elif last_turn.target_year and last_turn.target_month:
            y = last_turn.target_year
            m = last_turn.target_month
            start_date = f"{y:04d}-{m:02d}-01"
            end_date = f"{y:04d}-{m:02d}-10"  # 10 days default map slice

        res = self.orchestrator.map_agent.prepare_map_view(region, start_date, end_date)
        return ChatResponse(
            request_id=req_id,
            session_id=session.session_id,
            intent="hotspot_request",
            answer=f"Displaying hotspot map for {region} from {start_date} to {end_date} based on our previous discussion. Detection counts describe observed hotspots, not burned area or unique wildfire events.",
            region=region,
            period={"start": start_date, "end": end_date},
            evidence=res.get("evidence", []),
            calculations=[],
            limitations=["Detection counts describe observed hotspots, not burned area or unique wildfire events."],
            ui_actions=res.get("ui_actions", []),
            downloads=[],
        )

    def _build_download_followup(self, last_turn: Any, session: SessionMemory, req_id: str) -> ChatResponse:
        """Resolve 'download that CSV' using region and year from previous turn."""
        region = last_turn.region or session.active_region
        year = last_turn.target_year or session.active_year or 2021

        res = self.orchestrator.export_agent.prepare_export(region, year=year)
        return ChatResponse(
            request_id=req_id,
            session_id=session.session_id,
            intent="data_export",
            answer=f"Here is your download reference for {region} monthly data for {year}. Click the download link below.",
            region=region,
            period=last_turn.period,
            evidence=[],
            calculations=[],
            limitations=["Detection counts describe observed hotspots, not burned area or unique wildfire events."],
            ui_actions=[],
            downloads=res.get("downloads", []),
        )

    def _enrich_request_from_memory(self, request: ChatRequest, session: SessionMemory) -> ChatRequest:
        """Enrich user request with memory defaults if region or timeframe were omitted."""
        low = request.message.lower()

        # If user refers to 'next month' or a specific month name without a year, use session year
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", low)
        has_year = bool(year_match)

        # Detect month name in message
        has_month_name = any(re.search(rf"\b{name}\b", low) for name in OrchestratorAgent.MONTH_NAMES)

        if has_month_name and not has_year and session.active_year:
            # Append active year to message so orchestrator extracts it accurately
            enriched_msg = f"{request.message} in {session.active_year}"
            return ChatRequest(
                message=enriched_msg,
                region=request.region or session.active_region,
                session_id=session.session_id,
                context=request.context,
            )

        # If user asks 'what about next month'
        if "next month" in low and session.active_month and session.active_year:
            next_m = (session.active_month % 12) + 1
            next_y = session.active_year + (1 if next_m == 1 else 0)
            month_names = list(OrchestratorAgent.MONTH_NAMES.keys())
            next_month_name = [k for k, v in OrchestratorAgent.MONTH_NAMES.items() if v == next_m and len(k) > 3][0]
            enriched_msg = f"What was the fire activity in {next_month_name} {next_y}?"
            return ChatRequest(
                message=enriched_msg,
                region=request.region or session.active_region,
                session_id=session.session_id,
                context=request.context,
            )

        return request

    def _log_telemetry(self, request_id: str, session_id: str, intent: str, duration_ms: float, tools: list[str]) -> None:
        """Emit structured telemetry event without logging private data or secrets."""
        logger.info(
            f"TELEMETRY: request_id={request_id} session_id={session_id} intent={intent} "
            f"duration_ms={duration_ms} tools={','.join(tools)}"
        )


# Global singleton instance
_GLOBAL_AGENT_SERVICE = AgentService()


def get_agent_service() -> AgentService:
    """Return the global AgentService singleton."""
    return _GLOBAL_AGENT_SERVICE
