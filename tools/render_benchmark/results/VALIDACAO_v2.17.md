# Validação da v2.17 — fonte preparada

**Data:** 19/08/2026 · **Máquina:** i5-10300H (4 núcleos físicos), 24 GB, RTX 3050 Laptop, Windows 11
**Projeto:** `20260816-002530_IMG_3912_9d41f4134e` — 28,37 s · 1080×1920 · 30 fps · fonte HEVC 10 bits HLG
**Método:** clones isolados; nenhum arquivo de produção tocado; verificado ao final que nada vazou para `E:\ATIVAVID\Projetos`.

**Decisão: v2.17 aprovada na qualidade. Emitida a v2.17.1** por um defeito de concorrência (item 6), mais o ajuste de CQ e observabilidade de cache. Nenhuma mudança visível no resultado.

---

## 1. FINAL antigo vs FINAL v2.17

Mesmo projeto, mesmos estilos, mesmos dados — **os dois finais renderizados de verdade** (`ok=True`).

| Campo | Antigo | v2.17 | Igual? |
|---|---|---|---|
| Resolução | 1080×1920 | 1080×1920 | sim |
| FPS | 30/1 | 30/1 | sim |
| Frames | 851 | 851 | sim |
| Duração | 28,367 s | 28,367 s | sim |
| Tamanho | 52,18 MB | 51,73 MB | −0,9% |
| Bitrate | 15,43 Mbps | 15,30 Mbps | −0,8% |

**SSIM 0,9855 · PSNR 39,92 dB · VMAF 96,50**

## 2. Frames difíceis

Escolhidos **por medida** (brilho, movimento, saturação medidos sobre o final antigo), não por escolha manual.

| Situação | Frame | PSNR |
|---|---|---|
| Área escura | 808 | 41,79 dB |
| Highlight / movimento | 355 | 36,55 dB |
| Pele saturada | 776 | 37,82 dB |
| Meio-tom | 129 | 35,54 dB |
| Estático | 0 | 36,00 dB |

Comparações lado a lado e imagens de diferença em `bench/frames/`. Na diferença **amplificada 25×** não há estrutura visível em pele, cabelo, bordas finas (letreiro de neon) ou textura (parede verde).

**A diferença do corte DIMINUI no final:** SSIM 0,982 → 0,985 · PSNR 35,5 → 39,9 dB. O overlay e o encode final diluem.

## 3. Origem da diferença

| Comparação | SSIM | PSNR | Leitura |
|---|---|---|---|
| Controle: mesmo corte reencodado | 0,9936 | **45,23 dB** | piso do ruído de encode |
| Tonemap na hora vs fonte preparada | 0,9773 | **40,40 dB** | **a diferença nasce aqui** |
| Corte antigo vs corte v2.17 | 0,9822 | **35,54 dB** | **amplificada pelo zoom** |
| Final antigo vs final v2.17 | 0,9855 | **39,92 dB** | volta a diluir |

Não é "ruído normal": nasce no encode intermediário e é amplificada pelo reescalonamento do zoom sobre pixels já comprimidos.

**Deslocamento temporal descartado:** frame de mesmo índice dá 36,15 dB; vizinhos dão 24,30 dB. Os frames correspondem — sem risco de dessincronia.

## 4. CQ do intermediário

| CQ | Cache | PSNR (corte) | VMAF (FINAL) |
|---|---|---|---|
| 14 | 188 MB | 35,54 | 96,50 |
| 19 | 175 MB | 35,50 | — |
| **23 (escolhido)** | **134 MB** | 35,36 | **96,14** |

Confirmado que o CQ quase não move a qualidade — porque a diferença **não é de quantização**. cq23 entrega 29% menos disco por 0,36 ponto de VMAF. cq14 não se justificava.

## 5. Cache — HIT/MISS verificado ao vivo

Marcadores `PREPARED_SOURCE HIT` / `MISS` adicionados no log (não existiam).

| Cenário | Esperado | Medido |
|---|---|---|
| 1ª execução | MISS | MISS ✓ |
| 2ª execução | HIT | HIT ✓ |
| Headline alterada | HIT | HIT ✓ |
| Legenda alterada | HIT | HIT ✓ |
| Fonte alterada | MISS | MISS ✓ |
| Grade alterada | MISS | MISS ✓ |
| Resolução alterada | MISS | MISS ✓ |
| Tonemap alterado | MISS | MISS ✓ |

**FPS não invalida — e não deve.** O fps é normalizado depois, na extração do segmento (`-r`), não no cache. Verificado que a saída sai a 30 fps.

## 6. Concorrência — defeito encontrado e corrigido

**Defeito (v2.17):** o temporário tinha nome fixo (`<fonte>.prep.tmp.mp4`). Dois processos preparando a mesma fonte escreveriam no mesmo arquivo, e um poderia promover o que o outro ainda estava escrevendo.

**Correção (v2.17.1):** o nome do temporário leva o pid.

**Teste ao vivo, 2 processos simultâneos sobre a mesma fonte:**

- ambos registraram `MISS` (nenhum HIT falso)
- ambos promoveram com sucesso
- **zero temporários órfãos**
- arquivo promovido válido: duração 6,000000 s = duração da fonte

Fluxo confirmado: temporário próprio → validação de duração → promoção atômica (`replace`).

## 7. Benchmark de cache HIT (3 rodadas)

| Rodada | Tempo | Cache |
|---|---|---|
| 1 | 27,3 s | HIT |
| 2 | 29,1 s | HIT |
| 3 | 35,2 s | HIT |

**Mediana 29,1 s** (variação 7,9 s, térmica). Contra 294,4 s sem cache: **10,1×**. Os 32,4 s da medição original se confirmam.

## 8. Regressões

**No produto: nenhuma.** 161 testes passando, incluindo 7 novos de invalidação de cache e temporário por processo.

**Erros de método meus durante a auditoria**, todos detectados antes de virarem conclusão:

1. Apaguei a pasta `remotion` nos clones; `segments.json` sumiu, a composição saiu com 720 frames em vez de 851 e **os dois applies falharam**. Cheguei a medir SSIM 1,0 comparando arquivos copiados, não renderizados — desconfiei do resultado bom demais, conferi os hashes e refiz.
2. `rmtree` não removeu a pasta por lock do Windows e ambos os builds abortaram no `mkdir`.

Ambos corrigidos; os números deste relatório vêm das execuções válidas.

---

### Como reproduzir

```
py tools/render_benchmark/phase16_nvdec_cut.py    # corte: CPU vs NVDEC
pytest pipeline/test_prepared_source.py -q        # cache e concorrência
```

Scripts da auditoria em `scratchpad/` (build_finals.py, final_cmp.py, frames_dificeis.py, origem.py).
