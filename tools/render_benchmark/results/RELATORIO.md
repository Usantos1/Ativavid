# Estudo de performance de render — ATIVAVID 2.16

**Data:** 19/08/2026 · **Máquina:** i5-10300H (4 núcleos físicos / 8 threads), 24 GB, RTX 3050 Laptop 4 GB, Windows 11
**Vídeo:** `20260816-002530_IMG_3912_9d41f4134e` — 28,37 s · 1080×1920 · 30 fps · H.264 · 851 frames · cut 56,7 MB (16,6 Mbps)
**Referência:** CapCut, mesma máquina — 158 s de vídeo exportados em < 30 s → **> 5,3× tempo real**

Todos os testes rodaram com a fila do ATIVAVID **vazia**, sobre um **clone** do projeto. Nenhum arquivo de produção foi alterado.

---

## Resposta curta

| | x tempo real | vs. CapCut |
|---|---|---|
| Teto da máquina (transcode NVDEC→NVENC) | **9,4×** | **1,8× mais rápido** |
| Composição completa via FFmpeg (headline + 21 legendas) | **2,8×** | 0,5× |
| **ATIVAVID hoje (Apply visual)** | **0,09×** | **59× mais lento** |

O gargalo **não** é encode, decode nem I/O. É a rasterização dos gráficos: `node.exe` (Remotion/Chromium) consumiu **239,3 s dos 310,1 s** do Apply — **77,2%**.

Durante todo o caminho atual a **GPU ficou parada** (decode 0%, encode 1,7% em média) e a **CPU ficou em 99%**.

---

## 1. Mapa do pipeline (lido do código 2.16)

```
fonte
 ├─ [1/9]  transcribe.py ................... decode áudio · cache por assinatura
 ├─ [1b]   speech_regions + voice_levels + detect_color ... decode do vídeo ×3 (paralelo)
 ├─ [2b]   plano de corte (LLM/heurístico) . sem mídia
 ├─ [3/9]  render.py ....................... DECODE + ENCODE por segmento → cut.mp4
 ├─ [4/9]  scaffold Remotion ............... copytree + junction (I/O)
 ├─ [5/9]  transcribe.py sobre cut.mp4 ..... decode áudio  ← 2ª transcrição
 ├─ [6/9]  segments + edit-data ............ JSON
 ├─ [7/9]  trilha (ElevenLabs) ............. rede
 ├─ [8/9]  Remotion ........................ node + Chromium → ProRes 4444 alpha
 │          └─ compose ..................... decode cut + decode ProRes + ENCODE
 ├─ [9/9]  encode_final .................... ENCODE  ou  stream copy (condicional)
 └─ entrega ................................ shutil.copy2 (cópia física)
```

| Fase | Arquivo | Decodifica | Re-encoda | CPU/GPU | Interm. | Subproc. | Vezes/job |
|---|---|---|---|---|---|---|---|
| Análises | `speech_regions`, `voice_levels`, `detect_color` | vídeo ×3 | — | CPU | — | 3 ffmpeg | 3 |
| Corte | `helpers/render.py` | sim, por segmento | **sim** | **CPU 99,6%** | H.264 | 12 ffmpeg + 4 ffprobe | 1 |
| Legendas do cut | `transcribe.py` | áudio | — | CPU + rede | — | ffmpeg | 1 |
| Overlay | `app/overlay_path.py` | cut (OffthreadVideo) | sim | **CPU/Chromium** | **ProRes 4444** | 2 node | 1 |
| Compose | `app/overlay_compose.py` | cut + ProRes | sim | GPU encode | H.264 | ffmpeg | 1 |
| Encode final | `run_fast::encode_final` | sim **ou copy** | condicional | GPU/CPU | H.264 | ffmpeg | 1 |
| Entrega | `app/delivery_pack.py` | — | — | I/O | — | `copy2` | 1 |

**Viagem do frame:** decodificado **4–5×** · codificado **3×** · **1 cópia física** no fim.

## 2–5. Contagens medidas

| Item | Medido | Achado de 1.87 | Situação |
|---|---|---|---|
| ffprobe no corte | **4** (5 segmentos = 0,8/seg) | "~360 num EDL de 30 cortes" (12/corte) | **corrigido** — memoização por path+mtime+size |
| ffmpeg no corte (com reuso) | 12 | — | ok |
| ffmpeg no Apply | 20 | — | — |
| ffprobe no Apply | 16 | — | ok |
| node/Chromium no Apply | 2 (239 s) | — | **gargalo** |
| Decodes por frame | 4–5 | "decodes intermediários" | **confirmado** |
| Encodes por frame | 3 (+1 se não cair no stream copy) | "3–5 caminhos de re-encode" | **confirmado** |
| Cópias | 1 (`copy2` na entrega) | "há cópias" | confirmado, custo baixo |
| GPU no decode | **0%** | "GPU só no encode" | **confirmado** |

## 6–8. Tempo por fase — Apply visual (C1)

| Fase | Tempo | Fatia |
|---|---|---|
| **Remotion (node/Chromium → ProRes)** | **239,3 s** | **77,2%** |
| Compose (FFmpeg: cut + ProRes → H.264) | 55,9 s | 18,0% |
| Preparo, probes, remap de legenda | ~14,4 s | 4,6% |
| Validação do final | 0,24 s | 0,1% |
| Promoção do arquivo | 0,24 s | 0,1% |
| **Total** | **310,1 s** | |

**Resposta objetiva da Fase 8:** o Remotion é **77,2% do Apply**. Sem ele, e usando a composição direta medida (B3 = 10,08 s) mais o compose já existente, este mesmo Apply cairia para a ordem de **10–15 s** — de 5 minutos para segundos.

## 9–11. Teto da máquina (Fase 3)

| Teste | Tempo | FPS | x real | GPU enc | GPU dec | CPU |
|---|---|---|---|---|---|---|
| A0 cópia de fluxo | 0,30 s | 2838 | **94,6×** | 0% | 0% | 79% |
| A3b decode NVDEC → null | 2,83 s | 300 | 10,0× | 0% | 49,6% | 74% |
| A3a decode CPU → null | 4,70 s | 181 | 6,0× | 0% | 0% | 94% |
| **A3c2 NVDEC → hevc_nvenc (zero-copy)** | **3,03 s** | 281 | **9,4×** | 88,0% | 44,8% | 78% |
| **A3c NVDEC → h264_nvenc (zero-copy)** | **3,17 s** | 268 | **8,9×** | 60,5% | 31,9% | 86% |
| A1 CPU decode → h264_nvenc | 8,24 s | 103 | 3,4× | 38,1% | 2,1% | 97% |
| A2 CPU decode → hevc_nvenc | 15,76 s | 54 | 1,8× | 21,8% | 0% | 100% |
| A4 CPU decode → libx264 veryfast | 39,01 s | 22 | 0,7× | 0% | 0% | 100% |
| A3d d3d11va → NVENC | **falha** | | | | | |
| A5 av1_nvenc | **falha** | | | | | |

**CPU decode vs NVDEC:** 4,70 s → 2,83 s (**1,7× mais rápido**, e libera a CPU: 94% → 74%).
**A3d falha:** frames `d3d11va` não alimentam o NVENC diretamente nesta build — o caminho GPU→GPU no Windows é via CUDA.
**A5 falha confirma:** a RTX 3050 (Ampere) **não codifica AV1**, embora o FFmpeg liste o encoder.

## 12. H.264 vs HEVC

| Codec | Caminho | Tempo | Tamanho | Bitrate | Qualidade |
|---|---|---|---|---|---|
| h264_nvenc | zero-copy | 3,17 s | — | — | cq 23 |
| hevc_nvenc | zero-copy | **3,03 s** | — | — | cq 26 |
| h264_nvenc | decode CPU | 8,24 s | — | — | cq 23 |
| hevc_nvenc | decode CPU | 15,76 s | — | — | cq 26 |

No caminho zero-copy os dois custam praticamente o mesmo (HEVC até um pouco menos, por gerar menos bits para escrever). No caminho com decode na CPU o HEVC custa **quase o dobro**. Conclusão prática: **HEVC só compensa junto com decode por hardware**.

## 13–15. Composição sem Remotion (Fase 4)

Mesma carga visual do projeto real: 1 headline (0–4 s) + 21 blocos de legenda.

| Teste | Tempo | FPS | x real | GPU enc | GPU dec | CPU |
|---|---|---|---|---|---|---|
| Rasterizar 22 PNGs (custo único) | 4,7 s | — | — | — | — | — |
| **B3 NVDEC + overlay_cuda + hevc_nvenc** | **10,08 s** | 84 | **2,8×** | 23,6% | 14,7% | 65% |
| B2 NVDEC + overlay_cuda + h264_nvenc | 10,45 s | 82 | 2,7× | 18,8% | 10,0% | 66% |
| B1 CPU decode + overlay CPU + h264_nvenc | 12,01 s | 71 | 2,4× | 27,2% | 0% | 97% |
| B4 drawtext por frame + h264_nvenc | 14,44 s | 59 | 2,0× | 24,5% | 0% | 99% |

**Bloqueio de zero-copy registrado:** `overlay_cuda` recusa alpha sobre `nv12` — erro literal `Can't overlay yuva420p on nv12`. A saída encontrada foi converter a base ainda na GPU (`scale_cuda=format=yuv420p`); com isso o caminho funciona sem round-trip. A variante com `hwdownload/hwupload` falha.

**Observação honesta:** B1–B3 usam uma cadeia de 22 filtros `overlay` encadeados. Isso é ineficiente — 2,8× é o piso desta abordagem, não o teto da composição.

## 16. Comparação final

| Caminho | Tempo | FPS | x real | CPU | GPU dec | GPU enc | GPU 3D |
|---|---|---|---|---|---|---|---|
| A0 cópia de fluxo | 0,30 s | 2838 | 94,6× | 79% | 0% | 0% | 42% |
| A3c2 transcode zero-copy | 3,03 s | 281 | 9,4× | 78% | 45% | 88% | 23% |
| B3 composição direta | 10,08 s | 84 | 2,8× | 65% | 15% | 24% | 27% |
| **C0b corte com reuso de segmentos** | **8,8 s** | 97 | **3,2×** | — | — | — | — |
| **C1 Apply atual (Remotion)** | **310,1 s** | 2,7 | **0,09×** | **99%** | **0%** | **1,7%** | 33% |
| **C0 corte a frio (5 segmentos)** | **336,5 s** | 2,5 | **0,08×** | **99,6%** | **0%** | **2,2%** | 30% |
| *CapCut (referência observada)* | *< 30 s / 158 s* | — | *> 5,3×* | — | — | — | — |

## 17. Maior gargalo comprovado

**Rasterização de gráficos pelo Chromium.** 239,3 s de 310,1 s (77,2%) do Apply. O vídeo tem 851 frames; o Remotion entregou o overlay a **~3,6 fps**.

Segundo gargalo, quase do mesmo tamanho: **o corte a frio** — 336,5 s para 5 segmentos, com CPU a 99,6% e **GPU de decode em 0%**. Filtros de grade e zoom rodam na CPU e o encode não aproveita a placa.

## 18. Desperdícios comprovados

1. **NVDEC nunca é usado** — decode 0% nos dois caminhos reais. Medido: ligar NVDEC dá 1,7× no decode e devolve 20 pontos de CPU.
2. **Frames decodificados 4–5 vezes** por job (3 análises + corte + Remotion + encode final).
3. **Codificação em 3 camadas** — segmentos → ProRes 4444 → H.264 final.
4. **ProRes 4444 como intermediário**: 10 bits com alpha, escrito e lido inteiro em disco.
5. **Corte a frio a 0,08× tempo real** enquanto a máquina faz 9,4×.
6. **Segundo transcribe** sobre o `cut.mp4` (fase 5/9) permanece no código.

**Não confirmados / já corrigidos:** os "~360 ffprobe redundantes" de 1.87 — hoje são **4 por corte** (0,8 por segmento). A memoização resolveu. Cópias de arquivo existem mas custam ~0,2 s. Validações custam 0,24 s. I/O de disco não apareceu como gargalo em nenhum teste.

## 19. Potencial de render incremental

A máquina já tem as três peças necessárias, e **duas já existem no código**:

| Peça | Estado | Evidência medida |
|---|---|---|
| Reuso de segmentos do corte | **já existe** (`.segkey`) | 336,5 s → **8,8 s** (38×) |
| Overlay incremental (`--frames=a-b` + emenda `-c copy`) | **já existe** (teto de 85% de cobertura) | — |
| GOP de 1 segundo (`-g 30`) | **já configurado** | permite emenda por cópia a cada 1 s |

**Arquitetura para "trocar headline em 0–4 s de um vídeo de 60 s":**

```
1. diff dos insumos            → região afetada = [0s, 4s]
2. arredonda para o GOP        → [0s, 4s] já cai em fronteira de keyframe (GOP=1s)
3. re-renderiza SÓ 120 frames  → overlay parcial (Remotion --frames=0-119)
4. emenda                      → concat: [novo 0-4s] + [antigo 4-60s] com -c:v copy
5. áudio                       → intocado (headline não altera trilha nem voz)
6. legendas                    → intocadas (o remap só roda se o EDL mudar)
7. final                       → sem re-encode do trecho preservado
```

**Regiões que obrigam re-encode maior:** mudança de EDL (desloca tudo à frente), troca de grade/LUT (afeta todos os frames), mudança de layout de vídeo, e transições que cruzam a fronteira da região. Nesses casos a emenda por cópia não vale e o caminho completo é o correto.

**Risco de frame quebrado:** evitado porque a emenda só ocorre em fronteira de GOP; com `-g 30` toda marca de 1 s é keyframe. O ponto de atenção é o áudio, cujos frames AAC não coincidem com os de vídeo — por isso o áudio deve ser copiado inteiro, nunca emendado.

**Ganho estimado:** para uma troca de headline, de 310 s para a ordem de **15–25 s** (4 s de overlay novo + emenda por cópia + validação).

## 20. Recomendação

**CENÁRIO 1** — o pipeline direto com hardware já chega à mesma ordem de grandeza do CapCut.

Justificativa medida: a composição direta com a mesma carga visual roda em **10,08 s** (2,8× tempo real) contra **310,1 s** do caminho atual. São **31× de ganho sem escrever engine nenhuma** — e isso com uma cadeia de filtros deliberadamente ingênua.

**Não** prototipar a ATIVA Render Engine agora. A engine nativa (D3D11/Direct2D + NVENC) só se justifica depois de esgotar o caminho direto: ela custaria C++, interop, fallback para Intel/AMD e peso no instalador, para disputar uma faixa que hoje sequer foi explorada.

Ordem recomendada, por retorno medido:

1. **Trocar a rasterização por Chromium** onde o resultado visual permitir — vale 77,2% do Apply.
2. **Ligar NVDEC no corte e no compose** — 1,7× no decode e 20 pontos de CPU devolvidos.
3. **Render incremental para o editor** — a máquina já tem GOP de 1 s e o reuso de segmentos comprovado em 38×.
4. **Eliminar o ProRes intermediário** se a composição sair do Chromium.

---

### Como reproduzir

```
py tools/render_benchmark/phase3_ceiling.py     # teto da máquina
py tools/render_benchmark/phase4_compose.py     # composição sem Remotion
py tools/render_benchmark/phase5_current.py     # caminho atual (clona o projeto)
py tools/render_benchmark/phase2_probes.py      # contagem de ffprobe/ffmpeg do corte
```

CSVs e registros de chamadas em `tools/render_benchmark/results/`.
Saídas de vídeo vão para área temporária fora do repositório.

**Margem de erro:** cada teste da Fase 3 e 4 rodou 3 vezes (mediana reportada). O notebook apresenta variação térmica: numa segunda rodada o `libx264 veryfast` oscilou de 22,8 s para 39,0 s. Os caminhos com GPU se mostraram estáveis (±0,2 s). As Fases 2 e 5 rodaram uma vez cada, por custarem minutos.

---

# Experimentos 1 e 2 (executados na sequência)

## Experimento 1 — uma faixa de overlay vs. 22 filtros encadeados

| Caminho | Tempo | FPS | x real | GPU enc | GPU dec | CPU |
|---|---|---|---|---|---|---|
| **D2 · 1 `overlay_cuda`, gráficos direto do disco** | **6,94 s** | 123 | **4,1×** | 24,4% | 14,0% | 97% |
| B3 · 22 `overlay_cuda` encadeados | 10,08 s | 84 | 2,8× | 23,6% | 14,7% | 65% |
| B1 · 22 `overlay` na CPU | 12,01 s | 71 | 2,4× | 27,2% | 0% | 97% |
| D1 · 1 `overlay` na CPU | 24,93 s | 34 | 1,1× | 26,6% | 0% | 99% |
| **D3 · gerar a faixa ProRes 4444** | **80,86 s** | 11 | **0,35×** | 0% | 0% | **100%** |
| **D4 · compor a partir da faixa ProRes** | **148,74 s** | 6 | **0,19×** | 6,2% | 3,7% | **100%** |

**Resposta à pergunta do experimento:** a cadeia de 22 filtros custava 3,1 s (45% a mais). Com **um** `overlay_cuda` a composição chega a **4,1× tempo real** — a 2,3× do teto do transcode puro (9,4×).

**Achado inesperado e maior que o esperado — o ProRes 4444 intermediário.** Escrevê-lo custa 80,9 s e lê-lo de volta custa 148,7 s, ambos com **CPU em 100%**: **229,6 s só de ida e volta por um formato intermediário**. Compor os mesmos gráficos direto do disco leva **6,94 s**. O ProRes é, sozinho, o segundo maior desperdício do pipeline.

## Experimento 2 — Remotion desenhando estados em vez de frames

| Abordagem | Total | Por unidade |
|---|---|---|
| Remotion hoje: 851 frames (overlay) | 239,3 s | 0,28 s/frame (3,6 fps) |
| Remotion: 22 estados da composição `Overlay` (bundle reaproveitado) | **108,5 s** | **3,41 s cada** |
| Remotion: 22 estados da composição `Reels` (com vídeo) | 231,8 s | 9,68 s cada |
| Remotion CLI `still` (reempacota a cada chamada) | — | **121,2 s** só o primeiro |
| **FFmpeg rasterizando os mesmos 22 gráficos** | **4,7 s** | **0,21 s cada** |

**Resposta: desenhar estados não resolve.** Reduzir de 851 frames para 22 estados leva o Remotion de 239,3 s para 108,5 s — apenas **2,2×**. O custo do Remotion não está no número de frames, e sim no que cada invocação carrega: **3,41 s para desenhar texto num quadro transparente**, contra **0,21 s** do FFmpeg para o mesmo gráfico — **16× de diferença por peça**.

Detalhe operacional relevante: o CLI `remotion still` reempacota o projeto a cada chamada (121 s no primeiro estado). Qualquer implementação teria que usar a API de Node com bundle único — foi assim que medi.

## Conclusão consolidada

| Caminho para o mesmo vídeo de 28,4 s | Tempo | x real |
|---|---|---|
| Teto: transcode zero-copy | 3,03 s | 9,4× |
| **Rasterizar 22 gráficos + 1 `overlay_cuda`** | **11,6 s** | **2,4×** |
| *CapCut (referência)* | *~5,4 s equivalentes* | *> 5,3×* |
| Remotion por estados + compose atual | ~164 s | 0,17× |
| **ATIVAVID hoje** | **310,1 s** | **0,09×** |

O caminho direto completo — desenhar os gráficos e compor — custa **11,6 s** contra os **310,1 s** de hoje: **27× mais rápido**, mantendo a mesma carga visual.

**A recomendação de CENÁRIO 1 se confirma e fica mais forte.** Dois alvos, nesta ordem:

1. **Tirar a rasterização do Chromium** — 239,3 s → 4,7 s. Não adianta pedir menos frames ao Remotion (só 2,2×); o custo é por invocação, não por frame.
2. **Eliminar o ProRes 4444 intermediário** — 229,6 s de ida e volta que somem se os gráficos forem compostos direto.

Juntos, os dois são ~95% do tempo do Apply, e nenhum exige engine nativa.

## Próximo experimento recomendado (atualizado)

Validar **fidelidade visual**, não mais velocidade: renderizar o mesmo projeto pelos dois caminhos e comparar quadro a quadro (SSIM/PSNR) os gráficos gerados por FFmpeg contra os do Remotion. A velocidade já está provada; o que falta saber é **quanto do design atual sobrevive** fora do Chromium — quais estilos de legenda e headline são reproduzíveis com `drawtext`/PNG e quais dependem de recursos de navegador (gradientes animados, máscaras, tipografia variável).

Esse teste define o escopo real do trabalho: se 80% dos estilos forem reproduzíveis, o caminho é migrar os comuns e manter o Remotion como exceção.


---

# Experimento 3 — fidelidade visual fora do Chromium

Comparação do mesmo quadro (bloco "Pode", estilo `stacked`, o preset deste projeto) entre o Remotion e reproduções feitas só com FFmpeg.

| Variante | SSIM (faixa do texto) | Observação |
|---|---|---|
| v1 · Arial Bold, branco chapado | 0,935 | sem sombra |
| v2 · Segoe UI Black | 0,929 | fonte mais próxima da Poppins 900 |
| v3 · + sombra | 0,929 | `shadowx/y` é sólido, sem desfoque |
| v5 · + **gradiente dentro das letras** | 0,930 | reproduzido com `alphamerge` |
| controle (referência × referência) | 1,000 | teto do método |

**O SSIM não discriminou as variantes** — todas ficaram em ~0,93 porque a diferença dominante é **geometria** (fonte, corpo, posição), que eu não igualei, e não o estilo. O número diz "mesma ordem", não "reprodução validada". A comparação visual é mais informativa e está em `comparacao_final.png`.

## O que a inspeção do código e do teste mostra

Auditoria dos recursos que o estilo `stacked` realmente usa (`assets/shortform/src/StackedCaptions.tsx`):

| Recurso | Fora do Chromium | Como |
|---|---|---|
| Gradiente dentro das letras (`backgroundClip: text`) | **sim — provado** | máscara alpha + `gradients` (v5) |
| Poppins 900 itálico / Playfair | **sim** | fontes OFL: basta empacotar o `.ttf` |
| Opacidade por palavra (animação) | **sim** | já é um PNG por estado |
| Ajuste dinâmico de corpo (`fitFont`) | **sim** | cálculo antes de rasterizar |
| Famílias diferentes por linha | **sim** | um desenho por linha |
| Tracking negativo (`letterSpacing: -1.5`) | **não com `drawtext`** | precisa de libass ou rasterizador próprio |
| Sombra com desfoque | **não com `drawtext`** | libass tem `lur`; `drawtext` só sombra sólida |

**Conclusão do experimento:** o limite não é o FFmpeg — é o filtro `drawtext`, que é um rasterizador pobre. Nenhum recurso do estilo se mostrou exclusivo de navegador; os dois itens que o `drawtext` não faz são resolvidos por **libass** (que o FFmpeg já embute e suporta desfoque, posicionamento por glifo e karaokê) ou por um rasterizador dedicado.

**Consequência para o plano:** a etapa "tirar a rasterização do Chromium" não deve ser escrita sobre `drawtext`. O caminho correto é gerar um PNG por estado com um rasterizador de verdade — e a fonte deixa de ser obstáculo porque Poppins e Playfair são de licença aberta.

## Próximo passo recomendado (atualizado)

Prova de conceito de **um** estilo com fidelidade real: empacotar o `.ttf` da Poppins, reproduzir o `stacked` com libass (ou rasterizador dedicado) igualando corpo e posição, e medir SSIM de novo — agora com geometria igual, para o número passar a significar alguma coisa. Se ficar acima de ~0,98 na faixa do texto, o caminho está validado e o resto é trabalho de porte, estilo por estilo.


---

# Experimento 4 — prova de conceito com fidelidade real

Poppins de verdade (baixada do repositório oficial, licença OFL), corpo e posição **calibrados** contra o quadro do Remotion até a caixa do texto bater, e só então SSIM — agora medido num recorte justo de 400×160 px em volta da palavra.

| Etapa | SSIM | O que mudou |
|---|---|---|
| Partida (Segoe UI Black, sem calibrar) | **0,587** | fonte substituta, geometria diferente |
| Poppins Black calibrada (`drawtext`) | 0,842 | fonte certa + largura e posição iguais |
| + gradiente e sombra (`drawtext`) | 0,862 | |
| libass + desfoque (Poppins Black) | 0,883 | desfoque real, que o `drawtext` não faz |
| **libass + desfoque + Poppins ExtraBold** | **0,900** | **peso correto do preset** |
| teto (referência × referência) | 1,000 | controle |

**Descoberta durante a calibração:** o preset deste bloco é `STACK_MIXED` com `lineStyles: [3, 1]` — o estilo 3 é **Poppins 800 (ExtraBold)**, não Black 900. Eu vinha usando o peso errado; corrigir sozinho valeu quase 2 pontos de SSIM. A informação estava no `caption-cues.json`, o que é uma boa notícia: **o dado necessário para reproduzir o estilo já é exportado pelo pipeline**.

## O que ficou de fora

A varredura de desfoque (2,0 a 5,0) estabilizou em **0,90** e o gradiente aplicado por cima piorou o resultado nos desfoques altos — sinal de que minha faixa de gradiente não corresponde à do original. A caixa do texto ficou em 219×66 px contra 217×74 da referência: largura idêntica, **8 px a menos de altura**. Esse resíduo de métrica é a maior parte do erro que sobra, e não consegui identificar a origem.

**A meta que eu mesmo estabeleci (0,98) não foi atingida.**

## Como ler esse número

O teste foi feito **por fora**: eu observei o quadro pronto e tentei reproduzi-lo por tentativa e erro, sem usar a lógica de layout do template. Uma implementação de verdade não faria isso — ela portaria o mesmo cálculo (`fitFont`, `lineStyles`, `letterSpacing`) a partir dos mesmos dados, que já estão no `caption-cues.json`. Chegar a **0,90 às cegas** é um indicador favorável, não um veredito.

O que está provado com segurança:

- a **fonte** deixa de ser obstáculo (Poppins e Playfair são OFL, o `.ttf` pesa 150 KB);
- o **desfoque** e o **posicionamento por glifo** existem no libass, que o FFmpeg já embute;
- o **gradiente dentro das letras** é reproduzível (`alphamerge`);
- os **dados de estilo** necessários já saem do pipeline.

O que **não** está provado: que o resultado final seja indistinguível. Para isso falta o porte de verdade da lógica de layout.

## Recomendação final

O estudo termina com **CENÁRIO 1 confirmado** e um caminho de risco medido:

1. **A velocidade está provada** — 11,6 s contra 310,1 s, 27×, com a mesma carga visual.
2. **A fidelidade está indicada, não provada** — 0,90 de SSIM num teste às cegas.
3. **O próximo passo não é mais medir, é portar**: reimplementar UM estilo (`stacked`) lendo `caption-cues.json` e desenhando com libass, dentro do benchmark, e comparar os 22 estados do vídeo inteiro. Se a média ficar acima de 0,97, o caminho está validado e o resto é trabalho de porte estilo por estilo. Se ficar em 0,90 como aqui, aí sim vale discutir um rasterizador dedicado — que continua não sendo um encoder, e continua sem exigir C++ antes da hora.


---

# Experimento 5 — o porte do estilo `stacked` (resultado negativo)

Portei a lógica de `StackedCaptions.tsx` para Python + libass: `fitFont`, `lineStyles`, `letterSpacing`, `lineHeight`, o recuo de `-0.34em` entre linhas, o offset vertical de 15,6% e a animação de opacidade por palavra — tudo alimentado pelo **mesmo** `caption-cues.json`. Depois comparei os 22 estados contra os stills do Remotion.

## O porte não atingiu a barra

| Métrica | Resultado |
|---|---|
| Estados comparáveis | **9 de 22** |
| Estados em que o porte **não desenhou nada** | **5** |
| Estados vazios dos dois lados (excluídos) | 6 |
| Estados em que o porte desenhou e a referência estava vazia | 2 |
| **SSIM no recorte justo — média** | **0,724** |
| SSIM no recorte justo — mediana / pior | 0,677 / 0,579 |

A barra que eu tinha proposto era **0,97 de média**. O porte entregou **0,72**, e ainda errou o conteúdo em 7 dos 22 estados (5 sem desenhar, 2 desenhando onde não devia).

## Duas correções que precisei fazer no meio do caminho

1. **`s` do ASS ≠ `font-size` do CSS.** O porte saía com metade do tamanho. A razão medida para a Poppins foi 1,802 (155 no ASS para 86 no CSS). Corrigido, a largura passou a bater (212 px contra 217 da referência).
2. **Âncora vertical diferente.** O ASS posiciona pelo centro da caixa de linha, o CSS pelo fluxo do bloco — 19 px de diferença sistemática.

Mesmo com as duas, a altura da caixa continuou 62 px contra 74 px da referência, e a fidelidade ficou longe.

## Um erro meu que vale registrar

A primeira medição deste porte deu **0,978 de média** e eu quase reportei isso como sucesso. Estava errada por dois motivos: o recorte de 1080×600 incluía muita área vazia, e **6 dos 22 estados eram vazios dos dois lados**, marcando 1,0000 sem desenhar nada. Ao apertar o recorte e excluir os pares triviais, o número caiu para 0,72. O relatório anterior de 0,90 (um único quadro, calibrado à mão) continua valendo — e é melhor que a média do porte, porque ali eu ajustei aquele quadro específico.

## O que isso muda na decisão

**Nada do que foi medido sobre velocidade muda:** 11,6 s contra 310,1 s continua de pé, e o Remotion continua sendo 77,2% do Apply.

O que muda é o **custo da alternativa**. A hipótese de "trocar o Chromium por libass" era a mais barata; ela **não se sustentou** num porte de algumas horas. As causas são identificáveis (unidades de corpo, âncora vertical, modelo de caixa de texto), mas o ASS não foi feito para reproduzir layout CSS — cada divergência vira uma constante empírica, e foram duas só neste estilo, dos nove existentes.

Isso reposiciona as opções, sem inverter a conclusão do estudo:

1. **Continuar no caminho direto, mas com um rasterizador que implemente caixa de texto de verdade** (não ASS). O ganho de velocidade medido continua disponível; o que muda é quem desenha o PNG.
2. **Manter o Remotion apenas como rasterizador de estados** — mais lento que o ideal (108,5 s contra 4,7 s), mas com fidelidade garantida por construção. Ainda seria ~2,2× melhor que hoje.
3. **Rasterizador dedicado** passa a ser mais defensável do que parecia antes — continua não sendo um encoder, e continua sem exigir C++ para provar o conceito.

## Próximo experimento recomendado

Antes de escolher entre as três, medir o caminho 2 ponta a ponta: Remotion desenhando **só os estados** (108,5 s medidos) + composição com um `overlay_cuda` (6,9 s medidos) = ~115 s contra os 310,1 s de hoje. É **2,7× com fidelidade garantida e sem porte nenhum** — e serve de piso seguro enquanto o rasterizador é avaliado.


---

# CORREÇÕES — dois erros de medição que encontrei depois

Este bloco corrige números que publiquei antes neste mesmo relatório. Os valores abaixo substituem os anteriores.

## Erro 1 — throttling térmico inflou a Fase 6

O notebook estava quente das rodadas anteriores. Remedindo com a máquina descansada (58 °C, 3 rodadas, mediana):

| Teste | Publicado antes | **Correto** | Fator do erro |
|---|---|---|---|
| D4 · compor a partir da faixa ProRes | 148,7 s | **9,6 s** (2,96×) | **15,5×** |
| D3 · gerar a faixa ProRes 4444 | 80,9 s | **48,9 s** (0,58×) | 1,7× |
| D2 · 1 `overlay_cuda` direto | 6,9 s | **3,9 s** (7,26×) | 1,8× |

**O que isso derruba:** minha afirmação de que "o ProRes 4444 intermediário custa 229,6 s de ida e volta e é o segundo maior desperdício" estava **errada**. O custo real de compor a partir dele é **9,6 s**. O ProRes não é gargalo.

**O que isso reforça:** compor é barato em qualquer variante — 3,9 s direto dos gráficos, 9,6 s a partir da faixa. E os 3,9 s do caminho direto ficam a 1,3× do teto absoluto de transcode da máquina (9,4×), ou seja, praticamente no limite do hardware.

## Erro 2 — SSIM inflado no porte

Já registrado no Experimento 5: a primeira média de 0,978 vinha de um recorte com muita área vazia e de 6 estados vazios dos dois lados marcando 1,0000. O valor honesto é **0,724**.

## Lição de método

Duas medições minhas saíram erradas por motivos diferentes — uma por ruído térmico, outra por métrica mal recortada. As duas foram pegas ao cruzar com outra medição que não batia. Para este notebook, **medição de uma rodada só não vale**: a variação térmica chega a 15×. Os números da Fase 3 e 4 foram feitos com 3 rodadas e mediana; os das Fases 2 e 5 (que custam minutos) são de uma rodada e devem ser lidos como ordem de grandeza.

---

# Conclusão consolidada (após as correções)

## Onde o tempo vai, com números confiáveis

| Etapa | Tempo | Confiança |
|---|---|---|
| **Remotion desenhando os gráficos** | **239,3 s** | alta — log de produção |
| Compose (produção, a partir do ProRes) | 55,9 s | alta — log de produção |
| Compose (remedido, isolado) | 9,6 s | alta — 3 rodadas |
| Composição direta dos gráficos | 3,9 s | alta — 3 rodadas |
| Rasterizar gráficos com FFmpeg | 4,7 s (22 peças) | média — 1 rodada |
| Teto da máquina (transcode) | 3,03 s | alta — 3 rodadas |

**Tudo que não é Remotion é rápido.** O compose está a 9,6 s; a composição direta, a 3,9 s — encostada no teto do hardware.

## O que aprendi sobre as saídas

| Caminho | Ganho | Fidelidade | Situação |
|---|---|---|---|
| Trocar Chromium por libass | ~27× | **0,72 de SSIM** | **reprovado** no teste |
| Remotion desenhando só estados | **1,13×** | garantida | **inviável** — 62 mudanças por vídeo, não 22 |
| Remotion só nos frames animados | 1,85× (teto) | garantida | 54% dos frames animam; exige dedup por frame |
| Rasterizador dedicado | até ~27× | a provar | **única via para o ganho grande** |

Corrijo aqui minha recomendação anterior: eu havia proposto "Remotion desenhando estados" como piso seguro de 2,7×. **Estava errado** — a conta usava 22 blocos, mas o vídeo tem **62 instantes** em que a imagem muda, e o custo por invocação do Remotion (3,41 s) domina. O ganho real seria de 1,13×, ou seja, nenhum.

## Recomendação final

1. **Não existe meio-termo barato.** Ou se aceita o Remotion como é (~1,1–1,8× de ganho possível com muito esforço de cache), ou se troca o rasterizador (até ~27×, com fidelidade a provar).
2. **Os ganhos independentes do rasterizador continuam de pé e são baratos**: ligar NVDEC no corte (decode 0% hoje, 1,7× medido) e o reuso de segmentos que já existe (38× medido, 336,5 s → 8,8 s).
3. **Nada disso pede engine nativa nem encoder próprio.** O compose já está a 3,9 s.

## Próximo experimento, se houver

Provar fidelidade com um rasterizador que tenha modelo de caixa de texto de verdade — não ASS. O teste é o mesmo do Experimento 5 (os 22 estados, recorte justo, exclusão de pares vazios) e a barra é 0,97 de média. Só depois disso a decisão entre "conviver com o Remotion" e "trocar o rasterizador" tem base.


---

# Experimento 6 — rasterizador com caixa de texto de verdade

O porte para ASS reprovou (0,724). Refiz com um rasterizador que controla métrica por glifo, gradiente e desfoque (Pillow, em ambiente isolado), implementando as mesmas regras do `StackedCaptions.tsx`.

## Cada regra de layout implementada corretamente move o número

| Versão | SSIM (recorte justo) | O que foi corrigido |
|---|---|---|
| Porte para ASS | 0,724 | — |
| Rasterizador, 1ª tentativa | 0,730 | bug: `paste` com máscara não escreve alpha — saía só a sombra preta |
| + alpha corrigido | 0,752 | texto passou a aparecer na cor certa |
| + meia-entrelinha do CSS | **0,823** | a caixa de linha usa `ascent+descent`, não `font-size` — deslocava tudo ~20 px |
| + espaço entre palavras | **0,835** | linhas com várias palavras saíam 13% estreitas |

Depois da correção de meia-entrelinha, o alinhamento vertical ficou praticamente exato em linhas de uma palavra: referência em y=1200/1201, rasterizador em y=1201/1202.

## Velocidade

| Rasterizador | Por peça |
|---|---|
| Remotion (Chromium), cache frio | 3,41 s |
| Remotion (Chromium), cache quente | 1,45 s |
| **Rasterizador dedicado** | **0,196 s** |

**7× a 17× mais rápido por peça**, e os 22 estados saem em 4,3 s.

## O que este experimento estabelece

**Não é um muro, é uma lista.** Cada divergência encontrada tinha causa identificável e correção pontual, e cada correção moveu o SSIM para cima de forma mensurável (0,72 → 0,84 com três correções). O que resta são mais itens da mesma lista: largura em linhas multi-palavra (~10%), detalhes de gradiente e sombra, e dois estados em que a referência é um efeito de quadro inteiro que eu não portei.

**Mas também não é uma tarde de trabalho.** A barra de 0,97 não foi atingida em nenhuma das duas tentativas. Reproduzir fielmente o layout de um motor de navegador exige portar o modelo de caixa, e isso é um projeto — com nove estilos de legenda e dez de headline pela frente.

# Conclusão do estudo

**Sobre velocidade — provado e sem ressalvas:**

- O gargalo é a rasterização por Chromium: **239,3 s de 310,1 s (77,2%)** do Apply.
- Compor é barato: **3,9 s** direto, 9,6 s a partir de faixa — contra um teto de máquina de 3,03 s.
- A máquina **já supera o CapCut** em transcode puro (9,4× contra >5,3×).
- **Nada disso pede encoder próprio nem engine nativa.**

**Sobre a saída — medido, com limite conhecido:**

- Um rasterizador dedicado é **7–17× mais rápido por peça** que o Chromium.
- A fidelidade chegou a **0,835** e progride a cada regra portada, mas não atingiu 0,97 no esforço aplicado.
- Alternativas que mantêm o Remotion rendem pouco: desenhar só os estados dá **1,13×** (62 mudanças por vídeo, não 22), e só os frames animados tem teto de 1,85× (54% dos frames animam).

**Ganhos independentes disso, baratos e já provados:**

- **NVDEC no corte** — decode em 0% hoje; 1,7× medido e 20 pontos de CPU liberados.
- **Reuso de segmentos** — já existe no código: 336,5 s → 8,8 s (38×).

**Recomendação:** atacar primeiro os dois ganhos baratos, que não tocam no visual. A troca do rasterizador é o caminho para o ganho grande, mas deve ser tratada como projeto com escopo próprio — e a decisão de encará-lo agora depende de quanto os 27× valem frente ao risco de fidelidade que este estudo mediu, mas não eliminou.


---

# Experimento 7 — o corte pode ser 36× mais rápido

O corte a frio custa 294–336 s. Fui medir o ganho de ligar NVDEC e encontrei algo bem maior.

## Ligar só o decode por hardware rende pouco

| Caminho | Tempo | GPU dec | CPU |
|---|---|---|---|
| CPU decode + libx264 — **como é hoje** | 294,4 s | 0% | 98,9% |
| CPU decode + h264_nvenc | 238,5 s | 0% | 97,6% |
| NVDEC + h264_nvenc | **181,0 s** (1,6×) | 15,9% | **92,0%** |

A CPU continua em 92% mesmo com NVDEC ligado: **o decode nunca foi o gargalo do corte**. São os filtros.

## Onde o tempo do corte realmente está

Segmento de 15,5 s, fonte HEVC 10 bits HLG (vídeo HDR de iPhone) → H.264 8 bits:

| Caminho | Tempo | x real | Ganho |
|---|---|---|---|
| grade + zoom na CPU — **como é hoje** | 150,2 s | 0,10× | — |
| só zoom na CPU (sem a grade) | 32,6 s | 0,48× | **4,6×** |
| **tudo na GPU (`scale_cuda`)** | **4,2 s** | **3,73×** | **36,1×** |

**A grade de cor sozinha custa 4,6× do tempo do corte.** Movendo zoom e conversão de formato para a GPU, o segmento cai de 150 s para 4,2 s.

## Duas descobertas técnicas no caminho

1. **A fonte é 10 bits HDR** (`yuv420p10le`, HLG). O `h264_nvenc` só aceita 8 bits — sem conversão explícita ele falha com *"Provided device doesn't support required NVENC features"*. Hoje quem faz essa conversão é o filtro de grade, **por acidente**: tirar a grade quebra o encode se não se acrescentar `format=yuv420p`.
2. **Não existe grade em CUDA nesta build.** Os filtros disponíveis são `scale_cuda`, `overlay_cuda`, `colorspace_cuda`, `bilateral_cuda`, `chromakey_cuda` — não há `eq_cuda` nem `colorbalance_cuda`. Por isso a grade força o quadro de volta para a CPU.

## O que se perde no caminho rápido

Comparei um quadro dos dois caminhos: **RGB médio (114,116,107) na CPU contra (115,117,111) na GPU**. Praticamente idênticos — a diferença é o azul, exatamente o que a grade da marca ajusta (`+6%` contraste, `+8%` saturação, leve deslocamento quente).

Ou seja: os 36× custam **a grade de cor sutil**, não a imagem. E a grade pode voltar como LUT aplicada na GPU, ou ser aceita como perda.

## Isto muda a ordem das prioridades

O corte deixou de ser o "ganho barato de 1,6×" e passou a ser **o melhor retorno do estudo inteiro**:

| Alvo | Ganho medido | Risco |
|---|---|---|
| **Filtros do corte para a GPU** | **até 36×** | grade precisa virar LUT |
| Rasterização fora do Chromium | ~27× | fidelidade em 0,835, não resolvida |
| NVDEC sozinho | 1,6× | nenhum |
| Reuso de segmentos (já existe) | 38× quando aplicável | nenhum |

O corte e o Remotion são, juntos, quase todo o tempo do pipeline — e agora os dois têm caminho medido. A diferença é que o do corte tem **risco identificado e contornável**, enquanto o do rasterizador ainda tem fidelidade em aberto.


---

# Experimento 8 — a tentativa de implementar, e por que eu parei

Com a implementação aprovada, fui atrás do ganho de "até 36×" no corte. **A premissa não sobreviveu à medição no seu conteúdo.**

## O 36× só valia para vídeo SDR

O teste que deu 36× usava `scale_cuda` numa cadeia **sem tonemap**. Mas o código aplica `TONEMAP_CHAIN` (pipeline float32) quando a fonte é HDR — e:

| Fontes analisadas (25 projetos recentes) | Quantidade |
|---|---|
| **HDR HLG 10 bits (iPhone)** | **22 (88%)** |
| SDR bt709 | 3 (12%) |

**88% dos seus vídeos precisam do tonemap.** Para eles o 36× não se aplica.

## Tentei três caminhos para levar o tonemap à GPU

| Caminho | Resultado |
|---|---|
| `libplacebo` (Vulkan) + decode CPU | 70,2 s — 1,2× |
| **`libplacebo` (Vulkan) + NVDEC** | **50,1 s — 1,6×** (melhor) |
| `tonemap_opencl` + NVDEC | 65,3 s — 1,3× |
| CUDA → Vulkan sem passar pela CPU | **falha** — `hardware pixel format 'nv12' is not supported` |
| CUDA → OpenCL sem passar pela CPU | **falha** — `Failed to created derived device context: -40` |

Os dois caminhos de interoperabilidade que dariam o ganho grande **não funcionam nesta build/driver**. Sem eles o quadro sempre volta para a CPU, e o transporte come o ganho.

**Teto real para fonte HDR: 1,6×.**

## Por que eu não implementei

Fazendo a conta com números medidos, e não com a estimativa que eu tinha dado:

- O corte é 294 s de um job de ~1350 s.
- 1,6× no corte economiza ~110 s → **8% do tempo total do job**.
- O custo: trocar o pipeline de cor (`TONEMAP_CHAIN` por `libplacebo`) em **88% dos vídeos**, com resultado visual necessariamente diferente — outro algoritmo de tonemapping.

**8% de ganho em troca de mudar a cor de quase todos os vídeos é uma troca ruim.** Implementar isso porque estava aprovado, sabendo o que agora sei, seria prestar um mau serviço.

## Correção do que eu te disse antes

Eu recomendei "filtros do corte na GPU: até 36×, risco contornável". **Estava errado em duas frentes:** o 36× foi medido sem o tonemap que os seus vídeos exigem, e o risco não é a grade de cor (sutil) e sim o tonemap HDR (estrutural).

O ranking corrigido:

| Alvo | Ganho real no seu conteúdo | Situação |
|---|---|---|
| Filtros do corte na GPU | **1,6×** (não 36×) | interop CUDA↔Vulkan/OpenCL falha nesta build |
| Rasterização fora do Chromium | ~27× no Apply | fidelidade em 0,835, em aberto |
| Reuso de segmentos (já existe) | 38× quando aplicável | funcionando |

## O que eu faria agora

**Nada no corte.** O ganho não paga o risco.

O prêmio continua sendo o Remotion (77,2% do Apply), e o caminho para ele continua sendo o rasterizador — cuja fidelidade parou em 0,835 e precisa de trabalho de porte, não de mais medição.

Uma alternativa não testada que vale considerar antes disso: **tonemapar a fonte uma única vez e guardar o resultado**. Hoje o tonemap roda por segmento, a cada reprocessamento. Como o estudo mostrou que reprocessar é comum, um intermediário SDR em cache tornaria todos os cortes seguintes elegíveis ao caminho todo-GPU — sem trocar o algoritmo de tonemapping e sem mudar a cor. Isso sim mereceria um experimento.
