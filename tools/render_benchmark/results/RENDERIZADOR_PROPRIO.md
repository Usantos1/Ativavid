# Renderizador próprio — primeiro teste

**Data:** 20/08/2026 · máquina livre (fila vazia) · i5-10300H, RTX 3050
**Trecho:** quadros 600–850 (251 quadros) do projeto `20260816-002530_IMG_3912`
**Estilo:** o padrão (`stacked`, Poppins preto/itálico + Playfair de ênfase)

A pergunta mudou. Não é mais "dá para imitar o Remotion pixel a pixel" — isso
reprovou em 0,823 e o motivo era perseguir o Chrome. Sendo **nós** os donos do
visual, a pergunta é quanto custa desenhar.

## Tempo, mesmo trecho, mesmo formato de saída

| Caminho | Tempo | Por quadro |
|---|---|---|
| Remotion (hoje) | 39,7 s | 158 ms |
| Nosso, com ProRes 4444 no meio | 18,3 s | 73 ms |
| **Nosso, só a rasterização** | **3,3 s** | **13 ms** |

**O desenho em si é 12× mais rápido que o Remotion.** Os outros 60 ms do nosso
caminho são o ProRes 4444 — um formato intermediário que só existe porque o
Remotion é um navegador e não tem como receber o vídeo para desenhar por cima.

## Sem o intermediário

Desenhar e compor numa passada só, entregando o MP4 final. **Mediana de 3
rodadas** — a primeira medição deste teste deu 76 ms e era partida a frio;
número único nesta máquina não vale.

| Caminho | Por quadro | Tempo real |
|---|---|---|
| Hoje: Remotion (158) + compose (30) | **188 ms** | 0,16× |
| Uma passada, tela inteira no cano | 27 ms | 1,2× |
| **Uma passada, só a faixa da legenda** | **21 ms** | **1,6×** |

**~9× no fim a fim.** A faixa da legenda tem 560×432 — 0,9 MB por quadro no
cano contra 7,9 MB da tela inteira. A legenda mora sempre na mesma parte da
tela, então transmitir o resto era desperdício puro.

Saída conferida contra o caminho atual em
`comparacao_final_uma_passada.png`: mesma posição, mesma cor, mesmo peso.

### Contra o CapCut

A referência que motivou tudo isto: o CapCut exporta a 5,3× o tempo real nesta
máquina. Estamos em **1,6×**. Ainda 3× atrás — e não vou chamar de empate o que
não é. Mas as duas medidas não são a mesma coisa: a nossa **rasteriza legenda
do zero em todo quadro**, a do CapCut é exportação de uma timeline já montada.

## Aparência

`comparacao_renderizador_proprio.png` — Remotion à esquerda, nosso à direita,
compostos sobre o vídeo real. Mesma fonte, mesmo tamanho, mesma posição, mesma
sombra, mesma cor de marca.

Dois defeitos reais apareceram e foram corrigidos no caminho:

1. **Alpha pré-multiplicado.** A composição acumula cor já multiplicada pelo
   alpha, mas quem lê RGBA espera alpha direto. O texto saía lavado.
2. **Cor de ênfase chumbada.** O laranja padrão estava no código; a cor é da
   marca e vem de `captions.emphasisAccent` (aqui, vermelho).

## Segundo teste: o estilo difícil (`Recorte`)

O `Recorte` não é texto, é TRAÇO: um caminho de béziers que se desenha sozinho
em volta da palavra, esticado sobre a caixa dela, com ponta redonda, avanço
por comprimento de arco e sombra própria. Era o teste de que a arquitetura
estica além de texto.

**Esticou.** Implementação: curvas achatadas em polilinha, um estágio de traço
rasterizado por quadro da animação (~10), e o estágio final reaproveitado até
o fim — a mesma ideia de cache do texto.

| | Remotion | Nosso |
|---|---|---|
| 15 quadros do Recorte | 14,7 s | **1,0 s** |

Fidelidade conferida por tinta na faixa da legenda, quadro a quadro: a curva
de entrada acompanha (q1–8), o estado parado fica em 95% da mesma tinta
(46,8k vs 44,7k pixels — espessura de traço/serrilhado), e a saída abrupta
cai a zero no MESMO quadro (13). `comparacao_recorte.png` mostra o quadro 9
lado a lado sobre o vídeo real.

No caminho, a saída de legenda inteira (fade/blur "blur_up" + o corte abrupto)
foi implementada no renderizador — não existia e era visível.

**Divergência conhecida:** o quadro 0 tem ~6k pixels de tinta no Remotion e
nada no nosso — um quadro de defasagem na entrada da palavra. Pequeno, mas
real; fica anotado.

## Terceiro teste: o vídeo inteiro

851 quadros, 21 legendas, os três presets juntos (`phase23_video_inteiro.py`),
contra o Remotion renderizando o MESMO overlay completo.

**Overlay completo, mesmo formato (ProRes 4444 de tela inteira):**

| | Tempo | Por quadro |
|---|---|---|
| Remotion | 172,5 s | 203 ms |
| Nosso | 88,1 s | 104 ms |

Aqui o ProRes de tela inteira domina o NOSSO tempo — é o formato do
intermediário, não o do caminho final.

**Fim a fim (corte → legenda → MP4 final com áudio), 3 rodadas:**

| | Tempo |
|---|---|
| Caminho atual (Remotion 172,5 + compose ~25) | ~197 s |
| Uma passada, faixa da legenda (636×432) | **39,4 s** (mediana; 27,9 s fria) |

**5× de ponta a ponta** (7× com a máquina fria — as rodadas 2 e 3 subiram de
27,9 para ~39,7 s: térmica, de novo). 0,7× do tempo real contra 0,14× do
caminho atual. CapCut segue na frente (5,3×).

**Fidelidade, tinta por quadro na faixa das legendas** (696 quadros com
legenda, fora do cartão final): mediana da razão nosso/Remotion **1,003**
(p5 0,874 · p95 1,048). Os quadros fora de ±25%: os 4 flashes de transição
(elemento de tela cheia, fora do escopo — e trivial: branco que desbota), o
quadro 0 (defasagem de 1 quadro na entrada, já anotada) e a curva de entrada
de uma cue. `comparacao_video_inteiro.png`: quadro 13 s, produção vs nosso.

No caminho entraram: `SOLO_BIG`, a entrada com subida (translate 46→0 acoplado
à opacidade — valia para todos os estilos e estava faltando) e a saída
blur_up/abrupt.

## Quarto teste: o overlay COMPLETO (headline + cartão + flashes)

`phase24_elementos.py` fecha os elementos que faltavam, com composição em
camadas (headline + legenda + cartão no mesmo quadro, modo `mesclar`):

- **headline `realce`**: duas linhas balanceadas por largura medida, blocos na
  cor da marca. Primeira versão saiu 13% mais alta que a de produção — a caixa
  CSS é line-height + paddings, não ascent+descent da fonte. Corrigido por
  medida: bloco nosso 584×230 contra 581×229 da produção.
- **cartão final**: dim 0.82 + duas linhas com subida — visualmente idêntico.
- **flashes de corte**: facho rotacionado varrendo + clarão no corte.
  **Aproximados, não idênticos**: forma e tempo do facho diferem do CSS
  (mix-blend screen não existe no nosso compositor). São 28 de 851 quadros.

**Tela INTEIRA, todos os elementos, 785 quadros com tinta:** mediana da razão
nosso/Remotion **1,003** (p5 0,923 · p95 1,048). Fora de ±25%: só os quadros
de flash e o quadro 0 já conhecido.

Os tempos desta rodada saíram COM a fila do usuário rodando — ficam de fora
do relatório; a remedição limpa está pendente.

## Números LIMPOS (fila zerada, app fechado, mediana de 3)

A remedição derrubou números dos DOIS lados. O Remotion sob carga tinha dado
172,5 s — limpo faz em **107,0 s**; o "5×" anunciado antes estava contaminado
nos dois sentidos e **fica retirado**.

| Caminho completo (851 quadros, todos os elementos) | Tempo |
|---|---|
| Produção: Remotion (107,0) + compose (19,5) | **126,5 s** |
| Nosso, uma passada até o MP4 final | **77,6 s** |

**1,63× de ponta a ponta** com o overlay completo. Dois caches fizeram o
número (fidelidade conferida idêntica antes/depois — mediana 1,003):

1. **Quadro parado não recompõe**: assinatura do estado visual por quadro;
   419/851 quadros são bit-idênticos ao anterior e só reenviam os bytes.
2. **Palavra assentada não recompõe**: o composto das palavras paradas fica
   cacheado na camada; por quadro só as 1–2 animando entram por cima.

**Formato a formato, o Remotion ganha o ProRes:** overlay completo em ProRes
4444 deu 129,9 s nosso contra 107,0 dele. Nosso ganho vem de NÃO precisar do
intermediário — não de encodar ProRes mais rápido.

**Observação do usuário durante os testes:** nosso caminho ocupa ~50% de
CPU/memória; o do Remotion passa de 90%. A máquina continua utilizável.

### A escada de otimização (todas verificadas com fidelidade idêntica, 1,003)

| Passo | Mediana de 3 |
|---|---|
| Uma passada ingênua | 106,7 s |
| + quadro parado reenvia os próprios bytes (419/851) | 92,8 s |
| + palavra assentada composta uma vez (cache na camada) | 77,6 s |
| + retângulo convertido em cache; só o que anima reconverte | 72,3 s |
| + escurecimento do cartão vira multiplicação (era camada: 426 ms/quadro) | 57,7 s |
| + estágios do flash em cache, over em uint8 | **53,8 s** |

**Resultado da noite: produção 126,5 s → nosso 53,8 s = 2,35×**, a 0,53× do
tempo real. O chão medido do cano+ffmpeg sozinhos é 17,2 s — ainda há 36 s de
Python para atacar (headline compõe a caixa toda por quadro; o cano leva a
tela cheia mesmo quando só a faixa da legenda muda).

**Contra o CapCut (5,3× tempo real): estamos a 0,53×.** A distância era 38×
no caminho de produção; agora é 10×.

## O que estes testes NÃO respondem

- `SOLO_BIG` não foi feito (mas é o texto grande sem traço — subconjunto do
  que já existe).
- Headline, cartão final, contador de lista e gráficos próprios ficaram fora.
- Não há timeline nem ferramenta de refino manual — é render, não editor.
- O número do Remotion aqui (158 ms) é medido **isolado**. A telemetria de
  produção mostra bem pior sob carga; o ganho real tende a ser maior, mas não
  medi isso.

## Como reproduzir

```
py tools/render_benchmark/phase20_render_proprio.py <public> 900
py tools/render_benchmark/phase21_uma_passada.py <projeto> 600 851
```
