#Requires -Version 5.1
<#
  01_setup_env.ps1
  Crea el entorno virtual con Python 3.12, detecta la version de CUDA en nvidia-smi,
  consulta dinamicamente el indice oficial de PyTorch disponible, instala PyTorch CUDA,
  prueba torch.cuda.is_available() + multiplicacion de matrices en GPU ANTES de Unsloth,
  instala unsloth, verifica/instala triton-windows si hace falta, verifica bitsandbytes
  y descarga el modelo base unsloth/Qwen2.5-7B-Instruct-bnb-4bit.
#>

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Resolve-ProjectRoot {
    if (Test-Path (Join-Path $PSScriptRoot "train.py")) { return $PSScriptRoot }
    $parent = Split-Path -Parent $PSScriptRoot
    if ($parent -and (Test-Path (Join-Path $parent "train.py"))) { return $parent }
    throw "No se encontro train.py ni en '$PSScriptRoot' ni en su carpeta padre. Copia la carpeta completa del proyecto."
}

$ProjectRoot = Resolve-ProjectRoot
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "logs_windows"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir "01_setup_env.log"
try { Start-Transcript -Path $LogFile -Force | Out-Null } catch {}

function Fail-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    Write-Host "Revisa el log en: $LogFile" -ForegroundColor Yellow
    Write-Host "Para pedir ayuda ejecuta: .\99_recolectar_diagnostico.ps1" -ForegroundColor Yellow
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}

function Find-Python312 {
    $candidates = @()
    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $p = & $pyLauncher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $p) { $candidates += $p.ToString().Trim() }
    }
    $pyCmds = Get-Command "python" -All -ErrorAction SilentlyContinue
    foreach ($cmd in $pyCmds) {
        if ($cmd.Source -and ($cmd.Source -notlike "*\WindowsApps\*")) { $candidates += $cmd.Source }
    }
    foreach ($exe in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path $exe)) { continue }
        $ver = & $exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}|{sys.maxsize > 2**32}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and ($ver -eq "3.12|True")) { return $exe }
    }
    return $null
}

function Resolve-PyTorchCudaIndex {
    param([string]$DriverCuda)
    # Convierte "12.8" -> 128, "13.0" -> 130, etc.
    $parts = $DriverCuda -split "\."
    $driverNum = ([int]$parts[0]) * 10 + ([int]$parts[1])

    Write-Host "Consultando indices CUDA publicados en https://download.pytorch.org/whl/ ..." -ForegroundColor Cyan
    try {
        $html = (Invoke-WebRequest -Uri "https://download.pytorch.org/whl/" -TimeoutSec 20 -UseBasicParsing -ErrorAction Stop).Content
    } catch {
        Fail-Step "No se pudo consultar https://download.pytorch.org/whl/: $($_.Exception.Message)"
    }

    $regexMatches = [regex]::Matches($html, 'href="[^"]*?(cu\d{3,4})/?[^"]*"')
    $tags = New-Object System.Collections.Generic.List[object]
    $seen = @{}
    foreach ($m in $regexMatches) {
        $tag = $m.Groups[1].Value
        if ($seen.ContainsKey($tag)) { continue }
        $seen[$tag] = $true
        $num = [int]($tag.Substring(2))
        if ($num -le $driverNum) {
            $tags.Add([PSCustomObject]@{ Tag = $tag; Num = $num })
        }
    }

    if ($tags.Count -eq 0) {
        Fail-Step "No se encontro ningun indice CUDA en https://download.pytorch.org/whl/ compatible con CUDA $DriverCuda del driver."
    }

    $ordered = $tags | Sort-Object -Property Num -Descending
    foreach ($candidate in $ordered) {
        $torchIdxUrl = "https://download.pytorch.org/whl/$($candidate.Tag)/torch/"
        try {
            $resp = Invoke-WebRequest -Uri $torchIdxUrl -TimeoutSec 15 -UseBasicParsing -ErrorAction Stop
            if ($resp.StatusCode -eq 200 -and ($resp.Content -match "cp312" -and $resp.Content -match "win_amd64")) {
                return "https://download.pytorch.org/whl/$($candidate.Tag)"
            }
        } catch {
            # Probar siguiente indice menor disponible
        }
    }

    Fail-Step "Ninguno de los indices CUDA detectados en PyTorch tiene wheels cp312 win_amd64 para CUDA <= $DriverCuda."
}

try {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " CESVI - 01 Configuracion de entorno Windows (Unsloth + CUDA)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    # 1. Python 3.12
    $Py312 = Find-Python312
    if (-not $Py312) {
        Fail-Step "No se encontro Python 3.12 (64 bits). Instala Python 3.12 marcando 'Add python.exe to PATH' y reintenta."
    }
    Write-Host "[1/8] Python 3.12 encontrado: $Py312" -ForegroundColor Green

    # 2. Leer version de CUDA desde nvidia-smi
    $nvidiaSmi = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
    if (-not $nvidiaSmi) {
        $fallbackSmi = Join-Path $env:ProgramFiles "NVIDIA Corporation\NVSMI\nvidia-smi.exe"
        if (Test-Path $fallbackSmi) { $nvidiaSmi = Get-Command $fallbackSmi -ErrorAction SilentlyContinue }
    }
    if (-not $nvidiaSmi) {
        Fail-Step "No se encontro nvidia-smi. Instala el driver NVIDIA oficial y reinicia la PC."
    }
    $smiOut = (& $nvidiaSmi.Source 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or -not ($smiOut -match "CUDA Version:\s*(\d+\.\d+)")) {
        Fail-Step "No se pudo leer la version de CUDA en nvidia-smi. Actualiza el driver NVIDIA."
    }
    $DriverCuda = $Matches[1]
    Write-Host "[2/8] Driver NVIDIA reporta CUDA Version: $DriverCuda" -ForegroundColor Green

    # 3. Crear venv con Python 3.12
    $VenvDir = Join-Path $ProjectRoot ".venv_win"
    $VenvPy  = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path $VenvPy)) {
        Write-Host "[3/8] Creando entorno virtual en $VenvDir ..." -ForegroundColor Cyan
        & $Py312 -m venv $VenvDir
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPy)) {
            Fail-Step "Fallo la creacion del entorno virtual en $VenvDir."
        }
    } else {
        Write-Host "[3/8] Usando entorno virtual existente: $VenvDir" -ForegroundColor Green
    }

    & $VenvPy -m pip install -U pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { Fail-Step "Fallo al actualizar pip/setuptools/wheel." }

    # 4. Elegir e instalar PyTorch con el indice CUDA verificado
    $TorchIndex = Resolve-PyTorchCudaIndex -DriverCuda $DriverCuda
    Write-Host "[4/8] Instalando PyTorch desde $TorchIndex ..." -ForegroundColor Cyan
    & $VenvPy -m pip install --upgrade torch torchvision torchaudio --index-url $TorchIndex
    if ($LASTEXITCODE -ne 0) { Fail-Step "Fallo la instalacion de PyTorch desde $TorchIndex." }

    # 5. Verificar GPU + multiplicacion de matrices en GPU ANTES de instalar Unsloth
    Write-Host "[5/8] Verificando PyTorch CUDA y multiplicacion de matrices en GPU..." -ForegroundColor Cyan
    $gpuTestCode = @"
import torch
print("torch:", torch.__version__, "| CUDA runtime:", torch.version.cuda)
assert torch.cuda.is_available(), "torch.cuda.is_available() devolvio False"
print("GPU:", torch.cuda.get_device_name(0), "| capability:", torch.cuda.get_device_capability(0))
a = torch.randn(512, 512, device="cuda", dtype=torch.float16)
b = torch.randn(512, 512, device="cuda", dtype=torch.float16)
c = a @ b
torch.cuda.synchronize()
print("Matmul GPU OK | shape:", tuple(c.shape), "| suma:", float(c.sum().item()))
"@
    & $VenvPy -c $gpuTestCode
    if ($LASTEXITCODE -ne 0) {
        Fail-Step "PyTorch no pudo usar la GPU CUDA (fallo la verificacion previa a Unsloth). Revisa driver NVIDIA e indice $TorchIndex."
    }

    # 6. Instalar Unsloth + huggingface_hub
    Write-Host "[6/8] Instalando Unsloth y huggingface_hub..." -ForegroundColor Cyan
    & $VenvPy -m pip install unsloth
    if ($LASTEXITCODE -ne 0) { Fail-Step "Fallo 'pip install unsloth'." }
    & $VenvPy -m pip install -U huggingface_hub
    if ($LASTEXITCODE -ne 0) { Fail-Step "Fallo 'pip install -U huggingface_hub'." }

    # 7. Revisar triton-windows, probar import unsloth y verificar bitsandbytes
    Write-Host "[7/8] Verificando triton-windows, import unsloth y bitsandbytes..." -ForegroundColor Cyan
    $hasTritonWin = $false
    & $VenvPy -m pip show triton-windows *> $null
    if ($LASTEXITCODE -eq 0) {
        $hasTritonWin = $true
        Write-Host "triton-windows ya esta instalado." -ForegroundColor Green
    } else {
        Write-Host "AVISO: triton-windows no aparece instalado todavia; se probara 'import unsloth'." -ForegroundColor Yellow
    }

    $importOutput = (& $VenvPy -c "import unsloth; print('Unsloth import OK:', getattr(unsloth, '__version__', 'sin version'))" 2>&1) -join "`n"
    $importExit = $LASTEXITCODE
    if ($importExit -ne 0) {
        Write-Host $importOutput
        if ($importOutput -match "triton" -or (-not $hasTritonWin)) {
            Write-Host "Intentando instalar triton-windows y reintentar 'import unsloth'..." -ForegroundColor Yellow
            & $VenvPy -m pip install -U triton-windows
            if ($LASTEXITCODE -ne 0) {
                Fail-Step "Fallo 'pip install triton-windows'."
            }
            $importOutput2 = (& $VenvPy -c "import unsloth; print('Unsloth import OK:', getattr(unsloth, '__version__', 'sin version'))" 2>&1) -join "`n"
            if ($LASTEXITCODE -ne 0) {
                Write-Host $importOutput2
                Fail-Step "'import unsloth' siguio fallando tras instalar triton-windows. Si ves 'DLL load failed', instala Microsoft Visual C++ Redistributable x64 (https://aka.ms/vs/17/release/vc_redist.x64.exe)."
            }
            Write-Host $importOutput2 -ForegroundColor Green
        } else {
            Fail-Step "'import unsloth' fallo. Si ves 'DLL load failed', instala Microsoft Visual C++ Redistributable x64 (https://aka.ms/vs/17/release/vc_redist.x64.exe)."
        }
    } else {
        Write-Host $importOutput -ForegroundColor Green
    }

    Write-Host "Verificando bitsandbytes (python -m bitsandbytes)..." -ForegroundColor Cyan
    & $VenvPy -m bitsandbytes
    if ($LASTEXITCODE -ne 0) {
        Fail-Step "'python -m bitsandbytes' fallo. Revisa driver NVIDIA o instala Microsoft Visual C++ Redistributable x64."
    }

    # 8. Descargar modelo base con huggingface_hub
    $BaseModel = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
    Write-Host "[8/8] Descargando modelo base '$BaseModel' (~5.5 GB)..." -ForegroundColor Cyan
    $dlCode = "from huggingface_hub import snapshot_download; p = snapshot_download('$BaseModel'); print('Modelo listo en cache:', p)"
    & $VenvPy -c $dlCode
    if ($LASTEXITCODE -ne 0) {
        Fail-Step "Fallo la descarga del modelo base '$BaseModel' desde huggingface.co."
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " LISTO: Entorno Windows configurado correctamente." -ForegroundColor Green
    Write-Host " Siguiente paso: .\02_entrenar.ps1" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}
