"""Core: agents, lazy Redis init, async auto-update.

Fixes applied vs. the AI-generated version:
  - BUGFIX: `if "created_at" not in` had no body — fixed to `if "created_at" not in data:`
  - BUGFIX: `if` block in get_agents had no condition — fixed to `if data:`
  - FIX #1:  Redis password read in lifespan, not at module level.
  - FIX #2:  Lazy Redis init via init_core() with tenacity retry.
  - FIX #9:  auto_update stages file, validates syntax before overwrite.
  - FIX #13: httpx.AsyncClient replaces sync requests.get.
  - FIX #17: retry_on_timeout + health_check_interval on Redis client.
"""
import hashlib
import json
import os
import shutil
from datetime import datetime
from typing import Dict, Optional

import aiofiles
import httpx
import structlog
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

import redis.asyncio as aioredis

from config import settings

# ── Logging ───────────────────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.WriteLoggerFactory(
        file=settings.logs_dir / "moll-cod.log"
    ),
)
logger = structlog.get_logger()


# ── Agent model ───────────────────────────────────────────────────────────────

class Agent(BaseModel):
    name: str
    role: str
    model: str = "llama3.2"
    created_at: str = ""

    def __init__(self, **data):
        # BUGFIX: original code had `if "created_at" not in` with no body/colon
        if not data.get("created_at"):
            data["created_at"] = datetime.utcnow().isoformat()
        super().__init__(**data)


# ── Agent manager ─────────────────────────────────────────────────────────────

class AgentManager:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_agents(self) -> Dict[str, Agent]:
        try:
            raw = await self.redis.get("agents:state")
            # BUGFIX: original had bare `if` with no condition
            if raw:
                return {k: Agent(**v) for k, v in json.loads(raw).items()}

            defaults: Dict[str, Agent] = {
                "Kernel":     Agent(name="Kernel",     role="Main Kernel"),
                "CodeMaster": Agent(name="CodeMaster", role="Code Expert"),
                "Evolution":  Agent(name="Evolution",  role="Self-Improve"),
            }
            payload = json.dumps({k: v.model_dump() for k, v in defaults.items()})
            await self.redis.setex("agents:state", 86400 * 30, payload)
            return defaults
        except Exception as exc:
            logger.error("agents_fetch_error", error=str(exc))
            return {}

    async def get_active(self) -> str:
        val = await self.redis.get("active:agent")
        return val or "Kernel"

    async def set_active(self, name: str) -> None:
        await self.redis.setex("active:agent", 3600, name)


# ── Singletons ────────────────────────────────────────────────────────────────

redis_client: Optional[aioredis.Redis] = None
agent_mgr: Optional[AgentManager] = None


async def init_core() -> None:
    """Lazily initialise Redis + AgentManager inside lifespan. FIX #1 #2 #17."""
    global redis_client, agent_mgr

    password: Optional[str] = None
    try:
        if settings.redis_password_file.exists():
            password = settings.redis_password_file.read_text().strip()
        else:
            password = os.getenv("REDIS_PASSWORD")
    except OSError as exc:
        logger.warning("redis_password_read_error", error=str(exc))
        password = os.getenv("REDIS_PASSWORD")

    ssl_ca = str(settings.redis_ssl_ca) if settings.redis_ssl_ca.exists() else None

    redis_client = aioredis.from_url(
        str(settings.redis_url),
        password=password,
        ssl=True,
        ssl_ca_certs=ssl_ca,
        decode_responses=True,
        socket_timeout=5,
        retry_on_timeout=True,       # FIX #17
        health_check_interval=30,    # FIX #17
    )
    await redis_client.ping()
    agent_mgr = AgentManager(redis_client)
    logger.info("core_initialized")


async def shutdown_core() -> None:
    if redis_client:
        await redis_client.aclose()
    logger.info("core_shutdown")


# ── Auto-update ───────────────────────────────────────────────────────────────

async def auto_update(url: str, expected_sha256: str) -> str:
    """Download → verify SHA256 → validate syntax → staged copy. FIX #9 #13."""
    if not url or not expected_sha256:
        return "❌ update_url / expected_sha256 not configured"
    try:
        logger.info("update_started", url=url)
        # FIX #13: async httpx, not sync requests
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return f"❌ HTTP {resp.status_code}"

        content: bytes = resp.content
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            logger.error("update_sha256_mismatch")
            return "❌ SHA256 mismatch — update aborted"

        try:
            compile(content, "<update>", "exec")
        except SyntaxError as exc:
            return f"❌ Syntax error at line {exc.lineno}: {exc.msg}"

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        staged = settings.updates_dir / f"update_{ts}.py"
        backup = settings.versions_dir / f"backup_{ts}.py"
        app_path = settings.base_dir / "app.py"

        async with aiofiles.open(staged, "wb") as fh:
            await fh.write(content)
        if app_path.exists():
            shutil.copy2(app_path, backup)
        shutil.copy2(staged, app_path)   # FIX #9: staged copy

        logger.info("update_applied", ts=ts)
        return f"✅ Update applied\n💾 Backup: {backup.name}\n📦 Version: {ts}"
    except Exception as exc:
        logger.error("update_failed", error=str(exc))
        return f"❌ {type(exc).__name__}: {exc}"
