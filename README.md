# Qué hay que descargar e instalar (PC del laboratorio, RTX 4070)

Los tamaños salen del documento `docs/CONTEXTO_FINETUNE.md`. Son aproximados.

## 1. Antes de empezar (una sola vez por PC)

| Qué | Para qué | Cómo saber si ya lo tienes |
|---|---|---|
| Driver NVIDIA 550 o superior | Que la GPU funcione con PyTorch. No hace falta instalar CUDA Toolkit | `nvidia-smi` en Git Bash o PowerShell |
| Git para Windows (incluye Git Bash) | Clonar el repo y correr el script | `git --version` |
| WSL2 con Ubuntu | El entrenamiento corre en Linux. Instalarlo requiere permisos de administrador y reiniciar | `wsl -l -q` en PowerShell |

Si falta WSL2, en PowerShell como administrador: `wsl --install -d Ubuntu`, y reinicia.

## 2. Lo que instala `instalar_cesvi.sh` (dentro de Ubuntu)

Paquetes del sistema, con `apt`: `build-essential`, `cmake`, `git`, `curl`, `python3`, `python3-venv`, `python3-pip`. Python debe ser 3.10 a 3.12.

## 3. Lo que se descarga de internet

| Qué | Tamaño aprox. | De dónde |
|---|---|---|
| Entorno Python (`~/ft`: PyTorch, Unsloth y dependencias) | ~10 GB | pypi.org, download.pytorch.org |
| Modelo base `unsloth/Qwen2.5-7B-Instruct-bnb-4bit` | ~5.5 GB | huggingface.co |
| Repo CESVI (rama `temporal`) | pequeño | github.com |

Si hay poco tiempo o poca VRAM, el plan B es `unsloth/Qwen2.5-3B-Instruct-bnb-4bit`.

## 4. Lo que se genera durante el proceso

| Qué | Tamaño aprox. |
|---|---|
| Modelo fusionado a 16 bits | ~15 GB |
| GGUF f16 (paso intermedio) | ~15 GB |
| **GGUF final `cesvi-q4_k_m.gguf`** | **~4.7 GB** |
| Adaptador LoRA (`outputs/lora/`) | pequeño |

## 5. Requisitos de la PC

- Disco libre: **50 GB mínimo**. Con WSL2, el espacio cuenta en el disco donde vive Ubuntu.
- RAM: 16 GB mínimo, 32 GB ideal. WSL2 puede limitar la RAM por defecto. Si pasa, se sube en `C:\Users\<usuario>\.wslconfig`.
- Red hacia estos dominios: `huggingface.co`, `pypi.org`, `download.pytorch.org`, `github.com`. Si el laboratorio los bloquea, hay que pedir que los habiliten o usar hotspot.

## 6. Qué se lleva al terminar (por USB o nube, NO por GitHub)

- `gguf/cesvi-q4_k_m.gguf`
- `Modelfile`
- `outputs/lora/`

GitHub rechaza archivos de más de 100 MB, y el `.gguf` pesa ~4.7 GB.

## 7. Equipo de Ileana (solo inferencia)

Parrot OS con RTX 3060 y 16 GB de RAM. Ahí **no se entrena**. Solo se instala Ollama y se carga el `.gguf` con `ollama create cesvi-json -f Modelfile`.
