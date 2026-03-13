"""Async-safe self-improve with syntax validation.

Fixes applied vs. the AI-generated version:
  - FIX #7:  agents round-trip via model_dump() / Agent(**v) — types preserved.
  - BUGFIX:  asyncio.run(self_improve()) in UI lambda replaced with proper async call.
"""
import json
from datetime import datetime
from typing import Optional

import aiofiles
import structlog

from config import settings

logger = structlog.get_logger()


async def self_improve(
    current_code: Optional[str] = None,
    improvement_hint: str = "",
) -> str:
    try:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        app_path = settings.base_dir / "app.py"
        backup_path = settings.versions_dir / f"backup_{ts}.py"
        new_path = settings.versions_dir / f"MOLL-COD-{ts}.py"

        if current_code is None:
            if not app_path.exists():
                return "❌ app.py not found"
            async with aiofiles.open(app_path, encoding="utf-8") as fh:
                current_code = await fh.read()

        async with aiofiles.open(backup_path, "w", encoding="utf-8") as fh:
            await fh.write(current_code)

        hint_safe = improvement_hint[:100].replace("\n", " ")
        improved = current_code + f"\n# [Self-Improved {ts}] hint={hint_safe!r}\n"

        try:
            compile(improved, "<self_improved>", "exec")
        except SyntaxError as exc:
            return f"❌ Syntax error at line {exc.lineno}: {exc.msg}"

        async with aiofiles.open(new_path, "w", encoding="utf-8") as fh:
            await fh.write(improved)

        # FIX #7: import here to avoid circular import; use model_dump round-trip
        from core import Agent, agent_mgr
        if agent_mgr is not None:
            agents = await agent_mgr.get_agents()
            evo = f"Evo_{ts}"
            agents[evo] = Agent(name=evo, role="AutoEvolved")
            payload = json.dumps({k: v.model_dump() for k, v in agents.items()})
            await agent_mgr.redis.setex("agents:state", 86400 * 30, payload)

        logger.info("self_improve_done", ts=ts)
        return (
            f"✅ Self-improve completed\n"
            f"📦 Version: {new_path.name}\n"
            f"💾 Backup:  {backup_path.name}"
        )
    except Exception as exc:
        logger.error("self_improve_failed", error=str(exc))
        return f"❌ {type(exc).__name__}: {exc}"
