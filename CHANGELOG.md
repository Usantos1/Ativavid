# Changelog interno

## 0.1.67

Estilos volta a abrir o catálogo em `/estilo-padrao` (sem `unknown route`).
Complete preserva fala; só limpa silêncio, erro, repetição e take abandonada.

## 0.1.66

Fila sem jargão técnico: o cliente vê Preparando → Editando → Finalizando → Concluído.
O motor (OVERLAY/FULL, Remotion, FFmpeg, NVENC) continua só nos logs.

## 0.1.65

Novo Motor de Render Automático: aceleração por hardware, caminho OVERLAY para jobs compatíveis e fallback automático para FULL.

O cliente vê apenas **Motor de Render: Automático**. `overlayRollout = off` desliga o OVERLAY e força FULL.
