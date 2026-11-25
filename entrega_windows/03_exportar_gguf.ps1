#Requires -Version 5.1
<#
  03_exportar_gguf.ps1
  NO compila con CMake.
  Descarga el binario oficial precompilado de llama.cpp para Windows (releases de GitHub),
  mas convert_hf_to_gguf.py y su requirements.txt de la MISMA version (tag).
  Convierte outputs\merged_16bit -> gguf\cesvi-f16.gguf -> gguf\cesvi-q4_k_m.gguf
  y genera el Modelfile de Ollama.
#>

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Resolve-ProjectRoot {
    if (Test-Path (Join-Path $PSScriptRoot "train.py")) { return $PSScriptRoot }
    $parent = Split-Path -Parent $PSScriptRoot
    if ($parent -and (Test-Path (Join-Path $parent "train.py"))) { return $parent }
    throw "No se encontro train.py ni en '$PSScriptRoot' ni en su carpeta padre."
}

$ProjectRoot = Resolve-ProjectRoot
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "logs_windows"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir "03_exportar_gguf.log"
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

try {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " CESVI - 03 Exportar modelo a GGUF (Q4_K_M) + Modelfile" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    $MergedDir = Join-Path $ProjectRoot "outputs\merged_16bit"
    if (-not (Test-Path $MergedDir)) {
        Fail-Step "No existe '$MergedDir'. Ejecuta primero .\02_entrenar.ps1 para entrenar y fusionar el modelo."
    }

    $VenvWinPy = Join-Path $ProjectRoot ".venv_win\Scripts\python.exe"
    if (-not (Test-Path $VenvWinPy)) {
        Fail-Step "No existe .venv_win. Ejecuta primero .\01_setup_env.ps1."
    }

    $ToolsDir = Join-Path $ProjectRoot "tools_windows\llama.cpp"
    if (-not (Test-Path $ToolsDir)) { New-Item -ItemType Directory -Path $ToolsDir -Force | Out-Null }

    # 1. Consultar ultimo release oficial de ggml-org/llama.cpp
    Write-Host "[1/6] Consultando ultimo release oficial de ggml-org/llama.cpp..." -ForegroundColor Cyan
    $headers = @{ "User-Agent" = "cesvi-windows-export" }
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest" -Headers $headers -TimeoutSec 25 -ErrorAction Stop
    } catch {
        Fail-Step "No se pudo consultar GitHub Releases de llama.cpp: $($_.Exception.Message)"
    }
    $tag = $release.tag_name
    if ([string]::IsNullOrWhiteSpace($tag)) {
        Fail-Step "No se obtuvo tag_name del release de llama.cpp."
    }
    Write-Host "Version oficial detectada: $tag" -ForegroundColor Green

    # Elegir asset zip de Windows x64 CPU (sin requerir CUDA Toolkit ni Vulkan)
    $winAsset = $release.assets | Where-Object { $_.name -match "^llama-.*-bin-win-cpu-x64\.zip$" } | Select-Object -First 1
    if (-not $winAsset) {
        $winAsset = $release.assets | Where-Object { $_.name -match "^llama-.*-bin-win-avx2-x64\.zip$" } | Select-Object -First 1
    }
    if (-not $winAsset) {
        $winAsset = $release.assets | Where-Object {
            ($_.name -match "^llama-.*-bin-win-.*x64\.zip$") -and
            ($_.name -notmatch "cuda|vulkan|sycl|openvino|hip|arm64")
        } | Select-Object -First 1
    }
    if (-not $winAsset) {
        Fail-Step "No se encontro ningun zip binario Windows x64 CPU en el release $tag de llama.cpp."
    }

    $BinDir = Join-Path $ToolsDir ("bin_" + $tag)
    $ZipPath = Join-Path $ToolsDir $winAsset.name
    $QuantizeExe = $null
    if (Test-Path $BinDir) {
        $QuantizeExe = Get-ChildItem -Path $BinDir -Recurse -Filter "llama-quantize.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if (-not $QuantizeExe) {
        Write-Host "[2/6] Descargando binario Windows: $($winAsset.name)..." -ForegroundColor Cyan
        try {
            Invoke-WebRequest -Uri $winAsset.browser_download_url -OutFile $ZipPath -TimeoutSec 180 -UseBasicParsing -ErrorAction Stop
        } catch {
            Fail-Step "Fallo la descarga de $($winAsset.browser_download_url): $($_.Exception.Message)"
        }
        if (Test-Path $BinDir) { Remove-Item -Path $BinDir -Recurse -Force }
        New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
        Expand-Archive -Path $ZipPath -DestinationPath $BinDir -Force -ErrorAction Stop
        $QuantizeExe = Get-ChildItem -Path $BinDir -Recurse -Filter "llama-quantize.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $QuantizeExe) {
            Fail-Step "Se descomprimio $($winAsset.name) pero no se encontro llama-quantize.exe."
        }
    } else {
        Write-Host "[2/6] Binario ya descargado en $BinDir" -ForegroundColor Green
    }
    Write-Host "Usando cuantizador: $($QuantizeExe.FullName)" -ForegroundColor Green

    # 2. Descargar convert_hf_to_gguf.py y requirements de la MISMA version ($tag)
    $ScriptDirTag = Join-Path $ToolsDir ("src_" + $tag)
    if (-not (Test-Path $ScriptDirTag)) { New-Item -ItemType Directory -Path $ScriptDirTag -Force | Out-Null }
    $ConvertScript = Join-Path $ScriptDirTag "convert_hf_to_gguf.py"
    $ReqSubDir = Join-Path $ScriptDirTag "requirements"
    if (-not (Test-Path $ReqSubDir)) { New-Item -ItemType Directory -Path $ReqSubDir -Force | Out-Null }
    $ReqConvertFile = Join-Path $ReqSubDir "requirements-convert_hf_to_gguf.txt"

    Write-Host "[3/6] Descargando convert_hf_to_gguf.py y requirements del tag $tag ..." -ForegroundColor Cyan
    $rawBase = "https://raw.githubusercontent.com/ggml-org/llama.cpp/$tag"
    try {
        Invoke-WebRequest -Uri "$rawBase/convert_hf_to_gguf.py" -OutFile $ConvertScript -TimeoutSec 60 -UseBasicParsing -ErrorAction Stop
    } catch {
        Fail-Step "No se pudo descargar convert_hf_to_gguf.py del tag $tag : $($_.Exception.Message)"
    }

    $reqUsed = $null
    try {
        Invoke-WebRequest -Uri "$rawBase/requirements/requirements-convert_hf_to_gguf.txt" -OutFile $ReqConvertFile -TimeoutSec 60 -UseBasicParsing -ErrorAction Stop
        $reqUsed = $ReqConvertFile
    } catch {
        # Fallback a requirements.txt en la raiz del tag si la estructura cambiara
        $RootReqFile = Join-Path $ScriptDirTag "requirements.txt"
        try {
            Invoke-WebRequest -Uri "$rawBase/requirements.txt" -OutFile $RootReqFile -TimeoutSec 60 -UseBasicParsing -ErrorAction Stop
            $reqUsed = $RootReqFile
        } catch {
            Fail-Step "No se pudo descargar ni requirements-convert_hf_to_gguf.txt ni requirements.txt del tag $tag."
        }
    }

    # Si el requirements descargado referencia un directorio local (ej. ./gguf-py), usar paquete PyPI 'gguf'
    $reqLines = Get-Content -Path $reqUsed -Encoding UTF8
    $cleanReqFile = Join-Path $ScriptDirTag "requirements_win_resolved.txt"
    $cleanLines = @($reqLines | ForEach-Object {
        if ($_ -match "gguf-py") { "gguf" } else { $_ }
    })
    [System.IO.File]::WriteAllLines($cleanReqFile, $cleanLines, (New-Object System.Text.UTF8Encoding $false))

    # 3. Entorno aislado para conversion GGUF (no altera el PyTorch CUDA de .venv_win)
    $GgufVenvDir = Join-Path $ToolsDir ".venv_gguf"
    $GgufVenvPy  = Join-Path $GgufVenvDir "Scripts\python.exe"
    if (-not (Test-Path $GgufVenvPy)) {
        Write-Host "[4/6] Creando entorno aislado para conversion GGUF (.venv_gguf)..." -ForegroundColor Cyan
        & $VenvWinPy -m venv $GgufVenvDir
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $GgufVenvPy)) {
            Fail-Step "No se pudo crear el entorno de conversion en $GgufVenvDir."
        }
        & $GgufVenvPy -m pip install -U pip
        if ($LASTEXITCODE -ne 0) { Fail-Step "Fallo al actualizar pip en .venv_gguf." }
    } else {
        Write-Host "[4/6] Usando entorno de conversion existente: $GgufVenvDir" -ForegroundColor Green
    }

    Write-Host "Instalando dependencias de conversion (usando wheel CPU ligero para torch)..." -ForegroundColor Cyan
    & $GgufVenvPy -m pip install -r $cleanReqFile --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
    if ($LASTEXITCODE -ne 0) {
        Fail-Step "Fallo la instalacion de dependencias desde $reqUsed."
    }

    # 4. Convertir a GGUF f16 y cuantizar a Q4_K_M
    $OutDir = Join-Path $ProjectRoot "gguf"
    if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
    $F16File   = Join-Path $OutDir "cesvi-f16.gguf"
    $Q4kmFile  = Join-Path $OutDir "cesvi-q4_k_m.gguf"

    Write-Host "[5/6] Convirtiendo modelo fusionado a GGUF f16 (~15 GB)..." -ForegroundColor Cyan
    & $GgufVenvPy $ConvertScript $MergedDir --outtype f16 --outfile $F16File
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $F16File)) {
        Fail-Step "Fallo convert_hf_to_gguf.py al generar $F16File."
    }

    Write-Host "[6/6] Cuantizando a Q4_K_M (~4.7 GB)..." -ForegroundColor Cyan
    & $QuantizeExe.FullName $F16File $Q4kmFile Q4_K_M
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Q4kmFile)) {
        Fail-Step "Fallo llama-quantize.exe al generar $Q4kmFile."
    }

    # Generar Modelfile usando el script del proyecto
    & $VenvWinPy (Join-Path $ProjectRoot "make_modelfile.py") "gguf/cesvi-q4_k_m.gguf"
    if ($LASTEXITCODE -ne 0) {
        Fail-Step "Fallo make_modelfile.py."
    }

    Write-Host ""
    Write-Host "Archivos generados en ${OutDir}:" -ForegroundColor Green
    Get-ChildItem -Path $OutDir | ForEach-Object {
        $gb = [math]::Round($_.Length / 1GB, 2)
        Write-Host ("  - {0} ({1} GB)" -f $_.Name, $gb) -ForegroundColor Green
    }
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " LISTO: Llevate del laboratorio (USB exFAT/NTFS o nube, NO GitHub):" -ForegroundColor Green
    Write-Host "   1) gguf\cesvi-q4_k_m.gguf" -ForegroundColor Green
    Write-Host "   2) Modelfile" -ForegroundColor Green
    Write-Host "   3) outputs\lora\" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}
