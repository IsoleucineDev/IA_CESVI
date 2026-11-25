#!/usr/bin/env python3
"""Genera el Modelfile de Ollama con el MISMO system prompt usado en el entrenamiento."""
import sys
from gen_dataset import SYSTEM_PROMPT

gguf = sys.argv[1] if len(sys.argv) > 1 else "gguf/cesvi-q4_k_m.gguf"
mf = f'''FROM ./{gguf}

TEMPLATE """{{{{ if .System }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
{{{{ end }}}}{{{{ range .Messages }}}}{{{{ if eq .Role "user" }}}}<|im_start|>user
{{{{ .Content }}}}<|im_end|>
{{{{ else if eq .Role "assistant" }}}}<|im_start|>assistant
{{{{ .Content }}}}<|im_end|>
{{{{ end }}}}{{{{ end }}}}<|im_start|>assistant
"""

SYSTEM """{SYSTEM_PROMPT}"""

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.0
PARAMETER num_ctx 8192
PARAMETER num_predict 4096
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"
'''
open("Modelfile", "w", encoding="utf-8").write(mf)
print("Modelfile escrito. Siguiente: ollama create cesvi-json -f Modelfile")
