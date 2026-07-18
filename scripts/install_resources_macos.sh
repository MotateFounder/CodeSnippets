#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
DOWNLOADS_DIR="$REPO_ROOT/downloads"
LLAMA_DIR="$REPO_ROOT/src/assets/LlamaCPP"
MODELS_DIR="$REPO_ROOT/src/assets/llmmodels"
REPOLENS_DIR="$REPO_ROOT/src/services/repoLens"

LLAMACPP_ZIP_URL="${LLAMACPP_ZIP_URL:-}"
REPOLENS_ZIP_URL="${REPOLENS_ZIP_URL:-}"
REPOLENS_BIN_URL="${REPOLENS_BIN_URL:-${REPOLENS_EXE_URL:-}}"
MODEL_URL="${MODEL_URL:-}"

mkdir -p "$DOWNLOADS_DIR" "$LLAMA_DIR" "$MODELS_DIR" "$REPOLENS_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Python 3 was not found. Installing Python with Homebrew..."
    brew install python
  else
    echo "Python 3 is required. Install Python from https://www.python.org/downloads/macos/ or Homebrew."
    exit 1
  fi
fi

python3 - <<'PY'
import tkinter
print("Tkinter is available.")
PY

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$REPO_ROOT/requirements.txt"

download() {
  local url="$1"
  local dest="$2"
  if [ -z "$url" ]; then
    return 1
  fi
  echo "Downloading $url"
  curl -L "$url" -o "$dest"
}

if download "$LLAMACPP_ZIP_URL" "$DOWNLOADS_DIR/llamacpp.zip"; then
  python3 -m zipfile -e "$DOWNLOADS_DIR/llamacpp.zip" "$LLAMA_DIR"
fi

if download "$REPOLENS_ZIP_URL" "$DOWNLOADS_DIR/repolens.zip"; then
  python3 -m zipfile -e "$DOWNLOADS_DIR/repolens.zip" "$REPOLENS_DIR"
fi

if download "$REPOLENS_BIN_URL" "$REPOLENS_DIR/repolens"; then
  chmod +x "$REPOLENS_DIR/repolens"
fi

if [ -n "$MODEL_URL" ]; then
  MODEL_NAME="$(basename "${MODEL_URL%%\?*}")"
  [ -n "$MODEL_NAME" ] || MODEL_NAME="model.gguf"
  download "$MODEL_URL" "$MODELS_DIR/$MODEL_NAME" || true
fi

echo
echo "CodeSnippets resources are ready."
echo "Run with: $VENV_DIR/bin/python $REPO_ROOT/app.py"
echo
echo "Optional downloads can be supplied with environment variables:"
echo "  LLAMACPP_ZIP_URL, REPOLENS_ZIP_URL or REPOLENS_BIN_URL, MODEL_URL"
