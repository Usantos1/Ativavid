# Camada 1 — do original HDR ao master SDR (ENCERRADA)

Decide o que acontece **antes** do cut: tonemap, scaler e a ordem entre
escalar e tonemapar. É a camada onde a perda é irreversível — o que estoura
aqui não volta com bitrate nenhum na entrega.

Ferramentas: `camada1_master.py`, `camada1_npl_multi.py`, `prep_npl_tempo.py`.
Branch isolada: `benchmark/render-instagram`.

## Resultado

| decisão | valor | mudou? |
|---|---|---|
| scaler | `bicubic` | não |
| ordem | escalar antes do tonemap | não |
| **npl** | **150** (era 100) | **sim** |

## Scaler — não mexer

VMAF contra referência sem perda (tonemap em resolução cheia + lanczos):

| scaler | VMAF |
|---|---|
| lanczos | 99,660 |
| **bicubic (mantido)** | **99,604** |
| spline | 99,580 |
| bilinear | 98,121 |

Bicubic para lanczos rende **0,056 VMAF**. O limiar do perceptível fica perto
de 1 ponto — é vinte vezes menor que o menor efeito visível, e custaria 11%
mais tempo. A suspeita inicial de que o scaler era a fonte da perda de nitidez
foi **medida e descartada**.

## Ordem — não mexer

| ordem | VMAF | tempo |
|---|---|---|
| tonemapar antes (tecnicamente correto) | 99,660 | 77,6s |
| **escalar antes (mantido)** | **99,567** | **37,9s** |

0,093 VMAF pelo dobro do tempo. O comentário que já existia no código supunha
"delta invisível na resolução de entrega"; a suposição se confirmou.

## npl — 100 → 150

Medido em 4 cenas HLG do material real. `npl` não tem vencedor por métrica
(muda a aparência de propósito), então aqui vão características absolutas.

| cena | npl | luma | clip ≥235 | ≤16 |
|---|---|---|---|---|
| loja | 100 / 150 / 203 | 148,3 / 134,0 / 123,2 | **4,22% / 0,14% / 0,00%** | 1,88 / 2,32 / 2,76 |
| janela p/ rua | 100 / 150 / 203 | 136,5 / 123,0 / 112,9 | **5,72% / 0,95% / 0,01%** | 4,03 / 5,24 / 6,38 |
| pele em close | 100 / 150 / 203 | 121,2 / 108,3 / 98,9 | **4,57% / 0,13% / 0,00%** | 1,60 / 1,99 / 2,31 |
| vitrine/sombra | 100 / 150 / 203 | 126,1 / 113,3 / 103,8 | **3,38% / 0,23% / 0,01%** | 4,08 / 5,33 / 6,54 |

De 100 para 150 o clipping cai **25× a 60×** por ~13 pontos de luma. De 150
para 203 some o resto — que já era menos de 1% — por outros ~10 pontos, sem
ganho visível nos recortes. **150 é onde a curva vira.**

Custo assumido e **não compensado**: a imagem escurece. Nenhum ajuste de
`eq`/brightness/contraste entrou junto, para o efeito do npl ficar isolado.

### Prep real (3 rodadas, cache limpo antes de cada)

| npl | rodadas | mediana | prep |
|---|---|---|---|
| 100 | 167,1 / 207,5 / 269,1 | 207,5s | 111,2 MB |
| 150 | 160,4 / 162,0 / 183,1 | 162,0s | 106,9 MB |

A mediana sugere 22% a favor do 150 e **isso não é afirmável**: o
espalhamento do npl=100 foi de 102s (61%), esta máquina varia até 2,3× em
trabalho idêntico, e o 100 rodou primeiro com o disco frio. As rodadas mais
rápidas empatam (167,1 vs 160,4). **O que se sustenta: npl=150 não é mais
lento.**

### Cache

A chave em `_prep_key` inclui `TONEMAP_CHAIN`, então a troca invalida o cache
de propósito. Verificado plantando um prep com a cadeia antiga: o app
**regerou** em vez de reaproveitar, e a chave mudou (`a8d19612` →
`15158878`). O master novo saiu com clipping 0,23% — a assinatura do 150 —
contra 3,38% do 100.

## Limite desta decisão

Vale para material HLG **de interior**, que é o que o app recebe hoje: as 16
fontes HLG do corpus são todas loja. **Exterior com céu aberto não tem
cobertura** — é o caso clássico de estouro, e onde 203 poderia ganhar de 150.
Se passar a entrar material externo, reabrir este benchmark.
