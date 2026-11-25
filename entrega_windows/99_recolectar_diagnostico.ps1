#Requires -Version 5.1
<#
  99_recolectar_diagnostico.ps1
  Junta en un solo archivo de texto (diagnostico_cesvi.txt):
  - Sistema operativo y espacio en disco
  - Salida de nvidia-smi
  - Versiones de python / torch / triton / unsloth / bitsandbytes / transformers / trl
  - Ultimas lineas de los logs generados en logs_windows\
  para copiar y pegar facilmente al pedir ayuda.
#>

$ErrorActionPreference = "Continue"

function Resolve-ProjectRoot {
    if (Test-Path (Join-Path $PSScriptRoot "train.py")) { return $PSScriptRoot }
    $parent = Split-Path -Parent $PSScriptRoot
    if ($parent -and (Test-Path (Join-Path $parent "train.py"))) { return $parent }
    return $PSScriptRoot
}

$ProjectRoot = Resolve-ProjectRoot
$OutFile = Join-Path $PSScriptRoot "diagnostico_cesvi.txt"
$sb = New-Object System.Text.StringBuilder

function Add-Section {
    param([string]$Title, [string]$Body)
    [void]$sb.AppendLine("============================================================")
    [void]$sb.AppendLine($Title)
    [void]$sb.AppendLine("============================================================")
    [void]$sb.AppendLine($Body)
    [void]$sb.AppendLine("")
}

Add-Section "FECHA Y RUTA" ("Fecha: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`nProjectRoot: $ProjectRoot`nScriptRoot: $PSScriptRoot")

# Windows + Disco
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $driveName = ([System.IO.Path]::GetPathRoot($ProjectRoot)).Substring(0, 1)
    $drive = Get-PSDrive -Name $driveName
    $freeGB = [math]::Round($drive.Free / 1GB, 2)
    Add-Section "SISTEMA Y DISCO" ("OS: $($os.Caption) (Build $($os.BuildNumber), 64-bit: $([Environment]::Is64BitOperatingSystem))`nDisco ${driveName}: $freeGB GB libres")
} catch {
    Add-Section "SISTEMA Y DISCO" "Error consultando sistema/disco: $_"
}

# nvidia-smi
$nvidiaSmiPath = $null
$cmdSmi = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
if ($cmdSmi -and (Test-Path $cmdSmi.Source)) {
    $nvidiaSmiPath = $cmdSmi.Source
} else {
    foreach ($p in @(
        (Join-Path $env:WINDIR "Sysnative\nvidia-smi.exe"),
        (Join-Path $env:WINDIR "System32\nvidia-smi.exe"),
        (Join-Path $env:ProgramW6432 "NVIDIA Corporation\NVSMI\nvidia-smi.exe"),
        (Join-Path $env:ProgramFiles "NVIDIA Corporation\NVSMI\nvidia-smi.exe")
    )) {
        if ($p -and (Test-Path $p)) { $nvidiaSmiPath = $p; break }
    }
}
if ($nvidiaSmiPath) {
    $smiOut = (& $nvidiaSmiPath 2>&1) -join "`n"
    Add-Section "NVIDIA-SMI ($nvidiaSmiPath)" $smiOut
} else {
    Add-Section "NVIDIA-SMI" "No se encontro nvidia-smi."
}

# Python y librerias (preferir .venv_win si existe)
$VenvPy = Join-Path $ProjectRoot ".venv_win\Scripts\python.exe"
$PyCmd = if (Test-Path $VenvPy) { $VenvPy } else {
    $sysPy = Get-Command "python" -ErrorAction SilentlyContinue
    if ($sysPy -and ($sysPy.Source -notlike "*\WindowsApps\*")) { $sysPy.Source } else { $null }
}

if ($PyCmd) {
    $pyDiagCode = @"
import importlib, sys
print("Executable:", sys.executable)
print("Python:", sys.version)
for mod in ["torch", "triton", "unsloth", "bitsandbytes", "transformers", "trl", "datasets", "huggingface_hub"]:
    try:
        m = importlib.import_module(mod)
        ver = getattr(m, "__version__", "sin __version__")
        extra = ""
        if mod == "torch":
            extra = f" | cuda_runtime={m.version.cuda} | cuda_available={m.cuda.is_available()}"
            if m.cuda.is_available():
                extra += f" | device={m.cuda.get_device_name(0)}"
        print(f"{mod}: {ver}{extra}")
    except Exception as e:
        print(f"{mod}: NO DISPONIBLE ({type(e).__name__}: {e})")
"@
    $pyOut = (& $PyCmd -c $pyDiagCode 2>&1) -join "`n"
    $pipList = (& $PyCmd -m pip list 2>&1 | Select-String -Pattern "torch|triton|unsloth|bitsandbytes|transformers|trl|xformers|huggingface|gguf") -join "`n"
    Add-Section "PYTHON Y PAQUETES" ($pyOut + "`n`n-- pip list (paquetes clave) --`n" + $pipList)
} else {
    Add-Section "PYTHON Y PAQUETES" "No se encontro ni .venv_win ni python en PATH."
}

# Ultimas lineas de los logs
$LogDir = Join-Path $ProjectRoot "logs_windows"
if (Test-Path $LogDir) {
    $logs = Get-ChildItem -Path $LogDir -Filter "*.log" | Sort-Object LastWriteTime -Descending
    if ($logs.Count -eq 0) {
        Add-Section "LOGS" "La carpeta logs_windows existe pero no contiene archivos .log."
    } else {
        $logText = New-Object System.Text.StringBuilder
        foreach ($l in $logs) {
            [void]$logText.AppendLine("--- $($l.Name) (ultimas 100 lineas) ---")
            $tail = Get-Content -Path $l.FullName -Tail 100 -ErrorAction SilentlyContinue
            [void]$logText.AppendLine(($tail -join "`n"))
            [void]$logText.AppendLine("")
        }
        Add-Section "LOGS" $logText.ToString()
    }
} else {
    Add-Section "LOGS" "Aun no existe la carpeta logs_windows."
}

Set-Content -Path $OutFile -Value $sb.ToString() -Encoding UTF8
Write-Host "Diagnostico guardado en:" -ForegroundColor Green
Write-Host "  $OutFile" -ForegroundColor White
Write-Host "Abre ese archivo, copia su contenido y pegalo al pedir ayuda." -ForegroundColor Yellow
