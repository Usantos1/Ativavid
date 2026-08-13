# ATIVAVID Session (extensão)

Mantém cookies do Gemini/ChatGPT sincronizados com o ATIVAVID local (`http://127.0.0.1:4850`).

## Pasta correta (não some no update)

`%USERPROFILE%\ATIVAVID\extension\llm-session`

No app: **Chaves & IA** → **Abrir pasta da extensão**.

## Instalar / atualizar

1. `chrome://extensions` → Modo do desenvolvedor
2. **Carregar sem compactação** → pasta acima  
   (se já tinha apontando para Program Files: remova e carregue de novo)
3. Clique em **Recarregar** na extensão após cada update do ATIVAVID
4. **Fixe o ícone** na barra (quebra-cabeça → pin) para não “sumir”
5. Deixe o ATIVAVID no ar (o **X** manda para a bandeja — não encerra o servidor)

## Como funciona (v0.1.3+)

- Worker em segundo plano captura sozinho ao abrir ChatGPT/Gemini logado
- Reenvia a cada ~2 minutos
- Se o ATIVAVID estiver fechado, **guarda na fila** e manda quando o app voltar
- Badge **ON** = última sincronização ok
- Cookies salvos no PC: `%USERPROFILE%\ATIVAVID\sessions.json`

## Privacidade

- Cookies só vão para `127.0.0.1`
- Não compartilhe `sessions.json` entre PCs
