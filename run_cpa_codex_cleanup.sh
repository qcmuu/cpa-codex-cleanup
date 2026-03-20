#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

find_python() {
  local candidates=("python3.12" "python3.11" "python3.10" "python3" "python")
  local exe version major minor

  for exe in "${candidates[@]}"; do
    if ! command -v "$exe" >/dev/null 2>&1; then
      continue
    fi

    version="$("$exe" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)"
    major="${version%%.*}"
    minor="${version##*.}"
    if [[ "$major" =~ ^[0-9]+$ ]] && [[ "$minor" =~ ^[0-9]+$ ]]; then
      if (( major > 3 || (major == 3 && minor >= 10) )); then
        echo "$exe"
        return 0
      fi
    fi
  done

  return 1
}

if ! PYTHON_BIN="$(find_python)"; then
  echo "[ERROR] Python 3.10+ not found in PATH."
  echo "Please install Python 3.10+ first."
  exit 1
fi

VENV_DIR=".venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "[INFO] Creating virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if ! python -c "import curl_cffi" >/dev/null 2>&1; then
  echo "[INFO] Installing dependency: curl_cffi"
  python -m pip install --upgrade pip
  python -m pip install curl_cffi
fi

echo "[INFO] Starting cpa-codex-cleanup Web UI..."
echo "[INFO] URL: http://127.0.0.1:8123"

if command -v open >/dev/null 2>&1; then
  open "http://127.0.0.1:8123" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:8123" >/dev/null 2>&1 || true
fi

exec python cpa_codex_cleanup_web.py --host 127.0.0.1 --port 8123