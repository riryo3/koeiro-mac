#!/bin/bash
# Build the Female DSP native library for macOS (Apple Silicon).
# Needs the Xcode command line tools (xcode-select --install).
set -euo pipefail
cd "$(dirname "$0")/.."
clang++ -std=c++17 -O2 -shared -fPIC -fvisibility=hidden -arch arm64 -DNOMINMAX \
  -Ithird_party src/processors/native/female_dsp.cpp \
  -o src/processors/native/female_dsp_arm64.dylib
echo "built src/processors/native/female_dsp_arm64.dylib"
