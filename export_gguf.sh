#!/usr/bin/env bash
# Fusionado 16-bit -> GGUF f16 -> Q4_K_M con llama.cpp. Uso: bash export_gguf.sh [merged_dir] [out_dir]
set -euo pipefail
MERGED=${1:-outputs/merged_16bit}
OUT=${2:-gguf}
mkdir -p "$OUT"
[ -d llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp
# Solo se compila 'llama-quantize' (CPU, sin CUDA, sin libcurl): rápido y con pocas dependencias
cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=OFF -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build llama.cpp/build --config Release -j"$(nproc)" --target llama-quantize
pip install -q gguf sentencepiece protobuf
python llama.cpp/convert_hf_to_gguf.py "$MERGED" --outtype f16 --outfile "$OUT/cesvi-f16.gguf"
llama.cpp/build/bin/llama-quantize "$OUT/cesvi-f16.gguf" "$OUT/cesvi-q4_k_m.gguf" Q4_K_M
# Opcional (más calidad, ~5.4 GB; cabe en una 3060 de 12 GB):
# llama.cpp/build/bin/llama-quantize "$OUT/cesvi-f16.gguf" "$OUT/cesvi-q5_k_m.gguf" Q5_K_M
python make_modelfile.py "$OUT/cesvi-q4_k_m.gguf"
ls -lh "$OUT"
