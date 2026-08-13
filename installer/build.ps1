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
