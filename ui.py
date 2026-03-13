"""FastAPI + Gradio UI — all UI/auth bugs fixed.

Fixes applied vs. the AI-generated version:
  - FIX #3:  flask-talisman → starlette SecurityHeadersMiddleware.
  - FIX #4:  Passwords as bcrypt hashes via get_password_hash().
  - FIX #6:  All Gradio callbacks are async def — no asyncio.run() calls.
  - FIX #11: Command whitelist; raw shell strings rejected.
  - FIX #12: static_dir guaranteed by config.py on import.
  - BUGFIX:  `improve_btn.click(lambda: asyncio.run(...))` → proper async handler.
  - BUGFIX:  `@app.on_event("startup")` deprecated — replaced with lifespan in app.py.
  - BUGFIX:  `kb` global now injected after init_core() in app.py lifespan.
"""
from __future__ import annotations

import structlog
import gradio as gr
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.security import SecurityHeadersMiddleware

from config import settings
from core import agent_mgr, auto_update
from executor import executor
from middleware import (
    create_access_token,
    get_password_hash,
    limiter,
    setup_security_middleware,
    verify_password,
    verify_token,
)
from self_improve import self_improve

logger = structlog.get_logger()

# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title=settings.app_name, version=settings.version)
setup_security_middleware(app)
app.add_middleware(SecurityHeadersMiddleware)   # FIX #3
Instrumentator().instrument(app).expose(app)

# FIX #12: static_dir created by config.py
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

security = HTTPBearer(auto_error=False)

# FIX #4: bcrypt hashes — override via secrets/env in production
USERS_DB: dict[str, dict] = {
    "admin": {"hash": get_password_hash("ChangeMe123!"), "role": "admin"},
    "user":  {"hash": get_password_hash("UserPass456!"), "role": "user"},
}

_ALLOWED_CMDS = {"switch to", "code:", "self improve", "evolve", "update", "help"}


# ── Auth ──────────────────────────────────────────────────────────────────────

async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token required")
    payload = verify_token(creds.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    username = payload.get("sub", "")
    if username not in USERS_DB:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return {"username": username, "role": USERS_DB[username]["role"]}


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    from core import redis_client
    try:
        await redis_client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {
        "status": "healthy" if redis_ok else "degraded",
        "version": settings.version,
        "redis": "ok" if redis_ok else "error",
    }


@app.post("/api/login")
@limiter.limit("5/minute")
async def login(request: Request, username: str, password: str):
    user = USERS_DB.get(username)
    if not user or not verify_password(password, user["hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_access_token({"sub": username, "role": user["role"]})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/agents")
async def list_agents(current_user: dict = Depends(get_current_user)):
    agents = await agent_mgr.get_agents()
    return {"agents": {k: v.model_dump() for k, v in agents.items()}}


# ── Gradio message handler ────────────────────────────────────────────────────

async def handle_message(text: str, history: list) -> tuple[str, list]:
    """FIX #6: proper async def — no asyncio.run() anywhere."""
    if not text.strip():
        return "", history

    txt = text.lower().strip()

    # FIX #11: reject unrecognised slash-commands
    if txt.startswith("/") and not any(c in txt for c in _ALLOWED_CMDS):
        history.append([text, "❌ Unknown command. Type `help` for options."])
        return "", history

    if "switch to" in txt:
        agents = await agent_mgr.get_agents()
        for name in agents:
            if name.lower() in txt:
                await agent_mgr.set_active(name)
                history.append([text, f"✅ Active agent: **{name}**"])
                return "", history
        history.append([text, "❌ Agent not found"])
        return "", history

    if txt.startswith("code:"):
        code = text.split("code:", 1)[1].strip()
        result = executor.execute(code)
        history.append([text, result])
        return "", history

    if any(kw in txt for kw in ("self improve", "evolve")):
        hint = text.split(":", 1)[1].strip() if ":" in text else text
        result = await self_improve(improvement_hint=hint)
        history.append([text, result])
        return "", history

    if "update" in txt:
        result = await auto_update(settings.update_url, settings.update_expected_sha256)
        history.append([text, result])
        return "", history

    if "help" in txt:
        msg = (
            "**Available commands:**\n"
            "- `switch to <AgentName>` — activate agent\n"
            "- `code: <python>` — run in sandbox\n"
            "- `self improve [: hint]` — trigger self-improve\n"
            "- `update` — apply auto-update\n"
            "- `help` — this message"
        )
        history.append([text, msg])
        return "", history

    active = await agent_mgr.get_active()
    history.append([text, f"[{active}] Received: {text}"])
    return "", history


async def handle_upload(files) -> str:
    from kb import kb
    if kb is None:
        return "❌ KB not initialized"
    results = [await kb.index_file(f.name) for f in (files or [])]
    return "\n".join(results) if results else "No files uploaded"


async def handle_improve(_) -> str:
    """FIX: was asyncio.run(self_improve()) — now proper async."""
    return await self_improve()


# ── Gradio UI ─────────────────────────────────────────────────────────────────

def build_gradio_app() -> gr.Blocks:
    with gr.Blocks(
        title=f"{settings.app_name} v{settings.version}",
        theme=gr.themes.Soft(),
    ) as demo:
        gr.Markdown(f"# 🤖 {settings.app_name} `v{settings.version}`")
        gr.Markdown("Multi-agent AI platform | Type `help` for commands")

        with gr.Row():
            with gr.Column(scale=4):
                chatbot = gr.Chatbot(height=520, label="Chat")
                with gr.Row():
                    msg_in = gr.Textbox(
                        placeholder="code: print('hello')  |  switch to CodeMaster  |  help",
                        label="",
                        lines=1,
                        scale=5,
                    )
                    send_btn = gr.Button("Send ▶", variant="primary", scale=1)
                clear_btn = gr.Button("Clear 🗑", size="sm")

            with gr.Column(scale=1):
                gr.Markdown("### Tools")
                improve_btn = gr.Button("🔄 Self-Improve", variant="secondary")
                improve_out = gr.Textbox(label="Result", lines=4)
                upload = gr.File(label="📎 Upload to KB", file_count="multiple")
                upload_out = gr.Textbox(label="KB Result", lines=3)

        send_btn.click(handle_message, [msg_in, chatbot], [msg_in, chatbot])
        msg_in.submit(handle_message, [msg_in, chatbot], [msg_in, chatbot])
        clear_btn.click(lambda: ([], ""), outputs=[chatbot, msg_in])
        improve_btn.click(handle_improve, [improve_btn], [improve_out])
        upload.upload(handle_upload, [upload], [upload_out])

    return demo


gradio_ui = build_gradio_app()
app = gr.mount_gradio_app(app, gradio_ui, path="/")
