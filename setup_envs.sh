#!/usr/bin/env bash
# Creates one isolated Python 3.11 environment per model family under ./venvs (or $ASR_ENVS_DIR).
# Usage:  ./setup_envs.sh                 # all environments
#         ./setup_envs.sh nemo hf         # only these
# GPU/CPU: by default torch comes from PyPI (CUDA build on Linux x86-64, Metal/MPS on macOS).
#   CPU-only machine:      TORCH_INDEX=https://download.pytorch.org/whl/cpu   ./setup_envs.sh
#   DGX Spark (ARM, CUDA): TORCH_INDEX=https://download.pytorch.org/whl/cu130 ./setup_envs.sh
set -euo pipefail
cd "$(dirname "$0")"
ENVS_DIR="${ASR_ENVS_DIR:-$PWD/venvs}"
command -v uv >/dev/null || { echo "Installing uv..."; pip install -q uv; }
mkdir -p "$ENVS_DIR"
case "${OSTYPE:-}" in
  msys*|cygwin*) PY_REL="Scripts/python.exe" ;;   # Windows (Git Bash)
  *)             PY_REL="bin/python" ;;
esac

torch_pkgs() {   # install torch first so later packages reuse it
  local py=$1; shift
  if [ -n "${TORCH_INDEX:-}" ]; then uv pip install --python "$py" --index-url "$TORCH_INDEX" "$@"
  else uv pip install --python "$py" "$@"; fi
}

make_env() {
  local name=$1
  local py="$ENVS_DIR/$name/$PY_REL"
  echo "=== $name ==="
  [ -x "$py" ] || uv venv --python 3.11 "$ENVS_DIR/$name"
  case $name in
    nemo)     torch_pkgs "$py" torch
              uv pip install --python "$py" "nemo_toolkit[asr]" huggingface_hub soundfile ;;
    qwen)     torch_pkgs "$py" torch
              uv pip install --python "$py" qwen-asr soundfile ;;
    omni)     torch_pkgs "$py" torch
              uv pip install --python "$py" omnilingual-asr
              # torchaudio must match torch; pyarrow>=20 needs NumPy 2 but this stack pins 1.x
              tv=$("$py" -c "import torch; print(torch.__version__.split('+')[0])")
              torch_pkgs "$py" "torchaudio==$tv"
              uv pip install --python "$py" "pyarrow<20" ;;
    hf)       torch_pkgs "$py" torch
              uv pip install --python "$py" "transformers>=5.4.0" peft accelerate librosa sentencepiece protobuf soundfile numpy
              uv pip uninstall --python "$py" torchao 2>/dev/null || true   # torchao breaks peft ;;
              ;;
    whisperx) uv pip install --python "$py" whisperx soundfile ;;
    enhance)  torch_pkgs "$py" torch
              uv pip install --python "$py" clearvoice soundfile numpy ;;
    *) echo "unknown environment: $name (nemo qwen omni hf whisperx enhance)"; exit 1 ;;
  esac
  echo "=== $name ready ==="
}

ENVS=("$@")
[ ${#ENVS[@]} -eq 0 ] && ENVS=(nemo hf qwen omni whisperx enhance)
for e in "${ENVS[@]}"; do
  # A subshell outside any `if`/`||`, or bash would ignore set -e inside make_env and report a broken install as ready.
  set +e
  ( set -e; make_env "$e" )
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    rm -rf "${ENVS_DIR:?}/$e"     # a half-installed environment would show as ready in the app
    echo "!!! $e failed: the other models still work"
  fi
done
