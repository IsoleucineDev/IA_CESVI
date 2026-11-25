# CESVI: contexto completo del fine-tuning (QLoRA + Unsloth → GGUF → Ollama)

> Documento para retomar el trabajo en cualquier chat o sesión. Fecha de referencia: 25 nov 2026.

---

## 1. Objetivo

Que un modelo local en **Ollama** convierta hechos periciales verificados en el `choque.json` exacto que espera **Unity** (y la app CESVI). Se entrena con **QLoRA (Unsloth)** en una PC del laboratorio y se corre cuantizado **Q4_K_M** en la **RTX 3060** de Parrot OS.

**Alcance de hoy:** solo la generación del JSON. No incluye reportes ni dictámenes largos.

## 2. Proyecto CESVI

| Capa | Tecnología |
|---|---|
| Frontend | React 19 + Vite + TypeScript (Leaflet, catálogo de indicios/vehículos, timeline de escenas) |
| Backend | FastAPI + SQLAlchemy + SQLite (`app/services/llm.py`, `app/services/interview/engine.py`, `schema.py`, `chat_core.py`, `facts_utils.py`) |
| Motor 3D | Unity (mapa Google/Cesium), consume `choque.json` |
| Repo | `IsoleucineDev/CESVI` (deploy en Vercel: cesvi-project.vercel.app) |

### Arquitectura de prompts (Opción B, desacoplada)

1. **Modo Entrevista y Extracción Estructurada** (temperatura 0.1–0.2). Guía al perito paso a paso, valida consistencia física y reglas de Unity, y emite el JSON final sin inventar datos (supuestos con `estimado: true`). **Es el único modo que cubre este fine-tuning.**
2. **Modo Redacción de Dictamen** (temperatura 0.3–0.4). Redacta el reporte pericial a partir del JSON. **Queda fuera de alcance hoy.**

## 3. Hardware

| Equipo | GPU | Uso |
|---|---|---|
| Laboratorio (hoy) | **RTX 4070** (Ada, 12 GB, bf16 nativo) | Entrenamiento + fusión + GGUF |
| Tu equipo | RTX 3060 + Parrot OS + Ollama | Inferencia con GGUF Q4_K_M |

Nota: en una conversación anterior se mencionó una RTX 5050/5060 (Blackwell, 8 GB). Se cambió a la **4070**, que es más simple porque no requiere pasos especiales de Blackwell (CUDA 12.8, xformers desde fuente).

## 4. Reglas del esquema JSON de Unity

### Estructura (6 secciones de primer nivel)

`metadata` (obligatoria), `escena` (obligatoria; **`origen_geografico.latitud/longitud` son indispensables**), `impacto` (opcional), `vehiculos` (obligatoria), `elementos_estaticos` (opcional), `registro_impactos` (informativa).

### Reglas críticas

- UTF-8, **punto decimal** (nunca coma), números sin comillas, sin comentarios.
- `categoria`, `fase` e `id`: minúsculas, sin acentos, `snake_case`.
- `categoria` exacta, una de 13: `sedan`, `hatchback`, `suv`, `pickup`, `deportivo`, `van`, `limusina`, `ambulancia`, `bomberos`, `autobus`, `camion`, `tractocamion`, `semirremolque`. Fuera del catálogo = cubo gris. **No hay modelos de moto, bicicleta ni peatón.**
- **Ejes** en escena, vehículos y estáticos: `x` = Este, `y` = Arriba (0 en terreno), `z` = Norte. El origen (0,0,0) es el punto de impacto.
- **Excepción:** en `impacto.posicion`, `x` = Este, **`y` = Norte**, `z` = 0 (desplaza el origen respecto a `origen_geografico`).
- `rotacion_grados.y = rumbo − 180` (rumbo desde el norte, horario). Solo importa `y`.
- Mínimo **2 keyframes** por vehículo, ordenados por `tiempo_s`. Cerrar con **2 keyframes idénticos** en fase `detencion_posicion_final`.
- **Palabras prohibidas en fases previas al golpe real:** `impacto`, `choque`, `colision`, `caida` (disparan el efecto de choque en el primer keyframe que las contiene). Ejemplo de error: `evasion_para_evitar_choque`.
- Vehículos: `id` = `vehiculo_1`, `vehiculo_2`… (únicos); `dimensiones_m.largo` y `ancho` obligatorios.
- Estáticos: `id` = `<prefijo>_<numero>`, con prefijo `poste`, `semaforo`, `senal`, `roca`, `animal`, `indicio` u `objeto`.
- `tipo` de estático: `obstaculo` / `senalizacion` / `indicio`.
- **Escala:** modelos 3D (`poste`, `semaforo`, `senal`) usan solo `escala.y` = altura en metros. Cubos usan x = ancho, y = alto, z = largo. `indicio` es cubo plano con `escala.y = 0.03`.
- Datos aproximados: `estimado: true`, `masa_estimada: true`, `mu_estimado: true`.

### Errores comunes (según la especificación)

Categoría con mayúsculas o acentos, id de estático sin formato, falta `origen_geografico`, menos de 2 keyframes, confundir `y` (norte) con altura en `impacto.posicion`, palabra de impacto antes del golpe, coma decimal, ids duplicados.

## 5. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Modelo base | `unsloth/Qwen2.5-7B-Instruct-bnb-4bit` (bueno en JSON y español, cuantiza bien) |
| Plan B si hay OOM | `--seq 3072`, o `unsloth/Qwen2.5-3B-Instruct-bnb-4bit` |
| LoRA | `r=16`, `lora_alpha=32`, `dropout=0`, todos los módulos lineales |
| Entrenamiento | `lr=2e-4`, cosine, warmup 5 %, `adamw_8bit`, bf16, batch 1 × grad-accum 8, **2 épocas** |
| Longitud | `max_seq_length=4096` (los ejemplos miden ~2300 tokens de media y ~3200 de máximo, estimado por caracteres) |
| Pérdida | Solo sobre la respuesta del asistente (`train_on_responses_only`) |
| Dataset | **800–1200 ejemplos**; el generador usa 1000 (950 train / 50 val). ~300 enseñan el formato; 3000+ no mejora y gasta tiempo |
| Formato de salida | JSON **compacto** (sin indentación) para ahorrar tokens |
| Cuantización | `Q4_K_M` (~4.7 GB). Opcional `Q5_K_M` (~5.4 GB, cabe en 3060 de 12 GB) |
| Inferencia | temperatura 0.1, `top_p 0.9`, `repeat_penalty 1.0` (no penalizar repetición en JSON), `num_ctx 8192` |

### System prompt (idéntico en entrenamiento y en el Modelfile)

```
Eres el motor de extraccion de CESVI. Recibes hechos periciales verificados y devuelves SOLO un objeto JSON valido (UTF-8, punto decimal, sin comentarios, sin texto extra, sin ```) con el esquema de reconstruccion para Unity: metadata, escena (origen_geografico, condiciones), impacto, vehiculos, elementos_estaticos, registro_impactos. Reglas: ids vehiculo_N en orden de aparicion; categoria exacta de {sedan,hatchback,suv,pickup,deportivo,van,limusina,ambulancia,bomberos,autobus,camion,tractocamion,semirremolque}; categoria, fase e id en minusculas, sin acentos, snake_case. Ejes en escena/vehiculos/estaticos: x=Este, y=Arriba (0 en terreno), z=Norte. En impacto.posicion: x=Este, y=Norte, z=0. rotacion_grados.y = rumbo - 180. Minimo 2 keyframes por vehiculo ordenados por tiempo_s, cerrando con 2 keyframes identicos en detencion_posicion_final. Nunca uses impacto, choque, colision o caida en fases previas al golpe real. Estaticos: <prefijo>_<n> con prefijo poste|semaforo|senal|roca|animal|indicio|objeto; poste/semaforo/senal usan escala.y = altura en metros; indicio usa escala.y = 0.03. Marca datos aproximados con estimado / masa_estimada / mu_estimado = true. No inventes datos.
```

La fuente de verdad es `SYSTEM_PROMPT` en `gen_dataset.py`. `make_modelfile.py` lo importa. Si lo cambias, **reentrena**, porque el modelo aprendió con ese texto.

## 6. Archivos entregados (carpeta `cesvi_ft/`)

| Archivo | Para qué sirve |
|---|---|
| `check_env.sh` | Diagnóstico de solo lectura: GPU, RAM, disco, herramientas y red |
| `setup_env.sh` | Crea el venv `~/ft`, instala Unsloth, verifica la GPU y descarga el modelo base |
| `gen_dataset.py` | Genera `train.jsonl` / `val.jsonl` y contiene `validate_choque()` y `SYSTEM_PROMPT` |
| `train.py` | QLoRA con Unsloth, prueba rápida de JSON y fusión a 16 bits |
| `export_gguf.sh` | Compila `llama-quantize`, convierte a GGUF f16 y cuantiza a `Q4_K_M` |
| `make_modelfile.py` | Genera el `Modelfile` de Ollama con plantilla ChatML y el system prompt |
| `test_json.py` | Prueba el modelo en Ollama con `json.loads` estricto y el validador de reglas |

### Qué cubre el dataset

7 tipos de escenario: alcance (con vehículo estacionado o en movimiento), alcance de tractocamión + semirremolque, reversa contra estacionado, cruce lateral, choque contra poste, evasión de animal con choque contra roca, y caída en bache.

El texto de entrada incluye variaciones a propósito:
- Acentos y mayúsculas ("sedán", "pick-up", "autobús").
- Comas decimales.
- Frases trampa ("frenado previo al choque", "maniobra evasiva para evitar el choque").
- Datos "(estimado)".
- Campos de condiciones que a veces faltan, para que el modelo no los invente.
- Posiciones dadas como "X m al Este y Y m al Norte".

## 7. Procedimiento paso a paso

Todo desde la carpeta `cesvi_ft/`.

```bash
# 0. Diagnóstico (no instala nada)
bash check_env.sh

# 1. Entorno
bash setup_env.sh
source ~/ft/bin/activate

# 2. Dataset
python gen_dataset.py --n 1000 --seed 7 --out data

# 3. Prueba corta (2-3 min): verifica tokens, VRAM y tiempo por paso
python train.py --max_steps 20 --no_merge --smoke 0

# 4. Entrenamiento completo (guarda LoRA, prueba JSON, fusiona)
python train.py

# 5. GGUF Q4_K_M + Modelfile
bash export_gguf.sh
```

**Llévate del laboratorio:** `gguf/cesvi-q4_k_m.gguf`, `Modelfile`, `outputs/lora/`, `gen_dataset.py`, `test_json.py`, `make_modelfile.py`.

**En Parrot OS (3060):**
```bash
# Ajusta la ruta FROM del Modelfile si moviste el .gguf
ollama create cesvi-json -f Modelfile
python test_json.py --model cesvi-json --n 20
```

### Requisitos de la PC del laboratorio

- Driver NVIDIA 550 o superior. **No hace falta CUDA Toolkit**, porque PyTorch trae su runtime.
- Linux o WSL2 (Ubuntu). Los scripts son bash.
- Python 3.10–3.12 con `python3-venv`.
- `git`, `cmake`, `gcc`, `g++`, `make`, `curl`.
- RAM: 16 GB mínimo, 32 GB ideal.
- Disco: ~50 GB libres (venv ~10, base ~5.5, fusionado ~15, f16 ~15, Q4_K_M ~4.7).
- Red hacia `huggingface.co`, `pypi.org`, `download.pytorch.org` y `github.com`.
- Un USB de 16 GB o más (o nube) para llevarte el resultado.

## 8. Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| OOM al entrenar | `python train.py --seq 3072`; si persiste, usar el modelo 3B |
| PyTorch no ve la GPU | Revisar `nvidia-smi` y reinstalar torch con el índice `cu124` o `cu128` |
| Red bloqueada (`000` en `check_env.sh`) | Pedir al laboratorio habilitar los dominios, o usar hotspot |
| Poco tiempo | `--epochs 1` y/o `--n 600` en el generador |
| `convert_hf_to_gguf.py` falla por dependencias | `pip install gguf sentencepiece protobuf transformers` |
| Ollama devuelve texto extra o ``` | Probar `test_json.py --format-json`; revisar `/show template` en Ollama |
| JSON inválido con frecuencia | Más ejemplos con ese caso o más épocas; revisar con `test_json.py` cuáles reglas fallan |

## 9. Estado de verificación

**Probado en un entorno sin GPU:**
- Sintaxis de todos los scripts.
- El generador produce 3000/3000 ejemplos válidos.
- El validador rechaza categoría con mayúscula y fase con `choque` antes del golpe.
- `test_json.py --gold` da 50/50 sobre las respuestas correctas.
- El `Modelfile` se genera correctamente.

**NO probado (requiere GPU y red):** `train.py`, Unsloth, la exportación GGUF y Ollama. Por eso existe la prueba corta del paso 3. Si algo falla, usar el error completo para depurar.

## 10. Limitaciones y pendientes

1. **Formato de entrada real.** El texto de entrada del dataset sale de plantillas propias. Falta un ejemplo real de lo que `llm.py` / `engine.py` le manda al modelo (el `facts` de la entrevista) para adaptar `render_user()` y reentrenar. Es la mejora que más sube la precisión en producción.
2. **Sin motos, bicicletas ni peatones.** Unity no tiene modelos para ellos, y el dataset no enseña qué hacer si el perito los menciona.
3. **Sin turnos de entrevista.** El dataset enseña solo la conversión final (hechos → JSON), no la corrección de errores del perito ni el guiado paso a paso.
4. **Un solo punto de impacto por caso.** No hay escenarios con varios golpes.
5. **Integración con `backend/app/services/llm.py`.** Falta conectar `cesvi-json` en Ollama con tu respaldo existente. Se hace después de validar el modelo.
6. **Modo 2 (dictamen).** Fuera del alcance de este fine-tuning.
7. **Estimaciones de tiempo.** Los tiempos de entrenamiento son estimaciones, no mediciones. Mide el tiempo por paso en la prueba corta.
8. **Modelo 3B.** Es un plan B de memoria; puede dar menos calidad en JSON largos.
