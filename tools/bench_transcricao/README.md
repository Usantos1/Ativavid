# Benchmark de transcrição — Scribe × Whisper × Gemini

Compara cinco pipelines sobre os **mesmos** áudios, chamando o código de
produção que já existe. Não toca no pipeline: mede-o.

| | Cenário | Como roda |
| --- | --- | --- |
| A | Scribe | `helpers/transcribe.py` com `backend="elevenlabs"` |
| B | Whisper local | `helpers/transcribe.py` com `backend="local"` → `MotorWhisperLocal` |
| C | Gemini áudio | `gemini_api.py` — única integração nova |
| D | Whisper + Gemini | B, depois o Gemini revisa o texto **ouvindo** o áudio |
| E | Gemini só texto | B, depois revisão pelo `app/llm_gateway.py` que já existe |

## O que o benchmark NÃO reimplementa

O motor local é `app/transcricao/whisper_local.py`, chamado pela mesma porta
que o produto usa. Vêm junto, sem cópia: timestamps por palavra, a guarda
contra alucinação, o catálogo de modelo por VRAM, a queda para CPU, o cache e
o schema do Scribe que dez módulos consomem. O `motores.py` só chama e
cronometra.

Para cronometrar **a frio**, cada rodada aponta `ATIVAVID_TRANSCRIPT_CACHE`
para uma pasta descartável. A variável já existia; nenhuma linha de produção
mudou para isso.

## A única integração nova, e por quê

O Gemini do ATIVAVID (`app/llm_gateway.py` → `app/llm_session.py`) fala com o
gemini.google.com por **cookies** capturados pela extensão, e achata
`messages` numa string de texto. Não há upload de arquivo nem `inline_data`:
**não existe caminho de áudio ali**. Como C e D exigem que o Gemini ouça, o
`gemini_api.py` acrescenta a Gemini API oficial — isolada, sem nenhum módulo
do app importando dela. Se C e D perderem, apagar aquele arquivo não deixa
rastro.

O cenário E não usa a API: ele passa pelo gateway existente, de propósito, para
medir o que dá para ter **hoje** sem integração nova.

```
GEMINI_API_KEY=...            liga C e D
ELEVENLABS_API_KEY=...        liga A
uv sync --extra transcricao-cuda    # B
uv pip install google-genai         # C e D
```

## Ground truth sem transcrever tudo à mão

Transcrever 8 vídeos à mão é caro e desnecessário. Onde os motores dizem a
mesma coisa, a chance de estarem todos errados do mesmo jeito é desprezível —
e, se estiverem, o erro afeta os quatro igualmente e some na comparação. O que
decide o benchmark são os pontos de divergência.

Então `discordancia.py` alinha todos os motores contra o transcript do Whisper
(a espinha — é a fonte temporal do produto e do cenário D) e lista só onde
alguém discorda. `validar.py` gera uma página HTML por vídeo:

```
▶ ouvir   00:32.450
…vendi quinze mil na [ ? ] ontem à noite…
  ( ) Prime Camp
  ( ) praimcamp
  ( ) PrimeCamp
  ( ) Outro: ______
```

Sem servidor, sem instalar nada. A pessoa ouve 3 segundos e marca. No fim,
baixa o JSON.

Dois cuidados que a página tem:

- **A ordem das opções é embaralhada e nada diz de qual motor veio cada uma.**
  Se a pessoa souber que "aquela é a do Scribe", ela para de ouvir e começa a
  votar em motor — o viés que a referência existe para não ter. O mapa
  motor→texto fica no `propostas_<id>.json`, para o relatório.
- **Um ponto cobre no máximo 4 palavras.** Sem teto, fala rápida com várias
  divergências viraria uma pergunta longa, e a pessoa acabaria transcrevendo a
  frase inteira — o trabalho manual que isto existe para evitar.

A referência final é consenso onde todos concordam, ouvido humano onde não. O
relatório informa quantas palavras vieram de cada origem, e **avisa** quando
sobrou divergência sem validar, porque nesses pontos ele trata a versão do
Whisper como correta — o que favorece B, D e E.

## Rodar

```bash
cp tools/bench_transcricao/corpus.exemplo.json corpus.json   # preencha
python tools/bench_transcricao/rodar.py --corpus corpus.json --saida bench/
# abra bench/validacao/validar_v01.html, marque, salve o JSON na mesma pasta
python tools/bench_transcricao/relatorio.py --saida bench/
```

## A regra do cenário D

O Whisper é a **única** fonte de verdade temporal; o Gemini só corrige texto.
`alinhar.py` garante isso por construção e `conferir()` derruba a rodada se um
tempo escapar — erro de alinhamento vira exceção, nunca legenda torta.

O caso difícil, `PrimeCamp` → `Prime Camp`, tem política por tipo de bloco:

| bloco | política de tempo |
| --- | --- |
| igual n:n | tempos intactos; adota a grafia do Gemini (caixa de nome próprio) |
| troca 1:1 | herda `inicio`/`fim` **exatos** da palavra correspondente |
| **divisão 1→m** | reparte proporcional aos caracteres, `novo[0].inicio` e `novo[-1].fim` **cravados** |
| **fusão n→1** | `inicio` da primeira, `fim` da última. Exato |
| troca n:m | divisão proporcional no span do bloco, bordas cravadas |
| remoção | tempo órfão **absorvido** pelo vizinho — sem buraco no karaokê |
| inserção | **recusada**: revisor não inventa palavra |

A união dos intervalos nunca escapa do span do bloco, então as fronteiras de
segmento ficam intactas. Mais três freios: **âncora** (correção cujo `de` não
bate com o texto no índice é descartada, em vez de corromper outra palavra),
**confiança**, e **anti-retranscrição** (acima de 35% das palavras alteradas,
com amostra ≥ 20, a revisão inteira volta atrás).

## Honestidade embutida

- **Granularidade do Gemini.** O prompt manda declarar `palavra`/`frase`/
  `segmento` e proíbe interpolar. Se vier `frase`, as linhas de timestamp saem
  como `sem dado` — nunca um número inventado.
- **Formalizar a fala é erro.** `metricas.py` não normaliza: `cê` ≠ `você`,
  `tá` ≠ `está`. Quem "melhora" o português do usuário perde pontos.
- **Custo.** `custos.json` vem com nulos de propósito, inclusive o custo
  indireto de GPU local. Preço não preenchido vira `sem dado`.
- **Motor sem configuração falha alto**, e a célula fica vazia. Uma célula
  vazia é informação; uma chutada é ruído com aparência de dado.

## Testes

```bash
python -m pytest pipeline/test_bench_alinhamento.py \
                 pipeline/test_bench_metricas.py \
                 pipeline/test_bench_discordancia.py -q
```

30 testes. Os de alinhamento cobrem divisão, fusão, remoção, inserção
recusada, intervalo apertado e o freio de retranscrição — cada um conferindo
que a linha do tempo do Whisper sobreviveu.

## O que ainda depende de rodar na máquina real

Este contêiner Linux não tem GPU, FFmpeg, chaves nem os vídeos — e
`tools/render_benchmark/bench_lib.py` aponta para `E:\`, a máquina Windows
onde os benchmarks anteriores rodaram. O harness está pronto e testado; os
números precisam sair de lá.

Duas medições do pedido ainda não estão automatizadas, por dependerem de
render e do planejador com sessão de IA ativa:

- **karaokê renderizado** — `relatorio.py` mede a geometria dos tempos, que é
  o que decide se o realce quebra. O render em si sai por
  `helpers/captions_for_remotion.py` + `tools/conferir_legendas.py`.
- **impacto nos cortes** — os cinco transcripts ficam salvos no schema do
  Scribe, prontos para `helpers/pack_transcripts.py` → `helpers/llm_cut_plan.py`.
