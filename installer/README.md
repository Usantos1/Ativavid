# ATIVAVID — instalador

App Windows: arraste o vídeo → 1 clique → `final.mp4`. Uso diário **sem janela CMD**.

## Baixar

Arquivo: [`Instalar ATIVAVID.exe`](dist/Instalar%20ATIVAVID.exe) (v0.1.21)

1. Execute o instalador (pede admin uma vez)
2. Destino padrão: `C:\Program Files\ATIVAVID`
3. Atalho **ATIVAVID** → `ATIVAVID.vbs` (sem console)

## Gerar o .exe (dev)

Requer [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```powershell
.\installer\build.ps1
```

Saída: `installer/dist/Instalar ATIVAVID.exe`

## Sem Inno (só atalho na máquina de desenvolvimento)

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\installer\setup.ps1
```

## Como o app abre

| Arquivo | Uso |
|---------|-----|
| `ATIVAVID.vbs` | Padrão — atalho e pós-instalação |
| `ATIVAVID.cmd` | Só diagnóstico (pode mostrar console) |

## Primeiro uso

1. Abrir pelo atalho
2. **Chaves & IA** → `GROQ_API_KEY` (e demais se precisar)
3. **Estilos** → `@marca` no end card
4. **Licença** → ativar chave (se o gate estiver ligado)
5. Arrastar vídeos verticais 9:16

Projetos: `%USERPROFILE%\ATIVAVID\Projetos\`
