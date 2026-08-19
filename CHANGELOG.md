# Changelog

## 2.16

Ajustar legenda ou headline deixou de custar uma hora.

- **Mudança pequena agora usa o caminho rápido**: corrigir legenda, trocar headline ou cortar um trecho reaproveita o vídeo já processado, em vez de refazer tudo do zero (re-transcrever, re-analisar, re-cortar). O reprocessamento completo ficou só para quando entra material novo (anexar outro vídeo) ou b-roll/inserts
- **O app parou de brigar consigo mesmo por CPU**: ele contava os "threads" do processador como se fossem núcleos e abria o dobro de vídeos ao mesmo tempo do que a máquina aguenta. Cada vídeo ficava até 3x mais lento. Agora conta núcleo real — menos vídeos ao mesmo tempo, cada um terminando muito antes


## 2.15

Correção grave: o app estava derrubando os próprios vídeos.

- Ao reaproveitar um projeto, a limpeza de arquivos antigos encerrava processos "pelo nome" — e acabava **encerrando a própria edição em andamento**, além das edições dos outros vídeos rodando em paralelo. O vídeo morria no meio, sem mensagem, e o card ia para erro
- Era por isso que **reprocessar quase sempre falhava**: a pasta de trabalho já existia, então a limpeza rodava e matava a edição toda vez
- Também explicava erros "em cadeia" quando vários vídeos eram processados juntos: limpar um derrubava o render do outro
- Agora a limpeza só encerra o programa que realmente está segurando aquele arquivo, nunca a edição em andamento nem a dos vizinhos

## 2.14

Nenhum card fica preso na Fila.

- **O aviso "Revisar" não gruda mais no card**: um aviso de atualização antiga ficava salvo junto do vídeo e voltava para sempre, mesmo depois de resolvido. Agora ele some quando deixa de valer
- Card com aviso ganhou botões que resolvem: **Aplicar de novo** (refaz o vídeo mantendo os seus cortes) e **Dispensar** (mantém o vídeo como está e tira o aviso)
- **"Tentar novamente" não é mais beco sem saída**: se o arquivo do vídeo está quebrado ou sumiu do lugar, o app avisa na hora em vez de mandar para a fila e falhar de novo. Nesses casos o card mostra **Importar de novo** e **Apagar**

## 2.13

Projeto travado no "Aplicar" nunca mais.

- Quando o atalho rápido do Aplicar não consegue garantir a legenda alinhada, o app **reprocessa o vídeo inteiro sozinho** em vez de falhar — e os seus cortes manuais são mantidos no reprocesso
- Isso conserta o caso em que toda tentativa de aplicar dava "Não foi possível preparar este corte" para sempre, sem saída
- Ao terminar um vídeo, o app reajusta o relógio interno das legendas — era o descompasso que travava o Aplicar dos projetos mais antigos

## 2.12

Importar ficou mais simples — e o app agora respeita os seus cortes.

- Tela de importação nova: cards diretos, incluindo **Edição leve** (só tira silêncios e erros, sem IA mexendo no corte — o modo mais rápido) e **Viral** (retenção máxima em um clique). Proteção e Estilo ficam recolhidos para quem quiser ajustar
- **Reprocessar não desfaz mais os seus cortes**: se você removeu um trecho no editor e depois trocou headline/estilo, o corte manual é mantido — a IA só replaneja se você mudar ritmo, intensidade ou tipo de conteúdo
- Fim dos "flashes": takes de 0,2s que a IA às vezes deixava no corte (uma piscada de vídeo que parecia corte errado) são descartados — no plano da IA e nas sobras de remoção no editor
- Arquivo que chegou incompleto do celular (cópia interrompida) agora dá mensagem clara: copie de novo do celular — tentar de novo com o mesmo arquivo não resolve
- Se o app fechar no meio de um "Aplicar" (ex.: atualização do instalador), o projeto não fica mais preso em "Aplicando edição…" — mostra que foi interrompido e pede para aplicar de novo

## 2.11

Correção: cards de Concluídos não estouram mais a borda.

- Os botões novos (Pasta, Legenda) quebram linha quando o card é estreito, em vez de vazar para fora
- O selo "CONCLUÍDO" não é mais cortado na borda do card

## 2.10

Mais ritmos de corte, tipo Viral e a SUA fonte no sistema.

- **4 presets de ritmo novos** (7 no total): **Cirúrgico** (um corte por frase, zero pausas), **Narrativa** (blocos longos, a história nunca quebra), **Turbo** (corte máximo) e **Comercial** (ritmo de anúncio com flash e zoom fortes) — cada um com regras próprias para a IA
- Novo tipo de conteúdo **Viral**: gancho nos 2 primeiros segundos, zero enrolação e final que faz reassistir — com trilha phonk própria
- **Sua fonte no app**: coloque qualquer .ttf/.otf na pasta `ATIVAVID/Fontes` (ex.: a Integral do CapCut) e escolha "Sua fonte (pasta Fontes)" — vale para legendas e headlines

## 2.09

Home nova: mostra o que está acontecendo e vídeos de verdade.

- **Faixa "Agora"** no topo do Início: o que está processando, com a etapa real ("Renderizando efeitos…") e a barra — e a área de importar encolhe enquanto há trabalho
- **Título humano nos concluídos**: em vez de "IMG_3987", o card mostra a headline do vídeo
- **Ações do dia a dia no card**: botões "Pasta" (abre a publicar) e "Legenda" (copia o texto do post) direto no concluído
- **Arraste para qualquer lugar da janela**: um alvo gigante "Solte para importar" aparece na hora
- **Clipes de podcast** ganhou botão próprio na área de importar
- Os contadores do topo ("2 Processando · 49 Concluído") viraram atalhos clicáveis
- Os campos da tela Estilos agora respeitam o tema escuro (dropdown incluso)

## 2.08

Quatro layouts de vídeo novos e a tela de Estilos mais clara.

- **Moldura**: o vídeo vira um cartão arredondado sobre um fundo na cor da marca
- **Barra inferior**: vídeo no topo e uma faixa sólida embaixo, onde a legenda senta — leitura perfeita em qualquer cena
- **Fundo desfocado**: o vídeo aparece menor, flutuando sobre uma cópia borrada dele mesmo — o look clássico de Reels
- **Degradê**: uma sombra suave na base do vídeo para a legenda nunca sumir na cena clara (este mantém o render rápido)
- A área de marca em Estilos foi reorganizada: grupos claros ("Marca ativa", "Criar marca nova", "Imagens da marca"), botões que dizem o que fazem e sem textos técnicos

## 2.07

O app fica em silêncio quando não tem nada acontecendo.

- A Fila agora é avisada na hora que algo muda (evento do servidor), em vez de perguntar a cada 2,5 segundos
- Com a fila vazia e nada rodando, o app para de varrer o disco — zero trabalho em segundo plano
- Durante um processamento, a barra de progresso continua atualizando rápido como sempre
- Se a conexão de eventos cair, o comportamento antigo volta sozinho

## 2.06

Vídeo em Concluídos com seek instantâneo e sem pesar na memória.

- Dá para **pular para qualquer ponto** do vídeo pronto na visualização — antes o player só tocava do início
- O app **não carrega mais o vídeo inteiro na memória** para exibir (um final de 300 MB usava 300 MB de RAM por visualização; agora vai em pedaços de 64 KB)
- Verificado byte a byte no servidor real

## 2.05

Contador de lista: o 1º, 2º, 3º aparece na tela sozinho.

- Novo elemento **"Contador de lista"** (desligado por padrão): quando a fala enumera — "primeiro…", "segundo…", "motivo um…" — um selo com o número aparece no canto, na cor da marca, sincronizado com cada item
- Detecção direto das legendas, sem custo de IA, com proteção contra falsos positivos ("trinta segundos" não vira lista; a sequência precisa começar no primeiro)
- Só ativa quando encontra 2 ou mais itens de verdade

## 2.04

Entrada da headline do seu jeito.

- Novo controle **"Entrada da headline"** em Estilos → Personalizar: **Suave** (aparece subindo, como hoje), **Com peso** (entra crescendo, com impacto) ou **Deslizando** (vem da esquerda)
- Vale para todos os estilos de headline — Carimbo e Pergunta→Resposta mantêm as entradas próprias que já têm personalidade
- A escolha fica salva no preset da marca

## 2.03

Emoji nas legendas e headline que fica o tempo que você quiser.

- Novo elemento **Emoji nas legendas** (desligado por padrão): palavras como grátis, garantia, celular, cuidado e hoje ganham o emoji certo automaticamente — no máximo 1 a cada 6 segundos, sem poluir, sem custo de IA
- Novo controle **"Headline fica na tela"**: Alguns segundos (como hoje), O dobro do tempo, ou O vídeo inteiro
- Os dois valem para todos os estilos e ficam salvos no preset da marca

## 2.02

Validação completa e uma correção importante no reaproveitamento de render.

- Rodamos o pipeline inteiro de ponta a ponta num vídeo real com os recursos novos juntos (Impacto + Pergunta→Resposta + fontes da marca + palavras de destaque): tudo funcionando, 337/337 frames
- **Correção**: o reaproveitamento de render guardava tudo num lugar só — projetos diferentes se atropelavam e ninguém reaproveitava de verdade; agora cada projeto tem o seu espaço
- Medido depois da correção: repetir um render com os mesmos efeitos caiu de ~88s para ~16s (o desenho dos efeitos é reaproveitado inteiro e só a montagem final roda)

## 2.01

Imagens de apoio quando você pede, e timeline leve para arrastar.

- **B-roll deixa de depender do layout**: escolher "Poucas, sempre" ou "Várias, sempre" agora coloca imagens mesmo no vídeo de quadro cheio — antes o pedido era ignorado em silêncio porque o layout padrão desligava tudo
- O seletor ficou honesto: **Nunca · Só na tela dividida · Poucas, sempre · Várias, sempre** (quem não mexer continua com o quadro cheio limpo de hoje)
- **Arrastar a borda de um take ficou ~50× mais leve** — a timeline não é mais reconstruída (com todas as miniaturas) a cada movimento do mouse

## 2.00

Marca com voz própria: destaque suas palavras, leve seu preset e publique no feed.

- **Palavras de destaque da marca**: liste seus produtos, números e bordões (ex.: "película, 3D, blindada, 90 dias") e a legenda Empilhado passa a destacar essas palavras
- **Exportar e importar preset**: salve o estilo num arquivo e leve para outra máquina, ou receba um pronto — o botão Exportar grava em `Documentos do ATIVAVID → presets-exportados`
- **Novo formato Feed 4:5** (1080×1350), o tamanho que ocupa mais tela no feed do Instagram
- Disponíveis na importação e em Estilos, junto com os formatos que já existiam

## 1.99

Fonte da marca: escolha a tipografia das legendas e das headlines.

- Em Estilos → Personalizar: **Fonte da legenda** e **Fonte da headline**, com 8 opções (Poppins, Inter, Montserrat, Playfair Display, Lora, Anton, Bebas Neue, Archivo Black) ou "Padrão do estilo"
- Vale para todos os estilos de headline e de legenda — as quebras de linha são medidas na fonte escolhida, nada estoura
- Fontes de peso único (Anton, Bebas, Archivo Black) nunca ganham negrito falso borrado
- O estilo Empilhado mantém a tipografia própria (ele é um design de fontes por natureza)
- O preview do editor mostra a fonte real; a escolha fica salva no preset da marca

## 1.98

Clipes de podcast: um vídeo longo vira vários Reels de uma vez.

- Nova opção na importação: **Clipes de podcast** — a IA analisa o vídeo inteiro (até 2 horas), separa de 2 a 6 clipes independentes e cria **um vídeo próprio na Fila para cada um**, com headline própria
- Cada clipe começa num gancho e termina numa conclusão — nunca no meio de uma frase, e sem sobreposição entre clipes
- Os clipes herdam a marca, o tipo de conteúdo e as proteções escolhidas na importação
- O vídeo original não é duplicado no disco (os clipes apontam para o mesmo arquivo)
- Por enquanto funciona com vídeos verticais (9:16); vídeo de câmera deitada segue a regra atual

## 1.97

Nova headline Pergunta → Resposta: o gancho de retenção clássico.

- A pergunta abre o vídeo em branco; no momento em que a fala começa a responder, a **resposta entra numa pílula colorida** com efeito — a IA gera pergunta e resposta, e a virada é cronometrada pelo primeiro corte
- No editor, clique na headline para editar **o que está na tela**: antes da virada edita a pergunta, depois edita a resposta
- O "?" da pergunta é garantido automaticamente
- Estilo disponível na aba Estilos, com preview do conceito

## 1.96

Render incremental: corrigir headline ou palavra da legenda re-renderiza só o trecho afetado.

- Trocar a headline re-renderiza apenas os primeiros segundos do vídeo; corrigir uma palavra da legenda, só dali para a frente — o resto é reaproveitado do render anterior, sem perda de qualidade (emenda exata, frame a frame)
- Medido: correção de headline num vídeo de teste caiu de ~55s para ~26s de render — e o ganho cresce com a duração do vídeo
- O sistema guarda o último render de efeitos de cada projeto (limite de 3 GB no disco, os mais antigos saem sozinhos)
- Qualquer mudança maior (estilo, cores, cortes, posição) volta ao render completo automaticamente — na dúvida, refaz tudo

## 1.95

Mais velocidade de verdade e o novo tipo Anúncio (AIDA).

- Novo tipo de conteúdo **Anúncio (AIDA)**: a IA monta o corte na estrutura Atenção → Interesse → Desejo → Ação, com gancho forte nos 2 primeiros segundos e CTA garantido no fim — disponível na importação e em Estilos
- A exportação final não regrava mais o vídeo inteiro quando o render já sai pronto — medido: de dezenas de segundos para ~1s nessa etapa
- A análise inicial do vídeo (transcrição, silêncios, voz e cor) roda em paralelo — a fase custa o tempo da transcrição, não a soma das quatro
- Música do tipo Anúncio: batida comercial com fechamento marcado

## 1.94

Medição de verdade e render respeitando o perfil da máquina.

- Cada etapa do processamento agora é cronometrada por inteiro (análise, plano da IA, legendas, espera da trilha) — a estimativa de tempo da Fila fica realista depois de alguns vídeos na versão nova
- O render de efeitos passa a respeitar o perfil de desempenho escolhido em Sistema (antes usava um número fixo de trabalhadores, mesmo no perfil Econômico)
- Máquinas com mais núcleos usam mais trabalhadores no render; máquinas fracas continuam protegidas

## 1.93

Galeria de modelos prontos: um clique monta o visual completo.

- Nova seção **"Começar por um modelo"** no topo da aba Estilos, com 12 combinações completas: Venda agressiva, Educativo clean, Humor caótico, Notícia urgente, Sticker CapCut, Review direto, Minimalista, Institucional, Impacto total, Depoimento, Tutorial prático e Clipe de podcast
- Cada modelo define headline, legenda, cores, ritmo, intensidade, tipo de conteúdo e efeitos de uma vez — depois é só ajustar o que quiser e salvar
- Dá para salvar qualquer modelo ajustado como preset da marca (botão "Novo preset", como sempre)

## 1.92

Posição e tamanho da legenda agora são escolha sua.

- Em Estilos → Personalizar: **Posição da legenda** (Embaixo, Centro ou Alto) e **Tamanho da legenda** (Pequena, Média ou Grande)
- Vale para todos os 9 estilos de legenda — cada um sobe e escala do seu jeito, sem quebrar linha errado
- O preview do editor mostra a posição e o tamanho reais antes de renderizar
- A escolha fica salva no preset da marca, como as cores

## 1.91

Três estilos novos de headline.

- **Pílula**: uma barra compacta no topo que fica o vídeo inteiro — boa para dar contexto ("Parte 3", "Teste real")
- **Manchete**: faixa estilo jornal na base do vídeo, abaixo da legenda
- **Carimbo**: carimbo girado com borda grossa que entra com impacto
- A cor da headline da marca pinta o ponto da Pílula, a barra da Manchete e o Carimbo inteiro
- Espaço do b-roll continua certo mesmo com a Pílula fixa na tela

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
