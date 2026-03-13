"""Knowledge base — shared Redis client, async I/O.

Fixes applied vs. the AI-generated version:
  - FIX #8:  KnowledgeBase receives shared redis_client — no duplicate connection.
  - FIX #14: File read with errors='ignore'; hash also encoded with errors='ignore'.
"""
import hashlib
import random
from pathlib import Path
from typing import Optional

import aiofiles
import structlog

import redis.asyncio as aioredis

from config import settings

logger = structlog.get_logger()

_ALLOWED_EXT = {".py", ".md", ".txt", ".json", ".yaml", ".yml"}


class KnowledgeBase:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def index_file(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            return f"❌ Not found: {file_path}"
        if path.suffix not in _ALLOWED_EXT:
            return f"❌ Extension not allowed: {path.suffix}"

        # FIX #14: errors='ignore' prevents broken UTF-8 slices
        async with aiofiles.open(path, encoding="utf-8", errors="ignore") as fh:
            content = await fh.read(settings.sandbox_max_output_chars)

        if not content.strip():
            return "⚠️ File is empty"

        doc_id = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
        key = f"doc:{doc_id}"
        if await self._redis.exists(key):
            return f"✅ Already indexed: {path.name}"

        await self._redis.setex(key, 86400 * 7, f"### {path.name}\n\n{content}")
        logger.info("kb_indexed", file=path.name)
        return f"✅ Indexed: {path.name}"

    async def get_context(self, query: Optional[str] = None, limit: int = 5) -> str:
        try:
            keys = await self._redis.keys("doc:*")
            if not keys:
                return ""
            selected = random.sample(keys, min(limit, len(keys)))
            snippets = []
            for key in selected:
                val = await self._redis.get(key)
                if val:
                    body = val.split("\n\n", 1)[-1]
                    snippets.append(body[:1_000].strip())
            return "\n\n---\n\n".join(snippets)
        except Exception as exc:
            logger.error("kb_context_error", error=str(exc))
            return ""


kb: Optional[KnowledgeBase] = None
