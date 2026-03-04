# VOXOPS AI Gateway — Windows Startup Script
# Run this from the project root: .\scripts\start_backend.ps1

param(
    [switch]$Seed   # pass -Seed to also seed the database on first run
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  VOXOPS AI Gateway — Backend Launcher  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $ProjectRoot

# ── Find Python ──────────────────────────────────────────────
$PythonExe = $null

# 1. Try project .venv (preferred)
$VenvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    $PythonExe = $VenvPy
    Write-Host "[+] Using .venv: $VenvPy" -ForegroundColor Green
} else {
    # 2. Try venv/
    $VenvPy2 = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    if (Test-Path $VenvPy2) {
        $PythonExe = $VenvPy2
        Write-Host "[+] Using venv: $VenvPy2" -ForegroundColor Green
    } else {
        # 3. Fallback to system python
        try {
            $PythonExe = (Get-Command python -ErrorAction Stop).Source
            Write-Host "[+] Using system python: $PythonExe" -ForegroundColor Yellow
        } catch {
            Write-Host "[!] Python not found. Install Python 3.10+ and re-run." -ForegroundColor Red
            exit 1
        }
    }
}

# ── Check .env ─────────────────────────────────────────────
$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[!] .env file not found at $EnvFile" -ForegroundColor Red
    exit 1
}
Write-Host "[+] .env found." -ForegroundColor Green

# ── Install / verify dependencies ────────────────────────────
Write-Host ""
Write-Host "[*] Verifying dependencies..." -ForegroundColor Cyan
& $PythonExe -m pip install -q -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] pip install failed. Check requirements.txt." -ForegroundColor Red
    exit 1
}
Write-Host "[+] Dependencies OK." -ForegroundColor Green

# ── Seed database (optional) ─────────────────────────────────
if ($Seed) {
    Write-Host ""
    Write-Host "[*] Seeding database..." -ForegroundColor Cyan
    & $PythonExe (Join-Path $ProjectRoot "scripts\seed_database.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] Database seeding failed." -ForegroundColor Yellow
        # Non-fatal — continue
    } else {
        Write-Host "[+] Database seeded." -ForegroundColor Green
    }
}

# ── Load port from .env ───────────────────────────────────────
$Port = 8000
$EnvContent = Get-Content $EnvFile
foreach ($line in $EnvContent) {
    if ($line -match "^\s*APP_PORT\s*=\s*(\d+)") {
        $Port = [int]$Matches[1]
        break
    }
}

# ── Start server ──────────────────────────────────────────────
Write-Host ""
Write-Host "[*] Starting VOXOPS backend on http://localhost:$Port" -ForegroundColor Cyan
Write-Host "    Voice client : file://$(Join-Path $ProjectRoot 'frontend\voice_client\index.html')" -ForegroundColor DarkCyan
Write-Host "    Agent dashboard: file://$(Join-Path $ProjectRoot 'frontend\agent_dashboard\dashboard.html')" -ForegroundColor DarkCyan
Write-Host "    Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

$env:PYTHONPATH = $ProjectRoot
& $PythonExe (Join-Path $ProjectRoot "main.py")
