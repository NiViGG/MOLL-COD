#!/usr/bin/env bash
# HARLEY-AI — One-command deploy
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

echo ""
echo -e "${RED}  ██╗  ██╗ █████╗ ██████╗ ██╗     ███████╗██╗   ██╗${NC}"
echo -e "${RED}  ██║  ██║██╔══██╗██╔══██╗██║     ██╔════╝╚██╗ ██╔╝${NC}"
echo -e "${RED}  ███████║███████║██████╔╝██║     █████╗   ╚████╔╝ ${NC}"
echo -e "${RED}  ██╔══██║██╔══██║██╔══██╗██║     ██╔══╝    ╚██╔╝  ${NC}"
echo -e "${RED}  ██║  ██║██║  ██║██║  ██║███████╗███████╗   ██║   ${NC}"
echo -e "${RED}  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝  ${NC}"
echo -e "                    ${YELLOW}AI · Dr. Quinzel Edition${NC}"
echo ""

command -v docker >/dev/null || die "Docker not found. Install it first!"

# Check Docker Compose
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif docker-compose version >/dev/null 2>&1; then
    DC="docker-compose"
else
    die "Docker Compose not found!"
fi

# ── Directories ───────────────────────────────────────────────────────────────
for d in knowledge logs versions updates static secrets; do mkdir -p "$d"; done
log "Directories ready"

# ── .env ──────────────────────────────────────────────────────────────────────
[[ -f .env ]] || cp .env.example .env 2>/dev/null || true

# ── Check GPU ─────────────────────────────────────────────────────────────────
if command -v nvidia-smi >/dev/null 2>&1; then
    info "NVIDIA GPU detected! Edit docker-compose.yml to enable GPU for Ollama (see comments)"
fi

# ── Build ─────────────────────────────────────────────────────────────────────
log "Building Harley-AI image..."
$DC build

# ── Start ─────────────────────────────────────────────────────────────────────
log "Starting services (Ollama + Redis + App)..."
$DC up -d ollama redis

info "Waiting for Ollama to start (this may take a minute on first run)..."
for i in {1..40}; do
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        log "Ollama is up!"
        break
    fi
    sleep 3
    echo -n "."
done
echo ""

info "Pulling llama3.2 model (first run: ~2GB download)..."
curl -s http://localhost:11434/api/pull -d '{"name":"llama3.2","stream":false}' | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print('Model:', d.get('status','done'))" 2>/dev/null || \
    warn "Model pull may still be in progress"

log "Starting Harley app..."
$DC up -d app

log "Waiting for app health check..."
for i in {1..20}; do
    if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
        echo ""
        log "✅ HARLEY-AI is ALIVE and DANGEROUS!"
        echo ""
        echo -e "  ${RED}🔨 UI:      ${NC}http://localhost:8000"
        echo -e "  ${CYAN}🧠 API:     ${NC}http://localhost:8000/api/health"
        echo -e "  ${YELLOW}🤖 Ollama:  ${NC}http://localhost:11434"
        echo ""
        echo -e "  ${GREEN}Login:${NC} admin / HarleyQ!2026"
        echo -e "  ${GREEN}      ${NC} user  / puddin123"
        echo ""
        echo -e "  ${YELLOW}Logs:${NC} $DC logs -f app"
        echo ""
        exit 0
    fi
    sleep 3
    echo -n "."
done
echo ""
warn "App didn't respond in time. Check logs: $DC logs app"
