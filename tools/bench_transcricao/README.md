# Benchmark de transcrição — Scribe × Whisper × Gemini

Compara cinco pipelines sobre os **mesmos** áudios, chamando o código de
produção que já existe. Não toca no pipeline: mede-o.

| | Cenário | Como roda |
| --- | --- | --- |
| A | Scribe | `helpers/transcribe.py` com `backend="elevenlabs"` |
| B | Whisper local | `helpers/transcribe.py` com `backend="local"` → `MotorWhisperLocal` |
| C | Gemini áudio | **indisponível** — ver abaixo |
| D | Whisper + Gemini ouvindo | **indisponível** — mesmo motivo |
| E | Whisper + Gemini só texto | B, depois revisão pelo `app/llm_gateway.py` que já existe |

Nenhuma chave de API do Gemini, nenhum custo de API do Gemini: o cenário E usa
a sessão web por cookies que o projeto já tem.

## O que o benchmark NÃO reimplementa

O motor local é `app/transcricao/whisper_local.py`, chamado pela mesma porta
que o produto usa. Vêm junto, sem cópia: timestamps por palavra, a guarda
contra alucinação, o catálogo de modelo por VRAM, a queda para CPU, o cache e
o schema do Scribe que dez módulos consomem. O `motores.py` só chama e
cronometra.

Para cronometrar **a frio**, cada rodada aponta `ATIVAVID_TRANSCRIPT_CACHE`
para uma pasta descartável. A variável já existia; nenhuma linha de produção
mudou para isso.

## Por que C e D estão indisponíveis

Ambos exigem que o Gemini **ouça** o áudio. A integração do projeto
(`app/llm_gateway.py` → `app/llm_session.py`) fala com o gemini.google.com por
cookies capturados pela extensão, e envia **só texto**. Verificado no código,
não presumido — `app/llm_session.py:245` monta o pedido como:

```python
inner[0] = [prompt, 0, None, None, None, None, 0]
```

Uma string de prompt. Busca por `upload`, `push.clients6`, `multipart`,
`inline_data`, `attach`, `audio` e `file_data` no arquivo inteiro volta vazia.
Anexar arquivo no Gemini web exige um upload separado para
`push.clients6.google.com/upload/` e referenciar o identificador no payload.

Fazer C e D rodarem significaria uma de duas coisas, ambas fora do escopo:
introduzir a API paga do Gemini só para o teste, ou mexer no `llm_session.py`,
que é produção. Então os dois são registrados como **indisponíveis com a
integração atual** e o benchmark segue com A, B e E. A matriz mostra a lacuna
em vez de escondê-la, e `test_bench_ajustes.py` tem um teste que falha se algum
módulo do benchmark voltar a referenciar `google.genai` ou `GEMINI_API_KEY`.

```
ELEVENLABS_API_KEY=...              liga A
uv sync --extra transcricao-cuda    # B
sessão Gemini capturada na extensão # E (sem chave, sem custo)
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

## Rodar — uma operação só

```bash
python tools/bench_transcricao/benchmark.py --corpus corpus.json
```

Encadeia preflight → benchmark → preliminar → **para na validação humana** →
relatório final. Não reimplementa nada: chama o `main()` de cada etapa. Depois
de validar, rode o mesmo comando: o que já foi feito é reaproveitado e ele
segue direto para a matriz. No Windows há o atalho
`tools\bench_transcricao\benchmark.cmd`.

Sai com 0 (matriz impressa), 1 (parou na validação — esperado na primeira
passada) ou 2 (preflight barrou).

## Etapas separadas

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

79 testes. Os de alinhamento cobrem divisão, fusão, remoção, inserção recusada,
intervalo apertado e o freio de retranscrição — cada um conferindo que a linha
do tempo do Whisper sobreviveu. Os de contrato usam os tipos e a conversão
REAIS do projeto: se o schema mudar, isto falha antes de alguém gastar uma
noite de GPU. E `test_bench_gemini_resposta.py` cobre o que uma rodada de
horas encontra de verdade: JSON em cerca de código, prosa em volta, índice
errado, correções sobrepostas — nada disso pode derrubar o vídeo 7 nem, pior,
corromper a palavra errada em silêncio.

## Defeito temporal — o reparo automático não é sucesso

`helpers/captions_for_remotion.py::_word_items` **não quebra** com transcript
ruim — ele REPARA. Força `start` crescente (+1 ms) e duração mínima de 40 ms,
porque 133 dos 178 transcripts do usuário tinham palavra voltando no tempo.

A produção conseguir consertar **não torna o timestamp bom**: o reparo só troca
"legenda quebrada" por "legenda dessincronizada". Cada palavra movida é uma
palavra que o motor entregou fora do lugar. Por isso entra na matriz como
defeito do transcript original, com a distribuição inteira:

    palavras_reparadas
    deslocamento_total_ms
    deslocamento_mediano_ms
    p95_deslocamento_ms
    pior_deslocamento_ms

As cues saem do módulo de produção e os invariantes são os mesmos que
`tools/conferir_legendas.py` cobra dos projetos reais. É por aí que o cenário D
se prova: revisar texto não pode criar defeito temporal nenhum.

## Impacto nos cortes

`rodar.py --cortes` roda `helpers/pack_transcripts.py` →
`helpers/llm_cut_plan.py` — o planejador de produção — sobre CADA transcript e
registra nº de cortes, duração final e a **`divergência_do_plano`**: 0.0 = mesmo
vídeo, 1.0 = nenhum segundo em comum.

O nome é assim de propósito. **Não é medida de qualidade.** Um plano divergente
pode ser melhor ou pior; a conta só mostra quanto o transcript influencia a
edição. O plano do Whisper é o ponto de comparação por ser o que o produto usa
hoje, não por ser o certo — julgar qual edição ficou boa exige validação humana
separada, fora deste benchmark. Precisa de sessão de IA ativa; sem ela a linha
sai como `sem dado`.

## Brutos preservados

Cada motor grava em `<vídeo>/trabalho/bruto/` o que devolveu, antes de qualquer
normalização, alinhamento ou reparo: o payload do `transcribe.py` para A e B, o
texto verbatim da resposta do Gemini em C, e em D/E a lista de correções mais o
transcript-base antes do alinhamento. Nenhuma etapa lê de volta daqui — existe
só para auditar depois se um número estranho veio do motor ou de nós.

## O corpus sintético não pontua

`corpus_sintetico.py` marca o corpus e cada clipe com `sintetico: true`, o
`rodar.py` carimba a saída e o `relatorio.py` **recusa** (sai com 3) aquela
pasta. Voz de espeak não tem prosódia, hesitação, sobreposição de locutor nem
acústica de gravação: valida o encanamento e não decide arquitetura. A matriz
final usa somente vídeo real do ATIVAVID.

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
