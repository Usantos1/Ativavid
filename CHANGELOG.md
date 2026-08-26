# Changelog

## 2.92

- Correção interna de tipos do template (os estilos novos "Bolha de
  conversa" e "Marca-texto" agora são conhecidos pelo verificador de tipos
  — sem efeito visual, previne quebras em builds futuros)

## 2.91

- **Você define as hashtags do post.** Campo novo na tela de Estilo:
  "Hashtags do post (fixas)". O que você escrever ali sai EXATAMENTE assim no
  fim de toda legenda — a IA é obrigada a usar sua lista e proibida de
  inventar outras. Salvando como padrão da marca, vale para todos os vídeos

- **Legenda escrita para o Google (SEO local).** Campo "SEO local (cidade e
  termos de busca)": informe sua cidade e os termos que os clientes
  pesquisam (ex.: "Campinas SP; conserto de celular; troca de tela") e a IA
  passa a tecer cidade e termos naturalmente no corpo da legenda — pensada
  para busca indexada, não só para descrever o vídeo

## 2.90

- **As notas do card param de dar conselho errado.** "Plano B (Groq)" agora
  distingue os dois casos: quando as sessões web caíram de verdade, a nota
  manda recapturar; quando a IA principal só respondeu ilegível naquela
  geração (e o plano B salvou), a nota diz isso — recapturar não mudaria
  nada. Antes o card mandava recapturar com o Gemini saudável

- **O "Testar" do ElevenLabs enxerga os créditos.** Chave válida com carteira
  zerada dizia só "OK" — enquanto a trilha falhava por falta de créditos.
  Agora o teste mostra a sobra de créditos, e avisa quando o plano acabou

## 2.89

- **Novo estilo de legenda: "Bolha de conversa".** Cada frase falada aparece
  como uma bolha de chat estilo WhatsApp — verde escuro, cantos de mensagem,
  hora e os dois checks azuis — surgindo com o som de mensagem chegando.
  Feito para vídeo de loja de celular. Está no catálogo de "Estilo de
  legenda"; funciona no renderizador rápido como os demais

## 2.88

- **"Saiu sem IA" por resposta quebrada do Gemini — consertado.** Três vídeos
  reais saíram com o aviso "Saiu sem IA" mesmo com a sessão do Gemini viva: a
  resposta vinha com JSON defeituoso (vírgula faltando) e o plano inteiro
  morria, sem tentar o plano B. Agora resposta ilegível também cai para o
  Groq, que devolve JSON válido por contrato — o título e o corte saem da IA
  do mesmo jeito

- O seletor "Traço da ênfase" (novo na 2.87) estava com o visual branco do
  sistema no tema escuro — vestiu o estilo dos campos vizinhos

## 2.87

- **Nova ênfase "Marca-texto".** Irmã do círculo riscado: em vez de circular a
  palavra de destaque, pinta o fundo dela como um marca-texto — a tinta se
  espalha da esquerda para a direita no mesmo ritmo do risco, com o mesmo som
  de caneta riscando o papel. Mesma fonte, mesmo estilo, mesmos momentos de
  ênfase. Liga em Estilo → "Traço da ênfase" → Marca-texto (o padrão continua
  o círculo); a cor escolhida no "Cor do círculo riscado" também vale para o
  marca-texto (sem escolher, sai amarelo clássico)

## 2.86

- **Redimensionar sem piscar.** O arrasto pelas bordas funcionava mas piscava
  a tela inteira: a cada movimento o app reaplicava o acabamento da janela
  (cem vezes por segundo). Agora a janela só é tocada quando a geometria
  realmente muda, o acabamento entra uma única vez ao soltar o botão, e o
  laço roda a 60 quadros — arrasto liso

## 2.85

- **O redimensionar pelas bordas passou a funcionar de verdade.** As duas
  tentativas anteriores dependiam do mecanismo nativo do Windows, que não
  roda quando o clique nasce dentro do miolo do app (ele pertence a outro
  processo). Agora o próprio ATIVAVID conduz o redimensionamento: segurou a
  borda, a janela acompanha o mouse tick a tick até soltar o botão — em
  qualquer monitor e escala, com o mínimo de 900×600 respeitado

## 2.84

- **Botões da janela com a cara do Mac.** Minimizar, maximizar e fechar agora
  são as bolinhas amarela, verde e vermelha do macOS, com o símbolo
  aparecendo ao passar o mouse — nas duas telas do app

## 2.83

- **Redimensionar a janela agora funciona de verdade, em todas as bordas.**
  As bordas invisíveis dependiam de um mecanismo do Windows que o miolo do
  app (que roda em outro processo) engolia — na prática só uma borda pegava,
  uma vez. Agora as bordas moram na própria interface e entregam o
  redimensionar ao Windows nativamente: as quatro bordas e os quatro cantos
  respondem sempre, com o cursor certo, em qualquer monitor e escala

## 2.82

- **Vídeo sem trilha sonora agora avisa.** Quando a música de IA é pedida e a
  geração falha, o vídeo continua saindo (sem música) — mas antes isso era
  totalmente silencioso: nada no card, nada em lugar nenhum. Foi exatamente o
  que aconteceu quando os créditos do ElevenLabs esgotaram. Agora a ficha do
  card mostra "Trilha: Sem trilha sonora — créditos do ElevenLabs esgotados,
  renove o plano" (ou o motivo real da falha), e o motivo fica gravado no
  projeto

## 2.81

- **A janela funciona direito em monitor externo.** Num monitor com escala
  diferente da tela principal, arrastar e redimensionar o ATIVAVID caía no
  lugar errado (o Windows virtualizava as coordenadas). O app agora se
  declara ciente do DPI por monitor: bordas de redimensionar, arrasto e
  maximizar passam a responder certo em qualquer monitor — e a borda de
  pegar com o mouse cresce junto com a escala da tela

## 2.80

- **A nota do vídeo agora respeita o modo de edição.** A régua do score punia
  "abertura longa" e "takes longos" em vídeos dos modos que existem
  justamente para preservar (Vídeo completo, Sem cortes, Edição leve) — a
  dica aparecia em 92 de 157 projetos, muitos deles cumprindo o próprio
  contrato. Nesses modos a nota deixa de cobrar encurtamento e só aponta o
  que faz sentido (pausas longas); no Dinâmico/Shorts a régua continua
  exigente

## 2.79

- **O histórico do Aplicar agora registra o que mudou.** Cada entrada do
  histórico ganha a lista do que estava alterado (estilo, legendas, título,
  corte) — é o que permite auditar por que um Aplicar usou a emenda rápida
  (15-30s) ou o redesenho completo, e achar desperdício com dados em vez de
  suposição

## 2.78

- **"Liberar espaço" em Configurações.** Cada projeto entregue guardava o
  vídeo final em três lugares e o corte em dois — cópias idênticas, byte a
  byte — além de intermediários que o app sabe reconstruir. O botão novo
  deduplica as cópias (viram um arquivo só no disco, todos os caminhos
  continuam funcionando) e remove os intermediários de projetos entregues há
  mais de 7 dias. Fonte, vídeo final e a pasta publicar ficam intactos.
  Medido na base real: ~31 GB recuperáveis em 143 projetos

## 2.77

- **"Atualizar agora": o app se atualiza com um clique.** No aviso de nova
  versão, o botão principal agora baixa o instalador sozinho e o executa —
  o app fecha, atualiza e reabre. Chega de abrir o navegador, baixar e
  procurar o arquivo. O "Baixar pelo navegador" continua como alternativa

## 2.76

- **Atualizar o app não quebra mais a transcrição local.** A sincronização de
  dependências do instalador removia, a cada atualização, as bibliotecas de
  aceleração NVIDIA instaladas depois — e a transcrição em GPU passava a
  morrer com "cublas64_12.dll não encontrada" (foi a causa real do card em
  ERRO de hoje). Três defesas: o instalador agora detecta a GPU e sincroniza
  com as bibliotecas CUDA incluídas; a verificação de presença exige TODAS as
  bibliotecas (antes uma só bastava e ele dizia "já instalado" com o cublas
  faltando); e se a GPU quebrar no meio de uma transcrição, o motor refaz na
  CPU em vez de derrubar o vídeo

## 2.75

- **"Já estou aplicando" nunca mais trava um projeto para sempre.** Quando um
  Aplicar falhava e o vídeo era mandado para o reprocesso completo, o status
  ficava marcado como "na fila" e nunca era finalizado — e todo clique em
  Aplicar dali em diante respondia "Já estou aplicando as alterações deste
  vídeo" (um projeto real ficou travado assim por quatro dias). O bloqueio
  agora expira: fila parada há mais de 10 minutos ou execução com mais de
  2 horas não seguram mais o botão

## 2.74

- **"Comparar versões" lado a lado.** Quando o mesmo vídeo tem duas ou mais
  versões prontas (o "Gerar 5 versões" cria cinco), o menu "⋯" do card ganha
  "Comparar N versões": abre todas lado a lado, cada uma com o modo, a
  duração e o que saiu do corte — dá para tocar todas juntas e escolher a
  melhor na hora

## 2.73

- **O renderizador rápido parou de cair para o caminho lento à toa.** Alguns
  vídeos chegam da câmera com o relógio interno quebrado (quadros a mais ou a
  menos do que a duração diz). O caso "a menos" já era tratado; o caso "a
  mais" fazia a contagem final errar por 3 quadros e o app, por segurança,
  refazia tudo pelo caminho lento — 9 minutos em vez de ~2. A normalização
  do relógio agora cobre os dois sentidos, com prova no vídeo real que caiu

## 2.72

- **A limpeza de silêncio nunca mais come o fim de uma palavra.** O acabamento
  do render apara o silêncio no fim de cada corte usando um detector de nível
  de áudio — e fala baixinha podia passar por silêncio, decepando a palavra
  no arquivo final sem nada acusar. Agora a apara respeita a transcrição:
  para 60ms depois da última palavra do trecho, sempre

- **O card avisa quando o plano veio do Groq.** Se as sessões web (Gemini /
  ChatGPT) caírem, o vídeo continua saindo pelo plano B — mas agora a ficha
  do card mostra "IA: Plano B (Groq) — recapture em Chaves & IA", em vez de
  falhar em silêncio ou exigir abrir o painel de IA para descobrir

## 2.71

- **"Trazer de volta": restaure qualquer trecho removido com um clique.** A
  aba Visual ganhou o painel "O que saiu do corte": cada trecho removido
  aparece com o horário, o motivo e o texto que foi falado — e um botão
  "Trazer de volta". Clicou, o trecho volta ao corte e o vídeo é refeito
  automaticamente. A IA não desfaz sua decisão em refazeres futuros: o corte
  passa a ser tratado como edição manual sua

## 2.70

- **"Gerar 5 versões".** O botão de comparação agora cobre os cinco jeitos de
  editar: Dinâmico, Vídeo completo, Sem cortes, Reels/Shorts e Viral — cinco
  projetos na fila do mesmo arquivo, para escolher o melhor resultado

- **Ritmo do corte e Limpeza de fala na importação.** Dois controles novos no
  diálogo de importar: o ritmo (Natural, Dinâmico, Rápido, Muito rápido,
  Cirúrgico ou Narrativa) e a limpeza de fala (Desativada, Leve, Média,
  Forte). Vazio usa o padrão do modo; a escolha viaja com o projeto e trocar
  qualquer um dos dois num "refazer" replaneja o corte

## 2.69

- **"Gerar 3 versões" na importação.** Um clique importa o mesmo vídeo três
  vezes — Dinâmico, Vídeo completo e Sem cortes — e os três entram na fila
  para você comparar as versões lado a lado e escolher a melhor. Antes o
  jeito era importar na mão várias vezes trocando o modo

## 2.68

- **Novo modo: "Sem cortes".** O vídeo inteiro, do jeito que foi gravado —
  zero tesoura. Só legendas, título, cor e trilha. Aparece como card na
  importação e como opção no "Modo de edição" da tela de Estilo. Para quem
  quer o máximo de originalidade: nem silêncio sai

- **O card agora conta o que saiu do corte.** Linha nova na ficha do vídeo
  pronto: "Saiu: 23s silêncio · 4s repetição · 1s recomeço". O detalhe
  completo (cada trecho removido, com o texto falado e o motivo) fica em
  `corte_relatorio.json` no projeto. Chega de desconfiar no escuro — o corte
  se explica

## 2.67

- **O gancho nunca mais abre decepado.** A primeira frase do vídeo podia ser
  parecida com uma fala posterior (a piada volta ao bordão) e era tratada
  como "repetição" — o vídeo abria com o "Oi," cortado no meio. O começo
  agora é inegociável

- **O eco cômico fica.** Quando a cliente repete em pergunta o que a
  atendente afirmou ("…porque tem um negócio dentro." → "Tem um negócio
  dentro?"), o texto é igual mas são duas falas de duas pessoas — cortar a
  pergunta deixava a resposta seguinte sem sentido. Pergunta que ecoa
  afirmação é preservada; retake literal da mesma frase continua saindo

## 2.66

- **Uma aba antiga da tela de Estilo não muda mais o modo de edição por
  engano.** Uma aba aberta desde antes de uma troca de modo mostrava o valor
  antigo no seletor, e o "Salvar e refazer a Fase 2" mandava esse valor por
  cima do escolhido — um projeto em Vídeo completo voltou sozinho para Edição
  leve. Agora o seletor só entra no salvamento se você mexeu nele naquela
  tela; sem mexer, o modo gravado é preservado

## 2.65

- **No "Vídeo completo", nenhuma palavra falada fica de fora.** Mesmo depois
  da 2.64, o corte ainda decepava pontas de frase ("não vai levar." pela
  metade) e engolia trechos com fala (4,7s de diálogo central) — o fiscal
  trabalhava por blocos de frase cujos tempos desalinham dos tempos reais
  das palavras. Agora existe uma régua final palavra a palavra: tudo o que a
  transcrição diz que foi falado precisa estar no vídeo, exceto o que foi
  removido com justificativa confirmada (repetição literal, recomeço,
  cacoete). No vídeo do caso real, o modo passou a manter 86s de 121s, com
  todas as falas inteiras

## 2.64

- **O modo "Vídeo completo" passou a preservar de verdade.** Ele prometia só
  limpar (silêncio, erro + recomeço, repetição literal) mas entregou 56s de um
  vídeo de 2:01 — menos que a Edição leve. Dois defeitos no fiscal do modo:
  o rótulo que a IA dá ao trecho removido ("é repetição") valia sozinho, e um
  único bloco de 25s rotulado assim apagava quatro falas únicas da piada junto
  com a cantoria repetida; e uma frase que apenas **contém** um refrão repetido
  era tratada como se fosse toda repetição. Agora o rótulo da IA só vale com
  evidência na própria frase, e repetição removível é a frase cujo texto
  inteiro já existe em outro lugar. No mesmo vídeo, o modo passa a manter
  81s em vez de 56s — toda fala única fica

## 2.63

- **O instalador agora fecha o ATIVAVID antes de instalar.** Instalar com o
  app aberto deixava o servidor antigo rodando na memória: as telas mostravam
  os campos novos, mas o app ignorava o que eles mandavam — trocar o modo de
  edição e refazer não tinha efeito nenhum até reiniciar. Agora a instalação
  derruba o app sozinha, e o "Abrir ATIVAVID" no final já sobe a versão nova

- **O seletor "Modo de edição" entrou no lugar certo da tela de Estilo.**
  Estava sem o estilo dos campos vizinhos: rótulo gigante e caixa branca do
  sistema por cima do "Tipo de conteúdo" no tema escuro

- **O campo "Palavras de destaque da marca" deixou de ficar branco no tema
  escuro.** Faltava a regra de estilo para campos de texto naquela grade —
  só as caixas de seleção tinham

## 2.62

- **O título do vídeo voltou a ser escrito pela IA.** Um defeito no tipo de
  conteúdo *Viral* derrubava o planejamento inteiro, em silêncio: o app não
  dava erro, só passava a usar as primeiras palavras da fala como título. Como
  *Viral* é o tipo mais usado, isso pegou a maior parte dos vídeos das últimas
  semanas — saíam com títulos como "Ô meu amigo, boa tarde pra você" no lugar
  de uma manchete

- **Trocar o tipo de conteúdo passou a valer.** Escolher outro tipo na tela de
  Estilo e clicar em *Salvar e refazer a Fase 2* mandava tudo — ritmo,
  legenda, headline, cores — menos o tipo de conteúdo. O vídeo continuava com
  o tipo antigo, e como é ele que decide se o corte precisa ser refeito, o
  vídeo também voltava com a mesma duração. O texto do card final tinha o
  mesmo problema

- **O modo de edição agora pode ser trocado na tela de Estilo.** Um vídeo
  criado em *Edição leve* ficava preso no modo para sempre — trocar o estilo
  e refazer nunca mudava a minutagem. Agora a tela de Estilo mostra e deixa
  trocar o modo (Dinâmico / Vídeo completo / Edição leve), e o *Salvar e
  refazer a Fase 2* replaneja o corte de verdade

- **A janela de importar não lembra mais o modo escondido.** Escolher
  *Edição leve* uma vez deixava o modo marcado para as próximas importações,
  em silêncio — dava para trocar o estilo e o corte sair sempre igual sem
  nada explicar. Agora cada importação abre no modo recomendado, e o card do
  vídeo passa a mostrar o modo usado (Edição leve, Vídeo completo, Reels)

- **A edição leve também sai com título escrito.** O modo continua sem IA
  no corte, como promete — mas o título vinha das primeiras palavras da fala.
  Agora ele é pedido à parte, sem tocar no corte

- **Projetos antigos também ganham título ao refazer.** Vídeos criados antes
  desta versão nunca chegaram a guardar o título da IA; agora, ao refazer um
  deles, o app pede só o título e o vídeo sai nomeado — sem mexer no corte

- **Um caractere invisível não derruba mais o plano da IA.** Duas vezes o
  Gemini devolveu o plano com uma quebra de linha crua dentro de uma frase, e
  o vídeo inteiro caía para o corte automático por causa de um byte

- **O título não se perde mais ao refazer o vídeo.** Reaplicar uma correção,
  mexer no editor ou usar a edição leve reaproveita o corte de propósito — e
  junto se perdia o título escrito pela IA, que era substituído pelas
  primeiras palavras da fala. Um vídeo refeito três vezes ia de "Chip e
  carregador potente na loja" até "Meu filho, você tem chip aí nessa loja?"

- **A extensão do navegador voltou a entregar a sessão do Gemini.** A proteção
  contra sites maliciosos estava recusando a própria extensão, sem avisar. Sem
  a sessão, o app ficava sem IA para planejar o corte. Agora ela é aceita
  apenas nas duas rotas de captura, e o resto do app continua fechado

- **Vídeo de várias fontes ganhou título escrito.** O modo que junta vários
  takes decidia o corte sem IA — e junto ficava sem título: todos saíam com as
  primeiras palavras da fala como nome. Agora o app pede só o título à IA
  (sessão ou Groq), sem mexer no corte; se tudo falhar, segue como antes

- **O painel de IA parou de dizer "Pronto" com a sessão morta.** O status
  só conferia se os cookies existiam — dava para estar tudo expirado e o
  painel seguir verde. Agora cada chamada real registra se funcionou, e o
  cartão avisa "Capturado, mas a última chamada falhou — recapture" quando a
  sessão morreu depois da captura

- **O "Editar com IA" também sobrevive às sessões expiradas.** O chat do
  editor caía junto com as sessões do Gemini/ChatGPT; agora usa a mesma rede
  do planejador e cai para o Groq quando as duas morrem

- **O plano do vídeo sai mesmo com as sessões de IA expiradas.** As sessões
  do Gemini e do ChatGPT expiram juntas de tempos em tempos, e o corte caía
  para o modo automático sem título. Agora, se as duas falharem e houver chave
  do Groq configurada, o plano sai por ela — a Fila registra `groq` como
  origem, e a mensagem de erro passou a avisar quando as DUAS sessões
  precisam de recaptura, não só uma

- **A Fila avisa quando um vídeo saiu sem IA.** Antes esse aviso existia só num
  registro técnico que ninguém abre. O conselho segue a causa: quando foi a
  conexão, pede para reconectar; quando foi outra coisa, pede só para gerar de
  novo

- **"Abrir site" na tela IA parou de acumular guias.** O botão abria uma
  guia nova (às vezes duas) a cada clique. Agora abre o site uma única vez no
  navegador padrão

- **Render mais rápido no estilo de legenda em uma linha.** Ele era o único que
  ainda abria o navegador para desenhar; agora usa o motor próprio, como os
  outros. No teste de ponta a ponta o vídeo saiu idêntico e a fase de render
  caiu de 283s para 70s

- **Trocar o título renomeia o vídeo entregue.** O conteúdo já saía certo,
  mas o nome do arquivo e a pasta *publicar/* ficavam com o título antigo —
  na hora de postar, tudo aparecia com o nome velho. Agora o arquivo, o
  atalho "Ver final" e a pasta de publicação acompanham o título novo

- **Trocar o título também ficou rápido.** Escolher outra opção de título
  refazia o vídeo inteiro (~2 minutos); como o título vive nos primeiros
  segundos, agora o app redesenha só o começo e emenda no vídeo pronto — no
  teste real, 15 segundos. O estilo de título com pergunta e resposta continua
  pelo caminho completo, porque a resposta aparece mais adiante no vídeo

- **Corrigir legendas ficou mais rápido.** Trocar palavras da legenda
  redesenhava e reencodava o vídeo inteiro (~2 minutos). Agora o app refaz só
  os trechos corrigidos e emenda no vídeo pronto — o áudio e o resto dos
  quadros saem intactos, byte a byte. Funciona também com várias correções
  espalhadas pelo vídeo, que era o caso comum

- **Refazer um vídeo ficou mais rápido: a análise de cor tem memória.** A
  detecção de cor decodificava o vídeo inteiro a cada render — até 3 minutos
  numa fonte 4K60 — mesmo quando a fonte era exatamente a mesma. Agora o
  resultado fica guardado ao lado da fonte e o reprocesso reaproveita na hora;
  regravar o arquivo invalida sozinho

- **O corte deixou de cair no caminho lento por disputa.** Quando dois vídeos
  eram processados juntos, o segundo ia para o caminho antigo — cerca de 2,4x
  mais lento — só por não conseguir a vez. Agora ele espera a vez, que custa
  bem menos do que o desvio

- **Legenda desligada não deixa mais o render lento.** Quem desligava a legenda
  perdia o motor rápido por causa de um estilo que nem seria desenhado

## 2.61

- **Arrastar um vídeo não trava mais na tela "Solte para importar".** Soltar em
  cima do banner *Importar e editar com IA* — o alvo mais óbvio da tela —
  deixava aquela faixa tracejada presa por cima de tudo. O app não estava
  travado de verdade: os cliques atravessavam a camada, só que ela não saía
  mais da frente

- **A janela de importação abre mesmo com vídeo do iPhone.** O app tentava ler
  a duração do arquivo para sugerir um preset, e um `.MOV` gravado em HDR pelo
  iPhone não responde nem com sucesso nem com erro — a leitura ficava esperando
  para sempre e a janela nunca aparecia. Agora ele desiste em 4 segundos e abre
  do mesmo jeito; a duração só servia para escolher a sugestão


## 2.60

- **A legenda passou a ser revisada antes de ir para a tela.** Depois de
  transcrever no seu computador, o app manda só o TEXTO para o Gemini, que
  aponta palavras que provavelmente saíram erradas — nomes de marca, números,
  palavras técnicas. Num vídeo real de teste, *"perícula"* apareceu nove vezes
  e virou *"película"* nas nove. Comparado com a transcrição sem revisão em
  quatro vídeos conferidos de ouvido: o erro de palavra caiu de **22,7% para
  21,3%**, o de número foi de **82,7% para 85,1% de acerto**, e sobraram
  **menos correções para você fazer à mão** (7,9 em vez de 8,7 a cada 100
  palavras)

- **O karaokê não sai do lugar.** O tempo de cada palavra continua sendo o que
  o seu computador mediu — o Gemini não encosta nele. Medido nos 12 vídeos do
  teste: **zero milissegundo** de diferença. Quando uma palavra é separada em
  duas (*"PrimeCamp"* virando *"Prime Camp"*), as duas metades dividem
  exatamente o tempo que a palavra original ocupava, sem sobrar nem faltar

- **Não custa nada e o áudio não sai do seu computador.** A revisão usa a
  sessão do navegador que você já capturou pela extensão — sem chave de API,
  sem cobrança. Só o texto é enviado; o áudio nunca sai da máquina

- **Cada vídeo demora de 16 a 40 segundos a mais.** É o tempo de ida e volta
  até o Gemini, e ele quase não depende do tamanho do vídeo: no teste, um
  clipe de 12 segundos levou 26s e um de 90 segundos levou 16s

- **Se o Gemini estiver fora do ar, a legenda sai assim mesmo.** Sessão
  expirada, sem internet, resposta quebrada: o app entrega a transcrição do
  seu computador, do mesmo jeito que na 2.59, e diz no diagnóstico que a
  revisão não aconteceu. **Nunca cai sozinho para um serviço pago** — e na
  próxima vez tenta revisar de novo, sem transcrever tudo outra vez

- Importar de novo um vídeo já revisado continua instantâneo, e as duas
  versões (revisada e sem revisão) convivem no cache

- Para desligar à mão: variável de ambiente `ATIVAVID_REVISAO=off`. O efeito é
  imediato no próximo vídeo, sem reinstalar e sem apagar arquivo nenhum

## 2.59

- **As telas voltam a usar o monitor inteiro.** Em Marca e Integrações os
  cartões paravam no meio da largura e o resto da tela ficava vazio — não era
  falta de conteúdo, era uma coluna invisível que o layout mantinha viva sem
  motivo. Os três cartões de Integrações passaram de 377 para 507 pixels de
  largura, e os dois de Marca agora dividem a linha inteira

- **Configurações ficou mais direta.** O topo repetia "Perfil" e "Cache" logo
  acima dos cartões que já diziam a mesma coisa, e "Aceleração" era um cartão
  com uma frase só ao lado de outro cheio — viraram um. O Diagnóstico saiu de
  dentro do "Avançado", que é onde ninguém achava, e para quem é admin o
  "Avançado" já abre aberto

- **Licença mostra até quando cada aparelho vale.** Antes a lista dizia "SEM
  ACESSO" em vermelho para um computador com licença ativa, contradizendo o
  aviso no alto da própria tela

- **Liberar um cliente ficou um passo.** Ele lê o ID do aparelho na tela de
  Licença e te manda; você cola em "Liberar dispositivo", escolhe os dias e
  pronto. Sem criar conta, sem ele digitar chave nenhuma

- Espaçamento dos cartões emparelhado: dentro do mesmo cartão as distâncias
  variavam entre 8 e 35 pixels

## 2.58

- **Correção importante: a placa de vídeo não estava sendo usada na legenda.**
  Se você viu erros de transcrição na 2.57, era isto. O app precisava baixar
  um componente para usar a placa, mas por um erro meu ele nunca chegava a
  baixar — e a legenda saía pelo modo lento e menos preciso. Na mesma fala, o
  antes e o depois: *"trocar a **filha** do meu mouse"* virou *"trocar a
  **pilha** do meu mouse"*, e *"quando que **quiser** pra consertar"* virou
  *"quanto que **fica** pra consertar"*. De quebra ficou **5,7x mais rápido**
  (11s em vez de 64s no mesmo vídeo)

- Quem já usa a 2.57 não precisa fazer nada além de atualizar: o componente é
  baixado sozinho na próxima transcrição, com o progresso na tela

## 2.57

- **As legendas agora são feitas no seu próprio computador.** Nada de conta,
  chave ou mensalidade para transcrever — e depois da primeira vez, nem
  internet. Na prática você não vê diferença: a tela continua dizendo
  "Transcrevendo áudio…" e o vídeo sai igual. Comparado no mesmo vídeo, o
  novo motor acerta a posição de **96,6% das palavras** contra 99,7% do
  serviço em nuvem, e **87% delas caem dentro de 100 ms** uma da outra — a
  legenda karaokê continua no lugar

- **Na primeira transcrição o app se prepara sozinho.** Ele olha o seu
  computador, calcula o que precisa e baixa, mostrando o progresso e o tamanho.
  Com placa de vídeo NVIDIA são cerca de 3,6 GB; sem placa, 703 MB. Depois
  disso nunca mais aparece, e atualizar o ATIVAVID não baixa nada de novo

- **O app não trava mais quando o áudio não tem fala.** Num trecho só com
  música ou silêncio, o motor às vezes inventava frases — agora nada é
  escrito. E fala baixinha, pausas longas e palavras no começo de uma frase
  continuam intactas: testado em 1.055 palavras faladas de verdade, sem
  perder nenhuma

- **Importar de novo um vídeo já transcrito continua instantâneo**, e mudar
  headline, estilo, fonte, cor ou b-roll não refaz a transcrição

- **A chave do ElevenLabs virou opcional.** Ela ainda é usada pela trilha
  sonora e pela voz, mas não faz mais falta para legendar — e o app parou de
  avisar sobre isso

- Telas de Configurações e Licença usando a largura toda, e o instalador já
  sai com o nome que você recebe

## 2.56

- **As legendas agora saem do ElevenLabs, o serviço que você assina.** O app
  escolhia o serviço de transcrição pelo tamanho do vídeo e só usava o
  ElevenLabs em fontes acima de 5 minutos — nenhum vídeo seu chega perto disso
  (o mais longo tem 2,8 min), então **149 de 149 foram para o serviço gratuito**
  e o seu plano pago nunca foi usado. Comparado no mesmo vídeo, o ElevenLabs
  achou **54 palavras contra 51**, sem nenhuma fora de ordem (o outro tinha
  uma), e marca o tempo de cada palavra com mais precisão — que é o que a
  legenda karaokê usa. Também transcreve mais fiel à fala: onde o outro
  escreveu "Você jura?", ele escreveu "Cê jura?"

- **A espera para analisar o vídeo ficou muito mais previsível.** O serviço
  gratuito recusava pedidos quando você mandava vários vídeos de uma vez, e o
  app ficava esperando de 5 a 60 segundos por tentativa. Num lote da manhã de
  20/08 isso custou **19 vezes mais** que no lote da tarde do mesmo dia. Com o
  serviço pago isso deixa de acontecer

- **Se o ElevenLabs estiver fora do ar, o vídeo não trava.** O app volta
  sozinho para o serviço gratuito e termina o trabalho

- **Telas de Configurações e Licença mais compactas**, e os cards da lista não
  esticam mais para acompanhar a altura do vizinho

## 2.55

- **Importar de novo um vídeo que você já usou não transcreve tudo outra vez.**
  A transcrição ficava guardada dentro da pasta do projeto, então uma
  importação nova começava do zero — mesmo sendo exatamente o mesmo arquivo.
  Nos seus projetos isso aconteceu com **16 fontes** (uma delas importada 5
  vezes): 20 transcrições pagas em repetição e cerca de 22 minutos de espera.
  Agora o app reconhece o arquivo pelo **conteúdo**, não pelo nome, então
  reconhece até o mesmo vídeo salvo com outro nome — e reaproveita na hora

## 2.54

- **Corrigir uma legenda podia ser recusado sem motivo.** A conferência que o
  app faz antes de aplicar comparava a contagem de quadros com uma folga
  calibrada em 39 projetos. Com os 128 que você tem hoje essa conta ficou
  apertada demais: um projeto era recusado por 3 quadros — 0,1 segundo — e a
  correção simplesmente não acontecia. A folga agora acompanha o tamanho da
  edição do jeito certo, e os 128 passam. Continua pegando o caso que ela
  existe para pegar

- **O volume dos vídeos estava passando raspando no limite das plataformas.**
  Instagram, TikTok e YouTube pedem pico de no máximo −1,0 dBTP; o app mirava
  −1,2, que é exatamente o tamanho do erro que a normalização comete. Metade
  dos seus vídeos saía entre −1,0 e −1,2, e um saiu no limite exato. Quando
  passava disso, o vídeo inteiro era refeito do zero — 12 minutos a mais, sem
  você pedir nada. Agora sobra margem de verdade, e **o volume não muda**: a
  loudness continua em −14 LUFS

- **O ajuste de áudio podia piorar o som e ficava assim mesmo.** Em material
  difícil ele deixava o pico pior do que encontrou — e como trocava o arquivo
  antes de conferir, o resultado pior era o entregue, ainda por cima anunciado
  como corrigido. Agora ele só troca quando melhora de fato

- **Corrigir legenda ou mudar o corte agora passa pela mesma conferência de
  áudio** que um vídeo novo. Antes só o render inicial conferia; um vídeo que
  você corrigia saía sem essa checagem

- **Os atalhos de "Identidade visual" agora abrem na seção certa.** A tela de
  Marca prometia isso e não cumpria: Cor de destaque, Fontes e Cartão final
  caíam todos no topo do editor. Agora cada um para no ajuste que anuncia e
  pisca para você achar

- **Liberação de acesso pelo ID do aparelho.** Dá para liberar direto pelo
  código que aparece na tela de Licença, sem criar conta e sem digitar chave —
  o cliente clica em Atualizar e entra. Renovar soma sobre o que ainda resta

## 2.53

- **O logo agora é vermelho.** Mesma fonte, mesmo desenho, mesma qualidade — só
  a cor mudou. O ícone do app, o da barra de tarefas e o favicon foram junto, e
  a faixa fininha embaixo da barra do editor deixou de ser roxa para acompanhar

## 2.52

- **A tela de Presets mexia na marca errada.** Se você abrisse Presets sem
  passar antes pela tela de Marca, ela mostrava os presets da sua marca ativa
  (Prime Camp) mas criar, renomear e apagar iam para a marca "Padrão" — a lista
  na sua frente nem se mexia, então parecia que o botão não funcionou, enquanto
  o preset de outra marca mudava. Agora ela grava exatamente na marca que está
  mostrando, e o rótulo diz o nome certo

## 2.51

- **O botão "Baixar atualização" mandava para a versão errada.** O aviso dizia
  "Nova versão 2.50" e o botão abria o instalador da **0.1.24** — cada metade
  lia uma fonte diferente. Agora o botão baixa exatamente a versão que o aviso
  anunciou

## 2.50

- **A ficha do card estava invisível no modo claro.** Duração, formato, estilo
  e horários saíam em cinza quase branco sobre o card branco — dava para ver
  que tinha texto ali e não dava para ler. Era uma cor fixa onde deveria ser a
  cor do tema; agora ela acompanha claro e escuro

## 2.49

- **A tela de Estilo mostrava o estilo de fábrica, não o seu.** Ela carregava o
  arquivo que vem na instalação, enquanto "Salvar como padrão" grava em outro
  lugar — o que o app realmente usa. Na sua máquina, 7 campos divergiam: a tela
  dizia marca "Padrão" e cartão final vazio enquanto os vídeos saíam com
  "Prime Camp" e o seu CTA, e o ritmo e a limpeza de fala (que decidem o corte)
  apareciam errados

## 2.48

- **O aviso de atualização estava cego.** Você viu "está em 2.46 — sem
  atualização" com a 2.47 publicada, e estava certo em desconfiar: o app
  consultava uma política de versão que ficou parada em `0.1.24` e **parava
  ali**, sem nunca olhar as versões publicadas. Nenhuma das últimas versões
  chegou a aparecer como atualização. Agora ele olha o que foi publicado de
  verdade, e "atualização" passou a ser versão **maior** — antes, uma versão
  mais velha também seria oferecida
- **Mudar ritmo, intensidade ou tipo de conteúdo volta a replanejar o corte.**
  A verificação comparava o ajuste atual com ele mesmo, então nunca disparava:
  você mudava o ritmo, reprocessava, e o corte antigo ficava. Vale para cortes
  feitos a partir desta versão

## 2.47

- **A Lixeira parou de prometer o que não fez.** Apagar um projeto sempre dizia
  "foi para a Lixeira" — mesmo quando os arquivos **ficavam no disco** porque a
  reciclagem falhou. Você ia procurar lá para restaurar e não achava, ou
  contava com um espaço que nunca foi liberado. Agora ele diz o que aconteceu
  de verdade, com o motivo
- **"Abrir pasta" não perde mais o caminho da entrega.** O fim do processamento
  apagava o ponteiro para `publicar/<nome>/` logo depois de criá-lo — 13 dos
  seus projetos estavam com a pasta pronta e o caminho perdido

## 2.46

- **Palavras trocadas na legenda.** A transcrição às vezes marca uma palavra
  como começando um pouco *antes* da anterior — jitter de milésimos, mas quem
  monta a legenda ordena pelo tempo, então o texto saía embaralhado: `Olha
  jeito!` onde a fala diz `jeito! Olha`. Estava em **133 dos seus 178
  transcripts** (746 pares, com voltas de até 1 segundo). Agora a ordem da fala
  manda. Vale para vídeos novos **e** para os já transcritos, porque o conserto
  também acontece na hora de montar a legenda
- **O card de importação que falha não some mais.** Ele aparecia com o erro e
  era apagado pela atualização de tela dois segundos depois — o lote parecia
  nunca ter existido. Agora fica até você resolver, e os botões dele funcionam:
  "Tentar novamente" re-envia os arquivos, "Apagar" descarta

## 2.45

Três coisas que aplicar uma correção estragava — no arquivo entregue e na tela.

- **A capa embutida voltou ao arquivo entregue.** Aplicar uma correção refazia
  o vídeo e o arquivo em `publicar/` saía **sem a capa embutida** — a que o
  Instagram usa ao postar. Conferido nos seus entregues: os que vieram direto
  do pipeline tinham a capa; os que passaram por correção tinham perdido quase
  todos. Agora ela volta em ~1 s, e uma capa que você escolheu pelo botão
  Capa é preservada, nunca regenerada
- **Corrigir uma palavra também conserta a legenda do post.** O texto que você
  copia para o Instagram cita a fala, então a palavra errada podia estar lá —
  e ficava, mesmo depois da correção. O botão Copiar também passou a ler o
  arquivo atual em vez de uma cópia antiga
- **"Dispensar" no aviso de correção falha agora vale.** O cartaz REVISAR
  voltava a cada atualização da tela, para sempre. Dispensou, sumiu — e se
  falhar de novo, o aviso volta, porque é uma falha nova

## 2.44

Um defeito de legenda que estava em 73% dos seus vídeos.

- **A mesma palavra não aparece mais duplicada na legenda.** Quando uma palavra
  da fala atravessava dois trechos do corte, ela era escrita nos dois — e como
  a transcrição às vezes junta uma frase inteira numa "palavra" só, isso era
  comum: 93 dos seus 127 projetos tinham pelo menos uma, somando 298 cópias
  extras, com casos de até 5x a mesma palavra. Num deles, a primeira legenda do
  vídeo dizia `bora / bora / bora 32` onde a fala diz "bora" uma vez. Agora
  cada palavra pertence a um trecho só — o que ela mais atravessa — e nada se
  perde: conferido rodando os dois jeitos lado a lado nos 127 projetos, zero
  palavras legítimas sumiram
- Vale para vídeos novos e para correções aplicadas daqui em diante; os vídeos
  já prontos não são reescritos

## 2.43

Escolher uma pasta com subpastas passou a funcionar pelo botão, e a importação
deixou de copiar os arquivos por dentro do app.

- **"Escolher vídeos" e "Escolher pasta" agora abrem o seletor do Windows.** O
  seletor do navegador não aceita pasta — era por isso que, no botão, só dava
  para marcar os vídeos soltos
- **Importar ficou muito mais rápido, principalmente com arquivo grande.** O
  app é um programa de computador e os seus vídeos já estão no disco, mas a
  tela mandava os arquivos inteiros para dentro dele antes de começar. Agora
  ela manda só o caminho
- **"Cada subpasta vira um vídeo" passou a valer de verdade.** Os vídeos
  soltos dentro da pasta que você escolhe agora são um vídeo cada, com o nome
  deles. Antes eram colados num vídeo só, batizado com o nome da pasta.
  Testado na sua pasta: 12 vídeos viram 11 projetos, que é exatamente o que
  você montou à mão

## 2.42

Duas coisas que você apontou olhando o card.

- **"Estilo" mostrava a mesma coisa em todos os vídeos.** Eu tinha pego
  justamente os dois campos que nunca mudam nos seus projetos (manchete e
  legenda são `realce` e `stacked` nos 128, sem exceção). Agora ele mostra o
  **tipo de conteúdo** — Viral, Humor, Informativo, Educativo —, que é o que
  varia de verdade e o que você quis dizer. Nos projetos antigos, que não têm
  esse campo, a linha simplesmente não aparece
- **"Copiar legenda do post" não funcionava.** O botão existia no card desde
  sempre, mas nunca teve resposta ao clique: ele não fazia nada, em silêncio.
  Agora copia — e se o sistema recusar a cópia, o texto aparece na tela já
  selecionado, para o Ctrl+C. O botão de copiar o log técnico ganhou o mesmo
  reforço

## 2.41

Corrigir uma palavra da legenda deixou de refazer o vídeo inteiro, e o card de
Concluídos ficou no formato que você desenhou.

- **Corrigir uma legenda ficou 3,5x mais rápido.** O app redesenhava todos os
  quadros e reencodava o arquivo todo para trocar uma palavra. Agora ele
  reaproveita o que não mudou e refaz só a fatia mexida. Medido no mesmo vídeo,
  alternando os dois caminhos: **41,5 s → 11,9 s**, redesenhando 148 de 1243
  quadros. Quando as correções estão espalhadas pelo vídeo a fatia fica grande
  e ele mesmo desiste do atalho, refazendo tudo como antes — o resultado nunca
  fica pior, no máximo demora o de sempre
- **O card de Concluídos foi refeito:** o nome do vídeo manda, o selo desce
  para baixo dele, e o resto virou ficha com rótulo — vídeo original, vídeo
  editado, formato, estilo, início e final. A mensagem "Vídeo concluído" saiu:
  ela não dizia nada que o selo já não dissesse
- **"Estilo" é uma informação nova no card** (ex.: `Realce · Empilhado`)

## 2.40

O card de Concluídos passou a mostrar o que você pediu, e o arrastar pasta
parou de perder as subpastas.

- **Duração original e duração final, lado a lado** — o card diz `42s → 26s`.
  A duração de origem nunca tinha sido medida: só existia a entregue, então o
  quanto o corte apertou o vídeo era invisível
- **Início e conclusão, com data e hora** — `21/08/2026 · 08:22 → 08:33`, e a
  data só se repete quando o dia virou. O "início" mostrava a hora da
  **importação**, não a do processamento: num vídeo que esperou meia hora na
  fila, os dois números não tinham nada a ver
- **"Pasta" e "Legenda" foram para dentro do menu ⋯**, junto com "Tentar
  novamente". Na linha fica só "Visualizar"
- **Arrastar uma pasta com subpastas agora leva as subpastas.** Eram dois
  defeitos somados: soltar em cima do card disparava a importação **duas
  vezes**, e a segunda passada só enxergava os arquivos soltos e sobrescrevia
  a primeira; e ao arrastar várias pastas de uma vez, só a primeira era lida
- **Um lote que não importa agora diz o motivo.** Antes o card simplesmente
  sumia da tela, sem uma palavra
- **O menu ⋯ deixou de ficar congelado.** Ele era montado uma vez: "Copiar
  legenda do post" nunca aparecia depois que a legenda ficava pronta, e "Ver
  vídeo final" ficava desabilitado para sempre

## 2.39

Você me mostrou três coisas do editor nesta manhã e as três estão resolvidas.
Junto vieram dois defeitos que apagavam trabalho seu em silêncio.

- **A manchete existe desde o primeiro quadro.** Ela nascia invisível e só
  ficava legível 8 quadros depois, ainda subindo — o vídeo abria sem manchete
  nenhuma. Como ela é a primeira coisa que o espectador lê, era justamente o
  momento em que ela não estava lá. Conferido contra o renderizador de
  referência: no quadro 0 os dois desenham a mesma coisa
- **Clicar no meio da manchete agora põe o cursor onde você clicou.** Antes
  ele selecionava o texto inteiro, então apagar uma palavra do meio só dava
  para fazer andando com as setas
- **Dá para apagar legenda — uma ou várias.** Havia como trocar o texto, mas
  não como tirar a legenda: salvar com o campo vazio não fazia nada e também
  não avisava. Agora tem o botão **apagar**, e na linha do tempo `Ctrl+clique`
  marca uma legenda, `Shift+clique` marca o intervalo e `Delete` apaga todas.
  `Esc` larga a seleção e `Ctrl+Z` desfaz. O apagar fica pendente como
  qualquer outra edição da linha do tempo e vai junto no salvar — é isso que
  faz o `Ctrl+Z` valer de verdade e não só na tela
- **"Criar marca nova" estava apagando a marca que estava ativa.** O nome
  digitado apenas renomeava a marca em uso: a antiga sumia e nenhuma nova
  aparecia, com a mensagem dizendo "Marca salva e ativada". Isso já aconteceu
  duas vezes na sua máquina — as duas marcas que você tem hoje têm o nome de
  exibição discordando do arquivo, que é a marca do problema. As duas
  continuam lá; o que se perdeu foram as que foram substituídas
- **Corrigir uma legenda podia não pegar, e mesmo assim dizer que pegou.** O
  app respondia "Legenda corrigida" sem olhar se a troca tinha acontecido, e
  ainda apagava o seu pedido da tela. Quando não pega agora ele diz o motivo e
  guarda a correção
- **A correção aparecia no vídeo mas não no preview.** As palavras da legenda
  usam um nome de campo que o filtro de tempo não conhecia, então a correção
  nunca entrava na cue — e é a cue que o preview desenha. Você só via o
  resultado depois de refazer o vídeo inteiro
- **Arrastar a manchete ou a legenda avisa quando não consegue salvar.** Antes
  ela ficava parada no lugar novo como se tivesse sido salva
- **O histórico do apply passa a registrar onde foram os minutos** (corte,
  desenho, encode, validação), e não só o total. É o que falta para atacar a
  demora de aplicar uma correção, que hoje tem mediana de 6 minutos e meio

## 2.38

Comparei o desenho das legendas quadro a quadro com o renderizador de
referência — coisa que a validação antiga não fazia, porque ela só olhava os
quadros em que a palavra já tinha terminado de aparecer. Foi ali que estavam
os defeitos.

- **Metade das legendas aparecia um quadro fora do lugar.** A conta que decide
  em que quadro cada legenda entra arredondava para baixo quando devia
  arredondar para o mais próximo. Nos seus projetos, **57 de 112 legendas**
  caíam num quadro diferente do previsto — e o relógio interno delas (entrada,
  saída) ia junto. Num dos quadros conferidos o app desenhava três vezes mais
  do que devia; noutro, nada
- **A manchete voltou a aparecer com a animação dela.** Ao acertar a curva de
  entrada das legendas na versão anterior, acabei aplicando a mesma curva na
  manchete — que usa outra. Ela fica na tela nos primeiros 4 segundos de todo
  vídeo, então dava para notar

Depois dos dois, de 33 pontos conferidos contra a referência, os que ficavam
mais de 10% fora caíram de 11 para 4 — e desses 4, dois são diferença
conhecida do próprio navegador, já documentada.

## 2.37

Uma segunda auditoria, desta vez mirando só o que você usa de verdade — o
estilo `stacked`, a headline `realce`, o editor e a fila. Achou nove coisas,
todas conferidas nos seus projetos. Estas quatro são as que doem:

- **Marcar um trecho apagava do marcador até o FIM do vídeo.** É o seu fluxo
  de todo dia: marca com **M**, escreve a nota, salva. Testado com um vídeo de
  60 s: marcar **2 segundos** removia **50**. Agora remove exatamente o que
  você marcou
- **"tira o zoom daqui" apagava o take inteiro.** A nota virava corte por
  pedaço de palavra: `fora` casava em "fora de foco", `corte` em "aqui o corte
  ficou estranho". E o texto que você escreveu ia junto. Agora só corta com
  ordem explícita, e não corta quando a nota nomeia um elemento (zoom,
  legenda, trilha, manchete...)
- **O take de CTA que você grava e anexa sumia do corte.** Os tempos de cada
  take são contados do zero, e a etapa que protege a fala misturava os dois
  arquivos e engolia o mais curto. **5 dos seus projetos** estão assim — três
  perderam o CTA, dois perderam a Parte 2
- **Trocar o estilo de um vídeo em andamento virava card de ERRO** e não
  reeditava nada

E três acertos de desenho na legenda, que valem para todos os seus vídeos:

- **A palavra aparece com a curva certa.** A entrada era mais lenta que a do
  preview — a diferença chegava a 26% de opacidade no começo. Como a subida
  da palavra vem da mesma conta, ela também deslizava devagar
- **A última palavra de cada trecho agora assenta.** Quem entrava perto do
  fim ficava com tempo de entrada longo demais e o trecho acabava antes: ela
  piscava e sumia sem chegar ao lugar. Eram 27% das palavras
- Cartão final com o peso certo na segunda linha, e a faixa colorida da
  manchete sem 6 px sobrando de um lado só

## 2.36

Uma auditoria de leitura no código achou dez coisas; conferi cada uma nos
seus próprios projetos antes de mexer. Quatro delas mexem no que você vê:

- **Dois vídeos processando ao mesmo tempo podiam se atropelar.** Todos os
  projetos usavam a MESMA pasta temporária de trabalho — uma só, para os seus
  113. O render da fila e a correção que você faz no editor escrevem lá com o
  mesmo nome de arquivo, e um apagava o do outro no meio do caminho. Agora
  cada projeto tem a sua
- **Legenda voltou a ficar no tempo certo depois de uma emenda.** Quando um
  trecho terminava exatamente em fala, o app guardava "corte zero" e depois
  lia esse zero como se fosse o valor padrão — e a legenda de tudo que vinha
  depois aparecia 66 ms cedo demais, somando a cada trecho. Nos seus projetos
  isso acontecia em **55 de 111**
- **"Descartar" parou de desfazer trabalho já aplicado.** Se você corrigia,
  aplicava, corrigia de novo e desistia, ele voltava para antes da PRIMEIRA
  correção — jogando fora a que você já tinha visto pronta no vídeo
- **A palavra grande da legenda volta a crescer ao aparecer.** Ela nasce em
  88% e chega a 100% junto com o fade; estava aparecendo em tamanho fixo

E três que só aparecem se você mudar de estilo ou de formato — arrumadas
agora para não te esperarem lá na frente: o contador de lista (que nunca
desenhava no motor rápido), o número do contador que saía sem o "º", e o
alinhamento de quadro no formato YouTube.

Também passei a registrar, junto de cada correção, qual motor a desenhou e
por que caiu se caiu. Foi olhando esse tipo de registro que achei o
desperdício das versões 2.34 e 2.35 — e para as correções essa informação
não existia.

## 2.35

Duas coisas que atrapalhavam justamente o seu jeito de trabalhar: corrigir a
legenda e abrir a pasta para postar.

- **Corrigir legenda voltou a funcionar.** Ele recusava a correção dizendo que
  o mapa não batia com o corte — por diferença de 2 a 7 quadros, que é o
  normal de como o corte é montado. Olhando os seus 39 projetos, **25 deles
  (64%) seriam recusados assim**, e foi o que aconteceu em 9 das 10 correções
  que falharam no seu histórico. A conferência continua existindo, agora com a
  folga do tamanho certo
- **A pasta para postar acompanha a manchete em vez de duplicar.** Quando você
  corrigia o texto da manchete, o app criava uma pasta nova em `publicar/` e
  deixava a antiga lá, com uma cópia inteira do vídeo. Você tinha 11 projetos
  assim, somando **1,19 GB** — um deles com quatro pastas do mesmo vídeo, sem
  como saber qual era a boa. Agora ele renomeia a pasta e mantém um vídeo só
- **"Abrir pasta" parou de cair no vazio.** Em 5 dos 43 projetos o app apontava
  para uma pasta que não existia mais, pelo mesmo motivo

As 11 pastas duplicadas que já estão no disco continuam onde estão — são seus
arquivos, você decide se apaga.

## 2.34

Achei isto lendo as suas próprias estatísticas de render, não o código: na
semana de 14 a 20/08, **23 vídeos foram renderizados duas vezes** — 12,6 h de
máquina. O app descartava um vídeo pronto e refazia tudo do zero por duas
razões, e nenhuma das duas se sustentava.

- **Vídeo que ficava um pouco alto no som era refeito inteiro — e saía alto do
  mesmo jeito.** Em 8 dos 23 casos o vídeo refeito continuou fora do limite: a
  meia hora extra não consertava nada. Agora o app ajusta só a faixa de som, com
  a imagem intacta. O último caso levou 27 minutos para refazer; o ajuste leva
  menos de um minuto
- **E o vídeo passa a sair dentro do limite de verdade.** 18 dos seus vídeos da
  semana foram publicados com o som acima do teto que as plataformas pedem,
  porque o ajuste antigo mirava exatamente no teto e sempre passava um pouco. A
  mira agora tem folga
- **Vídeo era refeito por "faltam 2 quadros".** O corte às vezes chega com um
  pulo de dois quadros no fim, e a conta de duração contava esses dois. Agora a
  composição preenche o pulo e a contagem bate
- Efeito colateral bom dos dois: **menos vídeo entrando na fila lenta.** Quando
  o app precisava refazer, o vídeo levava em média 28 minutos em vez de 12

## 2.33

Uma rodada de defeitos que ninguém tinha como perceber sozinho: eles não
davam erro, só entregavam o vídeo um pouco diferente do que você aprovou.

- **O corte marcado voltou a fazer barulho.** O clique de corte estava mudo em
  todo vídeo desde que o motor novo virou o caminho principal — o clarão
  aparecia, o som não vinha. Seus últimos vídeos tinham de 4 a 14 desses
- **O contorno da headline estava pintado em dobro.** O preto ao redor do texto
  saía com o dobro da grossura do que o preview mostrava
- **Arrastar a headline até o topo funciona.** Ela voltava sozinha para o meio
  da tela quando você soltava bem na borda. Vale também para a legenda colada
  na base
- **A headline no editor agora é a headline de verdade.** Ela aparece com a
  caixa alta, o tamanho e a quebra de linha do estilo escolhido, em vez de um
  texto genérico. Como você posiciona olhando para ela, a posição escolhida
  passa a ser a que sai no vídeo
- **A proteção da sua fala voltou a valer no vídeo inteiro.** Depois dos 16
  minutos e 40 segundos ela simplesmente parava — a partir dali a IA podia
  cortar frase no meio sem ninguém segurar. Só afeta fonte longa
- **"Enviar à fila" parou de mentir.** Quando o envio era recusado (licença,
  pasta ou projeto), ele dizia "enviado" mesmo assim e você ia esperar na Fila
  um vídeo que nunca tinha começado
- **A fonte da marca passou a vestir o que devia.** Ela estava trocando a
  tipografia de estilos que têm família própria (e por isso ficavam
  descaracterizados) e, ao mesmo tempo, sendo ignorada nos estilos que deviam
  usá-la
- **Vídeo SDR a 50/60 quadros parou de trabalhar à toa.** Ele ajustava cor e
  tamanho dos 60 quadros por segundo para jogar metade fora no fim — o mesmo
  desperdício que a versão 2.32 tirou do vídeo HDR. De quebra, o movimento fica
  mais regular. (Aqui a máquina estava ocupada na hora de medir, então não
  prometo um número de tempo: o que está conferido é que a metade descartada
  deixou de ser processada, e que o vídeo sai com os mesmos quadros)

## 2.32

Corte mais rápido em vídeo de celular 4K a 60 quadros.

- **O preparo da fonte ficou ~1,7x mais rápido.** Ele convertia a cor de todos os 60 quadros por segundo, mas o vídeo final usa 30 — metade do trabalho ia para o lixo
- **De quebra, o movimento ficou mais regular.** No jeito antigo os primeiros quadros de cada trecho saíam em câmera lenta por um instante antes de estabilizar
- **Dois vídeos processando juntos não brigam mais pela placa de vídeo.** Um usa a GPU e o outro a CPU, em vez de os dois disputarem — antes isso era mais lento do que fazer um de cada vez
- Vídeo gravado a 30 quadros não muda em nada

## 2.31.2

- **A conferência de áudio do vídeo final parou de abrir o vídeo à toa** — ela só precisa do som
- **A correção de cor por trecho voltou a funcionar.** Era o mesmo defeito de caminho que a detecção de cor tinha: ela media, não conseguia ler o resultado e devolvia "sem correção" caladamente. Só afeta quem usa o modo automático de cor
- Quando o app não consegue ler as informações de cor de um vídeo, agora ele avisa no log em vez de seguir e entregar a imagem errada sem explicação

## 2.31.1

- **O menu "•••" abre inteiro.** Ele não estava atrás do vídeo — estava sendo cortado pela barra do topo. Agora sai da barra e aparece por cima de tudo
- **Cartão final mais rápido de desenhar.** O escurecimento do fim do vídeo estava custando quase metade do tempo de desenho do overlay; a imagem sai idêntica, byte por byte

## 2.31

- **A legenda também se arrasta.** Segure e mova para escolher a altura, igual à headline. Onde você solta é onde o vídeo desenha
- **Toque duplo volta ao padrão** — na legenda e na headline. Serve para desfazer um arraste sem ficar procurando a posição original
- A legenda no preview passa a aparecer **na altura real** do estilo. Antes ela usava uma tabela própria e ignorava o que estava salvo no projeto
- **Correção de cor voltou a funcionar.** Ela estava desligada em silêncio desde sempre no Windows, por causa do `:` do caminho do arquivo. Material achatado (sem contraste) volta a receber o ajuste automático; vídeo normal e HDR de celular não mudam em nada
- A análise da fala parou de abrir o vídeo à toa — ela só precisa do áudio

## 2.30

- **Agora dá para arrastar a headline no preview.** Segure e mova para escolher a altura — sai do rosto, do letreiro, do que estiver atrapalhando. Onde você solta é onde o vídeo desenha
- A headline no preview passa a aparecer **na altura real** de cada estilo. Antes ela ficava sempre no mesmo ponto, que raramente era o do vídeo final
- Clicar continua abrindo a edição do texto — só arrastar move

## 2.29.1

- **IA e Integrações agora usam a tela inteira.** Na 2.29 elas ficavam presas numa coluna estreita à esquerda, com o resto do monitor vazio. Em tela larga a IA mostra o passo a passo de um lado e o que você opera do outro; Integrações põe os três serviços lado a lado

## 2.29

Menu lateral redesenhado, com quatro telas que estavam escondidas.

- **O menu agora tem quatro seções**: Trabalho, Criação, Automação e Aplicativo. Licença saiu do menu e foi para o card da empresa; "Chaves & IA" virou **IA** + **Integrações**; Sistema virou **Configurações**
- **Projetos**: todos os seus trabalhos num lugar só, com filtro (em andamento, prontos, parados) e busca por nome
- **Marca**: escolher e criar marcas, que antes ficava numa barra dentro de Estilos
- **Biblioteca**: as imagens que a IA usa como b-roll agora aparecem em miniatura, e dá para adicionar por ali
- **Presets**: renomear, duplicar, apagar e escolher o padrão da marca
- **Rodapé virou a sua empresa**, não a sua conta: `Prime Camp · Plano Pro`. O clique abre conta, empresa, licença, atualizações e sair
- Item selecionado ficou discreto, os contadores alinhados, e o menu mais compacto
- **Em janela estreita o menu vira gaveta** e as telas se ajustam sem cortar nada
- Se o app não responder, as telas dizem o que houve e oferecem **Tentar de novo** — antes ficavam em branco

## 2.28

Emoji e b-roll no motor rápido — nenhum recurso cai mais no caminho lento.

- **Emoji nas legendas.** Passa a ser desenhado com a mesma fonte que o navegador usava (a Segoe UI Emoji do Windows), então o desenho é o mesmo. De quebra corrigiu um caso em que o ✅ saía como um quadradinho branco vazio
- **B-roll / inserts.** O cartão de imagem com o zoom lento (Ken-Burns) foi portado: mesma posição, mesmo crescimento, mesmo som de entrada
- **Logo e assinatura na headline** (estilo cartão) também entraram
- A caixa escura do cartão passa a ser uma peça só — antes a segunda linha ganhava uma caixa mais estreita e a borda direita saía em degrau
- Com isso o motor novo desenha **todos** os elementos. O Remotion continua instalado e assume sozinho se aparecer algo que o motor não conheça

## 2.27

Fonte da marca e headline pergunta→resposta no motor rápido.

- **Escolher uma fonte para a marca não joga mais o vídeo no caminho lento.** As 8 famílias do catálogo (Poppins, Inter, Montserrat, Playfair, Lora, Anton, Bebas, Archivo) e a sua própria fonte (a que você coloca na pasta Fontes) já são desenhadas pelo motor novo
- Fontes de peso único (Anton, Bebas, Archivo) não ganham negrito falso — o peso é limitado ao que a fonte tem, igual ao comportamento antigo
- **A headline pergunta→resposta** (pergunta abre, some, e a resposta entra numa pílula) também foi portada
- Se a fonte escolhida não existir ou estiver ilegível, o vídeo usa a padrão em vez de falhar
- Falta agora só o emoji nas legendas (precisa de uma fonte de emoji) e o b-roll

## 2.26

Contador de lista e logo no cartão final também no motor rápido.

- **Vídeos com contador de lista** (aquele selo numerado no canto) e **cartão final com logo** deixaram de cair no caminho lento
- **O emoji nas legendas continua indo pelo caminho antigo, e agora sei o porquê**: as fontes que embarcamos não têm o desenho dos emojis — sairiam como quadradinho vazio. Enquanto não houver uma fonte de emoji, esse caso precisa mesmo do caminho antigo
- Sobram no caminho antigo: emoji, headline pergunta→resposta, fonte de marca e b-roll

## 2.25

Todas as headlines agora usam o motor rápido.

- **Os 9 estilos de headline passaram a ser desenhados sem navegador**: contorno, cartão, realce, misto, sombra, sublinhado, pílula, manchete e carimbo. Antes só o realce; escolher outro jogava o vídeo inteiro no caminho lento
- **Cada um conferido quadro a quadro contra o desenho antigo** — 140 quadros por estilo, diferença de imagem entre 1% e 17%. Dois defeitos foram corrigidos na conferência: o carimbo desenhava a moldura só na primeira linha e a manchete deixava a faixa escura 20% mais curta
- Desenhar ficou entre 9x e 22x mais rápido conforme o estilo
- Com isso, legendas e headlines — os dois elementos que aparecem em todo vídeo — estão 100% no motor novo

## 2.24

Todos os estilos de legenda agora usam o motor rápido.

- **Os 4 estilos do catálogo (7 variantes) passaram a ser desenhados sem navegador**: empilhado, impacto, disperso e simples (simples, serifada, clássica, bloco, recorte). Antes só o empilhado; os outros caíam no caminho lento sem você saber
- **Cada um foi conferido quadro a quadro contra o desenho antigo** — 140 quadros de fala contínua por estilo, diferença de imagem entre 1% e 9%. Cinco defeitos reais foram encontrados e corrigidos nessa conferência (altura de caixa, espessura de sombra e origem do contorno)
- Na medição, desenhar ficou entre 5x e 18x mais rápido conforme o estilo
- Estilo que o app ainda não conheça continua indo pelo caminho antigo, automaticamente

## 2.23

Preparação do vídeo mais rápida — e sem a armadilha que quase entrou junto.

- **Vídeos de câmera 4K são preparados com ajuda da placa de vídeo** na etapa mais pesada do corte: mesma imagem, bit a bit idêntica, ~18% mais rápido
- **Com mais de uma fonte, elas são preparadas ao mesmo tempo** (~16% mais rápido). Máquina sem placa compatível continua funcionando igual, pelo caminho antigo
- **Cuidado que evitou uma regressão**: as duas melhorias juntas *pioravam* tudo (a placa satura com duas conversões simultâneas e o tempo quase dobrava). Agora a placa só entra quando há uma fonte só — foi medido antes de shipar
- Todos os 4 estilos de legenda do catálogo já estão desenhados pelo motor novo. Por enquanto só o empilhado (o seu) roda por padrão; os outros esperam validação lado a lado

## 2.22

Renderização em passada única: desenhar e montar viraram uma etapa só.

- **A renderização caiu de ~53 s para ~33 s** no vídeo de teste. Antes, mesmo com o desenho novo (2.21), as legendas viravam um arquivo intermediário de 150 MB que era lido de volta logo em seguida para juntar com o vídeo; agora o desenho vai direto para a montagem, quadro a quadro, sem arquivo no meio
- **Nada muda no resultado**: mesma mistura de voz + efeitos + trilha, mesma normalização de volume em 2 passadas, mesmas cores. Conferido contra o caminho anterior (diferença no nível de ruído de compressão) e aprovado pela validação oficial do app
- Se a passada única falhar por qualquer motivo, ele volta sozinho para o caminho em duas etapas — e, se este falhar, para o desenho antigo. Três camadas de segurança
- No seu último vídeo pesado (2 fontes), a fase de renderização já tinha caído de ~22 min para 1,5 min com a 2.21; com a 2.22 ela fica ainda ~40% menor

## 2.21.1

O "tempo restante" parou de mentir.

- **Antes ele ficava parado** ("~23 min restantes" por horas): era o chute da média histórica, sem olhar o relógio nem o andamento. Agora ele **desce com o tempo** e, a partir de 15% de progresso, o ritmo real do seu vídeo corrige a previsão — quanto mais anda, mais o número reflete o que está acontecendo de verdade
- Continua honesto: sem histórico e sem progresso, não inventa número

## 2.21

Renderizador próprio: as legendas passam a ser desenhadas sem navegador.

- **A etapa mais lenta do processamento caiu de ~107 s para ~33 s** no vídeo de teste (medido com a máquina livre). Antes, desenhar legendas, headline e cartão exigia abrir um navegador escondido (Remotion/Chrome), que ocupava mais de 90% da máquina; o desenho agora é feito direto, usando ~50%
- **A imagem é a mesma**: fidelidade medida quadro a quadro contra o desenho antigo (razão de tinta mediana 1,003 em 851 quadros), com os efeitos sonoros e a trilha preservados
- **Cobre o que seus vídeos usam** (legenda empilhada + headline realce + cartão + flashes — 100% dos seus 74 projetos). O que ainda não cobre (outros estilos, contador de lista, emoji, b-roll) continua indo pelo caminho antigo, automaticamente
- Se qualquer coisa falhar no desenho novo, ele volta sozinho para o antigo — e a validação final continua a mesma para os dois
- Para desligar à mão: variável de ambiente `ATIVAVID_RENDER_PROPRIO=0`

## 2.20

Corrigir corte parou de refazer o vídeo inteiro.

- **Antes, mexer no corte redesenhava tudo.** Tirar dois pedaços do fim custava o mesmo que reeditar o vídeo do começo — e redesenhar as legendas é 70 a 83% do tempo, mais de 20 minutos por vídeo nesta máquina
- **Agora o que vem antes do ponto que você mexeu é reaproveitado.** Só o trecho do corte em diante é redesenhado. No teste, cortando perto do fim, foram 251 de 851 quadros — 70% menos trabalho
- Se você mexer logo no começo, ou mudar estilo junto, ele volta a refazer tudo: aí não há o que reaproveitar mesmo
- **Correção junto:** a emenda estava entregando o trecho reaproveitado deslocado em um quadro. A contagem ficava certa, então ninguém percebia. Conferido agora quadro a quadro, o resultado sai idêntico

## 2.19.1

Correção: vídeo de câmera falhava logo no começo.

- **Arquivos de câmera (como os A001_… da Sony) davam erro e não passavam do corte.** O programa que lê as informações do vídeo repete o bloco de dados quando o arquivo tem uma estrutura que só câmeras usam, e a leitura entendia "24 quadros" como um texto quebrado. Vídeo de celular nunca mostrou o problema — por isso passou
- Foi corrigido em todos os pontos que liam essas informações. Em dois deles o erro era pior: não quebrava, respondia errado calado — um chegava a dizer "zero quadros"
- **Os vídeos que falharam funcionam com "Tentar novamente"**, sem precisar importar de novo

## 2.19

Importar vídeo parou de comer a memória da máquina.

- **Importar um vídeo de 250 MB usava 3,2 GB de memória.** O arquivo inteiro entrava na memória e ainda era copiado mais três vezes antes de chegar ao disco. Agora ele é gravado em pedaços, enquanto chega: o mesmo vídeo usa **22 MB**
- Isso importava porque a memória do import disputava com o ffmpeg e o Remotion, que rodam ao mesmo tempo quando há fila. Com vários vídeos grandes seguidos, a máquina ficava sem folga
- **Receber o arquivo também ficou ~14x mais rápido** (10,3 s para 0,75 s no vídeo de 250 MB, com a máquina livre)
- O arquivo chega íntegro: conferido byte a byte, e o leitor novo foi testado contra o antigo em dezenas de casos, incluindo nome com acento, dois arquivos de mesmo nome e upload interrompido no meio

## 2.18

A fila deixou de perder o estado dos cards.

- **A fila agora vive num banco de dados, não num arquivo de texto.** Antes, cada atualização reescrevia a lista inteira; se dois programas mexessem na fila ao mesmo tempo, o último a gravar desfazia o trabalho do outro — um vídeo que estava "Editando..." voltava sozinho para "Na fila"
- **Campos de tela não grudam mais no card.** A tela da Fila calcula coisas na hora (se já tem corte, se já tem capa, em que passo está) e isso estava sendo gravado junto com o card. Um passo antigo, uma capa já apagada ou uma mensagem passageira podiam ficar presos ali para sempre — foi a raiz dos cards travados que consertamos aos pedaços nas versões 2.13 e 2.14
- **Atualizar um card ficou ~40x mais rápido** com a fila cheia (4,0 ms para 0,08 ms com 200 vídeos, mediana de 3 medições)
- Sua fila é convertida sozinha na primeira abertura; o arquivo antigo fica guardado ao lado, por segurança

## 2.17.1

Correções da auditoria da v2.17 — sem mudança de comportamento visível.

- **Corrida entre dois vídeos ao mesmo tempo**: o arquivo temporário do cache tinha nome fixo, então dois vídeos usando a mesma origem podiam escrever no mesmo arquivo. Agora cada um tem o seu
- **Cache 29% menor**: o arquivo intermediário passou de 188 MB para 134 MB por vídeo, com diferença de qualidade imperceptível (VMAF 96,5 → 96,1)
- O log agora diz claramente quando o cache foi aproveitado ou refeito


## 2.17

Reprocessar um vídeo ficou 9x mais rápido.

- Vídeos gravados no iPhone são HDR, e converter essa cor era a etapa mais cara do corte — ela rodava **de novo a cada trecho e a cada reprocessamento**. Agora essa conversão é feita **uma vez por vídeo** e reaproveitada
- **A primeira edição leva o mesmo tempo de antes.** As seguintes (trocar headline, corrigir legenda, ajustar corte) caem de ~5 minutos para ~30 segundos no passo do corte — medido: 294s para 32s
- A imagem continua a mesma: os filtros são exatamente os mesmos, na mesma ordem, só aplicados mais cedo
- O arquivo intermediário fica na pasta do projeto e é refeito sozinho se você trocar a cor da marca ou o vídeo de origem


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
