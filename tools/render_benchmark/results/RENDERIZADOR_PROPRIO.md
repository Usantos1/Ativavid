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
