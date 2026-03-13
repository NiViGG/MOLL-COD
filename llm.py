"""Ollama LLM client — streaming + vision + embeddings.

Auto-detects available models and falls back gracefully.
Handles image input for llava/llava-phi3 vision models.
"""

import base64
import json
from typing import AsyncGenerator, Optional

import httpx
import structlog

from config import settings
from harley import HARLEY_SYSTEM_PROMPT, build_context_prompt

logger = structlog.get_logger()


class OllamaClient:
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self._available_models: list[str] = []

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                if r.status_code == 200:
                    data = r.json()
                    models = [m["name"] for m in data.get("models", [])]
                    self._available_models = models
                    return {"online": True, "models": models}
        except Exception as e:
            logger.warning("ollama_offline", error=str(e))
        return {"online": False, "models": []}

    def _pick_model(self, prefer_vision: bool = False) -> str:
        if not self._available_models:
            return settings.ollama_model
        if prefer_vision:
            for m in self._available_models:
                if "llava" in m or "vision" in m or "phi" in m:
                    return m
        for m in self._available_models:
            if "llama" in m or "mistral" in m or "qwen" in m or "gemma" in m:
                return m
        return self._available_models[0] if self._available_models else settings.ollama_model

    async def chat_stream(
        self,
        messages: list[dict],
        task: str = "default",
        file_content: Optional[str] = None,
        transcription: Optional[str] = None,
        image_data: Optional[bytes] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response token by token."""

        # Build system prompt
        extra = build_context_prompt(task, file_content, transcription)
        system = HARLEY_SYSTEM_PROMPT + ("\n\n" + extra if extra else "")

        use_vision = image_data is not None
        model = self._pick_model(prefer_vision=use_vision)

        # Prepare messages for Ollama
        ollama_messages = [{"role": "system", "content": system}]

        for m in messages[-(settings.max_context_messages):]:
            msg = {"role": m["role"], "content": m["content"]}
            ollama_messages.append(msg)

        # Inject image into last user message if present
        if use_vision and ollama_messages[-1]["role"] == "user":
            img_b64 = base64.b64encode(image_data).decode()
            ollama_messages[-1]["images"] = [img_b64]

        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": 0.85,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
                "num_predict": 2048,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        yield f"[Ollama error {resp.status_code}]"
                        return
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if chunk.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue

        except httpx.ConnectError:
            yield (
                "Ugh, my brain's disconnected, Puddin'! 💥 "
                "Ollama ain't running. Start it with: `docker compose up ollama -d`"
            )
        except Exception as e:
            logger.error("ollama_stream_error", error=str(e))
            yield f"Welp! Something exploded: {type(e).__name__} — {e}"

    async def embed(self, text: str) -> Optional[list[float]]:
        """Generate embeddings for semantic search."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": settings.ollama_embed_model, "prompt": text},
                )
                if r.status_code == 200:
                    return r.json().get("embedding")
        except Exception as e:
            logger.warning("embed_failed", error=str(e))
        return None

    async def ensure_models(self) -> list[str]:
        """Pull required models if not present."""
        status = await self.health()
        if not status["online"]:
            return []

        needed = [settings.ollama_model]
        if settings.whisper_model:
            pass  # whisper is separate

        pulled = []
        for model in needed:
            if not any(model in m for m in status["models"]):
                logger.info("ollama_pulling_model", model=model)
                try:
                    async with httpx.AsyncClient(timeout=600) as client:
                        async with client.stream(
                            "POST",
                            f"{self.base_url}/api/pull",
                            json={"name": model, "stream": True},
                        ) as resp:
                            async for line in resp.aiter_lines():
                                if line:
                                    try:
                                        d = json.loads(line)
                                        if d.get("status") == "success":
                                            pulled.append(model)
                                    except Exception:
                                        pass
                except Exception as e:
                    logger.error("model_pull_failed", model=model, error=str(e))
        return pulled


ollama = OllamaClient()
