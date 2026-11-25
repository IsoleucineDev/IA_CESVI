#!/usr/bin/env bash
# Diagnóstico del equipo (Linux / WSL2). Solo lee, no instala nada.
echo "== GPU =="; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || echo "NO HAY nvidia-smi"
echo "== Sistema =="; (lsb_release -ds 2>/dev/null || uname -a); echo "RAM:"; free -g | awk 'NR==2{print $2" GB total, "$7" GB disponibles"}'
echo "== Disco libre en este directorio =="; df -h . | awk 'NR==2{print $4" libres"}'
echo "== Herramientas =="
for c in python3 git cmake gcc g++ make curl; do
  if command -v $c >/dev/null; then echo "OK   $c: $($c --version 2>&1 | head -n1)"; else echo "FALTA $c"; fi
done
python3 -c "import venv" 2>/dev/null && echo "OK   python3-venv" || echo "FALTA python3-venv (sudo apt install python3-venv)"
echo "== Red (el firewall de la escuela puede bloquear) =="
for u in https://huggingface.co https://pypi.org https://download.pytorch.org https://github.com; do
  code=$(curl -s -o /dev/null -m 8 -w "%{http_code}" -I $u); echo "$u -> $code"
done
