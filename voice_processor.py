"""Voice/audio processing via OpenAI Whisper (local, offline).

Runs entirely locally — no API calls.
Model is loaded once and cached in memory.
"""

import io
import tempfile
import os
from pathlib import Path
from typing import Optional

import structlog

from config import settings

logger = structlog.get_logger()

_whisper_model = None


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
            logger.info("whisper_loading", model=settings.whisper_model)
            _whisper_model = whisper.load_model(settings.whisper_model)
            logger.info("whisper_ready", model=settings.whisper_model)
        except Exception as e:
            logger.error("whisper_load_failed", error=str(e))
            raise RuntimeError(f"Whisper failed to load: {e}")
    return _whisper_model


async def transcribe_audio(audio_data: bytes, filename: str = "audio.webm") -> dict:
    """Transcribe audio bytes using Whisper. Returns dict with text, language, segments."""
    try:
        model = _get_model()

        ext = Path(filename).suffix.lower() or ".webm"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        try:
            result = model.transcribe(
                tmp_path,
                task="transcribe",
                verbose=False,
                fp16=False,
            )
        finally:
            os.unlink(tmp_path)

        text = result.get("text", "").strip()
        language = result.get("language", "unknown")
        segments = result.get("segments", [])

        logger.info("transcription_done", chars=len(text), language=language)
        return {
            "text": text,
            "language": language,
            "duration_seconds": segments[-1]["end"] if segments else 0,
            "word_count": len(text.split()),
            "success": True,
        }

    except Exception as e:
        logger.error("transcription_failed", error=str(e))
        return {
            "text": "",
            "language": "unknown",
            "duration_seconds": 0,
            "word_count": 0,
            "success": False,
            "error": str(e),
        }


async def convert_audio(audio_data: bytes, source_ext: str) -> Optional[bytes]:
    """Convert audio to WAV for Whisper compatibility if needed."""
    if source_ext in (".wav",):
        return audio_data
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(io.BytesIO(audio_data))
        buf = io.BytesIO()
        audio.export(buf, format="wav")
        return buf.getvalue()
    except Exception as e:
        logger.warning("audio_conversion_skipped", error=str(e))
        return audio_data  # try anyway
