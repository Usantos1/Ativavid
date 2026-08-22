# ATIVAVID Local - bootstrap Windows
# Installs deps (winget), syncs Python (uv sync), embeds FFmpeg if needed,
# creates Desktop shortcut (ATIVAVID.vbs - no CMD window).
#
# Usage:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\installer\setup.ps1
#
# Flags:
#   -SkipWinget   skip winget installs
#   -NoShortcut   do not create desktop shortcut
#   -ForceFfmpeg  re-download vendor FFmpeg even if ffmpeg is on PATH

param(
  [switch]$SkipWinget,
  [switch]$NoShortcut,
  [switch]$ForceFfmpeg
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

function Write-Step([string]$msg) {
  Write-Host ""
  Write-Host "==> $msg" -ForegroundColor Cyan
}

function Test-Cmd([string]$name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Ensure-VendorFfmpeg {
  param([switch]$Force)

  $vendorDir = Join-Path $Repo "vendor\ffmpeg"
  $vendorExe = Join-Path $vendorDir "ffmpeg.exe"
  if ((Test-Path $vendorExe) -and -not $Force) {
    Write-Host "OK: FFmpeg embutido em vendor\ffmpeg"
    return
  }
  if ((Test-Cmd "ffmpeg") -and -not $Force) {
    Write-Host "OK: ffmpeg ja no PATH (vendor opcional)"
    return
  }

  Write-Step "Baixando FFmpeg essentials para vendor\ffmpeg"
  $tmp = Join-Path $env:TEMP ("ativavid-ffmpeg-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $zip = Join-Path $tmp "ffmpeg.zip"
  $url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
  } catch {
    Write-Host "Falha ao baixar FFmpeg: $_" -ForegroundColor Yellow
    Write-Host "Instale manualmente (winget install Gyan.FFmpeg) ou coloque ffmpeg.exe em vendor\ffmpeg" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    return
  }

  Expand-Archive -Path $zip -DestinationPath $tmp -Force
  $bin = Get-ChildItem -Path $tmp -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
  if (-not $bin) {
    Write-Host "Zip sem ffmpeg.exe - abortando vendor" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    return
  }
  $srcBin = $bin.Directory.FullName
  New-Item -ItemType Directory -Force -Path $vendorDir | Out-Null
  foreach ($name in @("ffmpeg.exe", "ffprobe.exe", "ffplay.exe")) {
    $f = Join-Path $srcBin $name
    if (Test-Path $f) {
      Copy-Item -Force $f (Join-Path $vendorDir $name)
    }
  }
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  if (Test-Path $vendorExe) {
    Write-Host "OK: FFmpeg em $vendorDir"
  } else {
    Write-Host "Vendor FFmpeg incompleto" -ForegroundColor Yellow
  }
}

Write-Step "ATIVAVID Local - instalacao"
Write-Host "Pasta: $Repo"

if (-not $SkipWinget) {
  if (-not (Test-Cmd "winget")) {
    Write-Host "winget nao encontrado. Instale App Installer da Microsoft Store, ou use -SkipWinget." -ForegroundColor Yellow
  } else {
    $pkgs = @(
      @{ Id = "Git.Git"; Name = "git" },
      @{ Id = "astral-sh.uv"; Name = "uv" },
      @{ Id = "Gyan.FFmpeg"; Name = "ffmpeg" },
      @{ Id = "OpenJS.NodeJS.LTS"; Name = "node" }
    )
    foreach ($p in $pkgs) {
      if (Test-Cmd $p.Name) {
        Write-Host "OK: $($p.Name) ja no PATH"
      } else {
        Write-Step "Instalando $($p.Id) via winget"
        winget install --id $p.Id -e --accept-package-agreements --accept-source-agreements
      }
    }
    Write-Host ""
    Write-Host "Se algum pacote acabou de instalar, FECHE e reabra o PowerShell para o PATH atualizar." -ForegroundColor Yellow
  }
}

Ensure-VendorFfmpeg -Force:$ForceFfmpeg

if (-not (Test-Cmd "uv")) {
  Write-Host "uv nao encontrado no PATH. Instale: https://docs.astral.sh/uv/" -ForegroundColor Red
  exit 1
}

Write-Step "uv sync (dependencias Python)"
uv sync --extra transcricao --directory $Repo

$Projects = Join-Path $env:USERPROFILE "ATIVAVID\Projetos"
New-Item -ItemType Directory -Force -Path $Projects | Out-Null
$Lib = Join-Path $env:USERPROFILE "ATIVAVID\Biblioteca"
New-Item -ItemType Directory -Force -Path $Lib | Out-Null
Write-Host "Projetos: $Projects"
Write-Host "Biblioteca B-roll: $Lib"

if (-not $NoShortcut) {
  Write-Step "Atalho na Area de Trabalho (sem CMD)"
  $Desktop = [Environment]::GetFolderPath("Desktop")
  $ShortcutPath = Join-Path $Desktop "ATIVAVID Local.lnk"
  $Wsh = New-Object -ComObject WScript.Shell
  $Sc = $Wsh.CreateShortcut($ShortcutPath)
  $Vbs = Join-Path $Repo "ATIVAVID.vbs"
  $Sc.TargetPath = Join-Path $env:SystemRoot "System32\wscript.exe"
  $Sc.Arguments = '//nologo "' + $Vbs + '"'
  $Sc.WorkingDirectory = $Repo
  $Sc.WindowStyle = 7
  $Sc.Description = "ATIVAVID Local - editar videos com 1 clique"
  $Icon = Join-Path $Repo "assets\preview\ativa-vid-icon.ico"
  if (Test-Path $Icon) { $Sc.IconLocation = "$Icon,0" }
  $Sc.Save()
  Write-Host "Criado: $ShortcutPath"
}

Write-Step "Pronto"
Write-Host "1. Duplo clique em ATIVAVID Local na Area de Trabalho (sem janela CMD)"
Write-Host "2. Cole a GROQ_API_KEY em Chaves (primeira vez)"
Write-Host "3. Ajuste Estilo da marca e importe videos"
Write-Host ""
Write-Host "Diagnostico (com console): .\ATIVAVID.cmd"
Write-Host "Atualizar depois: rode de novo .\installer\setup.ps1"
