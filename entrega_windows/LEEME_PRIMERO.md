# Guía paso a paso para Windows (sin WSL2) — Proyecto CESVI

> **AVISO IMPORTANTE (LEE ESTO PRIMERO):**
> Esta ruta nativa para Windows **NO ha sido probada todavía en una GPU real**. Se preparó siguiendo la documentación oficial de Unsloth para Windows (`unsloth.ai/docs/get-started/install/windows-installation`) y los scripts actuales del proyecto. Si aparece algún error, en la sección **"g. Si algo falla"** tienes cómo generar el archivo de diagnóstico para pedir ayuda.

---

## a. Qué se necesita

Antes de empezar, confirma que la computadora cumple con todo esto:

- **Sistema operativo:** Windows 10 o Windows 11 de **64 bits**.
- **Tarjeta gráfica (GPU):** NVIDIA con VRAM suficiente (en este proyecto: **NVIDIA RTX 4070** de 12 GB).
- **Internet:** conexión estable (se descargan ~15–20 GB entre librerías, modelo base y herramientas).
- **Espacio libre en disco:** al menos **60 GB libres** en el disco donde copies el proyecto (entorno Python ~10 GB, modelo base ~5.5 GB, modelo fusionado ~15 GB, GGUF intermedio ~15 GB, GGUF final ~4.7 GB, más margen temporal).
- **Permisos de administrador:** **solo** para instalar el driver de NVIDIA y Python (los scripts del entrenamiento y exportación no requieren ejecutar PowerShell como administrador).

---

## b. Qué instalar ANTES

Haz estas instalaciones **una sola vez** en la computadora nueva antes de correr los scripts:

### 1. Driver NVIDIA actualizado (obligatorio)

- **Qué es:** el controlador de tu tarjeta RTX 4070. Se recomienda versión **550 o superior**.
- **¿Hace falta instalar CUDA Toolkit aparte?** **No.** El driver actualizado ya incluye el soporte necesario y PyTorch descarga su propio runtime CUDA.
- **Descarga oficial:** [https://www.nvidia.com/Download/index.aspx](https://www.nvidia.com/Download/index.aspx) (elige tu modelo, por ejemplo *GeForce -> GeForce RTX 40 Series -> GeForce RTX 4070 -> Windows 10/11 64-bit*, descarga e instala).
- **Alternativa con `winget`:** para el driver de GPU es más seguro y limpio usar el instalador oficial de NVIDIA del enlace anterior (si ya tienes NVIDIA App puedes instalarla con `winget install --id Nvidia.NVIDIAApp -e --source winget` y actualizar el driver desde ahí). Si instalaste el driver nuevo, **reinicia la computadora**.
- **Cómo verificar que quedó bien:** abre **PowerShell** (busca `PowerShell` en el menú Inicio) y escribe:

```powershell
nvidia-smi
```

Debes ver una tabla con el nombre de tu GPU (`NVIDIA GeForce RTX 4070`) y arriba a la derecha algo como `Driver Version: 5xx.xx` y `CUDA Version: 12.x` (o superior).

---

### 2. Python 3.12 de 64 bits (obligatorio)

> **MUY IMPORTANTE:** Debe ser **Python 3.12** (NO uses 3.13 ni 3.14, porque Unsloth / PyTorch / Triton en Windows requieren 3.10–3.12 y este paquete está preparado para **3.12**).

- **Descarga oficial:** [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/) -> busca la sección **Python 3.12.x** y descarga **"Windows installer (64-bit)"** (por ejemplo [Python 3.12.10](https://www.python.org/downloads/release/python-31210/)).
- **Paso crítico al instalar:** en la primera pantalla del instalador, **marca la casilla inferior** que dice:
  - `[x] Add python.exe to PATH` *(o "Add Python to PATH")*
  Luego haz clic en **Install Now**.
- **Alternativa con `winget`** (en PowerShell):

```powershell
winget install --id Python.Python.3.12 -e --source winget
```

*(Si usas `winget`, **cierra y vuelve a abrir PowerShell** al terminar para que reconozca el comando `python`.)*

- **Cómo verificar:**

```powershell
python --version
```

Debe responder `Python 3.12.x` (por ejemplo `Python 3.12.10`). Si te abre la Microsoft Store, significa que no se marcó `Add python.exe to PATH` o no cerraste y reabriste PowerShell.

---

### 3. Git for Windows (obligatorio, incluye Git Bash)

- **¿El proyecto lo necesita?** **Sí**, para descargar el proyecto desde GitHub usando **Git Bash** (y actualizarlo si hace falta).
- **Descarga oficial:** [https://git-scm.com/download/win](https://git-scm.com/download/win) (instalación estándar: clic en *Next* hasta terminar).
- **Alternativa con `winget`:**

```powershell
winget install --id Git.Git -e --source winget
```

*(Si usas `winget`, cierra y vuelve a abrir PowerShell o abre **Git Bash** desde el menú Inicio.)*

- **Cómo verificar:**

```powershell
git --version
```

Debe mostrar algo como `git version 2.xx.x.windows.1`.

---

### 4. ¿Hacen falta Visual Studio Build Tools?

**NO. Para esta ruta NO hace falta instalar Visual Studio ni Visual Studio Build Tools** (que pesan varios gigabytes), por tres motivos:

1. La versión moderna de `triton-windows` ya trae integrado su propio compilador ligero (TinyCC).
2. PyTorch y Unsloth se instalan usando paquetes ya compilados (*wheels*).
3. El paso de exportación a GGUF descarga el ejecutable oficial ya compilado de `llama.cpp` para Windows, sin compilar con CMake.

**Excepción mínima (solo si aparece un error de DLL faltante):** en computadoras recién formateadas podría faltar el paquete básico de librerías de Microsoft (no los Build Tools completos, solo el *Redistributable* de ~25 MB). Si algún script te indica `DLL load failed`, instala **Microsoft Visual C++ Redistributable x64**:
- **Enlace oficial:** [https://aka.ms/vs/17/release/vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- **Alternativa con `winget`:**

```powershell
winget install --id Microsoft.VCRedist.2015+.x64 -e --source winget
```

---

## c. Cómo descargar el proyecto con Git Bash y abrir PowerShell en ella

1. Abre **Git Bash** (búscalo en el menú Inicio de Windows).
2. Copia y pega estos comandos exactos en Git Bash y presiona **Enter**. Esto crea la carpeta corta `C:\cesvi` (fuera de OneDrive) y descarga el proyecto desde GitHub:

```bash
mkdir -p /c/cesvi
cd /c/cesvi
git clone https://github.com/IsoleucineDev/IA_CESVI.git
```

*(Si ya lo habías descargado antes y necesitas actualizarlo, ejecuta en Git Bash:)*

```bash
cd /c/cesvi/IA_CESVI
git pull --rebase
```

3. Ya puedes cerrar Git Bash. Abre el Explorador de Windows y entra a `C:\cesvi\IA_CESVI\entrega_windows\`.
4. Para abrir **PowerShell exactamente dentro de esa carpeta**:
   - Haz clic en la **barra de direcciones** de la ventana del Explorador (donde dice `C:\cesvi\IA_CESVI\entrega_windows`),
   - Escribe `powershell` y presiona **Enter**.
   - Se abrirá una ventana azul o negra de PowerShell mostrando al final una línea como:
     `PS C:\cesvi\IA_CESVI\entrega_windows>`

> *(También puedes abrir PowerShell desde el menú Inicio y entrar con `cd C:\cesvi\IA_CESVI\entrega_windows`.)*

---

## d. Cómo habilitar scripts en PowerShell

Por seguridad, Windows bloquea la ejecución de scripts `.ps1` hasta que le des permiso en esa ventana. Copia y pega este comando exacto en PowerShell y presiona **Enter**:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

*(Si pregunta `[S] Sí  [A] Sí a todo ...`, escribe `S` o `A` y presiona Enter. Este permiso dura solo mientras esa ventana siga abierta y no cambia la configuración permanente de Windows.)*

---

## e. Orden de ejecución

En esa misma ventana de PowerShell (`PS C:\cesvi\IA_CESVI\entrega_windows>`), ejecuta los scripts **uno por uno en este orden exacto** (espera a que termine uno antes de lanzar el siguiente):

```powershell
.\00_verificar_equipo.ps1
```

```powershell
.\01_setup_env.ps1
```

```powershell
.\02_entrenar.ps1
```

```powershell
.\03_exportar_gguf.ps1
```

*(Si alguno falla y necesitas pedir ayuda, ejecuta también:)*

```powershell
.\99_recolectar_diagnostico.ps1
```

---

## f. Qué resultado esperar en cada paso y cuánto tarda aproximadamente

### Paso 1: `.\00_verificar_equipo.ps1`
- **Qué hace:** revisa Windows, GPU/VRAM, CUDA del driver, Python 3.12, espacio en disco (~60 GB) y conexión a internet. No instala nada.
- **Tiempo aproximado:** menos de **1 minuto**.
- **Qué esperar:** una lista donde todos los renglones dicen `[OK]`, y al final:
  `RESULTADO: Todo listo. Siguiente paso: .\01_setup_env.ps1`
- Si algún renglón dice `[FALLA]`, sigue la `Accion:` que aparece debajo en amarillo y vuelve a ejecutar `.\00_verificar_equipo.ps1`.

### Paso 2: `.\01_setup_env.ps1`
- **Qué hace:** crea el entorno virtual `.venv_win` con Python 3.12, consulta el índice CUDA de PyTorch compatible con tu driver, instala PyTorch y verifica una operación matemática en la GPU antes de instalar Unsloth; luego instala `unsloth`, comprueba `triton-windows` y `bitsandbytes`, y descarga el modelo base `unsloth/Qwen2.5-7B-Instruct-bnb-4bit` (~5.5 GB).
- **Tiempo aproximado:** **10 a 25 minutos** (depende de la velocidad de internet).
- **Qué esperar:** mensajes `[1/8]` hasta `[8/8]` sin errores rojos, incluyendo `Matmul GPU OK`, `Unsloth import OK`, salida de verificación de `bitsandbytes`, y al final:
  `LISTO: Entorno Windows configurado correctamente.`

### Paso 3: `.\02_entrenar.ps1`
- **Qué hace:** activa `.venv_win`, genera el dataset del proyecto (`data\train.jsonl` y `data\val.jsonl`, 1000 ejemplos) si todavía no existe, y ejecuta `train.py` con la configuración del proyecto (`Qwen2.5-7B-Instruct-bnb-4bit`, LoRA r=16/alpha=32, 2 épocas, seq=4096), hace una prueba rápida de 5 ejemplos (`SMOKE`) y fusiona el modelo a 16 bits (`outputs\merged_16bit`).
- **Tiempo aproximado:** estimado de **30 a 90 minutos** en una RTX 4070 (tiempo estimado, no medido en GPU todavía).
- **Qué esperar:** barra de progreso del entrenamiento bajando la pérdida (`loss`), resumen `SMOKE: X/5 válidos`, y al final:
  `Modelo fusionado en outputs\merged_16bit`
  `LISTO: Entrenamiento y fusion completados.`

### Paso 4: `.\03_exportar_gguf.ps1`
- **Qué hace:** descarga el binario precompilado oficial de `llama.cpp` para Windows (sin compilar), descarga `convert_hf_to_gguf.py` y sus requirements de esa misma versión, convierte el modelo fusionado a GGUF f16 (`gguf\cesvi-f16.gguf`, ~15 GB), lo cuantiza a `Q4_K_M` (`gguf\cesvi-q4_k_m.gguf`, ~4.7 GB) y genera el `Modelfile`.
- **Tiempo aproximado:** **5 a 15 minutos**.
- **Qué esperar:** al final muestra los tamaños en `gguf\` y qué archivos debes llevarte del laboratorio (por USB en formato **exFAT** / **NTFS** o por nube — **NO por GitHub**, porque GitHub rechaza archivos de más de 100 MB y el `.gguf` pesa ~4.7 GB):
  1. `gguf\cesvi-q4_k_m.gguf` (~4.7 GB)
  2. `Modelfile`
  3. `outputs\lora\`

---

## g. Si algo falla

### Errores más comunes y cómo resolverlos

1. **"No se puede cargar el archivo ... porque la ejecución de scripts está deshabilitada"**
   - Olvidaste ejecutar el paso **d**. Corre de nuevo:
     `Set-ExecutionPolicy -Scope Process Bypass`

2. **`python` abre Microsoft Store o dice que no es Python 3.12**
   - Reinstala Python 3.12 marcando `[x] Add python.exe to PATH`, **cierra PowerShell** y abre una ventana nueva.

3. **`nvidia-smi` no se reconoce o falla**
   - Instala o actualiza el driver NVIDIA oficial y **reinicia la computadora**.

4. **Falla la conexión a `huggingface.co`, `download.pytorch.org` o `github.com`**
   - La red de la escuela/laboratorio puede estar bloqueando descargas de IA. Conecta la PC a un hotspot/datos móviles o pide a sistemas que habiliten esos dominios.

5. **Error de memoria de video (`CUDA out of memory` / `OOM`) en `02_entrenar.ps1`**
   - Prueba reducir el largo máximo de secuencia ejecutando:
     ```powershell
     .\02_entrenar.ps1 --seq 3072
     ```
   - Si sigue fallando, usa el modelo más pequeño (plan B del proyecto):
     ```powershell
     .\02_entrenar.ps1 --model unsloth/Qwen2.5-3B-Instruct-bnb-4bit
     ```

6. **Error `DLL load failed` al importar `torch`, `triton` o `bitsandbytes`**
   - Instala **Microsoft Visual C++ Redistributable x64** (`winget install --id Microsoft.VCRedist.2015+.x64 -e --source winget` o desde [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)), cierra PowerShell, abre una nueva ventana y reintenta.

7. **El archivo `cesvi-q4_k_m.gguf` (~4.7 GB) no se deja copiar al USB ("el archivo es demasiado grande")**
   - El USB está en formato **FAT32** (límite 4 GB). Respalda lo que tengas en el USB, formatéalo en **exFAT** o **NTFS** en Windows y vuelve a copiarlo.

### Qué copiar y pegar para pedir ayuda

Ejecuta en PowerShell:

```powershell
.\99_recolectar_diagnostico.ps1
```

Esto crea el archivo **`diagnostico_cesvi.txt`** dentro de `entrega_windows\`. Ábrelo con el Bloc de notas, selecciona todo (`Ctrl+E` / `Ctrl+A`), cópialo (`Ctrl+C`) y pégalo cuando pidas soporte.

---

## h. Aviso sobre el estado de pruebas

> **IMPORTANTE:** Esta ruta de ejecución nativa en Windows **NO ha sido ejecutada ni probada en una GPU real**. Fue construida siguiendo la documentación oficial de Unsloth para Windows y adaptando los scripts Linux del proyecto. Si encuentras algún inconveniente en la RTX 4070, ejecuta `.\99_recolectar_diagnostico.ps1` y comparte `diagnostico_cesvi.txt` para ajustarlo.

---

## i. Nota sobre WSL2 (ruta recomendada si es posible)

Si el equipo de sistemas del laboratorio puede habilitar **WSL2 con Ubuntu** (requiere permisos de administrador y un reinicio, ejecutando `wsl --install -d Ubuntu` en PowerShell como administrador), esa ruta en Linux es la principal del proyecto (`setup_env.sh`, `train.py`, `export_gguf.sh`) y suele tener **menos sorpresas** con librerías como Triton, bitsandbytes y PyTorch que Windows nativo. Usa esta carpeta `entrega_windows\` cuando no sea posible instalar WSL2.
