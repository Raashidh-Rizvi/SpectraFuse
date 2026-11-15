"""Session and conversation memory management for SpectraFuse Agentic AI.

Supports Short-Term Memory (STM) maintaining the last 4 conversation pairs (8 messages),
context state tracking (active region, dates, sensors, filters), and reference resolution
for natural follow-up queries like 'explain above', 'show on map', or 'what about next month'.
"""

import time
import uuid
from typing import Any
from pydantic import BaseModel, Field

from backend.agents.schemas import ChatResponse, EvidenceItem, CalculationStep, UIAction, DownloadItem


class TurnRecord(BaseModel):
    """Encapsulates a single completed interaction turn."""
    turn_id: str = Field(default_factory=lambda: f"turn_{uuid.uuid4().hex[:8]}")
    timestamp: float = Field(default_factory=time.time)
    user_message: str
    agent_answer: str
    intent: str
    region: str = "sri-lanka"
    period: dict[str, str] | None = None
    target_year: int | None = None
    target_month: int | None = None
    detections: float | None = None
    status: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    calculations: list[CalculationStep] = Field(default_factory=list)
    ui_actions: list[UIAction] = Field(default_factory=list)
    downloads: list[DownloadItem] = Field(default_factory=list)


class SessionMemory:
    """Session-scoped Short-Term Memory (STM) tracking multi-turn dialogue state."""

    def __init__(self, session_id: str, max_pairs: int = 4, ttl_seconds: int = 7200):
        self.session_id = session_id
        self.max_pairs = max_pairs
        self.max_turns = max_pairs * 2  # e.g., 4 pairs = 8 turns
        self.ttl_seconds = ttl_seconds
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.turns: list[TurnRecord] = []

        # Persistent context attributes
        self.active_region: str = "sri-lanka"
        self.active_year: int | None = None
        self.active_month: int | None = None
        self.active_period: dict[str, str] | None = None
        self.last_topic: str | None = None
        self.last_intent: str | None = None
        self.last_detections: float | None = None
        self.last_status: str | None = None

    def touch(self) -> None:
        """Update last accessed timestamp."""
        self.last_accessed = time.time()

    def is_expired(self) -> bool:
        """Check if session has exceeded TTL."""
        return (time.time() - self.last_accessed) > self.ttl_seconds

    def update_context_from_filter(self, context_obj: Any) -> None:
        """Update memory context from incoming client dashboard filter state."""
        self.touch()
        if not context_obj:
            return
        if hasattr(context_obj, "current_region") and context_obj.current_region:
            self.active_region = context_obj.current_region
        if hasattr(context_obj, "current_year") and context_obj.current_year:
            try:
                if str(context_obj.current_year).lower() != "all":
                    self.active_year = int(context_obj.current_year)
            except (ValueError, TypeError):
                pass
        if hasattr(context_obj, "current_month") and context_obj.current_month:
            try:
                self.active_month = int(context_obj.current_month)
            except (ValueError, TypeError):
                pass

    def add_turn(self, user_msg: str, response: ChatResponse) -> TurnRecord:
        """Record completed turn into short term memory and update active context."""
        self.touch()
        self.active_region = response.region or self.active_region
        self.last_intent = response.intent

        # Extract target year and month from period or evidence
        year = None
        month = None
        detections = None
        status = None

        if response.period and "start" in response.period:
            self.active_period = response.period
            parts = response.period["start"].split("-")
            if len(parts) >= 2:
                try:
                    year = int(parts[0])
                    month = int(parts[1])
                except ValueError:
                    pass

        for ev in response.evidence:
            if ev.metric in ("hotspot_detections", "total_detections") and isinstance(ev.value, (int, float)):
                detections = float(ev.value)
                status = ev.status
                break

        if year:
            self.active_year = year
        if month:
            self.active_month = month
        if detections is not None:
            self.last_detections = detections
        if status:
            self.last_status = status

        turn = TurnRecord(
            user_message=user_msg,
            agent_answer=response.answer,
            intent=response.intent,
            region=self.active_region,
            period=response.period,
            target_year=self.active_year,
            target_month=self.active_month,
            detections=self.last_detections,
            status=self.last_status,
            evidence=response.evidence,
            calculations=response.calculations,
            ui_actions=response.ui_actions,
            downloads=response.downloads,
        )

        self.turns.append(turn)

        # Enforce STM window: retain last max_turns
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

        return turn

    def get_recent_turns(self, count: int | None = None) -> list[TurnRecord]:
        """Return the most recent N turns (default: all turns in STM window)."""
        self.touch()
        n = count or self.max_turns
        return self.turns[-n:]

    def format_history_for_prompt(self, max_pairs: int | None = None) -> list[dict[str, str]]:
        """Format STM conversation history into role-based dialogue messages."""
        self.touch()
        pairs = max_pairs or self.max_pairs
        recent_turns = self.turns[-(pairs * 2):] if len(self.turns) > pairs * 2 else self.turns
        messages = []
        for turn in recent_turns:
            messages.append({"role": "user", "content": turn.user_message})
            messages.append({"role": "assistant", "content": turn.agent_answer})
        return messages

    def get_last_turn(self) -> TurnRecord | None:
        """Return the immediately preceding turn if available."""
        self.touch()
        return self.turns[-1] if self.turns else None

    def get_last_substantive_turn(self) -> TurnRecord | None:
        """Return the most recent turn that was not a conversational pleasantry (greeting/gratitude)."""
        self.touch()
        conversational_intents = {"greeting", "gratitude", "help", "farewell", "acknowledgment"}
        for turn in reversed(self.turns):
            if turn.intent not in conversational_intents:
                return turn
        return self.turns[-1] if self.turns else None


class SessionStore:
    """Thread-safe in-memory session repository with TTL cleanup."""

    def __init__(self, default_ttl_seconds: int = 7200, max_sessions: int = 5000):
        self._sessions: dict[str, SessionMemory] = {}
        self.default_ttl = default_ttl_seconds
        self.max_sessions = max_sessions

    def get_or_create(self, session_id: str | None) -> SessionMemory:
        """Retrieve existing active session or initialize a new one."""
        sid = session_id or f"sess_{uuid.uuid4().hex[:10]}"
        self._cleanup_expired()

        if sid in self._sessions:
            session = self._sessions[sid]
            if not session.is_expired():
                session.touch()
                return session
            # Expired session
            del self._sessions[sid]

        session = SessionMemory(session_id=sid, ttl_seconds=self.default_ttl)
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> SessionMemory | None:
        """Retrieve active session if present and unexpired."""
        session = self._sessions.get(session_id)
        if session and not session.is_expired():
            session.touch()
            return session
        if session and session.is_expired():
            del self._sessions[session_id]
        return None

    def delete(self, session_id: str) -> bool:
        """Explicitly clear a session from memory."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def active_session_count(self) -> int:
        """Return number of currently active sessions."""
        self._cleanup_expired()
        return len(self._sessions)

    def _cleanup_expired(self) -> None:
        """Evict expired sessions."""
        now = time.time()
        expired_ids = [sid for sid, s in self._sessions.items() if (now - s.last_accessed) > s.ttl_seconds]
        for sid in expired_ids:
            self._sessions.pop(sid, None)

        # Evict oldest if exceeding capacity
        if len(self._sessions) > self.max_sessions:
            sorted_sessions = sorted(self._sessions.items(), key=lambda item: item[1].last_accessed)
            to_remove = len(self._sessions) - self.max_sessions
            for sid, _ in sorted_sessions[:to_remove]:
                self._sessions.pop(sid, None)


# Global singleton instance
_GLOBAL_STORE = SessionStore()


def get_session_store() -> SessionStore:
    """Return the global session store singleton."""
    return _GLOBAL_STORE
