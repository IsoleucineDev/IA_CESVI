#Requires -Version 5.1
<#
  00_verificar_equipo.ps1
  Diagnostico de solo lectura para Windows nativo (sin WSL2).
  Revisa: Windows 10/11 64-bit, GPU/VRAM (nvidia-smi), CUDA del driver,
  Python 3.12 en PATH, espacio en disco (~60 GB) y conexion a huggingface.co.
#>

$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Resolve-ProjectRoot {
    if (Test-Path (Join-Path $PSScriptRoot "train.py")) { return $PSScriptRoot }
    $parent = Split-Path -Parent $PSScriptRoot
    if ($parent -and (Test-Path (Join-Path $parent "train.py"))) { return $parent }
    return $PSScriptRoot
}

$ProjectRoot = Resolve-ProjectRoot
$Checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param([string]$Item, [string]$Estado, [string]$Detalle, [string]$Accion)
    $Checks.Add([PSCustomObject]@{
        Item    = $Item
        Estado  = $Estado
        Detalle = $Detalle
        Accion  = $Accion
    })
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " CESVI - Verificacion del equipo Windows (solo lectura)" -ForegroundColor Cyan
Write-Host " Carpeta del proyecto: $ProjectRoot" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Version de Windows y arquitectura 64 bits
try {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $is64 = [Environment]::Is64BitOperatingSystem
    $is64Proc = [Environment]::Is64BitProcess
    $build = [int]$os.BuildNumber
    $caption = $os.Caption.Trim()
    $isWin10Or11 = ($caption -match "Windows 10|Windows 11") -or ($build -ge 19041)
    if ($is64 -and $isWin10Or11 -and $is64Proc) {
        Add-Check "Sistema operativo" "OK" "$caption (Build $build, 64 bits)" "-"
    } elseif ($is64 -and $isWin10Or11 -and (-not $is64Proc)) {
        Add-Check "Sistema operativo" "FALLA" "$caption 64 bits, pero abriste PowerShell (x86) de 32 bits" "Cierra esta ventana y abre 'Windows PowerShell' de 64 bits (sin '(x86)')."
    } elseif (-not $is64) {
        Add-Check "Sistema operativo" "FALLA" "$caption (32 bits)" "Se requiere Windows 10 u 11 de 64 bits."
    } else {
        Add-Check "Sistema operativo" "FALLA" "$caption (Build $build)" "Actualiza a Windows 10 (build >= 19041) o Windows 11 de 64 bits."
    }
} catch {
    Add-Check "Sistema operativo" "FALLA" "No se pudo consultar Win32_OperatingSystem: $_" "Verifica manualmente en Configuracion -> Sistema -> Acerca de."
}

function Find-NvidiaSmiPath {
    $cmd = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
    if ($cmd -and (Test-Path $cmd.Source)) { return $cmd.Source }

    $candidates = @(
        (Join-Path $env:WINDIR "Sysnative\nvidia-smi.exe"),
        (Join-Path $env:WINDIR "System32\nvidia-smi.exe")
    )
    if ($env:ProgramW6432) {
        $candidates += (Join-Path $env:ProgramW6432 "NVIDIA Corporation\NVSMI\nvidia-smi.exe")
    }
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles "NVIDIA Corporation\NVSMI\nvidia-smi.exe")
    }
    foreach ($p in ($candidates | Select-Object -Unique)) {
        if ($p -and (Test-Path $p)) { return $p }
    }

    foreach ($repo in @(
        (Join-Path $env:WINDIR "Sysnative\DriverStore\FileRepository"),
        (Join-Path $env:WINDIR "System32\DriverStore\FileRepository")
    )) {
        if (Test-Path $repo) {
            $found = Get-ChildItem -Path $repo -Directory -Filter "nv*" -ErrorAction SilentlyContinue |
                ForEach-Object { Join-Path $_.FullName "nvidia-smi.exe" } |
                Where-Object { Test-Path $_ } |
                Select-Object -First 1
            if ($found) { return $found }
        }
    }
    return $null
}

# 2. GPU, VRAM y CUDA del driver (nvidia-smi)
$nvidiaSmiPath = Find-NvidiaSmiPath

if (-not $nvidiaSmiPath) {
    $wmiNv = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "NVIDIA" } | Select-Object -First 1
    if ($wmiNv) {
        Add-Check "GPU NVIDIA (nvidia-smi)" "FALLA" "Windows detecta '$($wmiNv.Name)' (DriverVersion $($wmiNv.DriverVersion)), pero no se encontro nvidia-smi.exe en PATH ni en System32/NVSMI." "Reinicia la PC si acabas de instalar el driver, o reinstala el driver oficial NVIDIA (https://www.nvidia.com/Download/index.aspx)."
    } else {
        Add-Check "GPU NVIDIA (nvidia-smi)" "FALLA" "No se encontro el comando nvidia-smi ni GPU NVIDIA activa en Windows" "Instala el driver NVIDIA oficial (https://www.nvidia.com/Download/index.aspx) y reinicia."
    }
    Add-Check "CUDA del driver" "FALLA" "Sin nvidia-smi no se puede leer la version de CUDA" "Instala primero el driver NVIDIA actualizado y reinicia."
} else {
    $gpuCsv = & $nvidiaSmiPath --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>&1
    $smiFull = (& $nvidiaSmiPath 2>&1) -join "`n"
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace(($gpuCsv -join ""))) {
        $gpuLine = ($gpuCsv | Select-Object -First 1).ToString().Trim()
        Add-Check "GPU NVIDIA y VRAM" "OK" "$gpuLine ($nvidiaSmiPath)" "-"
    } elseif ($smiFull -match "Driver Version:\s*([\d\.]+)") {
        Add-Check "GPU NVIDIA y VRAM" "OK" "Driver $($Matches[1]) detectado por $nvidiaSmiPath" "-"
    } else {
        Add-Check "GPU NVIDIA (nvidia-smi)" "FALLA" "nvidia-smi ($nvidiaSmiPath) devolvio error: $gpuCsv" "Reinstala el driver NVIDIA y reinicia la PC."
    }

    if ($smiFull -match "CUDA Version\s*:\s*(\d+\.\d+)") {
        $cudaVer = $Matches[1]
        Add-Check "CUDA del driver" "OK" "CUDA $cudaVer soportado por el driver" "-"
    } else {
        Add-Check "CUDA del driver" "FALLA" "No se pudo detectar 'CUDA Version' en la salida de $nvidiaSmiPath" "Actualiza el driver NVIDIA a version 550 o superior."
    }
}

# 3. Python 3.12 instalado y en PATH (evitar alias vacio de Microsoft Store)
function Find-Python312 {
    $candidates = @()
    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $p312 = & $pyLauncher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $p312) {
            $candidates += $p312.ToString().Trim()
        }
    }
    $pyCmds = Get-Command "python" -All -ErrorAction SilentlyContinue
    foreach ($cmd in $pyCmds) {
        if ($cmd.Source -and ($cmd.Source -notlike "*\WindowsApps\*")) {
            $candidates += $cmd.Source
        }
    }
    foreach ($exe in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path $exe)) { continue }
        $ver = & $exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{sys.maxsize > 2**32}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver -match "^3\.12\.(\d+)\|True$") {
            return [PSCustomObject]@{ Path = $exe; Version = ($ver -split "\|")[0] }
        }
    }
    return $null
}

$pyInfo = Find-Python312
$inPathPython = Get-Command "python" -ErrorAction SilentlyContinue
$isStoreAliasOnly = ($inPathPython -and ($inPathPython.Source -like "*\WindowsApps\*") -and (-not $pyInfo))

if ($pyInfo) {
    $inPathOk = $false
    if ($inPathPython -and ($inPathPython.Source -notlike "*\WindowsApps\*")) {
        $inPathVer = & $inPathPython.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($inPathVer -eq "3.12") { $inPathOk = $true }
    }
    if ($inPathOk) {
        Add-Check "Python 3.12 (PATH)" "OK" "Python $($pyInfo.Version) en $($pyInfo.Path)" "-"
    } else {
        Add-Check "Python 3.12 (PATH)" "FALLA" "Python $($pyInfo.Version) existe en $($pyInfo.Path), pero 'python' en PATH apunta a otra version o al alias de Windows." "Reinstala Python 3.12 marcando 'Add python.exe to PATH' y cierra/reabre PowerShell."
    }
} elseif ($isStoreAliasOnly) {
    Add-Check "Python 3.12 (PATH)" "FALLA" "'python' apunta al acceso directo vacio de Microsoft Store (WindowsApps)." "Instala Python 3.12 oficial (https://www.python.org/downloads/windows/) marcando 'Add python.exe to PATH', o ejecuta: winget install --id Python.Python.3.12 -e --source winget"
} else {
    $otherPy = ""
    if ($inPathPython -and ($inPathPython.Source -notlike "*\WindowsApps\*")) {
        $otherPy = (& $inPathPython.Source --version 2>&1) -join " "
    }
    $det = if ($otherPy) { "Se encontro '$otherPy', pero se requiere Python 3.12." } else { "Python 3.12 no esta instalado ni en PATH." }
    Add-Check "Python 3.12 (PATH)" "FALLA" $det "Instala Python 3.12 (64-bit) marcando 'Add python.exe to PATH', o ejecuta: winget install --id Python.Python.3.12 -e --source winget"
}

# 4. Git for Windows (necesario para descargar/actualizar con Git Bash)
$gitCmd = Get-Command "git" -ErrorAction SilentlyContinue
if ($gitCmd) {
    $gitVer = (& $gitCmd.Source --version 2>&1) -join " "
    Add-Check "Git for Windows" "OK" $gitVer "-"
} else {
    Add-Check "Git for Windows" "FALLA" "No se encontro el comando git en PATH." "Instala Git for Windows (https://git-scm.com/download/win) o ejecuta: winget install --id Git.Git -e --source winget"
}

# 5. Espacio libre en disco (~60 GB recomendados)
try {
    $driveName = ([System.IO.Path]::GetPathRoot($ProjectRoot)).Substring(0, 1)
    $drive = Get-PSDrive -Name $driveName -ErrorAction Stop
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    if ($freeGB -ge 60) {
        Add-Check "Espacio libre en disco ($driveName`:)" "OK" "$freeGB GB libres (minimo recomendado: 60 GB)" "-"
    } else {
        Add-Check "Espacio libre en disco ($driveName`:)" "FALLA" "Solo hay $freeGB GB libres en $driveName`: (se recomiendan ~60 GB)" "Libera espacio en el disco $driveName`: o mueve la carpeta del proyecto a un disco con >= 60 GB libres."
    }
} catch {
    Add-Check "Espacio libre en disco" "FALLA" "No se pudo consultar el espacio libre: $_" "Verifica manualmente en 'Este equipo' que tengas al menos 60 GB libres."
}

# 6. Conexion a huggingface.co (y URLs clave)
$urls = @(
    @{ Name = "Conexion huggingface.co"; Url = "https://huggingface.co"; Required = $true },
    @{ Name = "Conexion download.pytorch.org"; Url = "https://download.pytorch.org/whl/"; Required = $true },
    @{ Name = "Conexion pypi.org"; Url = "https://pypi.org/simple/"; Required = $true }
)
foreach ($u in $urls) {
    try {
        $resp = Invoke-WebRequest -Uri $u.Url -Method Head -TimeoutSec 12 -UseBasicParsing -ErrorAction Stop
        Add-Check $u.Name "OK" "HTTP $([int]$resp.StatusCode)" "-"
    } catch {
        # Algunos servidores rechazan HEAD; intentar GET ligero
        try {
            $resp2 = Invoke-WebRequest -Uri $u.Url -Method Get -TimeoutSec 12 -UseBasicParsing -MaximumRedirection 5 -ErrorAction Stop
            Add-Check $u.Name "OK" "HTTP $([int]$resp2.StatusCode)" "-"
        } catch {
            Add-Check $u.Name "FALLA" "No hay respuesta desde $($u.Url): $($_.Exception.Message)" "Revisa tu conexion a internet o pide al laboratorio habilitar $($u.Url) (o usa datos/hotspot)."
        }
    }
}

# 7. Verificar archivos del proyecto
$requiredFiles = @("train.py", "gen_dataset.py", "make_modelfile.py")
$missing = @()
foreach ($f in $requiredFiles) {
    if (-not (Test-Path (Join-Path $ProjectRoot $f))) { $missing += $f }
}
if ($missing.Count -eq 0) {
    Add-Check "Archivos del proyecto" "OK" "train.py, gen_dataset.py y make_modelfile.py presentes" "-"
} else {
    Add-Check "Archivos del proyecto" "FALLA" "Faltan: $($missing -join ', ') en $ProjectRoot" "Copia la carpeta COMPLETA del proyecto desde el USB, no solo entrega_windows."
}

# Mostrar resumen
Write-Host "RESUMEN DE VERIFICACION:" -ForegroundColor White
Write-Host ""
$fallas = 0
foreach ($c in $Checks) {
    if ($c.Estado -eq "OK") {
        Write-Host ("[OK]    {0}: {1}" -f $c.Item, $c.Detalle) -ForegroundColor Green
    } else {
        $fallas++
        Write-Host ("[FALLA] {0}: {1}" -f $c.Item, $c.Detalle) -ForegroundColor Red
        Write-Host ("        -> Accion: {0}" -f $c.Accion) -ForegroundColor Yellow
    }
}

Write-Host ""
if ($fallas -eq 0) {
    Write-Host "RESULTADO: Todo listo. Siguiente paso: .\01_setup_env.ps1" -ForegroundColor Green
    exit 0
} else {
    Write-Host "RESULTADO: Se detectaron $fallas punto(s) con FALLA. Corrige lo indicado en amarillo y vuelve a ejecutar .\00_verificar_equipo.ps1." -ForegroundColor Red
    exit 1
}
