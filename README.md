# edvid

Editor de vídeo por conversa. Você joga o material bruto numa pasta, abre seu
agente ali dentro e diz *"edita isso num vídeo de lançamento"*. Ele transcreve,
escolhe as melhores tomadas, corta os silêncios, aplica a correção de cor e te
mostra o resultado para aprovação — depois disso entram legendas, gráficos e
trilha.

Funciona em **short-form vertical** (Reels/TikTok/Shorts) e **longform
horizontal** (YouTube).

---

## Instalação

> **A instalação é feita por você, no seu terminal.** Não peça para o agente
> instalar a partir do link do GitHub — ele vai recusar, e com razão: nenhum
> agente deve baixar e executar código de um repositório desconhecido por conta
> própria. Cole os comandos abaixo você mesmo. Leva uns 5 minutos.

Depois de instalada, o agente ajuda com o resto (chave de API, verificação,
problemas de PATH) — aí é tudo local e não tem recusa nenhuma.

### Windows

Abra o **PowerShell** (não o Prompt de Comando antigo — os comandos abaixo não
funcionam nele).

**1. Instale os pré-requisitos:**

```powershell
winget install Git.Git astral-sh.uv Gyan.FFmpeg OpenJS.NodeJS.LTS
```

**2. Feche e reabra o PowerShell.** Isso não é opcional: o Windows só enxerga os
programas recém-instalados numa janela nova.

**Confira antes de seguir.** Este comando tem que responder as quatro versões:

```powershell
git --version; uv --version; ffmpeg -version | Select-Object -First 1; node --version
```

Se algum dos quatro disser *"não é reconhecido"*, o passo 1 não terminou ou você
não reabriu a janela. Resolva antes de continuar — os passos seguintes vão
falhar de um jeito bem menos claro.

**3. Baixe a skill:**

```powershell
git clone https://github.com/fillrochaa/edvid "$env:USERPROFILE\.claude\skills\edvid"
```

**4. Instale as dependências Python:**

```powershell
uv sync --directory "$env:USERPROFILE\.claude\skills\edvid"
```

Cole os comandos exatamente como estão. O `$env:USERPROFILE` é uma variável que
o PowerShell troca sozinho pelo caminho da sua pasta de usuário — não edite nada.

### macOS

Abra o **Terminal** (Aplicativos → Utilitários).

**1. Instale o Homebrew**, se você ainda não tem. O comando está em
[brew.sh](https://brew.sh).

**2. Instale os pré-requisitos:**

```bash
brew install git uv ffmpeg node
```

**Confira antes de seguir.** Este comando tem que responder as quatro versões:

```bash
git --version; uv --version; ffmpeg -version | head -1; node --version
```

Se algum disser *"command not found"*, resolva antes de continuar.

**3. Baixe a skill:**

```bash
git clone https://github.com/fillrochaa/edvid "$HOME/.claude/skills/edvid"
```

**4. Instale as dependências Python:**

```bash
uv sync --directory "$HOME/.claude/skills/edvid"
```

Cole os comandos exatamente como estão — o `$HOME` é uma variável que o Terminal
troca sozinho pelo caminho da sua pasta de usuário.

### Linux

Igual ao macOS, trocando o passo 2 pelo gerenciador da sua distro
(`apt install git ffmpeg nodejs`, `pacman -S git ffmpeg nodejs`) e instalando o
`uv` pelo instalador oficial em [astral.sh/uv](https://docs.astral.sh/uv/).

---

## Chave do Groq (obrigatória)

A transcrição roda no Groq Whisper. Sem essa chave nada funciona, porque a
edição inteira parte do texto do que foi falado.

Pegue uma chave gratuita em
[console.groq.com/keys](https://console.groq.com/keys) e grave num arquivo
`.env` dentro da pasta da skill:

**Windows (PowerShell):**

```powershell
Set-Content -Path "$env:USERPROFILE\.claude\skills\edvid\.env" -Value "GROQ_API_KEY=cole_sua_chave_aqui"
```

**macOS / Linux:**

```bash
echo "GROQ_API_KEY=cole_sua_chave_aqui" > "$HOME/.claude/skills/edvid/.env"
```

Substitua `cole_sua_chave_aqui` pela chave de verdade — essa parte sim você
edita. Se preferir, abra o Claude Code e peça: *"coloca minha chave do Groq no
.env da edvid"*.

### Chaves opcionais

Nenhuma é necessária para começar. O agente pede cada uma na primeira vez que o
recurso for usado, e você decide na hora:

| Chave | Para quê |
|---|---|
| `ELEVENLABS_API_KEY` | transcrever fontes longas (>5 min) com mais precisão |
| `PEXELS_API_KEY` | imagens e vídeos ilustrativos na Fase 2 |
| `TREBLO_API_KEY` | trilha sonora gerada por IA na Fase 3 |
| `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | imagens de marcas/pessoas específicas |

Imagens funcionam sem chave nenhuma via Wikimedia Commons, e trilha funciona com
um arquivo de música local. Nada da Fase 2 ou 3 fica bloqueado por falta de
chave.

---

## Skill do Remotion (necessária só na Fase 2)

A Fase 1 — corte, cor, áudio — funciona sem isso. Para legendas, gráficos e
imagens (Fase 2) a edvid precisa de uma segunda skill, a do Remotion.

Ela mora numa subpasta do repositório dela, então não dá pra clonar direto como
a edvid. Como o repo inteiro tem ~400 KB, o caminho mais simples é copiar — e
rodar o mesmo comando de novo é como se atualiza:

**Windows (PowerShell):**

```powershell
$t="$env:TEMP\rmskills"; Remove-Item -Recurse -Force $t,"$env:USERPROFILE\.claude\skills\remotion-best-practices" -EA SilentlyContinue; git clone -q --depth 1 https://github.com/remotion-dev/skills $t; Copy-Item -Recurse "$t\skills\remotion" "$env:USERPROFILE\.claude\skills\remotion-best-practices"; Remove-Item -Recurse -Force $t
```

**macOS / Linux:**

```bash
git clone -q --depth 1 https://github.com/remotion-dev/skills /tmp/rmskills && rm -rf "$HOME/.claude/skills/remotion-best-practices" && cp -R /tmp/rmskills/skills/remotion "$HOME/.claude/skills/remotion-best-practices" && rm -rf /tmp/rmskills
```

Na primeira vez que a Fase 2 rodar, ela ainda vai baixar as dependências do
Remotion (uns minutos). Nos vídeos seguintes é bem mais rápido, porque fica em
cache.

---

## Transcrição local, sem chave de API (opcional)

Por padrão a transcrição usa a API do Groq. Quem preferir rodar tudo na própria
máquina — sem chave, sem internet, sem cota — pode usar o
[whisper.cpp](https://github.com/ggml-org/whisper.cpp):

```bash
git clone https://github.com/ggml-org/whisper.cpp ~/whisper.cpp
cd ~/whisper.cpp && cmake -B build && cmake --build build -j --config Release
bash ./models/download-ggml-model.sh large-v3
```

Use o **large-v3** — os modelos menores erram muito em português. São ~3,1 GB, e
o download não avisa se for interrompido, então confira o tamanho no fim.

Depois é só pedir esse backend:

```bash
uv run python helpers/transcribe.py video.mp4 --backend whispercpp
```

A edvid acha o binário e o modelo sozinha em `~/whisper.cpp`. Se você instalou
em outro lugar, aponte com `WHISPERCPP_BIN` e `WHISPERCPP_MODEL` no `.env`.

Instalar o whisper.cpp **não muda nada** por si só: o Groq continua o padrão até
você pedir `--backend whispercpp` explicitamente.

**O que esperar.** Medido num clipe de 16s em português, contra a detecção
acústica de fala da própria skill:

| | Groq | whisper.cpp |
|---|---|---|
| Texto | referência | 28 de 29 palavras idênticas |
| Palavras no tempo certo | 97% | 66% |
| Desvio típico | — | 240 ms (pior caso 2,5 s) |

Ou seja: **o texto é equivalente, os tempos não.** Para a Fase 1 isso não
atrapalha, porque o corte usa a detecção acústica para definir as bordas, não os
tempos do Whisper. Para as legendas karaokê da Fase 2, que leem o tempo de cada
palavra, o desvio aparece na tela — nesse caso prefira o Groq.

---

## Primeiro uso

1. Coloque seus vídeos brutos numa pasta.
2. Abra o Claude Code **dentro dessa pasta**.
3. Diga: *"edita esses vídeos num Reels"* ou *"faz um inventário dessas tomadas
   e me propõe uma estratégia"*.

Tudo o que for gerado vai para uma subpasta `edit/` — seus arquivos originais
não são tocados.

---

## Atualizar

Para trazer a versão mais nova:

**Windows:**

```powershell
git -C "$env:USERPROFILE\.claude\skills\edvid" pull --ff-only
```

**macOS / Linux:**

```bash
git -C "$HOME/.claude/skills/edvid" pull --ff-only
```

`clone` baixa pela primeira vez; `pull` atualiza o que já existe. Rodar o
`clone` de novo não funciona — ele reclama que a pasta já existe.

Se o anúncio da versão disser que houve mudança de dependências, rode o
`uv sync` de novo depois do pull.

---

## Problemas comuns

**`uv` (ou `git`, ou `ffmpeg`) não é reconhecido como comando (Windows)** — são
as duas causas mais comuns, nessa ordem:

1. **Você pulou o passo 1.** Rode o `winget install` da instalação, reabra o
   PowerShell e tente de novo. Não precisa refazer o `git clone` se ele já
   funcionou.
2. **Você não reabriu o PowerShell** depois do `winget install`. O Windows só
   enxerga programas recém-instalados numa janela nova — feche essa e abra
   outra.

Se o `winget` não existir na sua máquina (Windows 10 mais antigo), instale o
`uv` pelo instalador oficial:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Uma janela pedindo para instalar as Ferramentas de Linha de Comando (macOS)**
— normal na primeira vez, o Mac não vem com `git` de fábrica. Aceite, espere
terminar e rode o `git clone` de novo.

**`destination path already exists and is not an empty directory`** — a skill já
está instalada. Você queria o comando de atualizar (`git pull`), não o de
instalar.

**`ModuleNotFoundError` ao usar a skill** — faltou o passo 4, o `uv sync`.

**O Claude não encontra a skill** — confirme que a pasta está exatamente em
`.claude/skills/edvid` dentro da sua pasta de usuário, e reinicie o Claude Code.

---

## Para quem quer contribuir com código

O caminho acima coloca o repositório dentro de `.claude/skills/`, que é o mais
simples para quem só quer usar. Se você vai desenvolver a skill e prefere o repo
junto dos seus outros projetos, clone onde quiser e crie um symlink para a pasta
de skills — o `install.md` documenta esse formato.

---

## Licença

Veja [LICENSE](LICENSE).
