"""FastAPI application — REST + streaming SSE endpoints."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from starlette.middleware.security import SecurityHeadersMiddleware

from config import settings
from file_processor import process_file
from harley import detect_task, get_agent_for_task, AGENT_DESCRIPTIONS, harley_error_message
from llm import ollama
from middleware import (
    create_token, hash_password, limiter, setup_middleware, verify_password, verify_token,
)
from voice_processor import transcribe_audio

logger = structlog.get_logger()

# ── In-memory session store (replace with Redis for prod) ─────────────────────
_sessions: dict[str, list[dict]] = {}

# ── Users (replace with DB in prod) ───────────────────────────────────────────
USERS = {
    "admin": {"hash": hash_password("HarleyQ!2026"), "role": "admin"},
    "user":  {"hash": hash_password("puddin123"),    "role": "user"},
}


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("harley_ai_starting", version=settings.version)
    await ollama.health()
    await ollama.ensure_models()
    logger.info("harley_ai_ready")
    yield
    logger.info("harley_ai_shutdown")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
setup_middleware(app)
app.add_middleware(SecurityHeadersMiddleware)

app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

security = HTTPBearer(auto_error=False)


async def get_user(creds: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token required")
    payload = verify_token(creds.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    username = payload.get("sub", "")
    if username not in USERS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return {"username": username, "role": USERS[username]["role"]}


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = USERS.get(username)
    if not user or not verify_password(password, user["hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad credentials, Puddin'!")
    token = create_token({"sub": username, "role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "username": username}


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    llm_status = await ollama.health()
    return {
        "status": "healthy",
        "version": settings.version,
        "llm": llm_status,
        "app": settings.app_name,
    }


# ── Chat (streaming SSE) ──────────────────────────────────────────────────────
@app.post("/api/chat/stream")
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def chat_stream(
    request: Request,
    message: str = Form(""),
    session_id: str = Form(default_factory=lambda: str(uuid.uuid4())),
    file: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_user),
):
    """SSE streaming chat endpoint with file + audio support."""

    file_content: Optional[str] = None
    file_info_text: Optional[str] = None
    transcription: Optional[str] = None
    image_data: Optional[bytes] = None
    task = "default"
    agent = "Harley"

    # ── Process uploaded file ─────────────────────────────────────────────────
    if file and file.filename:
        max_bytes = settings.max_upload_mb * 1024 * 1024
        raw = await file.read(max_bytes + 1)
        if len(raw) > max_bytes:
            error_msg = harley_error_message("file_too_large")
            return StreamingResponse(
                _simple_stream(error_msg), media_type="text/event-stream"
            )
        info = await process_file(file.filename, raw)
        file_content = info.content
        file_info_text = f"[File: {info.name} | {info.summary}]"
        if info.is_image:
            image_data = raw
            task = "image"
        elif info.is_audio:
            task = "voice"
        else:
            task = "file_analysis"

    # ── Process uploaded audio ────────────────────────────────────────────────
    if audio and audio.filename:
        max_bytes = settings.max_upload_mb * 1024 * 1024
        raw = await audio.read(max_bytes + 1)
        if len(raw) <= max_bytes:
            result = await transcribe_audio(raw, audio.filename)
            if result["success"]:
                transcription = result["text"]
                lang = result["language"]
                dur = result["duration_seconds"]
                message = message or f"[Voice message transcribed: {transcription}]"
                file_info_text = (
                    f"[Audio: {audio.filename} | duration={dur:.1f}s | lang={lang}]"
                )
                task = "voice"
            else:
                error_msg = harley_error_message("transcription_failed")
                return StreamingResponse(
                    _simple_stream(error_msg), media_type="text/event-stream"
                )

    # ── Task detection ────────────────────────────────────────────────────────
    if task == "default" and message:
        task = detect_task(message)
    agent = get_agent_for_task(task)

    # ── Build message for LLM ─────────────────────────────────────────────────
    user_content = message
    if file_info_text:
        user_content = f"{file_info_text}\n\n{message}" if message else file_info_text
    if transcription and task == "voice":
        user_content = f"[Transcribed voice]: {transcription}\n\n{message}" if message else f"[Voice]: {transcription}"

    # ── Session history ───────────────────────────────────────────────────────
    if session_id not in _sessions:
        _sessions[session_id] = []
    history = _sessions[session_id]
    history.append({"role": "user", "content": user_content})

    # Keep last N messages
    if len(history) > settings.max_context_messages * 2:
        history = history[-(settings.max_context_messages * 2):]
        _sessions[session_id] = history

    # ── Stream response ───────────────────────────────────────────────────────
    async def event_stream():
        # First event: metadata
        meta = {
            "type": "meta",
            "agent": agent,
            "agent_desc": AGENT_DESCRIPTIONS.get(agent, ""),
            "task": task,
            "session_id": session_id,
            "transcription": transcription or "",
        }
        yield f"data: {json.dumps(meta)}\n\n"

        # Stream LLM tokens
        full_response = []
        async for token in ollama.chat_stream(
            messages=history,
            task=task,
            file_content=file_content,
            transcription=transcription,
            image_data=image_data,
        ):
            full_response.append(token)
            yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

        # Save assistant response to history
        response_text = "".join(full_response)
        history.append({"role": "assistant", "content": response_text})
        _sessions[session_id] = history

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _simple_stream(text: str):
    yield f"data: {json.dumps({'type': 'meta', 'agent': 'Harley', 'task': 'error'})}\n\n"
    yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ── Session ───────────────────────────────────────────────────────────────────
@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str, current_user: dict = Depends(get_user)):
    _sessions.pop(session_id, None)
    return {"cleared": session_id}


# ── Agents info ───────────────────────────────────────────────────────────────
@app.get("/api/agents")
async def list_agents(current_user: dict = Depends(get_user)):
    return {"agents": AGENT_DESCRIPTIONS}


# ── Models ────────────────────────────────────────────────────────────────────
@app.get("/api/models")
async def list_models(current_user: dict = Depends(get_user)):
    status_data = await ollama.health()
    return status_data
