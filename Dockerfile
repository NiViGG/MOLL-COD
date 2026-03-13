FROM python:3.12-slim

# System deps for audio/file processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl openssl ffmpeg libmagic1 \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 aiuser
WORKDIR /app

RUN mkdir -p /app/{certs,secrets,knowledge,logs,versions,updates,static,uploads} \
    && chown -R aiuser:aiuser /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Whisper model during build
RUN python -c "import whisper; whisper.load_model('base')" || true

COPY --chown=aiuser:aiuser . .

USER aiuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "app.py"]
