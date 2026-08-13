' ATIVAVID — abre a janela nativa SEM nenhuma janela CMD.
' Atalho da Area de Trabalho aponta para este arquivo.

Option Explicit
Dim sh, fso, root, vendor, userFf, pyw, cmd

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root

vendor = root & "\vendor\ffmpeg"
If fso.FileExists(vendor & "\ffmpeg.exe") Then
  sh.Environment("PROCESS")("PATH") = vendor & ";" & sh.Environment("PROCESS")("PATH")
End If

' FFmpeg na pasta do usuario (gravavel sem admin)
userFf = sh.ExpandEnvironmentStrings("%USERPROFILE%\ATIVAVID\ffmpeg")
If fso.FileExists(userFf & "\ffmpeg.exe") Then
  sh.Environment("PROCESS")("PATH") = userFf & ";" & sh.Environment("PROCESS")("PATH")
End If

' So pythonw (sem console). Nunca "uv run" no atalho — uv abre CMD.
pyw = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then
  MsgBox "ATIVAVID ainda nao terminou a instalacao." & vbCrLf & vbCrLf & _
    "Feche e abra o instalador de novo, ou aguarde a primeira instalacao concluir.", _
    vbExclamation, "ATIVAVID"
  WScript.Quit 1
End If

' 0 = janela oculta; False = nao espera
cmd = """" & pyw & """ -X utf8 """ & root & "\app\launcher.py"""
sh.Run cmd, 0, False
