# MOLL-COD v21.2-SXX

**Production Multi-Agent AI Platform**  
FastAPI + Gradio + Redis TLS + RestrictedPython Sandbox + Self-Improve

> ✅ All 17 bugs fixed | One-command deploy | Production-ready

---

## Quick Start

```bash
chmod +x deploy.sh
./deploy.sh
```

The script auto-generates TLS certs, random secrets, builds Docker image, and waits for health.

| Endpoint | URL |
|---|---|
| 🖥️ Gradio UI | http://localhost:7860 |
| 🌐 REST API | http://localhost:8000 |
| 📊 Metrics | http://localhost:8000/metrics |
| ❤️ Health | http://localhost:8000/health |

**Default credentials** (change in production via `USERS_DB` or secrets):  
`admin / ChangeMe123!` · `user / UserPass456!`

---

## Chat Commands

| Command | Action |
|---|---|
| `help` | Show all commands |
| `switch to CodeMaster` | Activate an agent |
| `code: print("hello")` | Run Python in sandbox |
| `self improve: hint text` | Trigger self-improvement |
| `update` | Apply auto-update (if configured) |

---

## Architecture

```
config.py        Centralized pydantic-settings
middleware.py    JWT auth (jose), bcrypt, slowapi rate limiting, CORS
core.py          Agents, lazy Redis init, async auto-update (httpx)
executor.py      RestrictedPython sandbox with stdout capture
kb.py            Redis-backed knowledge base
self_improve.py  Async self-improve with syntax validation
ui.py            FastAPI + Gradio (async callbacks)
app.py           Lifespan manager, uvicorn entry point
```

---

## All 17 Bugs Fixed

| # | Severity | File | Fix |
|---|---|---|---|
| 1 | 🔴 CRITICAL | core.py | Redis password: try/except + env fallback |
| 2 | 🔴 CRITICAL | core.py | Lazy Redis init in lifespan, not module level |
| 3 | 🔴 CRITICAL | ui.py | flask-talisman → starlette SecurityHeadersMiddleware |
| 4 | 🔴 CRITICAL | ui.py | Passwords → bcrypt hashes (passlib) |
| 5 | 🔴 CRITICAL | executor.py | stdout captured via io.StringIO, never leaks |
| 6 | 🟠 HIGH | ui.py | Gradio callbacks → async def, no asyncio.run() |
| 7 | 🟠 HIGH | self_improve.py | model_dump() / Agent(**v) type-safe round-trip |
| 8 | 🟠 HIGH | kb.py | Shared Redis client injected, no duplication |
| 9 | 🟠 HIGH | core.py | Staged file copy + syntax validation before overwrite |
| 10 | 🟠 HIGH | docker-compose.yml | Unified secrets only, no env/secrets conflict |
| 11 | 🟡 MED | ui.py | Command whitelist + slowapi rate limiting |
| 12 | 🟡 MED | config.py | static_dir created on import + Dockerfile mkdir |
| 13 | 🟡 MED | core.py | httpx.AsyncClient replaces sync requests.get |
| 14 | 🟡 MED | kb.py | UTF-8 read with errors='ignore' |
| 15 | 🟢 LOW | requirements.txt | flask-talisman removed |
| 16 | 🟢 LOW | docker-compose.yml | Deprecated version: key removed |
| 17 | 🟢 LOW | core.py | retry_on_timeout + health_check_interval on Redis |

Plus additional bugs fixed from the AI-generated code:
- `create_access_token( dict, ...)` broken signature → `(data: dict, ...)`
- `if "created_at" not in` missing colon and body → fixed
- Bare `if` in get_agents with no condition → `if raw:`
- `asyncio.run(self_improve())` in Gradio lambda → proper async handler
- `@app.on_event("startup")` deprecated → lifespan context
- Import order in executor.py caused NameError → fixed
- `io.TextIOWrapper(io.BytesIO())` in _run() caused TypeError → removed

---

## License

MIT — see LICENSE
