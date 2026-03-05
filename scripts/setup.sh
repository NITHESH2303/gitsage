#!/usr/bin/env bash
set -euo pipefail

MODELS_DIR="$HOME/models"
MODEL_FILENAME="SmolLM2-1.7B-Instruct-Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/bartowski/SmolLM2-1.7B-Instruct-GGUF/resolve/main/SmolLM2-1.7B-Instruct-Q4_K_M.gguf"
MODEL_PATH="$MODELS_DIR/$MODEL_FILENAME"
MODELFILE_PATH="$(cd "$(dirname "$0")/.." && pwd)/ollama/Modelfile"

echo "======================================================="
echo "  gitsage setup"
echo "======================================================="

if command -v ollama &>/dev/null; then
    echo "[OK] Ollama already installed: $(ollama --version 2>&1 | head -1)"
else
    echo "[STEP 1] Installing Ollama via Homebrew..."
    if ! command -v brew &>/dev/null; then
        echo "[ERROR] Homebrew not found. Install it first: https://brew.sh"
        exit 1
    fi
    brew install --cask ollama
    echo "[OK] Ollama installed."
fi

mkdir -p "$MODELS_DIR"

if [[ -f "$MODEL_PATH" ]]; then
    echo "[OK] Model already exists at $MODEL_PATH — skipping download."
else
    echo ""
    echo "[STEP 2] Downloading $MODEL_FILENAME (~1.1 GB)..."
    curl -L --progress-bar -o "$MODEL_PATH" "$MODEL_URL"
    echo "[OK] Download complete."
fi

echo ""
echo "[STEP 3] Patching Modelfile FROM path to: $MODEL_PATH"
sed "s|FROM .*|FROM $MODEL_PATH|" "$MODELFILE_PATH" > /tmp/Modelfile.patched
cp /tmp/Modelfile.patched "$MODELFILE_PATH"
echo "[OK] Modelfile updated."

if pgrep -x ollama &>/dev/null; then
    echo "[OK] Ollama server already running."
else
    echo ""
    echo "[STEP 4] Starting Ollama server in background..."
    ollama serve &>/tmp/ollama.log &
    sleep 3
    echo "[OK] Ollama server started (logs: /tmp/ollama.log)."
fi

echo ""
echo "[STEP 5] Creating 'gitsage' model from Modelfile..."
ollama create gitsage -f "$MODELFILE_PATH"
echo "[OK] Model 'gitsage' created."

echo ""
echo "[STEP 6] Smoke test..."
RESPONSE=$(curl -s -X POST http://localhost:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{"model":"gitsage","prompt":"Reply with exactly: READY","stream":false}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','').strip())")

echo "  Model response: $RESPONSE"

echo ""
echo "======================================================="
echo "  Setup complete!"
echo ""
echo "  Quick start (after pip install -e .):"
echo "    gitsage commit --stage --commit --push"
echo "    git log -5 --oneline | gitsage pr"
echo "======================================================="
