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
python tools/bench_transcricao/preflight.py --corpus corpus.json   # confere tudo antes
python tools/bench_transcricao/rodar.py --corpus corpus.json --saida bench/ --cortes
python tools/bench_transcricao/preliminar.py --saida bench/        # já dá resultado
# abra bench/validacao/validar_v01.html, marque, salve o JSON na mesma pasta
python tools/bench_transcricao/relatorio.py --saida bench/
```

**Se a rodada cair, rode o mesmo comando de novo.** Ela retoma de onde parou:
cada cenário já concluído é reaproveitado do disco. `--refazer` força repetir.
Isto importa porque o cache de transcrição fica DESLIGADO durante o benchmark
(medição a frio), então sem retomada a repetição seria integral — horas de GPU
e cota paga de API outra vez.

O `preliminar.py` dá resultado no minuto em que a rodada termina, sem esperar
validação humana: concordância entre motores, quanto ouvido humano falta, e as
duas coisas que se verificam sozinhas — se o cenário D respeitou o tempo do
Whisper (se não respeitou, perdeu, com WER nenhum) e quanto a produção teve de
reparar cada legenda.

O `preflight.py` existe porque a rodada leva horas de GPU e cota de API, e
descobrir no vídeo 6 que faltava uma chave é caro. Ele confere FFmpeg, GPU,
faster-whisper, modelo já baixado, as duas chaves, sessão de IA, cada arquivo
do corpus, a cobertura de situações e o `custos.json` — em segundos, dizendo o
conserto de cada item. Sai com 2 se nem o cenário local roda, 1 se dá para
rodar parte.

Ele também **prevê o gasto e o tempo** a partir da duração real do corpus.
Cota de API se gasta uma vez: ver o número antes é a diferença entre decidir
rodar 8 vídeos e descobrir depois que deu para 3.

Para exercitar o encanamento antes de gastar os vídeos reais:

```bash
python tools/bench_transcricao/corpus_sintetico.py --saida bench/sintetico
python tools/bench_transcricao/rodar.py --corpus bench/sintetico/corpus.json \
       --saida bench/sintetico/bench --so whisper_local
```

Gera fala pt-BR com `espeak-ng` cobrindo gírias, marcas e números, com o texto
exato conhecido. Serve para ver o harness rodar inteiro — **não** para julgar
motor: voz sintética não tem prosódia, hesitação nem a acústica de uma gravação
de celular.

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

```bash
python -m pytest pipeline/test_bench_contrato.py pipeline/test_bench_impacto.py -q
# ou todos: python -m pytest pipeline/test_bench_*.py -q
```

62 testes. Os de alinhamento cobrem divisão, fusão, remoção, inserção recusada,
intervalo apertado e o freio de retranscrição — cada um conferindo que a linha
do tempo do Whisper sobreviveu. Os de contrato usam os tipos e a conversão
REAIS do projeto: se o schema mudar, isto falha antes de alguém gastar uma
noite de GPU. E `test_bench_gemini_resposta.py` cobre o que uma rodada de
horas encontra de verdade: JSON em cerca de código, prosa em volta, índice
errado, correções sobrepostas — nada disso pode derrubar o vídeo 7 nem, pior,
corromper a palavra errada em silêncio.

## Karaokê: a métrica certa não é "quebrou?"

`helpers/captions_for_remotion.py::_word_items` **não quebra** com transcript
ruim — ele REPARA. Força `start` crescente (+1 ms) e duração mínima de 40 ms,
porque 133 dos 178 transcripts do usuário tinham palavra voltando no tempo.

Então a pergunta não é se o karaokê quebra, e sim **quanto a produção teve de
mexer**. Cada milissegundo de reparo é uma palavra saindo de cima do áudio: na
tela continua bonito, e acende fora da hora. `impacto.py` mede isso —
`palavras_reparadas`, `deslocamento_total_ms`, `pior_deslocamento_ms` — usando
as cues geradas pelo módulo de produção, e cobrando os mesmos invariantes que
o `tools/conferir_legendas.py` cobra dos projetos reais.

É por aí que o cenário D se prova: revisar texto não pode criar reparo nenhum.

## Impacto nos cortes

`rodar.py --cortes` roda `helpers/pack_transcripts.py` →
`helpers/llm_cut_plan.py` — o planejador de produção — sobre CADA transcript, e
registra nº de cortes, duração final e a **sobreposição** com o plano do
Whisper. Não se espera plano idêntico; 1.0 seria o mesmo vídeo, 0.0 seria outro
vídeo inteiro. Precisa de sessão de IA ativa; sem ela a linha sai como
`sem dado`.

## O que ainda precisa da máquina real

Este contêiner Linux não tem GPU nem os vídeos, e o download dos pesos do
modelo (Systran/faster-whisper-* no HuggingFace) está bloqueado pelo proxy —
então nenhum motor de ASR roda aqui. `tools/render_benchmark/bench_lib.py`
aponta para `E:\`, a máquina Windows onde os benchmarks anteriores rodaram: é
de lá que os números têm de sair.

O que FOI verificado aqui, sem os pesos: o adaptador chega ao código de
produção real (a falha de download veio de dentro de
`_transcrever_local` → `primeiro_uso.preparar`, provando o caminho), e o
contrato de schema entre `ResultadoDeTranscricao.para_schema_scribe()` e o
adaptador está coberto por teste com os tipos reais do projeto.
