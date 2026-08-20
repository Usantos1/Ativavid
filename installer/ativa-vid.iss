; ATIVAVID — Inno Setup
; Compile: .\installer\build.ps1
; Saida: installer/dist/Instalar ATIVAVID 2.11.exe
;
; Instala em C:\Program Files\ATIVAVID (como app Windows normal).
; Atalho → ATIVAVID.vbs (sem janela CMD).

#define MyAppName "ATIVAVID"
#define MyAppVersion "2.28"
#define MyAppPublisher "ATIVAVID"
#define MyAppURL "https://github.com/fillrochaa/edvid"
#define MyAppExeName "ATIVAVID.vbs"

[Setup]
AppId={{A7C1D2E3-4F56-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
; Pasta padrao de programa Windows (pede admin uma vez)
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir=dist
OutputBaseFilename=Instalar ATIVAVID {#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
SetupIconFile=..\assets\preview\ativa-vid-icon.ico
UninstallDisplayIcon={app}\assets\preview\ativa-vid-icon.ico
CloseApplications=force
RestartApplications=no
VersionInfoProductName=ATIVAVID
VersionInfoDescription=Instalar ATIVAVID
VersionInfoCompany=ATIVAVID
VersionInfoVersion={#MyAppVersion}
InfoBeforeFile=
UsePreviousAppDir=yes
UsePreviousTasks=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "vendor\ffmpeg\*.exe,vendor\ffmpeg\*.dll,.git,.venv,node_modules,__pycache__,*.pyc,edit,cloud,installer\dist,.env,.ativavid-sessions.json,.pytest_cache,.ativavid-settings.json,ativa_vid.egg-info,Projetos"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: "//nologo ""{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\preview\ativa-vid-icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: "//nologo ""{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\preview\ativa-vid-icon.ico"; Tasks: desktopicon
Name: "{app}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: "//nologo ""{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\preview\ativa-vid-icon.ico"

[Run]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\installer\setup.ps1"" -NoShortcut"; \
  WorkingDir: "{app}"; \
  StatusMsg: "Instalando dependencias (FFmpeg, Node, Python)…"; \
  Flags: runhidden waituntilterminated
; Explorer abre o .lnk na sessão do usuário (igual ao atalho). wscript/cmd
; presos ao Setup morriam no Concluir; runasoriginaluser falhava se o exe
; foi iniciado com "Executar como administrador".
Filename: "{win}\explorer.exe"; \
  Parameters: """{app}\{#MyAppName}.lnk"""; \
  Description: "Abrir ATIVAVID"; \
  Flags: postinstall nowait skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;




