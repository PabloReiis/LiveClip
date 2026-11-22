# LiveClipAI V2 - instalador local Windows. Execute na pasta clonada do GitHub.
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $raiz

if (-not (Test-Path (Join-Path $raiz 'studio\server.py')) -or -not (Test-Path (Join-Path $raiz 'requirements.txt'))) {
    throw 'Execute este instalador dentro da pasta principal do LiveClipAI (studio/server.py e requirements.txt necessarios).'
}

Write-Host '\n[1/5] Procurando Python 3.11...' -ForegroundColor Cyan
$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.11 -c 'import sys; assert sys.version_info[:2] == (3, 11)' 2>$null
    if ($LASTEXITCODE -eq 0) { $py = 'py' }
}
if (-not $py) {
    Write-Host 'Python 3.11 nao encontrado. Instale Python 3.11 de https://www.python.org/downloads/ e marque Add Python to PATH.' -ForegroundColor Yellow
    exit 1
}

Write-Host '[2/5] Criando ambiente virtual local...' -ForegroundColor Cyan
$pythonVenv = Join-Path $raiz '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonVenv)) {
    & py -3.11 -m venv (Join-Path $raiz '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel criar o ambiente virtual.' }
}

Write-Host '[3/5] Instalando dependencias Python (pode baixar arquivos grandes)...' -ForegroundColor Cyan
& $pythonVenv -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Falha ao atualizar pip.' }
& $pythonVenv -m pip install -r (Join-Path $raiz 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar requirements.txt. Confira a mensagem acima.' }

Write-Host '[4/5] Preparando dados e configuracao isolados desta maquina...' -ForegroundColor Cyan
@('data','data\models','data\users','data\tmp') | ForEach-Object {
    New-Item -ItemType Directory -Path (Join-Path $raiz $_) -Force | Out-Null
}
$envFile = Join-Path $raiz '.env'
if (-not (Test-Path $envFile)) {
    @'
# Credenciais de APIs sao individuais. Preencha conforme README/.env.example.
# Os arquivos e dados ficam no proprio computador, na pasta data.
PEAKCUT_HOST=127.0.0.1
PEAKCUT_PORT=8767
'@ | Set-Content -LiteralPath $envFile -Encoding UTF8
}

Write-Host '[5/5] Conferindo ferramentas externas...' -ForegroundColor Cyan
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host 'FFmpeg: OK' -ForegroundColor Green
} else {
    Write-Host 'FFmpeg nao encontrado no PATH. Instale: https://ffmpeg.org/download.html (necessario para gerar videos).' -ForegroundColor Yellow
}
if (Get-Command deno -ErrorAction SilentlyContinue) {
    Write-Host 'Deno: OK' -ForegroundColor Green
} else {
    Write-Host 'Deno nao encontrado no PATH. Instale: https://docs.deno.com/runtime/getting_started/installation/ (recomendado para yt-dlp/YouTube).' -ForegroundColor Yellow
}
Write-Host '\nInstalacao Python concluida. Complete as configuracoes de API em .env e execute INICIAR_WINDOWS.bat.' -ForegroundColor Green
