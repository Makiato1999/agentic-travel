"""Reusable business logic for CLI and FastAPI interfaces."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from agentscope.message import Msg
from agentscope.model import OpenAIChatModel

from agents.intention_agent import IntentionAgent
from agents.orchestration_agent import OrchestrationAgent
from config import LLM_CONFIG, RESILIENCE_CONFIG, SYSTEM_CONFIG
from config_agentscope import init_agentscope
from context.memory_manager import MemoryManager
from services.result_formatter import ResultFormatter
from utils.circuit_breaker import CircuitBreaker, CircuitOpenError
from utils.llm_resilience import retry_with_backoff, run_health_check as check_llm_health


project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class TravelAssistantService:
    """Application service that encapsulates initialization and query handling."""

    _agentscope_initialized = False

    def __init__(self):
        self.user_id: Optional[str] = None
        self.session_id: Optional[str] = None
        self.memory_manager: Optional[MemoryManager] = None
        self.orchestrator: Optional[OrchestrationAgent] = None
        self.intention_agent: Optional[IntentionAgent] = None
        self.model: Optional[OpenAIChatModel] = None
        self._agent_cache: Dict[str, Any] = {}
        self.circuit_breaker: Optional[CircuitBreaker] = None

    async def initialize(self, user_id: str = "default_user", session_id: Optional[str] = None) -> Dict[str, str]:
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())[:8]

        if not self.__class__._agentscope_initialized:
            init_agentscope()
            self.__class__._agentscope_initialized = True

        timeout_sec = SYSTEM_CONFIG.get("timeout", 60)
        self.model = OpenAIChatModel(
            model_name=LLM_CONFIG["model_name"],
            api_key=LLM_CONFIG["api_key"],
            client_kwargs={
                "base_url": LLM_CONFIG["base_url"],
                "timeout": float(timeout_sec),
            },
            temperature=LLM_CONFIG.get("temperature", 0.7),
            max_tokens=LLM_CONFIG.get("max_tokens", 2000),
        )

        self.memory_manager = MemoryManager(
            user_id=self.user_id,
            session_id=self.session_id,
            llm_model=self.model,
        )

        self.intention_agent = IntentionAgent(name="IntentionAgent", model=self.model)

        from agents.lazy_agent_registry import LazyAgentRegistry

        self._agent_cache = {}
        lazy_registry = LazyAgentRegistry(
            model=self.model,
            cache=self._agent_cache,
            memory_manager=self.memory_manager,
        )

        self.orchestrator = OrchestrationAgent(
            name="OrchestrationAgent",
            agent_registry=lazy_registry,
            memory_manager=self.memory_manager,
        )

        rc = RESILIENCE_CONFIG
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=rc.get("circuit_failure_threshold", 5),
            recovery_timeout_sec=rc.get("circuit_recovery_timeout_sec", 60.0),
            half_open_successes=rc.get("circuit_half_open_successes", 2),
        )

        return {"user_id": self.user_id, "session_id": self.session_id}

    async def process_query(self, user_input: str) -> Dict[str, Any]:
        self._require_initialized()

        start_time = time.time()
        if self.circuit_breaker:
            self.circuit_breaker.raise_if_open()

        context_messages = await self._build_context_messages(user_input)
        intention_result = await self._run_intention(context_messages)
        intention_data = self._safe_json_loads(
            intention_result.content,
            fallback={"error": "无法解析意图识别结果"},
        )
        if intention_data.get("error"):
            return {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "query": user_input,
                "intention": intention_data,
                "result": {"error": "无法解析意图识别结果"},
                "agents_called": [],
                "display_text": "无法理解您的需求，请重新描述。",
                "timing": {
                    "elapsed_seconds": round(time.time() - start_time, 3),
                },
            }

        self.memory_manager.add_message("user", user_input)

        orchestration_result = await self._run_orchestration(intention_result)
        result_data = self._safe_json_loads(
            orchestration_result.content,
            fallback={"error": "解析结果失败"},
        )

        self.memory_manager.add_message("assistant", json.dumps(result_data, ensure_ascii=False))

        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "query": user_input,
            "intention": intention_data,
            "result": result_data,
            "agents_called": ResultFormatter.collect_agents_called(result_data),
            "display_text": ResultFormatter.render_to_text(result_data),
            "timing": {
                "elapsed_seconds": round(time.time() - start_time, 3),
            },
        }

    async def run_health_check(self) -> Dict[str, Any]:
        breaker_status = self.circuit_breaker.get_status() if self.circuit_breaker else None
        ok, message = await check_llm_health(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"],
            model_name=LLM_CONFIG["model_name"],
            timeout_sec=RESILIENCE_CONFIG.get("health_check_timeout_sec", 10.0),
        )
        return {
            "ok": ok,
            "message": message,
            "circuit_breaker": breaker_status,
        }

    def clear_short_term_memory(self) -> None:
        self._require_initialized()
        self.memory_manager.short_term.clear()

    def end_session(self) -> None:
        self._require_initialized()
        self.memory_manager.end_session()

    def get_status(self) -> Dict[str, Any]:
        self._require_initialized()
        full_context = self.memory_manager.get_full_context()
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "short_term": full_context["short_term"],
            "long_term": full_context["long_term"],
            "loaded_agent_count": len(self._agent_cache),
            "loaded_agents": sorted(self._agent_cache.keys()),
        }

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        self._require_initialized()
        return self.memory_manager.long_term.get_trip_history(limit)

    def get_preferences(self) -> Dict[str, Any]:
        self._require_initialized()
        return self.memory_manager.long_term.get_preference()

    async def _build_context_messages(self, user_input: str) -> List[Msg]:
        long_term_summary = await self._get_long_term_summary(user_input)
        recent_context = self.memory_manager.short_term.get_recent_context(n_turns=5)
        context_messages: List[Msg] = []
        if long_term_summary:
            context_messages.append(Msg(name="system", content=long_term_summary, role="system"))
        for msg in recent_context:
            context_messages.append(Msg(name=msg["role"], content=msg["content"], role=msg["role"]))
        context_messages.append(Msg(name="user", content=user_input, role="user"))
        return context_messages

    async def _run_intention(self, context_messages: List[Msg]):
        rc = RESILIENCE_CONFIG
        try:
            result = await retry_with_backoff(
                lambda: self.intention_agent.reply(context_messages),
                max_retries=rc.get("max_retries", 3),
                base_delay_sec=rc.get("retry_base_delay_sec", 1.0),
                max_delay_sec=rc.get("retry_max_delay_sec", 30.0),
            )
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise

    async def _run_orchestration(self, intention_result):
        rc = RESILIENCE_CONFIG
        try:
            result = await retry_with_backoff(
                lambda: self.orchestrator.reply(intention_result),
                max_retries=rc.get("max_retries", 3),
                base_delay_sec=rc.get("retry_base_delay_sec", 1.0),
                max_delay_sec=rc.get("retry_max_delay_sec", 30.0),
            )
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise

    async def _get_long_term_summary(self, user_input: str = "") -> str:
        summary_parts = []

        prefs = self.memory_manager.long_term.get_preference()
        if prefs:
            pref_lines = ["【用户背景信息】（来自长期记忆，可用于推断缺失信息）"]
            for pref_key, pref_value in prefs.items():
                if not pref_value:
                    continue
                if isinstance(pref_value, list):
                    pref_lines.append(f"• {pref_key}: {', '.join(pref_value)}")
                else:
                    pref_lines.append(f"• {pref_key}: {pref_value}")
            if len(pref_lines) > 1:
                summary_parts.extend(pref_lines)

        chat_summary = await self.memory_manager.get_long_term_summary_async(max_messages=50)
        if chat_summary:
            summary_parts.append("\n【历史会话总结】")
            summary_parts.append(chat_summary)

        all_trips = self.memory_manager.long_term.get_trip_history(limit=None)
        if all_trips:
            relevant_trips = []
            other_trips = []

            for trip in all_trips:
                origin = trip.get("origin", "") or ""
                destination = trip.get("destination", "") or ""
                if (origin and origin in user_input) or (destination and destination in user_input):
                    relevant_trips.append(trip)
                else:
                    other_trips.append(trip)

            trips_to_show = relevant_trips[:2] + other_trips[:1]
            if trips_to_show:
                summary_parts.append("\n【历史行程】")
                for i, trip in enumerate(trips_to_show[:3], 1):
                    origin = trip.get("origin", "未知")
                    destination = trip.get("destination", "未知")
                    start_date = trip.get("start_date", "")
                    purpose = trip.get("purpose", "")
                    relevance_mark = "✦ " if trip in relevant_trips else ""
                    summary_parts.append(
                        f"{i}. {relevance_mark}{origin} → {destination} ({start_date}) - {purpose}"
                    )

        return "\n".join(summary_parts) if summary_parts else ""

    def _require_initialized(self) -> None:
        if not self.memory_manager or not self.intention_agent or not self.orchestrator:
            raise RuntimeError("Service not initialized")

    @staticmethod
    def _safe_json_loads(content: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            return fallback
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return fallback
