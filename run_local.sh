#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# FinOps AI Platform — Local Development Runner
# Starts backend (port 8001) + frontend (port 3001) using local Ollama
# ─────────────────────────────────────────────────────────────
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   FinOps AI Platform — Local Development${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── Check Ollama ─────────────────────────────────────────────
echo -e "\n${YELLOW}[1/4] Checking Ollama...${NC}"
if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    MODEL_COUNT=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('models',[])))" 2>/dev/null || echo "?")
    echo -e "${GREEN}  ✅ Ollama is running ($MODEL_COUNT models available)${NC}"
else
    echo -e "${RED}  ❌ Ollama is not running. Start it with: ollama serve${NC}"
    exit 1
fi

# Check finops-aws model
if curl -s http://localhost:11434/api/tags | python3 -c "
import sys, json
models = [m['name'] for m in json.load(sys.stdin).get('models',[])]
if not any('finops-aws' in m for m in models):
    sys.exit(1)
" 2>/dev/null; then
    echo -e "${GREEN}  ✅ finops-aws model found${NC}"
else
    echo -e "${YELLOW}  ⚠️  finops-aws model not found. Creating from Modelfile...${NC}"
    ollama create finops-aws -f "$PROJECT_DIR/Modelfile" 2>/dev/null || echo -e "${RED}  Failed to create model${NC}"
fi

# ── Kill any old processes ───────────────────────────────────
echo -e "\n${YELLOW}[2/4] Cleaning up old processes...${NC}"
fuser -k 8001/tcp 2>/dev/null && echo "  Killed old backend on 8001" || true
fuser -k 3001/tcp 2>/dev/null && echo "  Killed old frontend on 3001" || true
sleep 1

# ── Start Backend ────────────────────────────────────────────
echo -e "\n${YELLOW}[3/4] Starting backend on port 8001...${NC}"
PYTHONPATH="$PROJECT_DIR" \
OLLAMA_URL="http://localhost:11434" \
FINOPS_MODEL="finops-aws" \
nohup python3 -m uvicorn src.api.main:app \
    --host 0.0.0.0 --port 8001 --reload \
    > /tmp/finops-backend.log 2>&1 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# Wait for backend health
for i in $(seq 1 15); do
    if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
        echo -e "${GREEN}  ✅ Backend ready at http://localhost:8001${NC}"
        break
    fi
    sleep 1
done

# ── Start Frontend ───────────────────────────────────────────
echo -e "\n${YELLOW}[4/4] Starting frontend on port 3001...${NC}"
cd "$PROJECT_DIR/frontend"

# Install deps if needed
if [ ! -d "node_modules" ]; then
    echo "  Installing npm dependencies..."
    npm install > /dev/null 2>&1
fi

VITE_PORT=3001 \
VITE_API_TARGET="http://localhost:8001" \
nohup npm run dev > /tmp/finops-frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

# Wait for frontend
for i in $(seq 1 15); do
    if curl -sf http://localhost:3001 > /dev/null 2>&1; then
        echo -e "${GREEN}  ✅ Frontend ready at http://localhost:3001${NC}"
        break
    fi
    sleep 1
done

# ── Summary ──────────────────────────────────────────────────
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  🚀  FinOps AI Platform is running!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Frontend  → ${GREEN}http://localhost:3001${NC}"
echo -e "  Backend   → ${GREEN}http://localhost:8001${NC}"
echo -e "  Ollama    → ${GREEN}http://localhost:11434${NC}"
echo -e "  LLM Model → finops-aws"
echo -e ""
echo -e "  Backend log:  tail -f /tmp/finops-backend.log"
echo -e "  Frontend log: tail -f /tmp/finops-frontend.log"
echo -e ""
echo -e "  Stop: ${YELLOW}kill $BACKEND_PID $FRONTEND_PID${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
