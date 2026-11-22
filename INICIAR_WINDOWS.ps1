# Inicia o LiveClipAI usando o Python e os dados LOCAIS desta instalacao.
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $raiz '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Ambiente Python ausente. Rode INSTALAR_WINDOWS.ps1 primeiro.' }
if (-not (Test-Path (Join-Path $raiz 'studio\server.py'))) { throw 'studio/server.py nao encontrado.' }
$data = Join-Path $raiz 'data'
New-Item -ItemType Directory -Force -Path $data | Out-Null
$env:PEAKCUT_DATA = $data
$env:PEAKCUT_MODELS = Join-Path $data 'models'
$env:PEAKCUT_HOST = '127.0.0.1'
$env:PEAKCUT_PORT = '8767'
$env:PEAKCUT_PUBLIC_URL = 'http://127.0.0.1:8767'
$env:DATABASE_URL = 'sqlite:///' + ((Join-Path $data 'peakcut.db') -replace '\\','/')
$env:PYTHONDONTWRITEBYTECODE = '1'
Write-Host 'LiveClipAI V2 - http://127.0.0.1:8767 (Ctrl+C para parar)' -ForegroundColor Green
Set-Location $raiz
& $python -B -m uvicorn studio.server:app --host 127.0.0.1 --port 8767
if ($LASTEXITCODE -ne 0) { throw "O servidor encerrou com codigo $LASTEXITCODE" }
