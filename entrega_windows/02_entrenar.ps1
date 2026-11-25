#Requires -Version 5.1
<#
  02_entrenar.ps1
  Activa el entorno .venv_win, genera el dataset si aun no existe
  (gen_dataset.py --n 1000 --seed 7 --out data) y ejecuta train.py
  con los parametros por defecto del proyecto (o los argumentos extra que pases).
#>

$ErrorActionPreference = "Continue"

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
$LogFile = Join-Path $LogDir "02_entrenar.log"
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
    Write-Host " CESVI - 02 Entrenamiento QLoRA con Unsloth (Windows)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    $VenvDir = Join-Path $ProjectRoot ".venv_win"
    $ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
    $VenvPy = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path $ActivateScript) -or -not (Test-Path $VenvPy)) {
        Fail-Step "No existe el entorno virtual .venv_win. Ejecuta primero .\01_setup_env.ps1"
    }

    Write-Host "[1/3] Activando entorno virtual: $VenvDir" -ForegroundColor Cyan
    . $ActivateScript

    # Generar dataset del proyecto si no existe todavia
    $TrainJsonl = Join-Path $ProjectRoot "data\train.jsonl"
    $ValJsonl   = Join-Path $ProjectRoot "data\val.jsonl"
    if (-not (Test-Path $TrainJsonl) -or -not (Test-Path $ValJsonl)) {
        Write-Host "[2/3] Generando dataset del proyecto (gen_dataset.py --n 1000 --seed 7 --out data)..." -ForegroundColor Cyan
        & $VenvPy (Join-Path $ProjectRoot "gen_dataset.py") --n 1000 --seed 7 --out data
        if ($LASTEXITCODE -ne 0) {
            Fail-Step "Fallo gen_dataset.py."
        }
    } else {
        Write-Host "[2/3] Dataset ya existente en data\train.jsonl y data\val.jsonl." -ForegroundColor Green
    }

    # Parametros por defecto del proyecto (en train.py):
    # --model unsloth/Qwen2.5-7B-Instruct-bnb-4bit --data data --out outputs
    # --seq 4096 --epochs 2 --bs 1 --ga 8 --lr 2e-4 --rank 16 --alpha 32 --smoke 5
    Write-Host "[3/3] Lanzando train.py (esto puede tardar 30-90 min en RTX 4070)..." -ForegroundColor Cyan
    if ($args.Count -gt 0) {
        Write-Host "Argumentos adicionales: $($args -join ' ')" -ForegroundColor Yellow
        & $VenvPy (Join-Path $ProjectRoot "train.py") @args
    } else {
        & $VenvPy (Join-Path $ProjectRoot "train.py")
    }
    if ($LASTEXITCODE -ne 0) {
        Fail-Step "train.py termino con errores. Si fue falta de memoria (OOM), prueba: .\02_entrenar.ps1 --seq 3072"
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " LISTO: Entrenamiento y fusion completados." -ForegroundColor Green
    Write-Host " Siguiente paso: .\03_exportar_gguf.ps1" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}
