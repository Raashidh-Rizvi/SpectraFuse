"""Orchestrator Agent: Directs multi-agent workflows, coordinates tools, and enforces guardrails."""

import re
import uuid
from datetime import date
from typing import Any

from backend.agents.analysis_agent import AnalysisAgent
from backend.agents.archive_analysis import archive_analysis, archive_statistic
from backend.agents.data_agent import DataQueryAgent
from backend.agents.explanation_agent import ExplanationAgent
from backend.agents.export_agent import ExportAgent
from backend.agents.map_agent import MapAgent
from backend.agents.recent_detections import recent_detections
from backend.agents.model_provider import BaseModelProvider, get_model_provider
from backend.agents.schemas import ChatRequest, ChatResponse, DownloadItem, UIAction
from backend.agents.validation_agent import ValidationAgent
from backend.chat import basic_lookup, coverage_order


class OrchestratorAgent:
    """Chief orchestrator coordinating specialist sub-agents, tool execution, and guardrails."""

    MONTH_NAMES = {
        "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
        "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
        "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    }

    GREETING_PATTERNS = [
        re.compile(r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening|day)|howdy|hola|sup|yo)\b", re.IGNORECASE),
        re.compile(r"\b(how\s+are\s+you|how\s+are\s+you\s+doing|how's\s+it\s+going)\b", re.IGNORECASE),
    ]

    GRATITUDE_PATTERNS = [
        re.compile(r"\b(thank\s*(you|u|kpu|q|s)?|thanks|thx|ty|much\s+appreciated|appreciate\s+it|cheers|tysm)\b", re.IGNORECASE),
    ]

    HELP_PATTERNS = [
        re.compile(r"\b(who\s+are\s+you|what\s+can\s+you\s+do|what\s+are\s+you|how\s+can\s+you\s+help|what\s+is\s+this|help\s*me|help)\b", re.IGNORECASE),
    ]

    FAREWELL_PATTERNS = [
        re.compile(r"\b(bye|goodbye|see\s+you|see\s+ya|have\s+a\s+good\s+(day|night)|farewell|take\s+care)\b", re.IGNORECASE),
    ]

    ACKNOWLEDGMENT_PATTERNS = [
        re.compile(r"^\s*(ok|okay|got\s+it|cool|great|nice|awesome|perfect|understood|alright|sure)\s*([.!]|\s*$)", re.IGNORECASE),
    ]

    SUBSTANTIVE_KEYWORDS = (
        "fire", "hotspot", "detection", "activity", "burn", "modis", "viirs", "noaa",
        "harmoniz", "calibrat", "anomaly", "departure", "unusual", "download", "export",
        "csv", "map", "bbox", "layer", "month", "season", "trend", "compare", "sensor",
        "holdout", "multiplier", "factor", "spatial", "resolution", "blank", "incomplete"
    )

    def __init__(self, provider: BaseModelProvider | None = None):
        self.provider = provider or get_model_provider()
        self.data_agent = DataQueryAgent()
        self.analysis_agent = AnalysisAgent()
        self.map_agent = MapAgent()
        self.explanation_agent = ExplanationAgent()
        self.export_agent = ExportAgent()
        self.validation_agent = ValidationAgent()

    def process(self, request: ChatRequest) -> ChatResponse:
        """Process user request through intent classification, specialist delegation, and guardrails."""
        req_id = f"req_{uuid.uuid4().hex[:12]}"
        sess_id = request.session_id or f"sess_{uuid.uuid4().hex[:8]}"
        user_msg = request.message.strip()
        low = user_msg.lower()

        # 1. Check for prompt injection / credential probe / jailbreaks / code injection
        injection_markers = (
            "ignore previous", "system prompt", "firms_map_key", "api_key", "password", "secret", "private",
            "drop table", "drop database", "truncate", "select * from", "--", "rm -rf", "c:\\users",
            "/etc/passwd", "/etc/shadow", "chmod 777", "exec(", "eval("
        )
        if any(w in low for w in injection_markers):
            return ChatResponse(
                request_id=req_id,
                session_id=sess_id,
                intent="unsupported_request",
                answer="Response intercepted by security guardrail: I cannot provide server credentials, private keys, execute arbitrary database queries, or override my operational instructions. I can only assist with active-fire analytics and verified satellite observations.",
                region=request.region,
                period=None,
                evidence=[],
                calculations=[],
                limitations=["Requests for system secrets, database modifications, or operational overrides are blocked."],
                ui_actions=[],
                downloads=[],
            )

        # 2. Deterministic conversational intent routing (Gratitude, Greetings, Help, Farewells)
        has_question_or_command = any(q in low for q in ("what", "why", "when", "where", "how many", "how much", "how reliable", "how does", "compare", "show", "download", "export", "can you show", "can you download", "tell me"))
        has_year = bool(re.search(r"\b(19\d\d|20\d\d)\b", low))
        has_month = any(re.search(rf"\b{name}\b", low) for name in self.MONTH_NAMES)

        # 2a. Gratitude / Thanks (applies even if user mentions "fire data" or "helpful", as long as not asking a new question)
        if any(p.search(low) for p in self.GRATITUDE_PATTERNS) and not has_question_or_command:
            return ChatResponse(
                request_id=req_id,
                session_id=sess_id,
                intent="gratitude",
                answer="You're very welcome! I'm here to help with satellite active-fire analytics, historical trends, sensor comparisons, seasonal departures, and map visualizations. Feel free to ask whenever you need more insights.",
                region=request.region,
                period=None,
                evidence=[],
                calculations=[],
                limitations=[],
                ui_actions=[],
                downloads=[],
            )

        # 2b. Greetings
        if any(p.search(low) for p in self.GREETING_PATTERNS) and not any(q in low for q in ("how many", "how much", "what", "why", "when", "compare", "show", "download", "export")) and not has_year and not has_month:
            return ChatResponse(
                request_id=req_id,
                session_id=sess_id,
                intent="greeting",
                answer="Hello! I am your SpectraFuse Satellite Intelligence Assistant. I can help you explore 25 years of NASA FIRMS active-fire observations across Sri Lanka and regional pilot zones. You can ask me to analyze monthly fire activity, compare MODIS and VIIRS sensors, explain seasonal departures, view hotspot maps, or download CSV data. How can I assist you today?",
                region=request.region,
                period=None,
                evidence=[],
                calculations=[],
                limitations=[],
                ui_actions=[],
                downloads=[],
            )

        # 2c. Help / Identity
        if any(p.search(low) for p in self.HELP_PATTERNS) and not has_year and not has_month:
            return ChatResponse(
                request_id=req_id,
                session_id=sess_id,
                intent="help",
                answer="I am the SpectraFuse Satellite Fire Intelligence Assistant, specialized in NASA FIRMS observations. Here is what I can do for you:\n\n• **Monthly Activity**: Query fire detections for any month from 2000 to present (e.g., *'What was fire activity in August 2021?'*).\n• **Sensor Comparison**: Compare 1 km MODIS and 375 m VIIRS observations (e.g., *'Compare MODIS and VIIRS for 2020'*).\n• **Seasonal Anomalies**: Discover if fire counts were unusually high or low compared to historical medians.\n• **Hotspot Maps**: Ask to *'Show that on the map'* to view individual detections and harmonized grids.\n• **Data Export**: Request to *'Download that CSV'* for verified time-series data.",
                region=request.region,
                period=None,
                evidence=[],
                calculations=[],
                limitations=[],
                ui_actions=[],
                downloads=[],
            )

        # 2d. Farewell
        if any(p.search(low) for p in self.FAREWELL_PATTERNS) and not has_question_or_command:
            return ChatResponse(
                request_id=req_id,
                session_id=sess_id,
                intent="farewell",
                answer="Goodbye! Feel free to return anytime for satellite fire analytics and verified observations. Have a wonderful day!",
                region=request.region,
                period=None,
                evidence=[],
                calculations=[],
                limitations=[],
                ui_actions=[],
                downloads=[],
            )

        # 2e. Acknowledgment
        if any(p.search(low) for p in self.ACKNOWLEDGMENT_PATTERNS) and not has_question_or_command:
            return ChatResponse(
                request_id=req_id,
                session_id=sess_id,
                intent="acknowledgment",
                answer="Understood! Let me know if you would like to explore monthly trends, inspect sensor calibrations, or view hotspots on the map.",
                region=request.region,
                period=None,
                evidence=[],
                calculations=[],
                limitations=[],
                ui_actions=[],
                downloads=[],
            )

        # 3. Extract entities (Region, Year, Month, Dates, BBox)
        region = request.region
        if "thailand" in low:
            region = "101,14,102,15"
        elif "sri lanka" in low or "sri-lanka" in low:
            region = "sri-lanka"
        elif "demo" in low:
            region = "demo"

        year_match = re.search(r"\b(19\d\d|20\d\d)\b", low)
        year = int(year_match.group(1)) if year_match else None

        extracted_month_num = None
        for name, num in self.MONTH_NAMES.items():
            if re.search(rf"\b{name}\b", low):
                extracted_month_num = num
                break

        # Fallback to context if available
        if year is None and request.context and request.context.current_year and request.context.current_year != "all":
            try:
                year = int(request.context.current_year)
            except ValueError:
                pass

        # 3. Classify Intent and Delegate to Specialist Agent
        ui_actions: list[UIAction] = []
        downloads: list[DownloadItem] = []
        lookup, operation = basic_lookup(user_msg, has_history=bool(request.history))
        calibration_question = any(w in low for w in ("multiplier", "calibration", "holdout", "factor", "how reliable"))
        monthly_topic = re.search(r"\b(?:fire activity|fire counts?|detections?|hotspots?|burning activity)\b", low)

        if lookup:
            intent = {"coverage": "coverage_question", "monthly": "monthly_summary", "frp": "trend_analysis"}[lookup.kind]
            res = archive_statistic(region, lookup, operation)
        elif coverage_order(low):
            intent = "clarification"
            res = {"answer": "Which sensor and archive period do you want to check? For example, ask how far back MODIS data goes."}
        elif not calibration_question and (re.search(r"\b(?:average|mean|median)\s+[a-z]", low)
                                          or re.search(r"\bwhat(?: is|'?s) the (?:mean|average)\b", low)):
            intent = "clarification"
            res = {"answer": "Which sensor and metric should I calculate? For example, ask for average monthly MODIS detections in 2024 or mean MODIS FRP in February 2024."}
        elif re.search(r"\b(districts?|protected areas?|forest reserves?|reserves?)\b", low):
            intent = "coverage_question"
            res = {"answer": "This archive supports regional and coordinate bounds. For a district, "
                             "reserve, or protected area, provide west,south,east,north coordinates "
                             "and a date range to query detections within that rectangle."}
        # Recent observations use archive acquisition times and per-product coverage.
        elif (re.search(r"\b(latest|recent|most recently|newest|currently burning)\b", low) and has_question_or_command) or (
            re.search(r"hotspots?|detections?", low) and not re.search(r"\bmap\b", low)
            and re.search(r"\b\d{4}-\d{2}-\d{2}\b", low)
        ):
            intent = "hotspot_request"
            dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", low)
            try:
                start = date.fromisoformat(dates[0]) if dates else None
                end = date.fromisoformat(dates[-1]) if dates else None
                bounds = re.search(r"(-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?)", low)
                bbox = tuple(map(float, bounds[1].split(","))) if bounds else None
                if bbox and not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
                    raise ValueError("Invalid bounds")
            except ValueError:
                res = {"answer": "Use valid dates in YYYY-MM-DD format and bounds in west,south,east,north order."}
            else:
                res = recent_detections(region, low, start, end, bbox)

        # Intent: Map / Hotspots
        elif any(w in low for w in ("map", "bounding box", "bbox", "layer")):
            intent = "hotspot_request"
            date_matches = re.findall(r"\b20\d\d-\d\d-\d\d\b", low)
            start_date = date_matches[0] if len(date_matches) >= 1 else f"{year or 2022}-03-01"
            end_date = date_matches[1] if len(date_matches) >= 2 else f"{year or 2022}-03-10"
            bbox_match = re.search(r"(-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*)", user_msg)
            bbox = bbox_match.group(1) if bbox_match else None

            res = self.map_agent.prepare_map_view(region, start_date, end_date, bbox=bbox)
            ui_actions = res.get("ui_actions", [])

        # Intent: Data Export
        elif any(w in low for w in ("download", "export", "csv")):
            intent = "data_export"
            res = self.export_agent.prepare_export(region, year=year or 2022)
            downloads = res.get("downloads", [])

        # Keep distinct periods instead of reducing the request to its first date.
        elif (
            len(set(re.findall(r"\b(?:19|20)\d{2}\b", low))) > 1
            or sum(bool(re.search(rf"\b{name}\b", low)) for name in self.MONTH_NAMES) > 1
            or re.search(r"year.by.year|year.over.year|annual|trend|patterns?|anomalies|seasonality", low)
            or re.search(r"observed.only|only observed|without estimates|exclude estimates", low)
            or ("harmoniz" in low and any(w in low for w in ("before", "after", "raw")))
            or (monthly_topic and has_year and not has_month and not any(w in low for w in (
                "compare", "comparison", "difference", " viirs", "modis", "calibrat",
                "holdout", "factor", "unusual", "anomaly", "departure", "incomplete", "missing",
            )))
            or (("compare" in low or "difference" in low) and has_month
                and not re.search(r"unusual|anomal|departure|normal", low)
                and not ("modis" in low and "viirs" in low))
            or re.search(r"\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])\b", low)
        ):
            intent = "monthly_summary" if has_year and not has_month and not re.search(
                r"compare|difference|trend|annual|pattern|year.by.year|harmoniz|anomal|season|\d{4}-", low
            ) and len(set(re.findall(r"\b(?:19|20)\d{2}\b", low))) == 1 else "trend_analysis"
            selected_year = request.context.current_year if request.context else None
            res = archive_analysis(region, low, selected_year, self.MONTH_NAMES)

        # Intent: Seasonal Anomaly / Departure
        elif any(w in low for w in ("unusual", "anomaly", "departure", "normal", "compared with earlier", "compared to earlier")):
            intent = "anomaly_explanation"
            target_year = year or 2023
            target_month = extracted_month_num or 3
            res = self.analysis_agent.analyze_seasonal_departure(region, target_year, target_month)

        # Intent: Methodology / Scientific Difference
        elif any(w in low for w in ("difference between", "what is modis", "what is viirs", "what does", "burned area", "unique fire", "wildfire events", "unique wildfire", "explain the difference")):
            intent = "methodology_question"
            res = self.explanation_agent.explain(user_msg, region)

        # Intent: Sensor Comparison
        elif any(w in low for w in ("compare", "comparison", "modis and viirs", "viirs vs modis")):
            intent = "sensor_comparison"
            target_year = year or 2020
            start_m = f"{target_year}-{extracted_month_num or 1:02d}"
            end_m = f"{target_year}-{extracted_month_num or 12:02d}"
            res = self.analysis_agent.compare_sensors_for_period(region, start_m, end_m)

        # Intent: Trend / Peak Harmonized Activity
        elif not calibration_question and any(w in low for w in ("highest", "peak", "most active", "record month", "top months", "maximum activity")):
            intent = "trend_analysis"
            res = self.data_agent.query_peak_months(region, top_n=5)

        # Intent: Calibration Multiplier / Reliability
        elif calibration_question or "harmoniz" in low:
            intent = "calibration_explanation"
            res = self.analysis_agent.explain_calibration_factor(region)

        # Intent: Missing / Incomplete Month or Coverage question
        elif any(w in low for w in ("incomplete", "blank", "missing", "why is this month blank")):
            intent = "coverage_question"
            res = self.explanation_agent.explain("incomplete month", region)

        # Intent: Provenance / Observed vs Estimated question
        elif year and extracted_month_num and any(w in low for w in ("observed or estimated", "estimated or observed", "why is", "is the selected month")):
            intent = "coverage_question"
            res = self.data_agent.query_monthly_summary(region, f"{year:04d}-{extracted_month_num:02d}")

        elif year and extracted_month_num and (monthly_topic or low.startswith("what about")):
            intent = "monthly_summary"
            res = self.data_agent.query_monthly_summary(region, f"{year:04d}-{extracted_month_num:02d}")
        else:
            intent = "clarification"
            res = {"answer": "What would you like to look up in the fire archive? Specify the sensor, metric, or period you’re interested in."}

        if intent == "clarification":
            return ChatResponse(request_id=req_id, session_id=sess_id, intent=intent, answer=res["answer"], region=region)

        # 4. Run Guardrail Validation Pass
        raw_answer = res.get("answer", "")
        evidence = res.get("evidence", [])
        calculations = res.get("calculations", [])
        limitations = res.get("limitations", [])

        validated = self.validation_agent.validate(
            draft_answer=raw_answer,
            evidence=evidence,
            calculations=calculations,
            limitations=limitations,
        )

        return ChatResponse(
            request_id=req_id,
            session_id=sess_id,
            intent=intent,
            answer=validated["answer"],
            region=region,
            period=res.get("period"),
            evidence=validated["evidence"],
            calculations=validated["calculations"],
            limitations=validated["limitations"],
            ui_actions=ui_actions,
            downloads=downloads,
        )
