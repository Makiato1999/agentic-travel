"""FastAPI entrypoint for the travel assistant."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.travel_assistant_service import TravelAssistantService
from utils.circuit_breaker import CircuitOpenError


app = FastAPI(
    title="Agentic Travel API",
    version="0.1.0",
    description="API layer for the business travel assistant.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


_sessions: Dict[str, TravelAssistantService] = {}


def get_session_service(session_id: str) -> TravelAssistantService:
    service = _sessions.get(session_id)
    if not service:
        raise HTTPException(status_code=404, detail="Session not found")
    return service


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/sessions", response_model=CreateSessionResponse)
async def create_session(payload: CreateSessionRequest) -> CreateSessionResponse:
    service = TravelAssistantService()
    session = await service.initialize(user_id=payload.user_id, session_id=payload.session_id)
    _sessions[session["session_id"]] = service
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
