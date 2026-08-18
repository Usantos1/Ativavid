# Changelog

## 1.90

Recursos novos no visual: mais estilos de legenda, headlines para escolher e trilha que combina com o conteúdo.

- Novo estilo de legenda **Impacto**: a palavra falada aparece numa caixa colorida que pulsa — o visual mais usado em Reels de venda
- Novo estilo de legenda **Recorte**: letras grandes com contorno grosso, estilo sticker de CapCut
- A IA agora sugere **3 headlines por vídeo** — as opções aparecem no editor e um clique troca na hora
- A **trilha sonora combina com o tipo de conteúdo**: humor ganha música divertida, venda ganha batida energética, educativo ganha som calmo de foco
- As cores da marca valem nos estilos novos: a cor de ênfase pinta a caixa do Impacto e a cor da legenda pinta o texto do Recorte
- Projetos antigos recebem os estilos novos automaticamente no próximo render
- O instalador ficou um pouco menor (limpeza de arquivos internos)

## 1.89

Velocidade: o mesmo vídeo fica pronto bem mais rápido, com a mesma qualidade.

- O vídeo não é mais transcrito duas vezes — menos espera e menos custo de API
- Cortes manuais reaproveitam os trechos que não mudaram: aplicar um ajuste pequeno não refaz a extração inteira
- A trilha sonora IA e a preparação do render começam em paralelo com o corte
- Gravar a capa no vídeo não regrava mais o arquivo inteiro (só o comecinho)
- A pré-visualização leve agora usa a placa de vídeo de verdade — antes falhava em silêncio e caía no modo lento
- O perfil de desempenho passa a valer também na extração paralela dos trechos
- Desperdícios internos removidos: sondas repetidas do mesmo arquivo, cópias e regravações desnecessárias, áudio normalizado uma vez só
- Fila e editor não pesam mais no disco com o app minimizado
- Correção em projeto antigo não usa mais legenda desatualizada do corte anterior
- "Excluir", "eliminar" e "reduzir" agora são entendidos como pedido de corte no Editar com IA

## 1.88

Consertos de confiança: o que estava vendido e o que podia apagar trabalho.

- Apagar um projeto no hub manda a pasta para a Lixeira, como no painel
- Aplicar alterações entra na mesma fila dos vídeos, com teto de jobs paralelos
- A Fila deixa de fingir que uma atualização ainda está rodando quando ela já falhou
- Pedido vago no Editar com IA (tipo “melhoria”, “melhora o vídeo”, “deixa melhor”) não corta o vídeo
- O preset escolhido na importação passa a valer no render (projeto > preset da marca > marca > padrão do app)
- Transcrição só reusa o cache se o arquivo fonte tiver o mesmo tamanho e data
- Intensidade do estilo volta a gravar na marca ativa
- Erro na Fila mostra a mensagem e abre o detalhe no card
- O app não inventa mais @lojaprimecamp no card final — a copy da marca fica vazia até você preencher

## 1.87

Editor de correções rápidas: ajuste o vídeo pronto sem mandar tudo de volta para análise.

- Dá para editar a headline direto no vídeo
- Dá para corrigir legendas direto no player
- Dá para fazer cortes manuais na timeline
- A agulha agora corta e exclui trechos, com os botões Cortar e Excluir
- Zoom na timeline para acertos mais precisos
- Novo botão Aplicar alterações
- Correções pequenas não precisam mais refazer toda a análise do vídeo
- Cortes manuais mantêm as legendas no tempo certo
- Se a atualização falhar, o vídeo anterior fica protegido
- A pasta publicar atualiza depois de aplicar as correções
- Aplicações de correções agora aparecem na Fila
- É possível continuar usando o ATIVAVID enquanto o vídeo é atualizado
- Concluídos mostra quando um vídeo está sendo atualizado
- Aviso global quando a atualização termina
- Melhor acompanhamento do processamento de correções
- Histórico de versões e restauração mais estáveis
- Ajustes gerais de estabilidade no editor
- Cortes manuais voltam a aplicar quando o áudio de um mesmo vídeo se cruza no corte
- Pedido vago no Editar com IA (tipo “melhoria”) não corta mais o vídeo inteiro
- A Fila não fica mais em “atualizando” quando a atualização já falhou

## 1.86

- No tipo de conteúdo da importação, as opções do menu ficam legíveis (texto escuro no fundo claro)
- A headline não repete mais “cursinho” no lugar de “1% mais feliz”; a correção vale no gancho, não só na legenda
- Vídeo em Concluídos abre pronto, sem o aviso cinza do Windows; se precisar perguntar, o modal fica no centro, no visual do app

## 1.85

- Em Concluídos, cada card mostra a data e a hora ao lado de “Vídeo concluído”
- A lista fica na ordem do último término — vídeo reeditado sobe para o topo

## 1.84

- A legenda do post na aba Visual vem aberta, com quebra de linha de Reel, logo abaixo da trilha — sem ficar atrás do botão de ajuda
- Acrescentar um vídeo no fim não para mais a fila só porque o preset da marca estava incompleto

## 1.83

- O botão Capa grava uma imagem JPG do frame que está na tela (com o texto do vídeo) ao lado da legenda, na pasta para postar

## 1.82

- Corrigir palavra na legenda agora vale de verdade: Perico vira Película na faixa, sem refazer o vídeo inteiro
- Pedir “troca X por Y” no Editar com IA grava a palavra no arquivo na hora
- Cada vídeo pronto ganha uma pasta com o nome do vídeo: o MP4, a capa e a legenda do post — pronta para mandar ao Drive / Mlabs
- O botão Capa grava a imagem nessa pasta; Abrir pasta abre ela, não o meio do projeto

## 1.81

- Dá para proteger um trecho na timeline: a IA não corta aquele pedaço
- Na importação e em Estilos, dá para escolher o tipo de conteúdo (educativo, humor, venda…)
- Cada marca pode ter vários presets (Humor, Venda, Review…) sem copiar arquivo pesado
- O editor guarda versões leves do corte para restaurar depois
- Na fila, o tempo restante aparece só quando o app já tem histórico de processamentos
- A tela Sistema ficou mais simples; o detalhe técnico continua em Avançado
- Marca, B-roll e card final ficam em Estilos, não mais misturados em Sistema

## 1.80

- Renomear vídeo abre um modal no centro da tela, no visual do app
- Visualizar abre o vídeo no player do editor, não no player do Windows

## 1.79

- Vídeo no fim volta a funcionar: o arquivo entra na pasta do projeto aberto, mesmo depois que o vídeo já foi editado

## 1.78

- Na barra de play: Vídeo no fim acrescenta um take novo depois do material já editado (vira o CTA)
- O botão de imagem continua só para recorte por cima; não mistura com take novo

## 1.77

- Preview do vídeo vai até o topo; a barra de play fica só na timeline
- Ver final e a aba Visual abrem o MP4 mesmo quando o nome não é final.mp4
- Clique no preview pausa e dá play

## 1.76

- Abrir ATIVAVID no final da instalação usa o atalho (como um clique na Área de Trabalho)

## 1.75

- Abrir ATIVAVID no final da instalação agora inicia o app (solto do instalador)

## 1.74

- Abrir ATIVAVID no final da instalação agora inicia o app de verdade
- Na barra de play: apagar o take e escolher a capa no frame da agulha

## 1.73

- Dá para importar uma pasta: cada subpasta vira um vídeo; se tiver vários arquivos na mesma pasta, eles entram juntos
- A tela não pisca mais enquanto importa
- Editor Visual mais limpo: preview em destaque, barra de play até o preview, legenda do post recolhível
- No topo do editor: Ver final, Abrir pasta e as abas Edição | Estilo | Visual

## 1.72

- A capa do vídeo agora é o primeiro frame e vai junto no arquivo na hora de postar

## 1.71

- Atalho na Área de Trabalho vem marcado
- Abrir o ATIVAVID no final da instalação volta a funcionar

## 1.70

- O vídeo pronto agora leva o nome da headline

## 1.69

- Novos modos de edição: Completo, Dinâmico e Reels/Shorts
- Melhor preservação de gancho, contexto e CTA
- Editar com IA agora aplica alterações reais na timeline
- Nova experiência de importação
- Home e fila mais simples de acompanhar
- Melhorias de velocidade no processamento

## 0.1.68

Menu ⋯ dos cards em Concluídos abre as ações do vídeo certo: abrir pasta, ver final, alterar estilo e apagar.

## 0.1.67

Estilos volta a abrir o catálogo em `/estilo-padrao` (sem `unknown route`).
Complete preserva fala; só limpa silêncio, erro, repetição e take abandonada.

## 0.1.66

Fila sem jargão técnico: o cliente vê Preparando → Editando → Finalizando → Concluído.
O motor (OVERLAY/FULL, Remotion, FFmpeg, NVENC) continua só nos logs.

## 0.1.65

Novo Motor de Render Automático: aceleração por hardware, caminho OVERLAY para jobs compatíveis e fallback automático para FULL.

O cliente vê apenas **Motor de Render: Automático**. `overlayRollout = off` desliga o OVERLAY e força FULL.
