# Instalador do Agente de Carreira (RF-EV-23): um clique, mesmo num computador sem Python.
# Instala o uv (se faltar), o Python e os pacotes do projeto, o navegador do agente, cria o atalho e abre o app.
# Use: clique duas vezes em instalar.cmd. Com -Verificar, só confere o que já está pronto (não instala nada).
param([switch]$Verificar)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $raiz

function Passo($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Falha($texto) { Write-Host ""; Write-Host "Não deu certo: $texto" -ForegroundColor Red; Read-Host "Aperte Enter para fechar"; exit 1 }

Write-Host "Agente de Carreira - instalação" -ForegroundColor Green
Write-Host "Pasta: $raiz"

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    $local = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path $local) { $uv = $local }
}
if ($Verificar) {
    Write-Host ("uv: " + $(if ($uv) { "instalado" } else { "falta (será instalado)" }))
    Write-Host ("ambiente do projeto (.venv): " + $(if (Test-Path (Join-Path $raiz ".venv")) { "pronto" } else { "falta" }))
    Write-Host ("pyproject.toml: " + $(if (Test-Path (Join-Path $raiz "pyproject.toml")) { "ok" } else { "NÃO ENCONTRADO" }))
    exit 0
}

if (-not $uv) {
    Passo "Instalando o uv (gerenciador do Python, da Astral)"
    try { powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex" }
    catch { Falha "não consegui instalar o uv. Confira a internet e tente de novo." }
    $env:Path = (Join-Path $env:USERPROFILE ".local\bin") + ";" + $env:Path
    $uv = "uv"
}

Passo "Instalando o Python e os pacotes do agente (alguns minutos na primeira vez)"
& $uv sync
if ($LASTEXITCODE -ne 0) { Falha "o 'uv sync' terminou com erro." }

Passo "Instalando o navegador do agente (Chromium)"
& $uv run playwright install chromium
if ($LASTEXITCODE -ne 0) { Falha "não consegui instalar o navegador do agente." }

Passo "Criando o atalho na Área de Trabalho"
& $uv run agente atalho
if ($LASTEXITCODE -ne 0) { Write-Host "O atalho não foi criado; abra pelo comando 'uv run agente app'." -ForegroundColor Yellow }

Passo "Abrindo o app"
& $uv run agente app
Write-Host ""
Write-Host "Pronto! Da próxima vez, abra pelo atalho 'Agente de Carreira' na Área de Trabalho." -ForegroundColor Green
Write-Host "No app, comece por 'Trazer seu currículo'."
Start-Sleep -Seconds 8
