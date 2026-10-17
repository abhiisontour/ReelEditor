#!/bin/bash
# reelkit setup: python deps, node deps (fonts + playwright-core), speech models (GitHub releases; Hugging Face is not needed).
set -e
cd "$(dirname "$0")"
MODELS=${REELKIT_MODELS:-$HOME/.cache/reelkit/models}
pip install --break-system-packages -q sherpa-onnx soundfile opencv-python-headless scipy numpy 2>&1 | grep -v -i warning || true
(cd web && [ -d node_modules ] || npm i -s --no-audit --no-fund >/dev/null)
mkdir -p "$MODELS" && cd "$MODELS"
REL=https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models
[ -d sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8 ] || curl -sSL --max-time 900 $REL/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8.tar.bz2 | tar xj
[ -d sherpa-onnx-whisper-small.en ] || curl -sSL --max-time 900 $REL/sherpa-onnx-whisper-small.en.tar.bz2 | tar xj
ls /opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell >/dev/null 2>&1 || echo "WARN: headless chromium not found; set REELKIT_CHROME"
command -v ffmpeg >/dev/null || echo "WARN: ffmpeg missing"
echo "reelkit setup ok (models in $MODELS)"
