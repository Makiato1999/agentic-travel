"""Primary FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.services.travel_assistant_service import TravelAssistantService
from backend.utils.circuit_breaker import CircuitOpenError


class PollingAccessFilter(logging.Filter):
    """Reduce noise from high-frequency task polling access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return "GET /api/v1/sessions/" not in message or "/tasks/" not in message


logging.getLogger("uvicorn.access").addFilter(PollingAccessFilter())


app = FastAPI(
    title="Agentic Travel API",
    version="0.2.0",
    description="API layer for the business travel assistant.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateSessionRequest(BaseModel):
    user_id: str = Field(default="default_user")
    session_id: Optional[str] = None


class CreateSessionResponse(BaseModel):
    user_id: str
    session_id: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    user_id: str
    session_id: str
    query: str
    intention: Dict[str, Any]
    result: Dict[str, Any]
    agents_called: List[Dict[str, str]]
    display_text: str
    timing: Dict[str, Any]


class CreateTaskResponse(BaseModel):
    task_id: str
    session_id: str
    status: str


_sessions: Dict[str, TravelAssistantService] = {}
_session_tasks: Dict[str, Dict[str, Dict[str, Any]]] = {}


def get_session_service(session_id: str) -> TravelAssistantService:
    service = _sessions.get(session_id)
    if not service:
        raise HTTPException(status_code=404, detail="Session not found")
    return service


def ensure_task_store(session_id: str) -> Dict[str, Dict[str, Any]]:
    if session_id not in _session_tasks:
        _session_tasks[session_id] = {}
    return _session_tasks[session_id]


def get_task(session_id: str, task_id: str) -> Dict[str, Any]:
    session_tasks = ensure_task_store(session_id)
    task = session_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/sessions", response_model=CreateSessionResponse)
async def create_session(payload: CreateSessionRequest) -> CreateSessionResponse:
    service = TravelAssistantService()
    session = await service.initialize(user_id=payload.user_id, session_id=payload.session_id)
    _sessions[session["session_id"]] = service
    ensure_task_store(session["session_id"])
    return CreateSessionResponse(**session)


@app.get("/api/v1/sessions/{session_id}/health")
async def session_health(session_id: str) -> Dict[str, Any]:
    service = get_session_service(session_id)
    return await service.run_health_check()


@app.post("/api/v1/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, payload: ChatRequest) -> ChatResponse:
    service = get_session_service(session_id)
    try:
        result = await service.process_query(payload.message)
    except CircuitOpenError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or "Service temporarily unavailable") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChatResponse(**result)


@app.post("/api/v1/sessions/{session_id}/tasks", response_model=CreateTaskResponse)
async def create_task(session_id: str, payload: ChatRequest) -> CreateTaskResponse:
    service = get_session_service(session_id)
    task_id = str(uuid.uuid4())[:8]
    task_state: Dict[str, Any] = {
        "task_id": task_id,
        "session_id": session_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "任务已创建",
        "query": payload.message,
        "created_at": time.time(),
        "updated_at": time.time(),
        "intention": None,
        "agents_planned": [],
        "agents_completed": [],
        "latest_results": [],
        "result": None,
        "display_text": "",
        "timing": None,
        "error": None,
    }
    ensure_task_store(session_id)[task_id] = task_state

    async def update_state(update: Dict[str, Any]) -> None:
        task_state["updated_at"] = time.time()
        task_state.update(update)

        if task_state.get("stage") == "agent_running":
            planned = task_state.get("agents_planned") or []
            completed = task_state.get("agents_completed") or []
            if planned:
                ratio = min(len(completed) / len(planned), 1)
                task_state["progress"] = max(task_state.get("progress", 36), int(48 + ratio * 40))
            else:
                task_state["progress"] = max(task_state.get("progress", 36), 60)

        if task_state.get("stage") == "completed":
            task_state["status"] = "completed"
        elif task_state.get("stage") == "failed":
            task_state["status"] = "failed"
        elif task_state["status"] == "queued":
            task_state["status"] = "running"

        if update.get("latest_results"):
            completed = list(task_state.get("agents_completed", []))
            for item in update["latest_results"]:
                agent_name = item.get("agent_name")
                if agent_name and agent_name not in completed:
                    completed.append(agent_name)
            task_state["agents_completed"] = completed

    async def run_task() -> None:
        try:
            await update_state(
                {
                    "status": "running",
                    "stage": "queued",
                    "progress": 4,
                    "message": "任务开始执行",
                }
            )
            result = await service.process_query_with_updates(payload.message, progress_callback=update_state)
            await update_state(
                {
                    "status": "completed",
                    "stage": "completed",
                    "progress": 100,
                    "message": "任务执行完成",
                    "intention": result.get("intention"),
                    "result": result.get("result"),
                    "display_text": result.get("display_text", ""),
                    "timing": result.get("timing"),
                    "agents_planned": [item["agent_name"] for item in result.get("agents_called", [])],
                    "agents_completed": [item["agent_name"] for item in result.get("agents_called", [])],
                }
            )
        except CircuitOpenError as exc:
            await update_state(
                {
                    "status": "failed",
                    "stage": "failed",
                    "progress": 100,
                    "message": "服务暂时不可用",
                    "error": str(exc) or "Service temporarily unavailable",
                }
            )
        except Exception as exc:
            await update_state(
                {
                    "status": "failed",
                    "stage": "failed",
                    "progress": 100,
                    "message": "任务执行失败",
                    "error": str(exc),
                }
            )

    asyncio.create_task(run_task())
    return CreateTaskResponse(task_id=task_id, session_id=session_id, status="queued")


@app.get("/api/v1/sessions/{session_id}/tasks/{task_id}")
async def get_task_status(session_id: str, task_id: str) -> Dict[str, Any]:
    get_session_service(session_id)
    return get_task(session_id, task_id)


@app.post("/api/v1/sessions/{session_id}/clear")
async def clear_session_memory(session_id: str) -> Dict[str, str]:
    service = get_session_service(session_id)
    service.clear_short_term_memory()
    return {"status": "ok"}


@app.post("/api/v1/sessions/{session_id}/end")
async def end_session(session_id: str) -> Dict[str, str]:
    service = get_session_service(session_id)
    service.end_session()
    _sessions.pop(session_id, None)
    _session_tasks.pop(session_id, None)
    return {"status": "ok"}


@app.get("/api/v1/sessions/{session_id}/status")
async def get_status(session_id: str) -> Dict[str, Any]:
    service = get_session_service(session_id)
    return service.get_status()


@app.get("/api/v1/sessions/{session_id}/history")
async def get_history(session_id: str, limit: int = 10) -> Dict[str, Any]:
    service = get_session_service(session_id)
    return {"items": service.get_history(limit=limit)}


@app.get("/api/v1/sessions/{session_id}/preferences")
async def get_preferences(session_id: str) -> Dict[str, Any]:
    service = get_session_service(session_id)
    return {"items": service.get_preferences()}
