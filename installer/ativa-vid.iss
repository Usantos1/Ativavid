; ATIVAVID — Inno Setup
; Compile: .\installer\build.ps1
; Saida: installer/dist/Instalar ATIVAVID 2.11.exe
;
; Instala em C:\Program Files\ATIVAVID (como app Windows normal).
; Atalho → ATIVAVID.vbs (sem janela CMD).

#define MyAppName "ATIVAVID"
#define MyAppVersion "3.61"
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
; `auto`: em ATUALIZACAO (ja instalado) a pagina de pasta some; na primeira
; instalacao ela continua aparecendo, que e quando a escolha importa.
DisableDirPage=auto
; O app atualiza sozinho e o instalador roda em silencio — perguntar o
; idioma no meio disso era etapa a toa. Quem abre o .exe na mao tambem
; nao ve mais a pergunta: usa o primeiro idioma da lista (pt-BR).
ShowLanguageDialog=no
OutputDir=dist
; Pontos, não espaços: ao subir o asset o GitHub troca espaço por ponto, então
; o arquivo publicado vira "Instalar.ATIVAVID.x.y.exe" — que é exatamente o
; nome para onde o download_url do gate de atualização aponta. Gerar já com o
; nome final evita ter um arquivo local com um nome e o do cliente com outro.
OutputBaseFilename=Instalar.ATIVAVID.{#MyAppVersion}
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
; `results` e `bench` sao saida de MEDICAO, nao produto: 34 MB de PNG de
; quadros que nao servem de nada na maquina de quem usa o app. Entraram no
; instalador quando o benchmark de render foi commitado, porque o Source e
; `..\*` recursivo.
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "vendor\ffmpeg\*.exe,vendor\ffmpeg\*.dll,.git,.venv,node_modules,__pycache__,*.pyc,edit,cloud,installer\dist,.env,.ativavid-sessions.json,.pytest_cache,.ativavid-settings.json,ativa_vid.egg-info,Projetos,tools\render_benchmark\results,bench"

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
; A entrada abaixo NAO leva `skipifsilent`: a atualizacao roda em
; /VERYSILENT e o app TEM de voltar sozinho — senao o usuario clica
; "Atualizar" e o app some.
; Explorer abre o .lnk na sessão do usuário (igual ao atalho). wscript/cmd
; presos ao Setup morriam no Concluir; runasoriginaluser falhava se o exe
; foi iniciado com "Executar como administrador".
Filename: "{win}\explorer.exe"; \
  Parameters: """{app}\{#MyAppName}.lnk"""; \
  Description: "Abrir ATIVAVID"; \
  Flags: postinstall nowait

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// Instalar por cima do app ABERTO deixava o servidor Python velho na memoria:
// as telas (lidas do disco) mostravam os campos novos, o servidor ignorava os
// campos que nao conhecia, e "instalei mas continua igual" (caso real, 24/08:
// o modo de edicao chegou no payload e nao foi gravado). CloseApplications
// nao pega: pythonw le os .py e fecha, o Restart Manager nao ve nada.
// Entao: derrubar os processos do app ANTES de copiar. So os que tem o
// diretorio de instalacao na linha de comando — e nunca o proprio PowerShell
// (a propria cmdline contem o caminho; sem o filtro de $PID ele se mataria
// no meio do trabalho).
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  R: Integer;
  Cmd: String;
begin
  Cmd := '-NoProfile -Command "Get-CimInstance Win32_Process | ' +
         'Where-Object { ($_.Name -match ''^(python|pythonw|wscript|node|ffmpeg)'') ' +
         '-and $_.CommandLine -like ''*' + ExpandConstant('{app}') + '*'' ' +
         '-and $_.ProcessId -ne $PID } | ' +
         'ForEach-Object { Stop-Process -Id $_.ProcessId -Force ' +
         '-ErrorAction SilentlyContinue }"';
  Exec('powershell.exe', Cmd, '', SW_HIDE, ewWaitUntilTerminated, R);
  Result := '';
end;




