#!/usr/bin/env bash
# Crea el entorno e instala Unsloth (RTX 4070 = Ada, sin pasos especiales).
set -euo pipefail
python3 -m venv ~/ft
source ~/ft/bin/activate
pip install -U pip
pip install unsloth
pip install -U "huggingface_hub[cli]"
python - <<'PY'
import torch
print("torch", torch.__version__, "| CUDA", torch.version.cuda, "| GPU", torch.cuda.get_device_name(0), "| cap", torch.cuda.get_device_capability(0))
assert torch.cuda.is_available(), "PyTorch no ve la GPU"
PY
echo "Descargando modelo base (~5.5 GB)..."
huggingface-cli download unsloth/Qwen2.5-7B-Instruct-bnb-4bit
echo "LISTO. Activa el entorno con: source ~/ft/bin/activate"
