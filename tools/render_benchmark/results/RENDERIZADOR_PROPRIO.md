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

Desenhar e compor numa passada só, entregando o MP4 final:

| Caminho | Por quadro |
|---|---|
| Hoje: Remotion (158) + compose (30) | **188 ms** |
| Uma passada só | **76 ms** |

**2,5× no fim a fim**, e ainda sobra folga: os 76 ms são dominados por empurrar
8,3 MB de RGBA por quadro pelo cano. Mandar só a caixa da legenda em vez da
tela inteira é a próxima economia óbvia.

## Aparência

`comparacao_renderizador_proprio.png` — Remotion à esquerda, nosso à direita,
compostos sobre o vídeo real. Mesma fonte, mesmo tamanho, mesma posição, mesma
sombra, mesma cor de marca.

Dois defeitos reais apareceram e foram corrigidos no caminho:

1. **Alpha pré-multiplicado.** A composição acumula cor já multiplicada pelo
   alpha, mas quem lê RGBA espera alpha direto. O texto saía lavado.
2. **Cor de ênfase chumbada.** O laranja padrão estava no código; a cor é da
   marca e vem de `captions.emphasisAccent` (aqui, vermelho).

## O que este teste NÃO responde

- Só um estilo (`stacked`). `SOLO_OUTLINE` e `SOLO_BIG` não foram feitos.
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
