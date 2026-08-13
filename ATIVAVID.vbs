' ATIVAVID — abre a janela nativa SEM nenhuma janela CMD.
' Atalho da Area de Trabalho aponta para este arquivo.

Option Explicit
Dim sh, fso, root, vendor, userFf, pyw, cmd, pathNow, localBin, wingetLinks, uvDir

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root

pathNow = sh.Environment("PROCESS")("PATH")

vendor = root & "\vendor\ffmpeg"
If fso.FileExists(vendor & "\ffmpeg.exe") Then
  pathNow = vendor & ";" & pathNow
End If

' FFmpeg na pasta do usuario (gravavel sem admin)
userFf = sh.ExpandEnvironmentStrings("%USERPROFILE%\ATIVAVID\ffmpeg")
If fso.FileExists(userFf & "\ffmpeg.exe") Then
  pathNow = userFf & ";" & pathNow
End If

' uv/node instalados pelo winget costumam ficar fora do PATH do wscript
localBin = sh.ExpandEnvironmentStrings("%USERPROFILE%\.local\bin")
If fso.FolderExists(localBin) Then pathNow = localBin & ";" & pathNow

wingetLinks = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Microsoft\WinGet\Links")
If fso.FolderExists(wingetLinks) Then pathNow = wingetLinks & ";" & pathNow

uvDir = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\uv")
If fso.FolderExists(uvDir) Then pathNow = uvDir & ";" & pathNow

If fso.FolderExists("C:\Program Files\nodejs") Then
  pathNow = "C:\Program Files\nodejs;" & pathNow
End If

sh.Environment("PROCESS")("PATH") = pathNow

' So pythonw (sem console). Nunca "uv run" no atalho — uv abre CMD.
pyw = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then
  MsgBox "ATIVAVID ainda nao terminou a instalacao." & vbCrLf & vbCrLf & _
    "Feche e abra o instalador de novo, ou aguarde a primeira instalacao concluir." & vbCrLf & vbCrLf & _
    "Ou no PowerShell (nesta pasta):" & vbCrLf & _
    ".\installer\setup.ps1 -NoShortcut", _
    vbExclamation, "ATIVAVID"
  WScript.Quit 1
End If

' 0 = janela oculta; False = nao espera
cmd = """" & pyw & """ -X utf8 """ & root & "\app\launcher.py"""
sh.Run cmd, 0, False
