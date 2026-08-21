# Compila o instalador .exe (Inno Setup 6).
# Saida: installer/dist/Instalar ATIVAVID <versao>.exe
# Se o Inno nao estiver instalado, tenta winget install.

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Iss = Join-Path $Root "ativa-vid.iss"
$Out = Join-Path $Root "dist"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

function Find-Iscc {
  $candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe"
  )
  return $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

function Read-AppVersion {
  $verFile = Join-Path (Split-Path $Root -Parent) "VERSION"
  if (Test-Path $verFile) {
    $v = (Get-Content $verFile -Raw).Trim()
    if ($v) { return $v }
  }
  $line = Select-String -Path $Iss -Pattern '#define MyAppVersion "([^"]+)"' | Select-Object -First 1
  if ($line) { return $line.Matches[0].Groups[1].Value }
  return "0.0.0"
}

$iscc = Find-Iscc
if (-not $iscc) {
  Write-Host "Inno Setup 6 nao encontrado - tentando winget..." -ForegroundColor Yellow
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
    $iscc = Find-Iscc
  }
}

if (-not $iscc) {
  Write-Host "Instale Inno Setup 6: https://jrsoftware.org/isinfo.php" -ForegroundColor Red
  Write-Host "Enquanto isso, rode: .\installer\setup.ps1 (atalho sem CMD ja funciona)"
  exit 2
}

# A build de venda precisa da config de licenca embutida. Sem ela o app sobe
# BLOQUEADO no cliente (fail-closed) — melhor barrar aqui do que descobrir
# depois que o instalador saiu sem gate nenhum.
$licCfg = Join-Path (Split-Path $Root -Parent) "license_config.json"
if (-not (Test-Path $licCfg)) {
  Write-Host "Falta license_config.json na raiz do repo." -ForegroundColor Red
  Write-Host "Copie license_config.example.json e preencha supabaseUrl + anon key (nunca a service role)."
  exit 3
}
try {
  $cfg = Get-Content $licCfg -Raw | ConvertFrom-Json
} catch {
  Write-Host "license_config.json nao e JSON valido." -ForegroundColor Red
  exit 3
}
foreach ($campo in @("supabaseUrl", "supabaseAnonKey")) {
  if (-not $cfg.$campo) {
    Write-Host "license_config.json sem '$campo'." -ForegroundColor Red
    exit 3
  }
}
if ($cfg.PSObject.Properties.Name -contains "supabaseServiceRoleKey") {
  Write-Host "license_config.json contem service role — NUNCA embutir no cliente." -ForegroundColor Red
  exit 3
}
if (-not $cfg.cacheSecret -or $cfg.cacheSecret.Length -lt 16) {
  Write-Host "license_config.json sem 'cacheSecret' forte (>=16 chars)." -ForegroundColor Red
  Write-Host "Gere um: py -c ""import secrets; print(secrets.token_urlsafe(32))"""
  exit 3
}
if (-not $cfg.checkoutUrl) {
  Write-Host "Aviso: checkoutUrl vazio — o botao Assinar fica escondido para o cliente." -ForegroundColor Yellow
}

$ver = Read-AppVersion
$expectedName = "Instalar ATIVAVID $ver.exe"

# Remove nomes antigos / duplicados na dist (so fica a build nova)
Get-ChildItem $Out -Filter "*.exe" -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host "Compilando com $iscc (saida: $expectedName)"
& $iscc $Iss
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$setup = Get-ChildItem $Out -Filter $expectedName | Select-Object -First 1
if (-not $setup) {
  $setup = Get-ChildItem $Out -Filter "Instalar ATIVAVID*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}
if (-not $setup) {
  Write-Host "Instalador nao encontrado em $Out" -ForegroundColor Red
  exit 1
}
$sizeMb = [math]::Round($setup.Length / 1MB, 1)
Write-Host ("OK: {0} ({1} MB)" -f $setup.FullName, $sizeMb) -ForegroundColor Green
