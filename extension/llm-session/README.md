# ATIVAVID Session (extensão)

Captura cookies da **sua** sessão nos sites de LLM e envia ao ATIVAVID local (`http://127.0.0.1:4850`).

## Instalar / atualizar no Chrome ou Edge

1. Abra `chrome://extensions` (ou `edge://extensions`)
2. Ative **Modo do desenvolvedor**
3. **Carregar sem compactação** → pasta `extension/llm-session`
   - Se já estava instalada: **Atualizar** (ícone de reload) ou remova e carregue de novo
4. Deixe o **ATIVAVID aberto** (atalho da Área de Trabalho)
5. Abra Gemini / ChatGPT **já logado** na mesma janela do navegador
6. Clique no ícone da extensão → capture o provedor

### Se der “sessão incompleta”

- Use o **mesmo Chrome/Edge** onde a extensão está (não outro perfil)
- Aba do Gemini/ChatGPT precisa estar aberta e logada
- Clique Capturar de novo depois da página carregar
- A v0.1.1 lê cookies **particionados** (Chrome novo) — atualize a pasta se ainda for 0.1.0

## Privacidade

- Cookies só vão para `127.0.0.1` (app local)
- **Não compartilhe** `.ativavid-sessions.json` nem cookies entre PCs — cada máquina captura a própria conta
