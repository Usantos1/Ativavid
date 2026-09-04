# Changelog

## 5.0.30

- **"Verificar" dizia "sem atualização" com a versão nova já publicada.** O
  app comparava, via que havia versão mais nova, e mesmo assim copiava a
  resposta antiga guardada no cache da licença. Agora a comparação decide,
  e clicar em Verificar renova a licença antes de responder — assim uma
  atualização obrigatória recém-publicada aparece na hora, não em até 30
  minutos.

## 5.0.29

- **Botão para baixar as trilhas e os efeitos prontos.** Em Configurações →
  Música dos vídeos agora há "Baixar trilhas e efeitos": 596 arquivos (376
  trilhas + 219 efeitos), 370 MB, uma vez só. Resolve as máquinas sem placa
  NVIDIA, onde a IA local não roda e a pasta de trilhas nascia vazia — o
  vídeo saía sem música nenhuma e não havia o que fazer na tela.
- **Nada do que você já tem é sobrescrito.** Quem já tem a Biblioteca cheia
  recebe só o que falta, e o botão diz quantos arquivos entraram. Baixar
  duas vezes não duplica nada.

## 5.0.28

- **O Diagnóstico anunciava uma aceleração de vídeo que a máquina não tem.**
  Num PC só com Intel UHD ele dizia "Aceleração de vídeo: h264_nvenc · Modo
  gpu" e, dois cartões adiante, "encoder=libx264" — os dois na mesma tela.
  A causa: `ffmpeg -encoders` lista o que foi compilado, não o que a placa
  aceita, e a build do app traz nvenc, qsv e amf em qualquer computador.
  Agora quem decide é a placa instalada; a lista do ffmpeg só volta a valer
  quando o Windows não responde qual é a placa.

## 5.0.27

- **O cliente via — e podia trocar — o backend do aplicativo.** Em
  Configurações → Avançado estavam a URL do Supabase, a anon key e o link de
  checkout, os três editáveis. Trocar qualquer um deles quebra a licença
  daquela máquina, e o dono nem saberia por quê. Agora o bloco é só do
  administrador: nasce escondido no HTML (JS que falha não expõe nada) e a
  rota que salva recusa esses três campos sem uma sessão de administrador.
  O resto do Avançado — reinstalar e teste de desempenho — continua para
  todo mundo.

## 5.0.26

- **O botão de instalar a IA local não aparece quando o download morreria no
  meio.** Antes de oferecer os 4,8 GB, o app confere se o `uv` está no lugar
  e se há uns 7 GB livres no disco onde o motor vai morar — que é o disco
  dos seus Projetos, não necessariamente o C:. Faltando um dos dois, o
  cartão diz o que falta e como resolver, em vez de começar um download que
  trava depois de vários minutos. Vale nos dois lugares que oferecem a
  instalação: Configurações → Música dos vídeos e o Diagnóstico.

## 5.0.25

- **Quatro estilos de MANCHETE novos.** Os oito estilos novos do dia anterior
  eram todos de legenda; a lista de manchete não mudava desde 29/08. Agora
  tem **Recorte** (caixa branca com a letra na cor da empresa), **Etiqueta**
  (caixa da cor com um fio branco por dentro), **Marca-texto** (traço atrás
  do corpo da letra) e **Entre linhas** (dois fios finos, acima e abaixo).
  Os quatro conferidos contra o desenho de referência: 1,014 a 1,042.
- **Quatro transições de corte, no lugar de uma.** Além do **Flash** de
  sempre: **Brilho** (clarão seco), **Escurece** (piscada preta) e **Faixa**
  na cor da empresa. A escolha fica em "Transição no corte", ao lado do
  Ritmo, e vale por preset.
- **A "Intensidade" do estilo agora vale nas transições.** Sutil, Médio e
  Forte mudavam o zoom e o corte e davam exatamente o mesmo flash.
- **Vídeo com take dentro de um cartão derrubava o motor rápido.** Quando a
  altura do cartão caía num número ímpar, o quadro do take saía um pixel
  menor que a máscara e o render inteiro caía para o caminho lento — 88,9
  segundos no lugar de uns 17, três vezes só em 01/09. Achado lendo o
  `pipeline.log` dos seus próprios projetos.
- **O Diagnóstico agora mostra o que dá para instalar — e instala dali.** A
  IA local de música é baixada sob demanda (4,8 GB) e quem nunca abriu
  Configurações não sabia que existe. O painel passa a dizer se ela está
  instalada, se ficou pela metade ou se a placa não permite, com o botão de
  baixar no próprio cartão.
- **A bolha de conversa cortava a última palavra.** A caixa da bolha era
  limitada à largura segura enquanto o texto quebrava na largura cheia: a
  sobra saía para fora da bolha e sumia no recorte. Achado varrendo os 23
  estilos de legenda contra o desenho de referência.
- **Filtro nas listas de estilo.** Com 19 manchetes e 23 legendas, achar de
  novo o que você gostou virou rolagem. O campo aparece só nas listas
  grandes e guarda o que você digitou.
- **O cartão de preset mostra a transição** junto com layout, legenda,
  manchete, ritmo e cores.
- **Correção de desenho antiga:** o feixe do flash saía espelhado desde
  30/08 — o Pillow gira ao contrário do navegador, e o sinal do ângulo tinha
  sido copiado igual. A mesma correção endireitou a faixa nova.

## 5.0.24

- **"Precisa de placa NVIDIA" numa máquina que tem placa NVIDIA.** A IA local
  de música só perguntava ao `nvidia-smi`, e quando o driver não o deixa no
  PATH do Windows a resposta virava "sem GPU" — a instalação era recusada
  numa máquina perfeitamente capaz. Agora o ATIVAVID procura o `nvidia-smi`
  onde o driver o instala e, se ainda não achar, usa o mesmo detector de
  placa da tela Sistema.
- **A tela diz QUAL placa encontrou.** Antes ela só falava do que faltava,
  então não dava para saber se o app tinha visto a placa errada ou não tinha
  visto nenhuma. Em Configurações → "Música dos vídeos" agora aparece o nome
  da placa detectada, e o mesmo nome entra no aviso quando a instalação é
  recusada.

## 5.0.23

- **A cor e a legenda da empresa não ficavam salvas.** Você escolhia o preset
  do cliente, ajustava o estilo, refazia o vídeo — e ele voltava com a
  legenda empilhada vermelha. Três coisas causavam isso, e as três foram
  corrigidas:
  - a empresa nova nascia com uma cópia inteira do estilo de fábrica
    (empilhado + vermelho) e essa cópia passava por cima do que você salvava;
  - "Salvar estilo base" gravava no padrão do aplicativo, não na empresa
    aberta na tela — agora grava na empresa, como a tela sempre prometeu;
  - cada preset guarda uma cópia completa do estilo, então o estilo base
    nunca alcançava o preset do vídeo. Agora a mudança desce para os presets
    que ainda estavam com o valor antigo. Preset com cor própria continua
    mandando, e o Salvar diz quantos foram atualizados.
- **Escolher um preset no editor não mudava nada.** Toda empresa nasce com um
  preset "Padrão" vazio; escolhê-lo deixava a tela com a cor do vídeo
  anterior, e o "Salvar e refazer" congelava essa cor no projeto — de onde
  ela nunca mais saía. Agora o preset leva para a tela o estilo cheio que o
  vídeo teria com ele.
- **Botão "Voltar ao preset" no editor.** O estilo ajustado dentro de um
  vídeo manda mais que a empresa e que o preset — então um vídeo editado
  antes de você acertar a cor ficava com a cor velha presa, e escolher o
  preset de novo não tirava. O botão fica ao lado de "Preset deste vídeo",
  repõe o estilo do preset e vale depois de "Salvar e refazer a Fase 2".
  O corte e a linha do tempo não são tocados.
- **Botão "Usar a cor da empresa" em Empresas.** Conserta o que já está
  gravado: os presets criados nas versões antigas congelaram o vermelho de
  fábrica, e nenhuma regra automática sabe se aquele vermelho foi escolha
  sua ou herança. O botão põe a cor de destaque da empresa na manchete e no
  realce de todos os presets dela de uma vez. O resto de cada preset fica
  como está.
- **As legendas coloridas novas usam a cor de ÊNFASE.** Neon, degradê,
  bandeira, pílula, etiqueta e fita degradê pintam uma superfície, não a
  letra. Como quase todo preset tem a legenda branca, elas saíam sem cor: o
  neon sem brilho e o degradê branco liso. A cor da marca aparece nas seis.

## 5.0.22

- **A cor da empresa voltava para o vermelho no vídeo.** A cor escolhida em
  Empresas pintava só a manchete; o realce da legenda continuava com o
  vermelho que vem do modelo do app, então uma empresa nova saía com faixa
  vermelha mesmo com outra cor escolhida. Agora a cor pinta os dois. Para
  as empresas que você já criou, basta abrir Empresas e clicar em "Salvar
  identidade" de novo.
- **Dois campos de preset na tela de estilo.** O de cima é o preset DESTE
  vídeo; o de baixo é o gerenciador (criar, duplicar, renomear, excluir).
  O de baixo começava mostrando o primeiro preset da lista, que quase nunca
  era o do vídeo — e os botões agiam nesse. Agora os dois começam no preset
  do vídeo e andam juntos.

## 5.0.21

- **A trilha sonora voltou a ser clicável.** O menu de trocar, ajustar o
  volume e remover a trilha existia desde a 4.101, mas o clique nunca
  chegava nele: a faixa da trilha estava com os cliques desligados no
  estilo da tela. Agora clicar nela abre o menu.
- **A agulha só anda pela minutagem.** Clicar num vídeo, num áudio, numa
  imagem ou numa legenda não move mais a agulha — antes qualquer clique na
  linha do tempo a puxava, inclusive o que era só para selecionar. A régua
  ficou mais alta e com o cursor de arrastar; arrastar um intervalo por
  cima dos takes continua levando a agulha junto.

## 5.0.20

- **Marca-texto: a faixa cortava a letra.** Ela cobria só o miolo da
  linha, então o pé do "p" e a ponta do "d" ficavam de fora. Agora a
  faixa abraça a letra inteira, com folga em cima e embaixo.

## 5.0.19

- **Mais quatro legendas de fundo colorido**, na linha da Bandeira:
  **Pílula** (cápsula na cor da empresa), **Etiqueta** (painel escuro com
  uma barra colorida na lateral), **Fita degradê** (faixa reta com o fundo
  em degradê) e **Marca-texto** (faixa de caneta marca-texto atrás da
  frase, amarela por padrão, que usa a cor de ênfase). São 23 estilos.
  Todos conferidos quadro a quadro contra o motor de referência.

## 5.0.18

- **Quatro estilos de legenda novos**, no menu Estilo de legenda:
  **Neon** (letra branca com brilho na cor da empresa), **Degradê** (a
  letra vai de branco à cor da empresa, com contorno escuro), **Bandeira**
  (fita inclinada na cor da empresa com o texto dentro) e **Máquina de
  escrever** (as letras aparecem uma a uma enquanto a pessoa fala). São 19
  estilos ao todo. Cada um foi conferido quadro a quadro contra o motor de
  referência antes de entrar.

## 5.0.17

- **Onze fontes novas** para legenda e headline, todas de licença aberta:
  Oswald, Roboto Condensed, Nunito, Rubik, League Spartan, Kanit Black,
  Barlow Condensed, Bangers, Righteous, Titan One e Luckiest Guy. Junto
  com as oito de antes, são 19 no menu "Fonte" de Estilos, mais a sua
  pasta Fontes. Cada uma sai com a mesma altura visível de legenda (o
  tamanho é corrigido por fonte).

## 5.0.16

- **Janela de "Inserir imagem / B-roll" em tela cheia.** Buscar online,
  Biblioteca e Emoji abrem ocupando a tela quase toda: campo de busca
  maior, mais miniaturas por linha e a grade cresce com a janela em vez de
  parar em dois terços da altura.

## 5.0.15

- **Painel do admin: o e-mail de quem abriu o app.** O registro de abertura
  só levava o e-mail de quem já estava liberado por conta. Quem entrou e
  está em teste, bloqueado ou com chave aparecia como "—". Agora o e-mail
  logado vai junto em toda abertura, e o PC ganha dono no painel na
  primeira vez que a pessoa abre o app depois de criar a conta.

## 5.0.14

- **Renomear a empresa renomeia a pasta de Entregas.** Antes a pasta velha
  ficava para trás e os vídeos novos começavam outra.
- **Aula nova aparece no menu.** Quando o admin publica uma aula, o item
  "Aulas" mostra quantas são novas desde a sua última visita, como a Fila.
  Abrir a tela zera o número.

## 5.0.13

- **Entregas sem surpresa no disco.** "Reunir vídeos antigos" agora conta e
  pesa antes: "Reunir 291 vídeos em Entregas/Prime Camp? Vai copiar cerca
  de 9,4 GB". Em Configurações dá para desligar a cópia automática de cada
  vídeo pronto (a pasta passa a encher só pelo botão Reunir).

## 5.0.12

- **Lista vazia por causa da empresa dizia "nenhum vídeo".** Com uma
  empresa sem vídeos ativa (ex.: Uander) e centenas na outra, Início, Fila,
  Concluídos e Projetos diziam que não havia vídeo nenhum. Agora dizem
  "Nenhum vídeo de Uander aqui" com o botão "Ver todas as empresas (291)".

## 5.0.11

- **"Comece por aqui" para quem acabou de instalar.** Sem nenhum vídeo, o
  Início mostra três passos com botão: cadastrar a empresa (com o perfil),
  assistir à primeira aula e importar o primeiro vídeo. Cada passo marca ✓
  sozinho quando é feito, e o guia some quando o primeiro vídeo entra.

## 5.0.10

- **Entregas: pacote caía em "Sem empresa".** Quando o pacote era montado a
  partir da pasta do projeto (e não da `edit/`), a empresa saía vazia e a
  cópia ia para `Entregas/Sem empresa/`. Aconteceu com 8 vídeos da Prime
  Camp no primeiro dia. Corrigido, e o app adota sozinho o que ficou lá:
  na próxima vez que o vídeo for tocado, a pasta é movida para a empresa
  certa em vez de duplicar.

## 5.0.9

- **Pasta de entregas configurável.** Em Configurações → Projetos e cache,
  "Pasta de entregas": aponte para a pasta do Google Drive (ou qualquer
  outra) e cada empresa ganha a sua subpasta lá, sincronizando sozinha.
  Vazio = `Entregas` ao lado dos Projetos, como antes. Vale na hora, sem
  reiniciar.
- **Roteiro aprende com as legendas aprovadas.** Além dos ganchos, a IA
  recebe as legendas dos posts que você aprovou no Multiplicador e segue o
  jeito de escrever, sem copiar.

## 5.0.8

- **Roteiro conhece os ganchos que a empresa já usou.** Antes de escrever,
  a IA recebe as headlines dos últimos vídeos da empresa ativa. Ela não
  repete nenhum e segue o estilo dos que você aprovou no Multiplicador
  (os que levam ✅ no nome).

## 5.0.7

- **O perfil da empresa alimenta toda a IA.** O que você preenche em
  Empresas → Perfil (o que vende, para quem, cidade, diferenciais, provas,
  oferta, contato, tom de voz, o que não falar) passa a entrar no
  planejador do corte, na headline e na legenda do post, não só no
  Roteiro. A headline deixou de ter "assistência técnica de celulares"
  fixo no pedido à IA. Quem não preencheu o perfil não muda nada.

## 5.0.6

- **Pasta de entrega por empresa.** Todo vídeo pronto passa a ser copiado
  também para `Entregas/<Empresa>/<nome do vídeo>/` (vídeo, capa e
  legenda), ao lado da pasta de Projetos. É a pasta para entregar ao
  cliente ou mandar ao Drive, sem caçar projeto por projeto. Quando a
  manchete muda, a pasta acompanha. Na tela Empresas: "Abrir pasta de
  entregas" e "Reunir vídeos antigos" (copia para lá o que já estava pronto).

## 5.0.5

- **Aulas: player próprio, sem links do YouTube.** O vídeo toca dentro do
  app com controles nossos (tocar/pausar, barra de progresso, tempo, som,
  tela cheia, setas para pular 10 s). Título, canal e "Assista no YouTube"
  do embed deixaram de ser clicáveis; ao acabar aparece "Próxima aula".
- **Minutagem.** Cada aula mostra a duração na lista e ao lado do título,
  e o cabeçalho soma o total. O app descobre a duração sozinho.
- **Descrição legível.** Quebras de linha viram parágrafos e os itens com
  ✅ (ou • e -) viram lista, mesmo quando colados numa linha só.
- **Engrenagem, anterior/próxima e concluir.** A engrenagem do player tem
  velocidade (0,5× a 2×, lembrada) e a legenda do YouTube, que vem sempre
  desligada. Botões de aula anterior e próxima na barra. "Concluir aula"
  marca com ✓ na lista (e ao terminar o vídeo marca sozinho); o cabeçalho
  conta as concluídas. A qualidade fica automática: o embed do YouTube não
  aceita mais escolher.
- Sair da aba Aulas pausa o vídeo. A lista das aulas fica parada enquanto a
  página rola e, com muitas aulas, rola por dentro.
- **Licença: PC bloqueado dizia "Modo aberto".** Quem estava com o bloqueio
  gravado (trial vencido, ou a recusa "crie sua conta") via o texto errado,
  sem os planos, sem o modal e sem o código do computador. Agora a tela
  mostra o motivo real, os planos para assinar e o código para mandar ao
  suporte. No servidor, o e-mail da conta passa a aparecer no painel do
  admin também para PC que só teve trial (rode o
  `RODAR-NO-SUPABASE-email-no-trial.sql`).

## 5.0.4

- **Copiar presets de uma empresa para outra.** Na tela Empresas, cada
  preset ganhou "Copiar para…" e o bloco ganhou "Copiar todos para…":
  escolha a empresa de destino e pronto. A cópia não vira o padrão da
  outra empresa e, se lá já existir um preset com o mesmo nome, a cópia
  chega como "(cópia)".

## 5.0.3

- **Aulas: central de ajuda dentro do app.** Nova tela "Aulas" (menu
  Aplicativo): a lista de aulas à esquerda, agrupada por seção, e o vídeo
  do YouTube tocando à direita, sem sair do ATIVAVID. Funciona mesmo
  bloqueado ou sem licença, e sem internet mostra a última lista baixada.
- **O admin gere as aulas ali mesmo.** Logado como admin, aparece o bloco
  "Gerenciar aulas": cole o link do YouTube, dê título, seção e ordem, e
  salve. Todo mundo que abrir o app vê na hora. Precisa rodar o
  `RODAR-NO-SUPABASE-aulas.sql` uma vez no Supabase.

## 5.0.2

- **Biblioteca de imagens e vídeos por empresa.** Nas abas Imagens e
  Vídeos, um seletor "De quem" mostra o acervo desta empresa + o Comum, só
  o Comum, ou todas. O que já estava na Biblioteca virou **Comum** (vale
  para todas as empresas, nada some). Adicionar guarda para a empresa ativa
  (ou para o Comum, se a vista "Só Comum" estiver marcada), e cada arquivo
  tem um seletor para mudar de dono. Trilhas e efeitos continuam comuns.
- O b-roll automático e o editor só oferecem as imagens da empresa do vídeo
  e as comuns. O que sobe pela timeline entra na Biblioteca da empresa do
  vídeo.
- Na pasta: `Biblioteca/images/<empresa>/` e `Biblioteca/clips/<empresa>/`;
  a raiz de cada uma é o Comum.

## 5.0.1

- **Tela "Empresas" (era "Presets").** Um card por empresa em cima: clicar
  ativa a empresa (o mesmo que o menu do rodapé). "+ Nova empresa" cria uma
  do zero. Abaixo, tudo da empresa ativa em blocos com nome claro:
  **Identidade** (nome, logo, cor de destaque, formato, fontes e cartão
  final), **Perfil** (o que a IA sabe: veio da tela do Roteiro, que agora só
  aponta para cá) e **Presets de edição** (os jeitos de cortar dela).
- **Apagar empresa.** Somem a identidade, o perfil e os presets dela. Os
  vídeos continuam nos Projetos como "sem empresa" e os roteiros ficam no
  disco. A última empresa não pode ser apagada.
- **Logo por empresa.** Clique no quadrado do logo e escolha um PNG, JPG ou
  WebP de até 3 MB. Aparece no card e no rodapé da barra lateral.
- Menu do rodapé ganhou "Nova empresa / gerenciar", que abre esta tela.

## 5.0.0

- **Numeração nova: 5.0.0.** Daqui em diante é maior.menor.correção
  (5.0.1, 5.1.0…). Começa em 5 porque 4.1.1 seria lida como mais antiga
  que 4.101 pelo atualizador.
- **Workspace por empresa.** O card no rodapé da barra lateral abre a lista
  de empresas (marcas): escolher uma filtra Fila, Concluídos, Projetos e a
  tela inicial para os vídeos dela, e troca a marca ativa (presets, estilos
  e roteiro seguem junto). "Todas as empresas" mostra o acervo inteiro, com
  o nome da empresa em cada card. Cada vídeo sabe de quem é pelo preset
  usado ou pela importação; vídeo sem empresa aparece em todos.

## 4.101

- **Roteiro mais viral e mais vendedor.** O prompt ganhou a regra "viral
  que vende": gatilhos mentais de propósito (curiosidade, dor, prova
  social, escassez real, autoridade, contraste, identificação, erro
  comum), cada gancho marcado com o gatilho usado, retenção gancho →
  tensão → entrega → CTA, e proibição de inventar número, prazo ou
  promessa. Seletor "Gatilho" na tela, atalho "Explorar ângulos" (6
  ângulos com gancho pronto) e a seção "Por que para o scroll" na resposta.
- **Marca e preset à vista na importação.** Saíram de dentro de "Estilo"
  para o topo do "Editar com IA": escolha a marca e o preset antes de
  importar, sem refazer depois.
- **Mídia no editor.** O modal "Inserir imagem / B-roll" ficou bem maior; a
  Biblioteca tem abas Imagens, Vídeos, Sons e Trilhas; e a **trilha** agora
  se troca pela linha do tempo: clique nela para trocar (pela Biblioteca),
  ajustar o volume ou remover. A escolha vale no Aplicar e sobrevive ao
  Refazer.
- **Imagem na trilha principal.** O "Importar" da linha do tempo aceita
  JPG, PNG e WEBP: a imagem vira um trecho de 5 s no tamanho do vídeo e
  entra onde a agulha está.

## 4.100

- **Tempo exato da headline, em segundos, por preset.** Em Estilo, ao lado
  de "Headline fica na tela", entrou "Tempo exato da headline (s)". Com um
  número ali (aceita vírgula), a headline fica exatamente esse tempo — nunca
  mais que o vídeo, no mínimo meio segundo — e a legenda que espera a
  headline respeita o mesmo tempo. Vazio, continua como antes (alguns
  segundos / o dobro / o vídeo inteiro). Cada preset guarda o seu.

## 4.99

- **Perfil da empresa com campos, por marca.** No Roteiro, "Perfil da
  empresa" virou um formulário: o que vende, para quem, cidade, diferenciais,
  provas, oferta do momento, como o cliente fala com você, tom de voz e o
  que não falar. A IA recebe uma linha por campo em todo roteiro.
- **"Montar com meus vídeos".** Um botão lê as falas e legendas dos seus
  últimos vídeos concluídos desta marca (sem repetir as combinações do
  Multiplicador) e preenche um rascunho do perfil; você corrige e salva.
  Nada é gravado sem o Salvar.

## 4.98

- **Roteiro: o cartão final entra no prompt mesmo quando a marca não o
  tem.** A Prime Camp guarda o "Segue @lojaprimecamp" no preset, não na
  marca, e o primeiro roteiro real saiu com "(sem cartão)". Agora o
  preset ativo cobre. E enquanto os dados da empresa não forem
  preenchidos, o link "Preencher dados da empresa (recomendado)" fica
  aceso.
- **Roteiro: a lista e a caixa de digitar ficam paradas.** Só as
  mensagens rolam; a tela inteira não vai mais para cima.

## 4.97

- **Roteiro: a IA escreve o que gravar.** Tela nova abaixo de Presets, em
  formato de conversa. Você escolhe estilo (venda, viral, educativo, erro
  comum, bastidor, prova, promoção, humor), duração, objetivo e tom,
  escreve sobre o que é o vídeo (ou parte de um dos atalhos) e recebe
  ganchos que param o scroll, o roteiro por blocos com tempo, CTA, texto
  na tela e a legenda do post — limpo, sem markdown, para ler e gravar.
  A IA usa os dados da empresa ("Dados da empresa", salvo na marca) e o
  cartão final. Os roteiros ficam guardados neste computador, por marca;
  dá para copiar o roteiro, só os ganchos, ou pedir outra versão. Mesma
  IA do corte (sessão do navegador, Groq de reserva), sem chave nova.
- **Freepik mostra mais imagens.** A busca trazia só fotos em pé (9:16),
  por isso "vinham poucas". Agora as em pé vêm primeiro e o resto do
  banco completa a lista, até 24 por busca.

## 4.96

- **Freepik (Magnific) como banco de imagens e vídeos.** No "Buscar
  online" do editor há três fontes: Pexels · fotos, Freepik · fotos e
  Freepik · vídeos. A busca mostra prévias; o download acontece só no
  clique, por id (é o que a Freepik conta). A chave entra em Integrações →
  "B-roll — Freepik (Magnific)", com Testar. O b-roll automático e o
  planejador usam a Freepik quando não há chave do Pexels.

## 4.95

- **Multiplicador: escolha a marca e o preset antes de criar as
  combinações.** A janela ganhou os seletores de Marca e Preset (vêm com a
  marca ativa e o preset ativo dela); todas as combinações saem com o
  escolhido. Antes o lote saía com o preset padrão e a pessoa descobria
  no editor, 27 vídeos depois.

## 4.94

- **Trial só com cadastro.** Quem instala e abre sem conta vê "Crie sua
  conta para testar 7 dias grátis" com o botão "Criar conta grátis"; o
  trial nasce no cadastro e guarda o e-mail — o painel passa a saber de
  quem é cada PC em teste. Quem já estava em trial segue como antes.
  Precisa rodar de novo `supabase/rpc_license.sql` (sem isso o servidor
  continua dando trial sem conta).
- **Contas: "Apagar", não só "Revogar".** Apaga a liberação, o login
  (e-mail e senha) e o vínculo dos PCs — para e-mail digitado errado.
- A linha "nenhum PC entrou com esta conta" saía colada no "0 de 1".

## 4.93

- **Licença: de quem é cada PC.** O painel mostra o e-mail do dono em
  todas as tabelas (conta vinculada, e-mail da liberação ou quem estava
  logado ao abrir), a coluna "PCs" das contas passa a dizer quantos PCs
  entraram de fato ("0 de 1 — nenhum PC entrou com esta conta") e
  "Liberar dispositivo" / "Bloquear" aceitam o código curto que o cliente
  lê na tela (8372A270), resolvendo para o ID completo em vez de criar um
  dispositivo fantasma. O registro de abertura passa a mandar o e-mail
  logado — para isso, rode de novo `supabase/registro_de_uso.sql` no
  Supabase (o app funciona sem, só sem essa coluna).

## 4.92

- **A pasta de entrega tem o nome do vídeo — e ganha o ✅ ao aprovar.**
  A pasta `publicar/<nome>/` passa a se chamar pelo nome do card
  ("G1 · C2 · CTA3") nos vídeos com nome fixo; renomear ou marcar
  "Aprovado" renomeia a pasta junto ("✅ G1 · C2 · CTA3"), sem duplicar
  nada. Se a pasta estiver aberta no Explorer, o nome muda e a tela avisa
  para fechar a pasta e aprovar de novo.

## 4.91

- **Copiar o nome do vídeo (com o ✅).** Botão ⧉ ao lado do nome no
  cabeçalho do editor e "Copiar nome" no menu "⋯" do card — copia o nome
  completo, do jeito que você usa para nomear a pasta de entrega.

## 4.90

- **Renomear e aprovar o vídeo direto do editor.** No cabeçalho, o nome
  do vídeo agora é clicável (renomear) e ganhou o checkbox **Aprovado**:
  marcar põe o ✅ na frente do nome, desmarcar tira — o mesmo sinal que
  você já usava na mão, e o card do hub mostra o mesmo nome.

## 4.89

- **"Copiar estilo" quebrava antes de copiar** (erro "job is not
  defined"), e por isso o "Colar estilo" nunca acendia. Corrigido.
- **O menu "⋯" não some mais depois de copiar.** Repintar um card com o
  menu aberto deixava o card sem menu — agora os menus fecham antes de
  qualquer repintura. Fluxo completo (copiar → colar → refazer) provado
  em ambiente isolado, com o estilo colado idêntico ao da origem.
- Redimensionar a janela não gera mais um erro escondido ao fechar os
  menus (defeito antigo).

## 4.88

- **"Colar estilo" sempre visível no menu.** Ele só aparecia depois de
  copiar um estilo — escondido, ninguém descobria. Agora fica no menu de
  todo vídeo pronto: desabilitado com a dica "copie um estilo primeiro"
  até você copiar, e ativo ("Colar estilo (de …)") nos outros vídeos.

## 4.87

- **Copiar e colar estilo entre vídeos.** No menu "⋯" de um vídeo pronto,
  "Copiar estilo" guarda o estilo dele; nos outros cards aparece "Colar
  estilo (de …)", que aplica o mesmo estilo e manda o vídeo refazer a
  parte visual. Bom para alinhar os 27 criativos do Multiplicador a um
  que ficou do jeito certo.

## 4.86

- **Dois vídeos ao mesmo tempo não travam mais a transcrição.** Com 2
  jobs em paralelo, dois modelos de transcrição disputavam a placa de
  vídeo de 4 GB e os dois rastejavam (vídeos de 21 s parados por mais de
  40 minutos em "Ouvindo o que foi falado"). Agora a transcrição local
  tem uma vaga na máquina: um vídeo transcreve por vez e o outro espera
  alguns segundos pela vez dele — o card diz "esperando a vez".

## 4.85

- **Editor e card mostram o mesmo nome.** O editor mostrava o nome do
  arquivo final enquanto o card mostrava o título do projeto (nos
  criativos do Multiplicador, "G2 · C1 · CTA2" de um lado e a manchete do
  outro). Agora o editor recebe o nome exatamente como o card o calcula.

## 4.84

- **O editor mostra o nome do vídeo editado.** No cabeçalho, além da
  manchete e de "arquivo · duração · formato", entra em destaque o mesmo
  nome que o vídeo tem no card ("G3 · C1 · CTA3", por exemplo).

## 4.83

- **Voltar do vídeo para Concluídos não apaga mais a lista.** A tela
  guarda o último retrato dos seus projetos e pinta na hora; enquanto o
  servidor responde ela diz "Carregando…" em vez de "Nenhum vídeo pronto".
- **A lista carrega 4–5x mais rápido.** O servidor guarda o card dos
  vídeos concluídos e só remonta quando o projeto muda de verdade
  (medido com 246 projetos: 0,66 s → 0,14 s, card idêntico).

## 4.82

- **O selo e o capítulo do vídeo longo aparecem na Edição.** Eles só
  existiam queimados no vídeo final — na Edição não havia bloco na
  timeline nem cartão no preview. Agora ambos entram como bloco na faixa
  de texto e o cartão aparece no preview quando a agulha passa na janela
  deles (no Visual, com o final pronto, nada desenha em dobro por cima
  do que já está queimado).

## 4.81

- **O selo do vídeo longo mostra a SUA marca.** O cartãozinho que entra
  no começo do vídeo (lower third) pegava só a primeira palavra da sua
  linha de marca e completava com um nome padrão do sistema — saía
  "Segue / ATIVAVID" em vez de "@lojaprimecamp". Agora ele usa o seu
  arroba (ou a linha inteira, se não tiver arroba), a segunda linha só
  aparece se você a preencheu, e sem marca configurada o selo nem entra.

## 4.80

- **O vídeo longo agora sai com a legenda queimada.** Antes ela ia só
  como arquivo .srt (para o CC do YouTube) e o editor ficava sem a faixa
  de legenda — "cadê a legenda?". Agora ela aparece no próprio vídeo
  (embaixo, centralizada, estilo 16:9), a faixa volta ao editor para
  corrigir o texto, e o .srt continua saindo — corrigiu no editor, vale
  para o vídeo e para o arquivo.

## 4.79

- **Áudio do vídeo longo com o teto certo.** O primeiro vídeo longo pelo
  caminho novo saiu com o pico de áudio em -0,4 dB (o padrão da casa é
  -1,0) — a soma da voz com a trilha não tinha limitador na saída. Agora
  tem, com folga, no mesmo padrão dos Reels.

## 4.78

- **Atualizar avisa quando tem vídeo sendo editado.** Atualizar fecha o
  aplicativo, e um render no meio recomeça do zero — agora o app avisa e
  pede confirmação antes, em vez de fechar calado por cima do trabalho.
- **A IA insiste antes de desistir do plano de corte.** Quando o Gemini
  recusa ou responde fora do formato, o app repete o pedido na própria
  sessão (na prática a segunda tentativa responde certo) antes de cair
  nos caminhos de reserva.

## 4.77

- **Vídeo longo (YouTube 16:9) renderiza em minutos, não em horas.** O
  vídeo final do formato longo é o corte + lower third + título de
  capítulo + trilha — mas ele era re-renderizado quadro a quadro num
  navegador (um vídeo de 11 minutos levava horas por 10 segundos de
  arte). Agora a arte é pintada direto nos quadros e o vídeo é montado
  num passe único de ffmpeg, com a mesma aparência (animações de entrada
  e saída incluídas) e a placa de vídeo acelerando quando existe.
- Vídeo longo com b-roll (imagem/vídeo de cobertura) segue no caminho
  antigo por enquanto, com o motivo anotado na ficha.

## 4.76

- **A IA não recusa mais o plano de corte.** Em vídeo longo, o Gemini
  entendia o pedido como "edite um arquivo de vídeo" e respondia "só
  consigo gerar texto" — e o corte caía no plano automático. O pedido
  agora deixa claro desde a primeira linha que a tarefa é devolver o
  plano em texto (JSON). O registro do job também passa a dizer quando
  foi recusa (antes aparecia como "JSON quebrado", que confundia o
  diagnóstico).

## 4.75

- **Vídeo longo não derruba mais o corte.** Um vídeo de 15 minutos vira
  centenas de trechos, e a soma do áudio estourava o limite de comando do
  Windows — o corte morria com "nome do arquivo muito grande". O mix
  agora soma em lotes (mesmo som, comandos pequenos).
- **O card mostra o formato certo do vídeo.** Um vídeo com preset YouTube
  aparecia na Fila com "9:16" ao lado da duração — o rótulo era fixo na
  tela. Agora ele vem do preset do job: Reels 9:16, YouTube 16:9,
  Quadrado 1:1, Feed 4:5. O corte em si sempre esteve certo; só o rótulo
  mentia.

## 4.74

- **ElevenLabs saiu do produto.** Nada no ATIVAVID depende mais de conta ou
  créditos de nuvem: a transcrição roda na sua máquina (como já era o
  padrão) e a trilha é composta pela IA local (MusicGen), com a sua
  Biblioteca de trilhas de reserva.
- O card da chave ElevenLabs saiu das Integrações e o Doutor não cobra mais
  essa chave. Configuração antiga que apontava para a nuvem continua
  funcionando — resolve para o motor local, sem erro.
- O card de Música em Configurações ficou mais simples: sem escolha de
  motor (só existe um), mantendo o instalar/estado da IA local.

## 4.73

- **Emoji e efeito sonoro não somem mais depois do render.** Eles voltam
  para a timeline como camada viva — dá para mover, ajustar o volume,
  trocar de lugar ou apagar, e o próximo "Aplicar" respeita exatamente o
  que está na tela (mover não duplica mais; apagar não ressuscita mais).
- No Visual, o emoji já queimado no vídeo não aparece dobrado — o cartão
  vivo só entra na Edição, igual às imagens.

## 4.72

- **Camadas de verdade na timeline.** Arraste um bloco de imagem ou vídeo
  **para cima ou para baixo** e ele muda de camada — a faixa de mídia ganha
  uma fileira por camada, como num editor profissional. A fileira de baixo
  aparece **na frente** no vídeo; legenda e headline continuam sempre por
  cima de tudo. A dica durante o arrasto mostra a camada ("camada 2").
- Um bloco novo já nasce na primeira fileira livre — nunca em cima de outro
  que ocupa o mesmo trecho.
- A ordem de pintura (camada e depois início) sai igual no preview e nos
  dois motores de render.

## 4.71

- **Recorte de tempo do vídeo inserido (in/out).** Arrastar a borda
  **esquerda** do bloco de vídeo agora corta o **começo do arquivo** —
  você escolhe qual trecho do take entra, como num editor profissional
  (a dica mostra "take a partir de Xs"). A borda direita segue definindo
  a duração. O preview do cartão já toca a partir do ponto escolhido, e o
  render sai igual nos dois motores.
- **Conserto de raiz junto:** os quadros do take agora são extraídos no
  tamanho real do cartão — redimensionar um cartão de vídeo podia
  derrubar o render (máscara e quadro de tamanhos diferentes).

## 4.70

- **A Biblioteca mostra a miniatura dos vídeos.** No "Inserir imagem /
  B-roll", os clipes de vídeo apareciam como cartão escuro com um play —
  sem dar para saber qual vídeo era. Agora cada clipe mostra um quadro do
  próprio vídeo, com o play como selo por cima.

## 4.69

- **Mudou no Estilo, aplicou na Edição — vai tudo junto.** Antes, mexer
  na aba Estilo e aplicar pela Edição levava só a timeline: headline,
  card final e o resto do estilo saíam velhos, sem aviso. Agora qualquer
  mexida no Estilo acende o "Aplicar alterações" (mostra "estilo" no
  pendente) e o clique salva o estilo junto e refaz a Fase 2 completa.
  Mexeu SÓ no estilo? O mesmo botão aplica também.

## 4.68

- **"Nenhum" nas animações — e mais 3 pares novos.** Agora dá para
  desligar a animação de entrada e/ou de saída (**Nenhum**: aparece
  inteiro no primeiro quadro / fica até o fim). E chegaram **Carimbo**
  (bate grande e assenta, como a headline), **Piscar** (estroboscópio ao
  entrar ou antes de sumir) e **Esticar** (abre/fecha na vertical, como
  persiana). São **18 entradas e 14 saídas**, com rolagem no menu — tudo
  idêntico nos dois motores de render.
- **Trecho excluído não volta mais no refazer (vídeos de vários takes).**
  Num vídeo do Multiplicador (ou de várias partes), excluir um trecho e
  depois refazer — por exemplo, ao adicionar uma foto — remontava o corte
  do zero e o trecho voltava. Agora o refazer mantém o seu corte, como já
  acontecia nos vídeos de uma fonte só; mudar ritmo/intensidade/tipo
  continua replanejando de propósito.

## 4.67

- **Sem imagem dupla na aba Visual.** O vídeo final já traz a mídia
  aplicada (com a animação), e o editor desenhava o cartão da camada por
  cima — dava duas cópias, com "a de trás se mexendo". Na Visual agora só
  aparece o cartão do que ainda não foi aplicado; na Edição tudo continua
  como camada.

## 4.66

- **A faixa de mídia subiu para logo abaixo do vídeo principal — e na
  mesma altura.** As imagens e vídeos inseridos aparecem como camadas
  grandes, com miniatura legível, colados no filmstrip do vídeo. A faixa
  de texto (gancho) e a de sons vêm em seguida.

## 4.65

- **O bloco de mídia mostra a mídia, não o nome.** Na timeline, a imagem
  ou vídeo inserido aparece como miniatura repetida dentro do bloco —
  igual à faixa do vídeo principal. O nome do arquivo continua no
  tooltip, para quem quiser conferir.

## 4.64

- **Mais 8 animações no menu.** Entradas novas: **Quicar** (cai de cima e
  quica), **Elástico** (estica como mola), **Balançar** (pêndulo que
  assenta), **Borrão** (chega desfocado) e **Virar** (abre como uma
  porta) — 14 entradas no total. Saídas novas: **P/ cima**, **Borrão** e
  **Virar** — 11 saídas. Tudo com o mesmo desenho nos dois motores de
  render, inclusive o desfoque, calibrado para o motor rápido sair igual
  ao navegador.
- **Animação não passa mais por trás de outra imagem.** A ordem das
  camadas agora é a da timeline: quem entra depois fica por cima (nos
  dois motores e no preview), e o cartão selecionado sobe ao topo
  enquanto você mexe nele.

## 4.63

- **Botão "Animações" com o catálogo dobrado.** Na faixa fx, um botão só
  abre o menu com as animações de entrada e de saída lado a lado.
  Entradas novas: **Da direita, De baixo, De cima e Girar** (além de
  Suave, Pop, Da esquerda, Fade e Zoom). Saídas novas: **P/ esquerda,
  P/ baixo, Zoom e Girar** (além de Suave, Encolher, P/ direita e Corte).
  O clique demonstra o movimento no cartão e o render sai igual nos dois
  motores — inclusive a rotação do Girar, desenhada pixel a pixel no
  motor rápido.

## 4.62

- **Lados cortam, cantos redimensionam — como num editor profissional.**
  No cartão de vídeo/imagem: arrastar uma alça **lateral** corta só
  daquele lado (o conteúdo que fica não se mexe nem muda de tamanho —
  some só o pedaço que você tirou); arrastar um **canto** redimensiona a
  imagem inteira mantendo a proporção e o enquadramento. Por trás disso o
  cartão ganhou zoom de conteúdo, que sai idêntico nos dois motores de
  render.

## 4.61

- **O vídeo/imagem inserido não some mais da timeline depois do render.**
  Ele volta como CAMADA VIVA: o bloco reaparece na linha do tempo e o
  cartão no preview, com a posição, tamanho, efeitos e enquadramento que
  já valem no vídeo — dá para mover, redimensionar, trocar a animação,
  reenquadrar ou apagar, e o Aplicar acende na hora. Apagar o bloco tira
  do vídeo no próximo Aplicar; nada duplica ao aplicar de novo.

## 4.60

- **Enquadrar: agora dá para recortar o que aparece no cartão.** Duplo
  clique no vídeo/imagem inserido (ou o botão **Enquadrar** na faixa fx) e
  o arrasto passa a mover o conteúdo dentro do quadro — você escolhe a
  parte que fica visível. Sai igual nos dois motores de render (e mudar o
  enquadramento de um take de vídeo re-extrai os quadros certos).
- **Trava de centro com linha de alinhamento.** Arrastando o cartão, perto
  do meio ele gruda no centro (vertical e horizontal) e a linha acende —
  igual editor profissional.
- **Medidas das margens durante o arrasto.** Enquanto arrasta, cada lado
  mostra a distância até a borda em pixels do vídeo (ex.: `149 | 149` dos
  dois lados = centralizado), do lado de fora do cartão. Solta o mouse,
  some tudo.

## 4.59

- **Efeitos de entrada E saída para vídeo/imagem, escolhidos na timeline.**
  Selecione o bloco de mídia (clique nele na linha do tempo ou no próprio
  cartão) e a faixa **fx** aparece na timeline — fora do vídeo, sem tapar
  nada. Entradas: Suave, Pop, Deslizar, Fade e Zoom. Saídas: Suave,
  Encolher, Deslizar e Corte seco. O clique demonstra o movimento no
  cartão, e o vídeo final sai igual nos dois motores de render.
- **Ctrl+V cola imagem na agulha.** Copiou uma imagem em qualquer lugar
  (print, WhatsApp Web, pasta do Windows) e deu Ctrl+V no editor: ela
  entra na Biblioteca e na timeline no ponto da agulha.
- **Cartão de vídeo sem "tela preta".** O preview pula o comecinho escuro
  do take e mostra um quadro com conteúdo assim que o arquivo carrega.

## 4.58

- **Vídeo adicionado à mão aparece de verdade no preview.** Um take de
  vídeo posto pela caixa "imagem ou vídeo" saía como ícone de imagem
  quebrada e, ao redimensionar, virava um pontinho invisível no canto.
  Agora o cartão toca o vídeo (mudo, como no render) e o tamanho é
  proporcional à tela — redimensionar a janela não desloca mais nada.
- **Adicionou mídia, o "Aplicar alterações" acende.** Vídeo, imagem, som
  ou emoji posto na mão agora conta como alteração pendente: o botão
  vermelho de cima faz tudo em um clique (salva e envia à fila) — sem
  precisar procurar o salvar dentro do "Mais…".
- **Animação de entrada do vídeo/imagem, à sua escolha.** Passe o mouse
  sobre o cartão no preview: Suave (sobe e aparece, o padrão), Pop
  (cresce com quique) ou Deslizar (entra pela esquerda). O clique já
  demonstra o movimento no próprio cartão, e o vídeo final sai igual nos
  dois motores de render.

## 4.57

- **Multiplicador de criativos.** Novo botão na tela inicial: você solta as
  variações de gancho, corpo e CTA em três caixas e o ATIVAVID monta
  **todas as combinações** na ordem gancho → corpo → CTA — 3 × 3 × 3 = 27
  vídeos entram na fila de uma vez, cada um como um projeto próprio com o
  nome da combinação (G1 · C2 · CTA3). Os arquivos ficam guardados uma vez
  só (as combinações usam link, sem duplicar espaço) e a transcrição de
  cada take é aproveitada entre as combinações. É o fluxo de teste de
  criativo para tráfego pago: sobe tudo no gerenciador e deixa o algoritmo
  achar o vencedor. Teto de 48 combinações por lote.

## 4.56

- **Palavra que o corte removeu não pisca mais no meio da legenda.** Quando
  o corte tirava um trecho, a palavra que ficava quase toda dentro dele
  ainda aparecia na legenda como um flash de milissegundos — e podia cair
  no meio da fala seguinte (num vídeo real, um "né?" de 8ms entrou dentro
  de "Prime Camp" e a tela mostrou "Prime né? Camp"). Agora a palavra só
  entra na legenda se uma parte de verdade dela ficou no áudio. Medido nos
  seus projetos: 55 de 202 vídeos tinham palavras-fantasma dessas (de 1 a
  6 por vídeo). Clique em "Salvar e refazer a Fase 2" no vídeo afetado
  depois de atualizar.

## 4.55

- **Trocar o motor de transcrição para o ElevenLabs agora vale também
  para vídeo já importado.** Um refazer reusava o transcript local antigo
  (foi o que manteve a legenda alucinada do vídeo do "defeito
  sobrenatural" mesmo depois da troca). A regra tem direção: pedido pago
  com transcript local gravado re-transcreve; pedido local com transcript
  pago gravado mantém — o que custou dinheiro não se joga fora.

## 4.54

- **Legenda "toda errada e remontada" no refazer: era alucinação do
  Whisper.** Caso real de 31/08: um vídeo de esquete saiu com 132 palavras
  no transcript, 121 delas duplicatas exatas ("ei," repetido 107 vezes, 9
  no mesmo instante). Agora o funil da legenda descarta duplicata exata e
  corta rajada da mesma palavra (a partir da 3ª em sequência de
  metralhadora); fala pausada de verdade ("ei... ei... ei") sobrevive.
  Clique em "Salvar e refazer a Fase 2" uma vez depois de atualizar.
- **Letras do mesmo tamanho com fonte só-maiúsculas.** A Integral desenha
  tudo em capital; a letra que falta nela descia para a reserva em
  minúscula e saía um ç pequeno no meio de "PROMOÇÃO". Fonte
  só-maiúsculas agora sobe o texto para caixa alta nos dois motores e no
  preview — toda letra do mesmo tamanho.

## 4.53

- **A altura normalizada chegou também à headline.** Título curto bate no
  teto de tamanho, e o teto em pixels rendia alturas diferentes por fonte
  (Anton 21% mais alta). O mesmo fator das legendas agora vale no título,
  nos dois motores.

## 4.52

- **O mesmo fallback de fonte nos três lugares.** Quando a fonte da marca
  não tem uma letra, o vídeo do Remotion caía na fonte do sistema
  enquanto o motor rápido caía na Poppins — o mesmo projeto podia sair
  diferente conforme o motor. A pilha agora termina em Poppins no
  template, no motor e no preview.
- **O preview do editor mostra a SUA fonte.** Com fonte própria
  ("arquivo", ex.: Integral), o preview exibia a legenda na fonte do
  template e o vídeo final saía na sua — agora ele carrega a mesma fonte
  do render.
- A moldura da headline passou a medir a largura com a fonte que
  realmente desenha cada letra (caixa justa mesmo com letra na reserva).

## 4.51

- **Acento e ç saem certos em QUALQUER fonte.** Fonte que não tem o glifo
  (fontes de demonstração como a Integral DEMO não têm nenhum acento)
  ganhava o carimbo da fonte no meio da palavra; agora a letra que falta
  sai na fonte padrão, alinhada — exatamente o que o Chrome já fazia no
  outro motor. A ficha do card avisa quando isso acontece.
- **Toda fonte com a mesma altura.** No mesmo tamanho, a Anton saía 21%
  maior que as outras — trocar de fonte mudava o tamanho visível da
  legenda. Cada fonte agora tem um fator de altura, aplicado no dado (os
  dois motores e o preview leem o mesmo número); fonte própria do usuário
  é medida na hora.
- Medição completa do catálogo (13 fontes × acentos × alturas) virou
  teste: fonte nova sem acento ou fora da altura quebra a suíte antes de
  chegar a um cliente.

## 4.50

A maior auditoria do projeto até aqui: seis varreduras paralelas (dados da
máquina, exceções e arquivos, licença e cobrança, front-end, paridade dos
dois motores, suíte de testes) e todos os achados executados.

**Consertos que protegem os seus vídeos**

- O "Liberar espaço" liga arquivos por hardlink para economizar disco; um
  Aplicar alterações depois disso podia **corromper o corte do projeto em
  silêncio**. Fechado — e o retry do canário e a promoção do final também
  saíram da mesma armadilha.
- Vídeo aberto no player durante o Aplicar agora dá a mensagem certa
  ("feche o vídeo e tente de novo") em vez de falha genérica.
- Configurações e estado do canário gravam de forma atômica: um
  desligamento no meio da gravação não apaga mais a sua pasta de projetos
  da configuração nem solta uma pausa legítima do canário.
- "Reverter correções" agora avisa quando não há versão guardada — antes
  dizia "revertido" sem ter revertido nada.
- Legenda cobrindo só parte do vídeo (caso real: 12s legendados num vídeo
  de 24s) e sessão de IA expirada no meio do lote agora aparecem na FICHA
  do card — antes eram avisos de log que ninguém vê.
- Fonte num caminho de nuvem (OneDrive) não pendura mais a fila para
  sempre: as sondas de vídeo ganharam limite de tempo.

**Os dois motores desenham igual (varredura completa contra o Remotion)**

- Emoji e efeito sonoro postos à mão **sumiam** no caminho de reserva do
  render — as duas camadas foram portadas.
- A entrada da headline escolhida no preset (pop / deslizar) agora
  acontece também no motor rápido.
- Pílula ganhou a bolinha colorida; carimbo ganhou a batida de entrada, o
  fundo translúcido e as sombras certas; cartão final desenha todas as
  linhas; scatter, impacto, bolha e contador alinhados ao template.
- Varredura de 30 desenhos contra o Remotion: todos na faixa saudável.

**Licença e segurança**

- PC bloqueado não serve mais de "proxy de IA" de graça nem escreve na
  Biblioteca sem licença.
- Cookies de sessão (Gemini/ChatGPT) agora são cifrados no disco, como já
  eram as chaves.

**Tela**

- O pill de status do card parou de vazar CAIXA ALTA para os chips da
  timeline do editor; o toast do editor parou de sair híbrido.
- Exportar/Importar preset voltaram a aparecer na tela Estilos do hub.
- O resumo do Sistema (Perfil/Cache) finalmente aparece; a pastilha de
  versão do editor passou a responder ao clique; Esc fecha o painel de IA.

## 4.49

- **Emoji na headline agora sai desenhado de verdade** — colorido, como
  nas legendas. "Foi Traído 2 Vezes 🐂🐂" saía com duas caixinhas porque a
  headline usava o caminho de texto sem emoji do motor próprio; agora ela,
  o bloco de várias linhas e o cartão final usam o mesmo desenho de emoji
  que as legendas já tinham. A largura da moldura também passou a medir o
  emoji na fonte certa.
- A 4.48 foi desfeita: a regra certa é desenhar o emoji, não apagá-lo.

## 4.48

- Removia o emoji da headline em todos os caminhos (saía como caixinha).
  **Desfeita na 4.49**, que ensina o motor a desenhá-lo.

## 4.47

- **Corrigido: "Tentar novamente" morria com "[WinError 32] O arquivo já
  está sendo usado por outro processo"** — sem processo nenhum segurando
  nada. A validação do canário economiza a cópia de ~160 MB ligando o
  corte à pasta do Remotion por hardlink; no retry, a cópia tentava
  escrever o arquivo por cima dele mesmo, e no Windows isso dá exatamente
  esse erro. Foi o que derrubou o vídeo "Carregador veicular serve no
  Fusca?".
- De quebra, o caminho de reencode nesse mesmo cenário escreveria por cima
  do arquivo que está lendo; o link agora é quebrado antes.

## 4.46

- **No PC bloqueado, a janela agora mostra os dois planos** — anual e
  mensal, lado a lado, cada um abrindo o seu checkout. Antes ela mostrava
  um preço só, e o mensal (que existe desde a 4.45) nem aparecia.
- **Assinar virou o botão em destaque.** O vermelho da janela era do
  "Ativar", que servia a quem tinha chave; agora é o plano anual. As duas
  saídas discretas ficaram: entrar na minha conta e agora não.
- **A chave de ativação saiu do app.** Quem já pagou entra com **e-mail e
  senha**: toda compra cria a conta sozinha. Liberar na mão continua no
  painel de licença, por conta.

- **Sem "Agora não".** Nessa janela o app já está bloqueado: o caminho de
  volta ao trabalho é assinar, ou entrar na conta de quem já assinou.
- **Corrigido: clicar no plano dizia "Assinatura indisponível agora"** com
  o link configurado. O estado da licença só era gravado depois de
  desenhar o painel de Licença — que ainda não existe na tela quando o
  bloqueio aparece —, então a janela mostrava os planos com o dado novo e o
  clique procurava o link no dado velho, vazio.
- **Diagnóstico não alarma mais com pausa antiga do canário.** Ele dizia
  "Desenho rápido pausado" no modo Automático, onde essa pausa não segura
  nada; a anotação continua visível, sem alarme.

Chave já ativada num computador continua valendo — o que acabou foi o
lugar de digitar uma nova.

## 4.45

- **Dois planos na tela: Anual R$ 399 e Mensal R$ 59.** O produto virou
  **ATIVAVID Pro** e cada plano é um botão que leva ao seu próprio
  checkout. O anual fica em destaque, com "R$ 33,25/mês · melhor preço" —
  ele se paga em 7 meses.
- O mensal existe para quem não quer travar o ano; o anual continua sendo
  o melhor negócio para os dois lados.
- Plano sem link configurado simplesmente não aparece.

Nos bastidores: a função que libera a licença passou a aceitar vários
preços e a calcular os dias a partir do **próprio plano** — anual vale 365
dias, mensal vale 35 (30 + folga para a renovação atrasar sem derrubar
ninguém). Antes ela dava 365 dias para qualquer compra, o que faria o
mensal de R$ 59 valer um ano inteiro.

## 4.44

- **A chave de ativação saiu da tela e virou janela.** Ela serve para a
  minoria que comprou fora do app e ocupava o mesmo peso do preço para
  todo mundo. Agora abre no botão **Tenho uma chave**, com a caixa já em
  foco, e fecha sozinha quando a chave vale.
- De quebra: esse botão tentava ativar o que estivesse na caixa (vazia) e
  devolvia "Falha ao ativar" para quem só queria ver onde digitar.
- **O plano ganhou nome:** "Pro anual · R$ 399 / ano". Antes era só um
  número — e é o nome que deixa caber mais de um plano na mesma tela.

## 4.43

- **Quem está no teste agora pode assinar.** A faixa de compra só aparecia
  para quem *não* tinha acesso — e no trial a pessoa tem. Resultado: quem
  se convencia no segundo dia não tinha botão nenhum, precisava esperar o
  teste vencer e ser barrado para conseguir pagar.
- Agora ela aparece durante o teste com o prazo no recado — "Seu teste
  acaba em 3 dias. Assine agora e não perca o acesso." — e os dois
  caminhos: **Assinar agora** e **Tenho uma chave**.
- O botão de assinar só existe se houver link de pagamento configurado
  (botão que leva a uma desculpa é pior que botão nenhum), e continua
  escondido para quem já tem licença ativa e para o administrador.

## 4.42

- **O card "Suporte Prime Camp" some de quem não tem licença ativa.** Ele
  estava aparecendo em computador no trial. O código marcava para esconder;
  quem desfazia era o CSS: o `hidden` do navegador perde para qualquer
  regra de autor com `display`, e o card tem `display:flex`.
- Era defeito de família, não caso isolado — já havia três remendos
  individuais no arquivo pelo mesmo motivo. Agora uma regra só (`[hidden]`
  manda, sempre) vale para o app inteiro e para o editor, então componente
  novo já nasce escondendo quando pedem para esconder.

Conferido nos dois estados: em trial o bloco fica com altura zero; com
licença ativa ele volta, com o número e o link do WhatsApp levando o código
da máquina junto.

## 4.41

- **Botão "Assinar agora" passa a existir de verdade.** O checkout da Prime
  Camp foi criado na Stripe (ATIVAVID — Licença anual, R$ 399/ano, com
  renovação) e o link entrou na configuração que vai dentro de cada
  instalação. Até aqui o campo estava vazio: quem chegava no fim do trial
  via a janela da licença **sem forma de comprar** — e nada avisava.
- **O diagnóstico (Sistema) passou a checar isso.** Ele avisa se não houver
  link de pagamento, e também no caso mais traiçoeiro: link configurado só
  na máquina do dono e vazio na build que os clientes instalam.

## 4.40

- **Importar num computador bloqueado agora diz "licença", não "falha no
  upload".** O bloqueio funcionava — o rodapé já mostrava "Licença
  bloqueada" —, mas a tentativa de importar virava um card vermelho com
  "falha no upload" e um botão "Tentar novamente" que nunca ia dar certo.
- A recusa por licença chegava à tela de várias formas (403 com corpo, 403
  sem corpo, resposta vazia, conexão caindo no meio do envio) e só a
  primeira era tratada. Agora, quando a importação falha, o app pergunta o
  motivo antes de pintar o card: se for licença, abre a janela de ativação
  com o texto do servidor e o código do computador.
- Erro de rede também parou de se chamar "falha no upload": quando o app
  já sabe que a licença não vale, o recado é esse.

## 4.39

- **Bloquear um computador agora vale de verdade.** Havia dois furos, os
  dois medidos no seu banco: o servidor respondia "liberado" para uma
  máquina com bloqueio gravado (quem barrava era só o app, com uma segunda
  pergunta que existe da 4.27 para cima), e o veredito guardado se soltava
  sozinho na checagem seguinte — o PC bloqueava por instantes e voltava a
  trabalhar.
- **O bloqueio passou para o servidor.** Ele para antes de olhar chave,
  conta ou trial. Vale para qualquer versão do app. *Precisa de um passo
  seu:* Supabase → SQL Editor → cole `supabase/rpc_license.sql` → Run.
- **E o app deixou de dar 30 minutos de folga.** O status fica guardado
  por 30 min para não consultar a cada clique; agora, mesmo servindo do
  cache, ele pergunta "fui bloqueado?" a cada 5 minutos.
- **Ao bloquear, o painel confere se pegou.** Se o servidor ainda
  responder "liberado" para aquele PC, você vê o aviso na hora, com o que
  falta fazer — em vez de descobrir depois que a máquina continuou
  trabalhando.
- **A lista de máquinas parou de cortar.** A caixa mostrava uma linha e
  meia de três; o cabeçalho vinha centralizado e sem respiro; a data
  ocupava "30/08/2026, 21:59:13" em cada célula; e o campo de busca tinha
  uma seta de menu que não abre — essa seta, aliás, estava em **todo**
  campo de digitar do app.

## 4.38

- **O cliente agora enxerga o código do computador dele.** Antes o id só
  existia em dois lugares: o painel de admin (que é seu) e o botão de
  suporte — que só aparece para quem já paga, ou seja, justamente quem não
  precisa pedir nada. Quem estava em trial ou bloqueado não tinha como
  dizer qual máquina era a dele.
- Aparece como **código curto** (`8256B455`), do tamanho de ditar no
  telefone, com um botão **Copiar** que manda o id completo — que é o que
  o painel precisa para bloquear ou liberar. Fica na tela de Licença e na
  janela que abre quando alguém esbarra no bloqueio.
- **Do seu lado:** a lista de máquinas mostra o mesmo código curto e ganhou
  uma busca — o cliente dita `8256B455`, você cola e acha o PC.

## 4.37

- **O painel de máquinas passa a mostrar o trial.** Duas colunas novas:
  *1ª abertura* e *Trial* (dias que faltam e desde quando). Era a única
  pergunta que o painel não respondia — "esse PC está instalado há dias e
  ainda mostra 4 dias, por quê?".
- **Máquina em trial sem registro de abertura agora aparece.** O registro
  de aberturas só existe desde a 4.27; PC em versão anterior ficava
  invisível. Na conta real eram 3 trials e a tela mostrava 1 máquina — um
  painel que esconde justamente quem está em trial não vigia trial nenhum.
- A conta dos dias é a mesma do servidor, para o número no painel bater
  com o número que o cliente vê na tela dele.

Vale saber: **o trial começa no primeiro contato com o servidor, não na
instalação.** Um PC instalado antes e aberto depois só começa a contar
quando abre — por isso um computador "com vários dias de instalação" pode
estar no quarto dia de trial.

## 4.36

- **A fila também para quando a licença cai.** O bloqueio cobria a hora de
  *criar* o vídeo, e o Worker não olhava licença nenhuma: quem enfileirasse
  30 vídeos no último dia do trial — ou tivesse a fila cheia na hora em que
  o computador fosse bloqueado — continuava produzindo, porque a fila é
  retomada sozinha na abertura seguinte.
- O vídeo **espera na fila** em vez de virar erro ("Sem licença — o vídeo
  espera aqui"): licença renovada, ele sai sozinho. Quem só ficou uns
  minutos sem responder já está coberto pela janela de 72 h sem internet.
- Um defeito no gate **libera** a fila, nunca trava: erro na verificação
  não pode parar o trabalho de quem pagou.

Testado por HTTP, com o veredito do servidor trocado pelo que o banco
devolve em cada caso — trial válido, trial vencido, sem internet e
computador bloqueado.

## 4.35

- **A aba Visual passa a tocar uma cópia leve, como a Edição já fazia.**
  Ela tocava o arquivo entregue inteiro. Medido no seu vídeo de 1:30
  (1080×1920, 159 MB): decodificar em uma thread leva 50,1 s para 90,2 s
  de vídeo — 1,8× o tempo real, quase sem folga, e é isso que trava. A
  cópia leve leva 2,6 s (35×) e tem 10,6 MB. O quadro do player tem uns
  500 px de largura: os 1080 nunca apareceram na tela.
- A cópia leva o **som** (a da Edição é muda de propósito, porque a
  timeline tem a onda) — na Visual você está conferindo trilha, efeito e
  voz.
- Ela nasce sozinha na primeira vez que você abre a Visual de cada
  projeto, em segundo plano: nos 186 projetos que já existem, a primeira
  abertura ainda toca o arquivo cheio e troca sozinha quando a cópia fica
  pronta. Se a cópia falhar, o vídeo cheio volta sem você fazer nada.
- Cuidado que a mudança exigiu: a cópia nasce depois do entregue e vira o
  `.mp4` mais novo da pasta. Todo lugar que escolhe o vídeo entregue por
  data agora a ignora — sem isso, o app passaria a tratar a cópia como o
  produto (no card, no "Abrir pasta", no pacote de publicação).

O que já estava descartado por medição: o servidor entrega o vídeo em
2,3 ms por pedaço de 256 KB, então nem o arquivo nem a entrega travavam.

## 4.34

- **A ficha do vídeo diz o nome, não o parágrafo.** As linhas "IA" e
  "Trilha" tinham virado justificativa ("Plano B (Groq): a IA principal
  respondeu ilegível nesta geração. O vídeo saiu com IA normalmente.").
  Agora a linha diz **Groq (plano B)**, **Gemini**, **IA local
  (MusicGen)**, **ElevenLabs Music**, **Sua biblioteca (viral)** — e o
  porquê aparece ao passar o mouse, sem sumir.
- **As duas linhas aparecem em todo vídeo pronto.** Antes só existiam
  quando algo desviava do normal: o caminho que dava certo não se
  identificava, então "qual IA fez este?" só tinha resposta quando dava
  errado. Trilha reaproveitada do render anterior agora também se
  identifica — ela não gastou crédito nenhum.
- **O player do editor faz menos trabalho por quadro.** Mover a agulha
  obrigava o navegador a refazer o layout da timeline inteira a cada
  quadro: medido na página carregada, escrever a posição custa 0,001 ms,
  mas escrever e então ler a rolagem custa 1,51 ms — 60 vezes por segundo,
  o tempo todo. Agora a leitura é uma só, no começo do quadro, e cada
  valor só é escrito quando muda. Rolar a timeline também redesenha a onda
  uma vez por quadro em vez de três ou quatro (7,8 ms cada).

Sobre a travada no player: o servidor entrega o vídeo em 2,3 ms por pedaço
de 256 KB, então o arquivo e a entrega estão fora de suspeita — era
trabalho a mais na tela. Se ainda travar depois desta versão, me diga em
qual aba (Edição ou Visual): são vídeos diferentes tocando.

## 4.33

- **"Salvar na Biblioteca" no editor.** Marque o começo e o fim de um
  trecho com **M** — a mesma marcação que você já usa para apontar legenda
  errada — e o balão que abre agora tem, além de "Aplicar e enviar à fila",
  o botão **Salvar na Biblioteca** com a categoria (reação, humor, meme,
  viral). O trecho é recortado do vídeo que você está vendo, no ponto que
  você viu, já em 1080×1920.
- É a peça que faltava: a 4.31 e a 4.32 fizeram o vídeo de humor usar os
  clipes da Biblioteca em tela cheia, mas a única forma de pôr um clipe lá
  era recortar arquivo na mão, fora do app. Agora o acervo nasce do que
  você já filmou — e é material seu, sem risco nenhum.
- Nome com acento vira nome sem acento no arquivo ("reação" → `reacao`):
  esse arquivo é copiado para dentro do projeto e vira caminho lido pelos
  dois motores de render.

## 4.32

- **A inserção de humor entra em tela cheia.** Antes ela caía no cartão de
  780×500 no alto do vídeo — bom para ilustrar um produto, péssimo para uma
  reação: vira miniatura e a piada não acontece. Os dois motores já sabiam
  desenhar em tela cheia; faltava o b-roll automático pedir.
- **No máximo uma inserção a cada 12 segundos.** A quantidade vinha só do
  modo de b-roll e nunca olhava a duração: num teste real saíram 2 inserções
  num vídeo de 9,6s — uma a cada 4,8s, que é pisca-pisca. Em vídeo longo o
  teto não muda nada.

Os dois consertos saíram de um render de verdade, com material seu: o
primeiro teste entregou o cartão pequeno e as inserções amontoadas; o
segundo, depois das correções, entregou tela cheia aos 4,3s e aos 17,2s de
um vídeo de 34,5s.

## 4.31

- **Vídeo de humor passa a usar os clipes de humor da Biblioteca.** O app já
  tinha tudo menos a ligação: a Biblioteca aceita vídeo e tem as categorias
  **humor, meme, reação e viral**; o pipeline sabe encaixar um clipe num
  momento da fala; e o tipo "Humor" já manda preservar setup → punchline. Só
  que, com o layout Limpo (o seu em 114 de 114 vídeos), as inserções ficavam
  desligadas por padrão e ninguém olhava o tipo — com a Biblioteca cheia de
  clipes de humor, nenhum entrava.
- Agora: tipo **Humor** + clipe guardado nessas categorias = inserções
  ligadas, e a escolha é pela categoria (a palavra "reação" não aparece na
  fala, e é justamente o que entra). Sem clipe guardado nada muda — o app
  não inventa b-roll onde não há material.

## 4.30

- **O desenho rápido podia estar desligado sem ninguém saber.** Achei nos
  arquivos do app: o motor rápido estava **pausado** por um pico de áudio de
  0,09 dB — o mesmo caso que a 4.29 corrigiu. Quando isso acontece, o app
  grava "modo desligado" e **todo vídeo seguinte** sai pelo caminho completo,
  cerca de 3x mais lento (421s contra 1383s de média nos seus 413 jobs).
  Seis vídeos seus saíram assim. Agora o diagnóstico avisa, com o motivo e a
  data, e o card do vídeo conta quando foi esse o caso.
- **68 GB para liberar, avisados onde você está.** A sua pasta tem 155 GB e
  **68 GB dá para recuperar sem perder vídeo nenhum** — 34 GB de cópias
  repetidas (viram atalho, nada é apagado) e 34 GB de arquivos que o app
  refaz sozinho. Isso já era medido, mas só aparecia numa dica dentro de
  Configurações. Agora aparece em Projetos, só a partir de 20 GB, e some ao
  liberar. "Agora não" cala por 30 dias.

## 4.29

- **Pico de áudio 0,1 dB acima do alvo não refaz mais o vídeo inteiro.**
  Medindo os seus 174 vídeos: 14 ficaram acima do limite e **13 deles por no
  máximo 0,49 dB**. Seis desses foram refeitos do zero no Chrome por causa
  disso — 484s, 533s, 207s só de render — e o pico final continuou acima
  mesmo depois. Agora o ajuste de áudio roda como sempre e, se sobrar um
  excesso pequeno, o vídeo é entregue com o número registrado. Excesso
  grande (1 dos 174) continua caindo.
- **O caminho rápido de render voltou a funcionar quando há barra de
  progresso.** Uma variável escrita dentro de uma função aninhada, sem
  `nonlocal`, fazia a passada única estourar no primeiro quadro — e o vídeo
  caía no caminho de duas etapas, que grava um arquivo de ~150 MB e o lê de
  volta. Aparecia em 3 dos 174 projetos, só no registro técnico, sem avisar
  ninguém. Um teste novo varre o código inteiro procurando essa mesma forma.

## 4.28

- **Bloquear um computador não bloqueava nada — agora bloqueia.** Testei
  contra o servidor de verdade: marcar uma máquina como bloqueada não mudava
  **uma vírgula** na resposta da licença. A função existia no banco e
  ninguém a consultava, nem para uma máquina com licença válida. Agora o app
  pergunta a cada validação. Medido de ponta a ponta: licença boa + máquina
  bloqueada = sem acesso, o veredito fica gravado, ficar offline não devolve,
  e desbloquear volta na hora.
- **O registro de aberturas ganhou tela.** Em Licença, no seu painel de
  admin: uma linha por **máquina** com quantas vezes abriu, a última vez,
  quem, a versão — e o botão **Bloquear**. O link "registro deste PC" abre o
  arquivo local da máquina em que você está.
- **A tela do vídeo mostra o PRESET, não mais a marca.** "Marca deste vídeo"
  virou "Preset deste vídeo" e lista os presets de verdade; trocar ali aplica
  o estilo e o cartão final e o vídeo sai assim ao refazer. O menu lateral do
  editor também perdeu o item "Marca", que tinha ficado para trás desde a
  4.19.

## 4.27

- **Bloquear um computador agora funciona mesmo sem internet.** Testando o
  sistema de licença achei dois caminhos por onde uma máquina bloqueada
  continuava trabalhando: **atrasar o relógio do Windows** (a janela de 72h
  offline nunca fechava) e **ficar offline logo depois de ser bloqueada** (o
  app voltava para a última licença guardada e liberava por mais 72h). Os
  dois estão fechados, e desbloquear continua funcionando na hora.
- **Toda abertura do app vira registro.** Uma linha por vez que o ATIVAVID
  abre, em `%USERPROFILE%\ATIVAVIDberturas.jsonl`: máquina, usuário do
  Windows, versão e situação da licença. Funciona sem internet e sem
  servidor — é o arquivo que o suporte pede quando precisa entender um caso.
- **Suporte Prime Camp na tela de Licença.** Aparece só para quem tem
  licença ou assinatura ativa; quem está em teste ou bloqueado não vê. O
  botão já abre o WhatsApp com o identificador da máquina na mensagem.

## 4.26

- **A IA agora recebe o pedido que a nota cobrava.** A ficha reclamava da
  abertura longa em **103 dos seus 170 vídeos** ("as primeiras falas
  prendem melhor entre 1,5 e 3,5s"), mas a regra que a IA recebia para o
  tipo **Viral** — 118 dos seus vídeos — falava do que a frase precisa
  *ser* e nada sobre quanto ela deve *durar*. Medindo a primeira fala nos
  seus 189 projetos: mediana de **5,6s**, e só 23 de 144 no modo Dinâmico
  caíam na faixa boa. Agora Viral e Humor pedem a abertura de 1,5 a 3,5s —
  escolhendo uma frase que já caiba, nunca cortando uma frase longa pela
  metade.
- **E a nota parou de cobrar isso de quem não deve dar.** Educativo,
  Informativo, Institucional e Review preservam por contrato — a regra
  deles manda não pular passo. O Informativo tinha mediana de 15,3s de
  abertura e levava bronca por seguir a própria regra. São 13 vídeos seus
  que deixam de ser cobrados.

## 4.25

- **A ficha do vídeo parou de culpar o ElevenLabs pela sua própria
  escolha.** Ela dizia "Trilha composta pela IA local (MusicGen) — o
  ElevenLabs estava indisponível" toda vez que a IA local compunha. Mas o
  seu app está configurado em **Configurações → Motor de música: IA
  local**, e nesse modo a IA local compõe primeiro, de propósito, sem
  gastar créditos — a nuvem nem chega a ser chamada. Agora a ficha diz
  qual dos dois foi.
- **A fonte sem acento avisa na hora de escolher.** O aviso existia, mas
  só aparecia na ficha do vídeo pronto — com o "DEMO" já gravado por cima
  de cada acento. Agora a lista de fontes avisa no clique, embaixo do
  próprio seletor.

## 4.24

- **A legenda agora faz um tique de digitar, não um sopro.** Um vídeo de
  33s tem umas 42 legendas — uma a cada 0,8s — e o som que cada uma tocava
  era o mais longo e o mais alto da pasta (0,406s, pico -0,8 dBFS). Agora é
  um tique de **0,030s**, 4 dB mais baixo. A palavra única em destaque
  continua com o som cheio: essa é rara e é o ponto.
- **As listas dos seletores ficaram escuras de verdade.** Eu disse que
  tinha resolvido na 4.21 e não tinha: as duas folhas de estilo tinham uma
  regra pintando a lista de branco na mão, e ela ganhava do ajuste que eu
  fiz. Agora a cor sai do tema, nos dois temas.
- **Dá para apagar arquivos da Biblioteca.** Um ✕ em cada item; o arquivo
  vai para a **Lixeira do Windows**, então dá para trazer de volta por lá.
  Arquivo que vem com o app não tem o botão.
- **O seletor de categoria mostra todas as categorias da pasta.** Antes
  oferecia só as cinco que o vídeo usa (clique, risco, whoosh, pop, corte),
  então não dava para mover um arquivo para uma categoria que você mesmo
  criou — impacto, riser, sino, swoosh, transição. São 12 agora, com
  rolagem.
- O selo "toca no vídeo" só aparece quando a troca de efeitos está ligada.
  Com ela desligada, ele dizia que tocava um som que o vídeo não usa.

## 4.23

- **Três modos novos na importação, e a última linha deixou de ter um
  cartão sobrando.** Os novos: **Tutorial / passo a passo** (a IA mantém a
  ordem dos passos e não pula nenhum), **Anúncio / oferta** (gancho nos 2
  primeiros segundos, problema, prova e convite no fim — nunca termina sem
  chamar para a ação) e **Depoimento de cliente** (corte conservador,
  preserva o veredito e o motivo dele). Cada um junta uma intenção de corte
  com um tipo de conteúdo que a IA já obedecia — o "Viral" sempre foi feito
  assim.
- Quando um cartão fica sozinho na última linha, ele passa a ocupar a linha
  inteira, em qualquer quantidade e em qualquer largura de janela.

## 4.22

- **Os efeitos sonoros voltaram a ser os do app.** A troca automática pelos
  efeitos da sua Biblioteca virou uma opção, **desligada**. Ela nunca foi
  pedida — foi ideia minha na 4.10 — e saiu errada duas vezes em dois dias.
  Se quiser ligar de novo, o interruptor está na Biblioteca, na aba
  "Efeitos sonoros". Projetos que já tinham som trocado voltam ao som do
  app sozinhos no próximo render.
- **E o que ainda passava, agora não passa.** O clique do corte tem 0,057s
  e a folga que eu tinha dado deixava entrar um som de 0,63s — 11 vezes
  maior. Foi o que sobrou no vídeo das 18:51. A folga agora é proporcional
  ao som que está sendo trocado.
- **"Criar preset novo" cria de verdade.** Ele só trocava de tela. Agora
  pergunta o nome, cria o preset a partir do estilo base e abre o editor
  nele — e avisa que o preset novo já vira o padrão.

## 4.21

- **A sua fonte aparece pelo nome.** A lista de fontes dizia só "Sua fonte
  (pasta Fontes)" — agora diz **FONTSPRING DEMO - Integral CF Bold**, que é
  o arquivo que está em `%USERPROFILE%\ATIVAVID\Fontes` desde 29/08. Ela
  sempre esteve instalada; a tela é que nunca disse o nome. Aviso
  importante: esse arquivo é a versão **DEMO**, que carimba "DEMO" no lugar
  de todo acento — o app já avisa quando você usa. Ponha o arquivo da
  Integral completa na mesma pasta e ela aparece na lista igual.
- **Mais de uma fonte na pasta agora dá para escolher.** Antes o app pegava
  sempre o primeiro arquivo em ordem alfabética e não dizia; a segunda fonte
  nunca tocava.
- **As listas de seleção pararam de abrir brancas no tema escuro.** O
  editor de estilo não tinha o ajuste que o resto do app ganhou em 29/08 —
  por isso o seletor de fonte abria branco. Um teste passa a cobrir as duas
  folhas de estilo de uma vez.
- **"Conferir os vídeos entregues" saiu de Configurações e foi para
  Projetos.** Ela lê os seus projetos e refaz o que saiu torto — é trabalho,
  não ajuste de máquina. Configurações fica com a instalação.

## 4.20

- **Agora dá para editar o estilo de um preset.** Cada preset ganhou
  "Editar estilo": abre o mesmo editor de Estilos, já com aquele preset
  carregado, e o botão vira "Salvar preset e voltar". Salvar ali muda só
  aquele preset — o estilo base e os outros ficam como estão.
- **Antes disso, editar um preset era impossível — e perigoso.** Estilos
  editava o estilo base e, ao salvar, copiava por cima do preset marcado
  como padrão, qualquer que fosse o preset em questão. Dos seus três, só o
  padrão mudava; o "Uander" dizia "não define o visual" e não havia como
  definir. Testado com os seus presets: depois de salvar o Uander, o estilo
  base ficou idêntico e os outros dois presets também.
- **A barra de Estilos diz o que você está editando** — "Editando o estilo
  base" ou "Editando o preset X", com um botão para voltar à base. Entrar
  por Estilos no menu sempre abre a base.

## 4.19

- **O apito no meio do vídeo: era um efeito da sua Biblioteca, longo
  demais para a vaga.** No lugar do "whoosh" do corte — que dura 0,45s —
  entrou o `swoosh--070.mp3`, de **10,78 segundos**. Um som de transição de
  quase 11s toca por cima de tudo. Agora o substituto tem de caber: no
  máximo 2,5x o som que ele troca, e ganha o mais parecido em duração, não
  o mais recente. Dos seus 70 `swoosh`, só 9 cabiam nessa vaga — e a
  escolha era por data, com todos importados no mesmo dia. Na sua pasta,
  82 dos 233 efeitos passam de 3 segundos.
- **O som do app volta antes de cada troca.** Sem isso o arquivo errado de
  um render antigo ficava no projeto para sempre. O vídeo que já saiu
  continua com o apito — refaça esse um e ele sai limpo.
- **O ajuste de volume do efeito voltou a ser aplicado.** Ele existia desde
  a 4.13, e uma mudança seguinte reescreveu a linha da cópia e o deixou
  pelo caminho. Agora o efeito entra no volume do som que substitui.

- **Marca e Presets viraram uma tela só: Presets.** Você pediu ("quero
  apenas um deles"), e os seus arquivos diziam a mesma coisa: as marcas
  salvas e os presets tinham os mesmos nomes — Prime Camp, Uander, Prime
  Camp [Centro] —, a mesma identidade criada duas vezes em duas telas. As
  outras marcas guardavam só o que o app tinha gerado sozinho. Nada foi
  apagado: os três presets continuam lá, com o mesmo padrão marcado.
- **O que a tela de Marca tinha de próprio mudou de casa.** O formato de
  saída (Reels, YouTube, Quadrado, Feed) ficou no topo de Presets, ao lado
  de "Criar preset novo", e os atalhos de identidade — cor de destaque,
  fontes, cartão final e logo — viraram um cartão no pé da mesma tela. Só
  saiu o que existia em dobro: trocar de marca e criar marca.
- **A palavra "marca" saiu do caminho.** O cartão do preset dizia "padrão
  da marca" e "usa o estilo padrão da marca"; agora diz "padrão" e "usa o
  estilo base". Link ou botão antigo que apontava para Marca abre Presets.

## 4.18

- **A legenda "Impacto" ficou igual ao desenho original — agora de
  verdade.** Ela tem duas sombras: a da caixa da palavra destacada e a do
  texto das palavras brancas. A 4.11 corrigiu só a primeira, e por isso a
  diferença mudava conforme o vídeo — o excesso da segunda cresce com o
  número de palavras. Com as duas certas, dois vídeos diferentes medem o
  mesmo: 1,020 e 1,020.
- **A conferência de desenho passou a valer para qualquer projeto.** Cada
  projeto guarda a cópia do desenho do dia em que foi feito, e comparar
  contra uma cópia velha inventa defeito: um projeto de ontem acusou cinco
  manchetes erradas que não tinham nada de errado. Agora a referência é
  sempre o desenho de hoje. Antes disso, só 1 dos seus 187 projetos servia
  para conferir.


## 4.17

- **O feixe de luz do corte varre a parte certa do quadro.** O flash tem
  duas peças: o clarão e um feixe que atravessa a tela. O feixe estava
  deslocado 462 pixels para a direita, sempre — e ele aparece umas oito
  vezes em cada vídeo seu. A comparação com o desenho original foi de
  0,63 para 0,89.
- **O card avisa quando há correção salva e não aplicada.** Você marca no
  editor, salva, e aquilo só vira vídeo quando você manda aplicar — se
  parasse no meio, nada na Fila dizia. Só avisa quando o pedido é mais
  novo que o vídeo entregue: dos 12 projetos que a outra tela acusava, 10
  eram sobra de coisa já aplicada.
- **O painel de projetos abre na hora.** Ele media a duração de cada
  vídeo entregue ao abrir — 31 segundos parado com os seus 187 projetos.
  Agora essa medição acontece no arranque, em segundo plano.


## 4.16

- **A conferência de desenho passou a pegar defeito de forma.** Ela
  comparava só a quantidade de tinta — e foi assim que a manchete
  "Carimbo" ficou espelhada com o número dentro do normal. Agora ela
  também mede a diferença ponto a ponto e avisa quando a forma foge, com
  o limite calibrado no catálogo inteiro.


## 4.15

- **Instalação em outra pasta não paga mais a instalação longa do
  Remotion.** Para não repetir um download demorado, o app procura uma
  cópia pronta num projeto existente — e o lugar onde procurar estava
  escrito à mão, apontando para a pasta de projetos de uma máquina só.
  Quem instalasse com a pasta noutro lugar não achava nada e esperava do
  zero. Agora ele olha a pasta que você configurou.
- **A conferência de desenho passou a cobrir o flash do corte.** Ele
  aparece em quase todo vídeo seu — uns oito por vídeo — e era a única
  peça que nunca tinha sido comparada com o desenho original. A primeira
  medida mostra diferença no fim do flash; ficou registrada com os números
  e uma ressalva, sem mexer no desenho por palpite.


## 4.14

- **Efeito que já vem distorcido não entra mais no vídeo.** 40 dos seus
  233 efeitos chegam com o som no teto — e a troca pegava simplesmente o
  mais recente da categoria. Se calhasse de ser um desses, a distorção ia
  para todos os vídeos, por cima da sua voz. Agora o app escolhe o
  primeiro que está limpo; se nenhum estiver, fica o som dele.
- **A Fila parou de prometer quanto falta.** O "~N min restantes" errava
  por 47% na mediana, e só 24% das previsões ficavam perto do real — dizia
  *"~1 min restante"* num vídeo que levou 15 minutos. No lugar entra o que
  o programa sabe de fato: **há quanto tempo** ele está trabalhando nesse
  vídeo. Responde à mesma pergunta ("travou?") sem inventar número.


## 4.13

- **A Fila diz em que passo o vídeo está.** *Olhando o vídeo… Ouvindo o
  que foi falado… Escolhendo os cortes… Cortando o vídeo…* — as quatro
  mostravam a mesma frase, "Preparando vídeo...", e são elas que levam
  quase metade da espera. Dava para ficar minutos sem saber se tinha
  andado.
- **Quando um vídeo falha, o card diz por quê.** Antes era sempre a mesma
  frase. Agora: resposta ilegível da IA, falta de espaço em disco, falha
  no corte — cada uma com o que fazer. E quando o próprio programa já
  tinha escrito uma explicação (como "Sessão Gemini incompleta"), ela
  passa inteira em vez de ser trocada pela frase genérica.
- **Diagnóstico, espaço e placa de vídeo continuam acessíveis com a
  licença bloqueada.** São leitura da sua própria máquina — como "Abrir
  pasta" e "Ver vídeo final" já eram.


## 4.12

- **As manchetes "Carimbo" e "Fita" giravam para o lado errado.** O
  carimbo saía inclinado ao contrário do desenho original — espelhado. A
  medida de área não via nada (mesma tinta, forma trocada); quem
  denunciou foi a diferença ponto a ponto, a maior de todo o catálogo.
  A Fita ficou praticamente idêntica ao original depois da correção.
- **O corte volta a escolher o codificador de vídeo certo quando é
  chamado sozinho.** Ele perguntava ao perfil da sua máquina qual placa
  funciona — e essa pergunta só chegava quando o programa era iniciado de
  um jeito específico. Sem ela, caía num codificador que passa no teste
  sintético e falha no vídeo de verdade.
- **"Abrir o log deste vídeo" funciona mesmo com a licença bloqueada.**
  Ele é só leitura, como "Abrir pasta" e "Ver vídeo final" — e é
  justamente o que se precisa mandar para o suporte quando algo deu
  errado.


## 4.11

- **A legenda "Impacto" voltou a ter a sombra do desenho original.** Ela
  saía com a sombra pela metade — o quadro parado parecia certo porque a
  diferença está no halo, não na letra. Achado medindo o desenho contra o
  original: 0,846 de 1,00, agora 1,032.
- **O log de cada vídeo passou a ser guardado.** Tudo que o programa conta
  enquanto faz o vídeo — tempo de cada etapa, motor usado, motivo de cada
  queda — ia para um arquivo temporário apagado no fim. Agora fica ao lado
  do vídeo, e o menu ⋯ do card tem "Abrir o log deste vídeo".
- **O "Aplicar alterações" volta a mostrar quanto já andou.** A barra
  contava os quadros só no caminho que quase nunca roda; no caminho normal
  ficava parada. O redesenho é 80% da sua espera quando você corrige uma
  legenda.
- **O card diz quando um vídeo saiu pelo caminho lento.** Aparece só
  quando há o que contar (17 dos seus 187 projetos) — em 15 deles o
  desenho rápido falhou e o vídeo foi refeito, três vezes mais devagar.
- **O diagnóstico passou a olhar também o disco dos modelos.** Ele só
  media o disco dos projetos (552 GB livres) e nunca o `C:`, onde ficam os
  1,9 GB de modelos de transcrição, os caches e o instalador da
  atualização — e que está com pouco espaço.


## 4.10

- **Os efeitos que você importou passaram a entrar no vídeo.** Você tem
  234 efeitos na Biblioteca e só os 30 de *clique* tocavam. Os 70 de
  *swoosh* nunca tocaram — o vídeo chama essa vaga de *whoosh*, e o app
  comparava a palavra em vez do som. Agora são 100 que entram, e o whoosh
  toca na manchete de todo vídeo.
- **E a Biblioteca diz quais tocam e quais só ficam guardados.** Os 133
  restantes (*impacto*, *transição*, *riser*) não têm vaga no vídeo: cada
  som agora mostra onde entra — *"toca: whoosh da manchete"* — ou que está
  só guardado. Antes a lista parecia cheia de som em uso.
- **Efeito novo já entra com a vaga certa.** Arrastar `meu-whoosh.mp3`
  antes deixava o arquivo sem categoria e sem tocar; agora o nome basta.
- **O aviso de versão nova voltou a dizer o que mudou.** Ele chegava com
  o título e a lista vazia. Agora traz as notas da versão — e as onze
  versões já publicadas foram corrigidas também.
- **Publicar no Instagram não diz mais que o vídeo sumiu.** Quando a
  manchete muda, o arquivo é renomeado; 10 dos seus projetos guardavam o
  nome antigo e a publicação respondia *"vídeo final não encontrado"* com
  o vídeo ali do lado.


## 4.09

- **A recusa da IA não vira mais a legenda do post.** Dois dos seus
  `legenda.txt` são, por inteiro, *"Sou apenas um modelo de linguagem.
  Não posso ajudar com isso."* — o texto que você copia para o Instagram.
  A checagem só olhava tamanho e hashtags, e uma recusa passa nas duas.
  Agora ela é reconhecida e fica valendo o rascunho montado do corte.
- **A lista de prontos mostra o vídeo, não o nome do arquivo.** 61 dos
  seus 184 vídeos apareciam como *Elizangela001_08291440_C039* ou
  *A001_08191405_C003* — 33% da lista, e justamente os mais recentes.
  Agora aparecem pelo que são: *"Celular na lanterna? Você acredita"*.
- **E o título passou a vir da manchete do vídeo.** Ele saía da primeira
  linha da legenda do post e vinha cortado no meio da palavra em 10
  casos — num deles era a tal recusa da IA. A manchete é curta por
  natureza, e o corte, quando precisa, respeita a palavra.


## 4.08

- **Mexer na linha do tempo não apaga mais a fala de cada trecho.** Ao
  salvar, o corte era remontado só com os tempos: a frase que cada trecho
  carrega, o motivo e o papel (gancho, CTA) sumiam. Todos os 17 projetos
  seus que passaram por "Aplicar alterações" estavam sem nenhuma frase,
  contra 11% dos que nunca passaram. Agora o trecho que continua no mesmo
  lugar mantém o que já se sabia dele.
- **A nota do vídeo passou a acompanhar o corte.** Ela é a nota do corte,
  e o "Aplicar alterações" refaz o corte — 13 dos seus 17 projetos
  corrigidos mostravam a nota do corte anterior, uma delas de 90 horas
  antes, com dicas sobre pausas que talvez você já tivesse tirado. Agora
  a nota é refeita junto.


## 4.07

- **Aplicar alterações passou a refazer a cópia leve do vídeo.** Ela
  nascia só quando o vídeo era criado; cada correção sua refazia o corte e
  deixava a cópia para trás — 46 dos seus 186 projetos estavam assim, um
  deles há quase quatro dias. A partir do primeiro "Aplicar" o projeto
  perdia o vídeo leve do editor para sempre. A cópia é refeita em segundo
  plano: você não espera por ela.
- **E os projetos que já estavam atrasados se consertam ao abrir.** Abrir
  um deles no editor manda refazer a cópia em segundo plano — essa vez
  ainda usa o vídeo completo, a próxima já abre leve. Sem varredura e sem
  espera.


## 4.06

- **O vídeo leve só é usado enquanto for o mesmo vídeo.** Cada "Aplicar
  alterações" refaz o corte, e em 46 dos seus 186 projetos a cópia leve
  ficou para trás — uma delas por quase quatro dias. Sem esta checagem o
  editor mostraria trechos que já não existem. Agora, cópia atrasada é
  ignorada e o editor usa o vídeo completo.
- **A tira de miniaturas da linha do tempo abre 7x mais rápido.** Ela sai
  da cópia leve quando esta serve: 1,2s no lugar de 8,8s, as mesmas
  miniaturas. (A onda do áudio continua vindo do vídeo completo — a cópia
  leve não tem som.)
- **Correção da 4.05:** abrir o editor com a janela minimizada podia
  deixar a tela sem vídeo até a próxima verificação.


## 4.05

- **O editor voltou a usar o vídeo leve.** Todo projeto tem uma cópia leve
  do corte para o arrasto na linha do tempo ficar fluido — 2 MB no lugar
  de 45 MB, 9 MB no lugar de 124 MB. São 186 projetos com a cópia e
  nenhum a usava: o editor perguntava se ela existia de um jeito que o
  servidor não sabia responder, e caía no arquivo cheio, em 4K.
- **E parou de bater no disco à toa.** Com o editor aberto e ninguém
  mexendo, ele pedia o estado a cada 2 segundos para sempre — 1800
  pedidos por hora disputando a máquina com o render. Agora o intervalo
  cresce sozinho enquanto nada muda e volta ao normal no primeiro clique.
  Com a janela minimizada, quase para.


## 4.04

- **"Traço da ênfase" voltou a funcionar.** O seletor entre *círculo* e
  *marca-texto* aparecia na tela, aceitava o clique e não mudava nada: ele
  era ligado antes do estilo carregar, dava erro no meio, e a segunda
  tentativa achava que já estava ligado e desistia.
- **A primeira tela não tem mais um buraco.** Com o app vazio, o Início
  mostrava o título "Recentes", um botão "Ver fila" e meia tela em branco.
  Agora diz o que vai acontecer, e o botão some enquanto não há nada na
  fila.


## 4.03

- **A tela de Presets mostra nome, não código interno.** O cartão dizia
  *LAYOUT limpa · LEGENDA stacked · MANCHETE realce · RITMO dinamico* e,
  embaixo, *informational*. Agora diz *Limpo · Empilhado · Realce ·
  Dinâmico* e *Informativo* — os nomes que você vê em todo o resto do app.
- **Quando o motor rápido cai, o relatório diz por quê.** Ele desenha o
  vídeo 3x mais rápido; quando estoura no meio, o vídeo é refeito pelo
  caminho lento. O relatório mostrava "lento, sem motivo" — um vídeo seu
  levou 479s onde levaria 130s e o motivo só saiu num log que ninguém lê.
- **O preview de desenvolvimento voltou a mostrar a mesma coisa que o
  app.** Três rotas só existiam no app: a placa de vídeo ficava em
  "Detectando GPU…" para sempre e a Fila não recebia aviso de mudança.


## 4.02

- **Liberar espaço passou a ver os 10,7 GB do Remotion.** A pasta
  `node_modules` é o maior item de um projeto — 636 MB cada — e era a
  única que a limpeza não olhava. Nos seus projetos são 16 cópias de
  verdade, todas de vídeo entregue e parado há mais de uma semana.
  O que dá para liberar passou de 58 GB para 68 GB.
- **Atalho de pasta deixou de ser tratado como pasta.** Outros 168
  projetos apontam para uma instalação compartilhada do Remotion por
  atalho. Sem essa distinção a limpeza anunciaria 107 GB que não existem
  e, pior, apagaria a instalação compartilhada — quebrando os outros 167
  projetos de uma vez. Agora o atalho é desfeito como atalho e o conteúdo
  do outro lado fica de pé.
- **E a conta continua instantânea.** Olhar essas pastas fazia a tela de
  Configurações demorar 6,6s em vez de 0,4s — 16 vezes mais. A medida
  agora fica guardada (só entra na conta projeto entregue e parado, e o
  que está parado não muda de tamanho) e é feita no arranque, em segundo
  plano: quando você abre a tela, o número já está lá.


## 4.01

- **A revisão da legenda passou a saber o nome da sua loja.** *Prime Camp*
  saía errado 30 vezes nas transcrições — *Prêmio Camp*, *Prime Cup*,
  *PremiCamp*, *Prêmio Campo* — e ia assim para a legenda, queimada no
  vídeo. O revisor já corrigia marcas, mas tinha de adivinhar quais eram;
  agora ele recebe os nomes dos seus kits de marca.
  A troca é feita pelo contexto, não por parecença: *primeira*, *prêmio* e
  *primeiro* continuam como você falou.


## 4.00

- **O corte não cai mais no meio de uma palavra.** Um terço das bordas de
  trecho terminava dentro de uma palavra, e o vídeo saía com a sílaba
  decepada. Duas vezes a palavra cortada foi *PrimeCamp* — o nome da loja,
  na última frase do vídeo, bem onde ele mais precisa ser ouvido.
  A culpa não era da IA: o plano dela pedia a frase inteira, com o nome
  incluído; era o corte que usava o tempo cru. Agora toda borda se encaixa
  na palavra — ela entra inteira quando já estava dentro, e o caco de
  início sai inteiro. Nos seus 38 vídeos mais recentes isso devolve 272
  palavras completas e custa 0,8s a mais de vídeo.


## 3.99

- **Um quadro de diferença não manda mais o vídeo inteiro para o caminho
  lento.** O conferidor exigia que o vídeo saísse com o número exato de
  quadros previsto, e a checagem de duração logo ao lado já aceitava
  0,08s de folga — as duas discordavam. Todas as quedas registradas nos
  seus projetos foram por 1 a 3 quadros, e cada uma refazia o vídeo no
  motor lento, 3x mais devagar, sem consertar nada.
  Agora a folga de quadros sai da própria folga de duração. Vídeo cortado
  ou de outro corte continua recusado — a diferença ali é de segundos.


## 3.98

- **O corte passou a dizer onde gasta o tempo.** Ele é 30% do tempo de
  cada vídeo — 12,6 horas somadas nos seus 172 projetos — e era uma caixa
  preta: o relatório dava só o total. Agora separa extrair os trechos,
  juntar e a passada de filtro.
  Não muda nada no vídeo; muda o que dá para melhorar depois.

## 3.97

- **Busca sem resultado não diz mais que você não tem vídeos.** Era um
  defeito que a própria busca criou na 3.94: procurar algo inexistente
  mostrava "Nenhum vídeo pronto ainda" para quem tem 183 prontos.
  Agora diz *Nenhum resultado para "xyz"*, com um botão para limpar a
  busca ali mesmo.

## 3.96

- **O editor não fala mais em nome de arquivo.** Enquanto o vídeo está
  sendo cortado, a tela dizia "assim que o `cut.mp4` existir…". Agora diz
  "Ainda cortando o seu vídeo — pode fechar esta tela, o trabalho
  continua."
- Uma verificação nova impede que nome de arquivo ou de motor de render
  volte a aparecer em qualquer tela.

## 3.95

- **A conferência dos vídeos agora conserta, não só acusa.** Cada item da
  lista ganhou um **"Refazer"**: o vídeo volta para a fila e é recriado com
  o pipeline de hoje, que já corrige o que a conferência apontou.
  Pede confirmação — substitui o vídeo entregue e ocupa a fila por alguns
  minutos.

## 3.94

- **A busca acha pelo título do vídeo.** Ela olhava só o nome da pasta (um
  carimbo de data com o nome do arquivo da câmera) — digitar "lanterna" não
  achava "Celular na lanterna?", que é o que está escrito no cartão.
- **Concluídos ganhou busca.** São 183 vídeos prontos e a única forma de
  achar um era rolar a lista.
- O campo agora diz o que dá para procurar: título, arquivo ou data.

## 3.93

- **A espera de "Aplicar alterações" agora mostra quanto já andou.**
  "Redesenhando o vídeo com as suas correções… 47%" — a porcentagem vem do
  próprio desenho, quadro a quadro. É o passo mais longo da espera (80% do
  tempo) e até agora era uma frase parada.
  Não é uma previsão de quanto falta: é a conta do que já foi feito.

## 3.92

- **A espera de "Aplicar alterações" diz o que está acontecendo.** O minuto
  mais longo da espera (80% do tempo) é o redesenho do vídeo, e o que se
  lia era "Aplicando edição..." — uma frase parada que não conta nada.
  Agora: "Redesenhando o vídeo com as suas correções…".
- Tentei também mostrar **quanto falta** e o dado reprovou: mesmo em faixas
  grossas, a previsão acertava 47% das vezes. Prometer "cerca de 2 minutos"
  e levar 40 segundos é pior que não prometer nada.

## 3.91

- **Quando "Aplicar alterações" falha, agora diz o que houve e o que
  fazer.** Antes era sempre a mesma frase — "não foi possível preparar este
  corte" — sem motivo e sem saída. No seu histórico, 14 de 99 aplicações
  falharam e todas mostraram essa mesma linha.
  Cada motivo conhecido virou uma frase com o próximo passo: legenda que
  não casou com o corte novo, corte no disco diferente do que a tela
  mostra, fila cheia. O que ninguém conhece continua na frase de antes.

## 3.90

- **"Conferir os vídeos entregues"**, em Configurações. Passa uma checagem
  em todos os seus projetos e mostra o que saiu torto: trecho pedindo tempo
  que a fonte não tem, pausa sobrando dentro do corte, vídeo sem trilha.
  Leva ~11 segundos para 187 projetos.
  Era uma ferramenta que só rodava por linha de comando — e foi por ela que
  os defeitos mais caros apareceram, nenhum deles dando erro na hora.

## 3.89

- **O som da manchete estava igual em todos os estilos, e não é.** A
  **Pílula** não tem som nenhum no desenho de referência — e ganhava um. O
  **Carimbo** é um pouco mais alto que os outros — e saía igual.
- O resto do som foi conferido e está certo: cliques da legenda, risco,
  pop da bolha, whoosh do cartão de imagem e o clique do corte marcado.

## 3.88

- **Conserto de um estrago meu na 3.87.** A guarda que impedia a legenda
  desligada de ser desenhada saía do montador cedo demais e levava junto
  tudo o que vem depois: **b-roll, contador de lista, card final e o som
  dos cortes**. Valia só para quem escolhe "Nenhuma" na legenda, mas ali
  era pior que o defeito original.
- **O contador de lista foi medido pela primeira vez** e bate com o desenho
  de referência (1,077).

## 3.87

- **Escolher "Nenhuma" na legenda não tirava a legenda do vídeo.** O motor
  rápido — que desenha a maioria dos vídeos — não olhava se a legenda estava
  ligada: ele desenhava assim mesmo. A manchete e o card final sempre
  tiveram essa checagem; a legenda passou batido.

## 3.86

Quatro headlines saíam diferentes do desenho de referência. Medi as 15 e
consertei as que estavam fora:

- **Manchete**: a barra colorida ficava **fora** da tarja, à esquerda, e o
  texto ia centrado. Agora ela fica dentro, como no desenho, e o texto
  alinha à esquerda.
- **Sublinhado**: a barra ficava abaixo da linha e por cima do texto — lia
  como uma régua solta. Agora ela passa **atrás** das letras, como um
  marca-texto, e tem a espessura certa.
- **Vazado** e **Degradê na letra**: saíam com **metade** do borrão da
  sombra.

Depois: as 15 headlines dentro da faixa (0,93 a 1,10), e nenhuma das onze
que já estavam certas se mexeu.

## 3.85

- **O karaokê saía com duas legendas na tela.** Ele desenhava o estilo
  Empilhado por cima de si mesmo. Acontecia em qualquer projeto que já
  tivesse sido renderizado em Empilhado e depois trocasse para karaokê: o
  arquivo de legendas do estilo antigo ficava para trás e era desenhado
  junto. Medido: 2,557 de tinta contra o desenho de referência, agora
  **1,010** — dentro da faixa dos outros catorze estilos.

## 3.84

- **Preset que não define visual agora diz isso.** Um dos seus presets só
  guarda o tipo de conteúdo e umas opções — nenhum campo de aparência. A
  linha ficava vazia e parecia igual à de um preset completo.
- **Os registros de render passaram a ter data.** Sem ela, 416 registros
  viram um monte sem tempo: hoje 21 deles estavam com o pico de áudio acima
  do teto e não havia como saber se eram antigos (de antes do conserto que
  já existe) ou um defeito vivo.

## 3.83

- **A Bolha de conversa estava saindo sem sombra.** O borrão era calculado
  num quadro do tamanho exato do balão e ficava preso dentro dele, onde o
  próprio balão o cobre: 126 pixels de halo contra 23.279 do desenho de
  referência. Sobre imagem clara isso custa leitura, não só acabamento.
  Depois do conserto a bolha bate 0,964 com a referência (era 0,743).
- **A Bolha também estava com a letra errada** — Poppins Black (900) em vez
  do peso 400 que o navegador usa.
- **A Bolha virava Karaokê na rede de segurança.** Quando o motor rápido
  declina, o render cai numa composição que não conhecia esse estilo: o
  vídeo saía com outra legenda e nenhuma linha de aviso.

## 3.82

- **A IA passou a conhecer os estilos de legenda.** Ela nunca teve a lista:
  um pedido como "põe legenda metálica" virava um nome que não existe, e o
  vídeo saía em **karaokê** — e ainda pelo caminho lento, porque estilo
  desconhecido tira o job do motor rápido. Dois prejuízos, nenhum aviso.
  Agora ela recebe a lista, aceita o nome que aparece na tela ("Metálico")
  e recusa o que não existe, dizendo o motivo.
- **A lista de estilos passou a ter um dono só.** Ela vivia repetida em três
  arquivos; um estilo novo que esquecesse uma cópia não dava erro, só não
  acontecia.
- **A seleção múltipla se solta ao trocar de aba e ao desfazer.** Ficava
  marcada com índices antigos — e uma marca invisível apaga o item errado.

## 3.81

- **O card "Atualizações" saiu de Configurações.** A pastilha de versão na
  barra do título já checa ao abrir, avisa sozinha quando sai versão nova e
  instala no clique — o card repetia isso num lugar onde ninguém procura.
  O "Reinstalar a última versão" foi para o **Avançado**: quando não há
  atualização, reinstalar por cima é conserto, não atualização.

## 3.80

- **Vidro e Metálico refeitos.** O Vidro agora é a **letra** que é de vidro
  — 32% de transparência, o take aparece através dela, com um fio de luz na
  borda. Não há mais painel escuro atrás. O Metálico virou **prata lisa**,
  sem a faixa escura que cortava a letra no meio.
- **Ponteiro de seleção na linha do tempo (tecla V).** Arraste um retângulo
  e marque takes, legendas e blocos de uma vez; **Delete** apaga tudo junto
  e **um** Ctrl+Z desfaz o gesto inteiro. Blocos marcados se arrastam no
  tempo em conjunto.
- **A bandeira de marcar virou o marcador do CapCut.**
- **Diagnóstico aberto de cara**: a checagem roda ao abrir Configurações e o
  resultado nasce expandido em cards, com um botão só — "Checar novamente".
- **A tela de Configurações usa a largura do monitor**: em 1920px eram
  1160px de coluna e ~490px de tela vazia; agora são 1590px e 4 cards por
  linha em vez de 3.
- **Presets explicam o que são**: cada um mostra o que decide (layout,
  legenda, manchete, ritmo e cores) e o topo diz a diferença para a Marca.

## 3.79

- **Cinco estilos de legenda novos**: **Metálico** (letras cromadas, com a
  liga tirada da cor que você escolher), **Vidro** (painel de vidro fumado
  atrás do texto), **Contorno fino** (o Recorte com traço de 3px em vez de
  7px), **Moldura** (caixa alta pequena dentro de uma linha fina) e **Eco**
  (a cópia ciano/magenta deslocada). Os cinco foram conferidos quadro a
  quadro contra o desenho de referência.
- **PNG transparente não ganha mais fundo preto.** O cartão substituía o
  alpha da imagem pela máscara de canto arredondado: toda logo em PNG
  chegava ao vídeo com um retângulo preto atrás. Agora arte com
  transparência entra inteira, sem cartão, com a sombra da própria forma.
- **O botão de ajuda saiu de cima do vídeo de verdade.** Escondê-lo não
  bastava — ele voltava toda vez que a aba de Edição abria.
- **Arrastar no vídeo não dá mais play.** Mover ou redimensionar a imagem
  terminava em play no fim do gesto.
- **Player novo na Biblioteca**: play, **forma de onda** do arquivo, tempo
  e clique em qualquer lugar da linha para tocar. Saiu o controle do
  navegador espremido no canto.

## 3.78

- **Conserto do menu ⋯.** Na 3.77 abrir "Atalhos e gestos" escondia o próprio
  botão do menu — depois de um clique ele sumia do cabeçalho. Erro meu.
- **O botão do menu agora tem nome: "Mais •••"**, para ser achado.
- **O menu do Proteger fica por cima da linha do tempo.** A barra tem vidro
  fosco, e isso lhe dá um empilhamento próprio: sem z-index nela, a linha do
  tempo passava por cima do menu.

## 3.77

- **"Vídeo no fim" virou "Importar"** — e o take entra **onde a agulha
  está**: se ela cai no meio de um take, esse take é dividido e o novo entra
  entre as duas metades. Antes o vídeo importado ia sempre para o fim, que
  era a única coisa que o botão sabia fazer.
- **Só quem vai mesmo para o fim vira CTA.** Um CTA no meio do vídeo
  confundiria o planejador do próximo corte.
- **O menu do Proteger abre para baixo.** Com a janela pequena a barra fica
  colada no topo e o menu saía da tela — o primeiro item aparecia cortado.
- **O Proteger explica o que faz**: ele marca um trecho para o corte
  automático não mexer nele quando você refizer a Fase 2.
- **A ajuda saiu de cima do preview** e foi para o menu (⋯), com as outras
  ações da tela. O botão flutuante tapava o canto do vídeo — que é
  justamente onde a legenda mora.

## 3.76

- **Os botões de corte agora existem de verdade.** Na 3.75 eles saíram sem
  ícone e sem clique — só as teclas Q e W funcionavam. Foi erro meu na hora
  de aplicar a mudança.
- **Cortar vale para a imagem e o emoji selecionados**: Cortar divide o bloco
  em dois, Q encurta o começo até a agulha e W encurta o fim. Antes o app
  respondia "selecione um take" mesmo com a imagem marcada.
- **O efeito sonoro explica em vez de fingir que cortou**: ele toca inteiro a
  partir de um instante, então o que se faz é mover ou excluir.
- **A capa ficou compacta** e não estica mais a coluna da linha do tempo.

## 3.75

- **Cortar e apagar para os lados**, como no CapCut: dois botões novos na
  barra e as teclas **Q** (apaga da agulha para a esquerda) e **W** (para a
  direita). Vale no take que estiver sob a agulha, sem precisar selecionar
  antes.
- **Clicar na imagem acende o Excluir da barra** — o ✕ colado no bloco saiu
  de vez. Delete também funciona.
- **A coluna da capa ficou só com a capa**, sem o ícone de vídeo ao lado.

## 3.74

- **A Capa foi para o lugar certo**: na coluna da esquerda, logo abaixo do
  ícone da faixa de vídeo — fora da linha do tempo, como no CapCut. Na 3.73
  eu a tinha posto dentro da faixa, onde ela empurrava os clipes e virava
  mais um bloco.

## 3.73

- **A Capa foi para o começo da faixa de vídeo**, como no CapCut: ela é o
  quadro zero do que vai ser publicado, e o lugar dela é ali — não num botão
  perdido na barra. O bloco mostra a capa já escolhida.
- **O ✕ saiu da frente.** Agora você **clica no bloco para selecionar** e
  aperta **Delete**. O ✕ aparece só no bloco selecionado, onde tem espaço.
- **Marcar, Cortar e Excluir viraram ícone** (o nome fica no passar do
  mouse). Isso devolveu espaço na barra, que era o que fazia os nomes
  recolherem cedo na sua tela.

## 3.72

- **A imagem se ajusta pelos quatro lados e pelos cantos** — oito alças. Puxe
  qualquer uma e o lado oposto fica parado, como numa caixa de verdade.
- **Ela pode cobrir a tela inteira.** A proporção deixou de ser travada: como
  o cartão era 780x500 e o vídeo é 9:16, antes não existia tamanho que
  cobrisse tudo. A foto continua sem deformar — o que sobra é recorte.

## 3.71

- **Alça no canto para mudar o tamanho.** A imagem e o emoji ganharam um
  quadradinho no canto: arraste na diagonal e eles crescem ou diminuem. Só a
  roda do mouse não bastava — é um gesto que ninguém vê.
- A roda continua funcionando para quem preferir.

## 3.70

- **A imagem que você insere agora se move e muda de tamanho.** Arraste ela
  sobre o vídeo e use a roda do mouse para aumentar ou diminuir. Antes toda
  imagem entrava no mesmo cartão fixo no alto — no seu vídeo de ontem a foto
  tapava a cena e não havia como tirar do caminho.
- O cartão **nunca deforma**: a altura acompanha a largura na proporção de
  sempre. E quem não mexer continua com o cartão de antes, igualzinho.

## 3.69

- **Agora dá para pegar e apagar o som que você põe.** Clicar no bloco levava
  só a agulha para o ponto, e o ✕ ficava escondido até o mouse passar por
  cima — num bloco de meio segundo (24px) isso era alvo pequeno demais.
- O ✕ do bloco que você criou fica **sempre visível**, com área de toque
  maior que o desenho.
- **O bloco da mão também se move e se estica na Edição**, não só no Visual:
  ele nasce no relógio da Edição, que é onde você monta a linha do tempo.

## 3.68

- **Dá para tirar o que você pôs.** Passe o mouse no bloco de imagem, som ou
  emoji e clique no **✕**. Antes só o Ctrl+Z imediato desfazia: passado esse
  instante, o emoji errado ficava no vídeo.
- O ✕ só aparece no que você criou. O bloco do GANCHO não some por aí — a
  manchete se desliga no Estilo, e apagá-la com um ✕ seria surpresa demais.

## 3.67

- **A imagem que você insere não some mais no refazer.** O render reconstrói a
  pasta interna do projeto, e a imagem escolhida morava só lá: ela sumia antes
  de entrar no vídeo. Agora fica guardada fora dessa pasta e volta sozinha na
  hora de renderizar. Vale também para o som que vem da sua Biblioteca.
- Provado num vídeo de ponta a ponta: emoji na tela, cartão da imagem no lugar
  certo e o efeito sonoro 7 dB acima do mesmo trecho sem ele.

## 3.66

- **A manchete se troca na própria linha do tempo.** Clique no bloco GANCHO e
  abre uma janela com o texto atual — antes o clique levava você para editar
  dentro do vídeo, o que dava no mesmo que não editar ali.
- **Somar coisas ficou na linha do tempo.** Embaixo das faixas agora tem
  **+ imagem ou vídeo · som · emoji · legenda**, e tudo entra na posição da
  agulha. Antes cada um estava num canto diferente da tela.
- **Dá para ouvir o som antes de pôr** (▶ no cartão) e **a roda do mouse sobre
  o bloco de som muda o volume** — que era fixo em 50%.

## 3.65

- **O bloco GANCHO agora aparece na Edição** — e é lá que você estava. Na 3.58
  eu liguei o clique, mas desenhei o bloco só no Visual: continuava sem dar
  para trocar a manchete pela linha do tempo na tela onde você trabalha.
- Vale também em vídeo **sem legenda**: a faixa do gancho não depende dela.

## 3.64

- **O emoji se arrasta na tela.** Pegue e leve para onde quiser sobre o vídeo
  — antes ele nascia no centro-alto e ficava lá, mesmo tapando o rosto de
  quem fala. A **roda do mouse** sobre ele muda o tamanho.
- A posição e o tamanho vão junto no Salvar, e são exatamente os que o vídeo
  vai usar.

## 3.63

- **Você vê o emoji e a imagem antes de renderizar.** O que você põe à mão
  agora aparece sobre o vídeo na hora, na posição e no tamanho exatos do
  render — antes era preciso aplicar e esperar o vídeo para descobrir que o
  emoji estava tapando o rosto.
- O efeito sonoro fica de fora da prévia de propósito: som não se vê, e um
  ícone dele só taparia a imagem.

## 3.62

- **"Aplicar alterações" passou a levar a mídia que você põe à mão.** Imagem,
  efeito sonoro e emoji só entravam no vídeo pelo "Refazer a Fase 2"; quem
  aplicasse — que é o botão natural depois de mexer na linha do tempo —
  recebia o vídeo sem eles, sem aviso.
- Aplicar duas vezes **não duplica**: a mesma imagem não entra de novo.

## 3.61

- **Emoji na mão.** Leve a agulha ao ponto, abra o seletor de mídia e vá na
  aba **Emoji**: o escolhido entra grande na tela e fica 1,6s. O bloco é
  arrastável na linha do tempo, junto da manchete.
- Ele **não** entra como foto de propósito: uma foto vira cartão no meio da
  tela, e o emoji tem que ficar solto sobre o vídeo.

## 3.60

- **Efeito sonoro na mão.** Leve a agulha até o ponto, abra o seletor de mídia,
  aba **Biblioteca**, e escolha um som da sua pasta **Efeitos**: ele vira um
  bloco na faixa de som da linha do tempo e toca ali no vídeo. O bloco é
  arrastável; o que vale é o começo, porque o efeito toca inteiro.
- **Som deixou de aparecer como cartão quebrado** no seletor — ele tentava
  mostrar uma miniatura de um .mp3. Agora tem cartão próprio.
- **Trilha ficou de fora do seletor** de propósito: música de fundo dura
  minutos e se escolhe no estilo, não como bloco na agulha.

## 3.59

- **A mídia que você põe à mão agora aparece no vídeo.** A tela sabia inserir
  imagem na agulha desde sempre e guardava o pedido — mas o app nunca lia esse
  pedido na hora de renderizar: a imagem era salva e sumia, calada. Agora ela
  entra no vídeo, e sobrevive ao estilo "Limpo" (quadro cheio dispensa b-roll
  *automático*; o que você pediu não é automático).
- **Se um arquivo não estiver na pasta do projeto, o card avisa** em vez de
  deixar o vídeo sair sem ele.
- **Efeito sonoro na mão: o motor já toca.** Os dois motores passaram a
  entender um efeito posto num instante (`sfxManual`). Falta o seletor na
  tela — vem na próxima.

## 3.58

- **A manchete se edita pela linha do tempo.** Clique no bloco **GANCHO** e o
  editor abre — antes era preciso achar a manchete sobre o vídeo, no quadro
  certo. Arrastar o bloco continua movendo, sem abrir o editor.
- **Mídia na agulha também na tela de Edição.** O botão de imagem só
  funcionava no Visual; agora entra pela Edição, que é onde você monta a
  linha do tempo. Vale imagem, clipe da Biblioteca ou arquivo seu, e o bloco
  entra na posição da agulha, arrastável. Na Edição aparece só o que você põe
  à mão: os inserts que a IA colocou seguem no Visual, porque o relógio deles
  é o do vídeo final.

## 3.57

- **Escrever legenda na mão.** Leve a agulha até um trecho sem legenda e
  clique em **+ escrever legenda** (a pastilha ao lado da headline): você
  escreve o texto e ele entra na linha do tempo como qualquer outra legenda —
  mesmo desenho, mesmas quebras, mesmo realce. Serve para b-roll, fala baixa
  ou uma frase que ninguém falou. Se o trecho já tiver legenda, ele avisa em
  vez de escrever por cima.
- **A nota do corte aparece no card.** A nota (gancho, clareza, ritmo, CTA) e
  a dica mais útil dela existiam só no painel do preview; agora vêm na ficha
  do vídeo, onde você já olha a fila.

## 3.56

- **As dicas da nota agora dizem onde e quanto.** Passei os 185 vídeos já
  entregues e vi a mesma frase genérica repetida: "a abertura está longa ou
  curta demais" saiu em 103 deles, sem dizer para que lado nem de quanto.
  Agora sai *"A abertura tem 9,0s — corte antes: as primeiras falas prendem
  melhor entre 1,5 e 3,5s"*. O trecho longo do meio diz **qual** trecho e em
  que minuto ele começa; o fechamento e as pausas dizem o tamanho e a
  quantidade.

## 3.55

- **O preview mostra o layout escolhido.** Degradê, Vinheta, Cinema e Borda da
  marca agora aparecem por cima do vídeo na hora em que você clica — antes o
  cartão era a única pista e você só via o resultado depois do render. Os
  layouts que mexem no enquadramento (Moldura, Barra inferior, Fundo
  desfocado) continuam sem prévia de propósito: imitá-los por aqui mentiria
  sobre o corte.
- **A ficha passa a registrar o áudio do vídeo entregue.** Quando o motor
  rápido é reprovado e o vídeo é refeito, o pico registrado era o da
  tentativa, não o da entrega — um vídeo entregue em −1,3 dBTP ficava gravado
  como −0,7.

## 3.54

- **As quatro cores voltaram a caber numa fileira.** Na 3.52 eu medi pela
  largura da coluna (906px), mas quem manda é a grade dentro do bloco Visual,
  que recebe 840 — na sua tela a fileira quebrava em 3+1. O cartão agora
  encolhe até 201px sem cortar nada.
- **Todo estilo mostra o nome.** Com 15 headlines e 11 legendas, cartão sem
  nome vira adivinhação: não dava para pedir "usa o Vazado" nem achar de novo
  o que você tinha gostado. Antes só os desenhos de layout tinham rótulo.

## 3.53

- **Três layouts de vídeo novos.** *Vinheta* (bordas escurecidas, o rosto
  ganha foco), *Cinema* (as duas tarjas pretas) e *Borda da marca* (moldura
  fina na sua cor). Os três são tinta por cima do quadro cheio, de propósito:
  assim o render continua no motor rápido, ao contrário de Moldura, Barra
  inferior e Fundo desfocado, que obrigam o caminho lento.
- **Cinco estilos de headline novos.** *Faixa cheia* (a faixa corta a tela de
  ponta a ponta), *Fita* (as caixas tortas), *Neon* (letra branca com brilho
  da sua cor), *Vazado* (caixa cheia com a letra recortada — o vídeo aparece
  dentro dela) e *Degradê na letra* (branco em cima, sua cor embaixo).
- **O "Degradê" voltou a acontecer.** O motor rápido — que faz cerca de 18 de
  cada 20 renders — nunca olhou o layout escolhido: quem marcava Degradê
  recebia o vídeo sem degradê nenhum, sem aviso. Agora os dois motores
  desenham a mesma coisa, conferido quadro a quadro.

## 3.52

- **As quatro cores do estilo ficam lado a lado.** Cor da headline, de ênfase,
  da legenda e do círculo ocupavam uma faixa da tela inteira cada uma, com
  duas bolinhas no canto e o resto vazio. Agora são quatro cartões numa
  fileira só; em janela estreita a fileira vira 2x2 sozinha.
- **"Traço da ênfase" foi para junto do Estilo de legenda.** É a palavra
  realçada da legenda que recebe o risco — e, dentro do cartão de cor, ele
  deixava aquele cartão mais alto que os outros três.

## 3.51

- **Os nomes dos botões voltaram.** Na 3.50 o rótulo era a primeira coisa a
  sair quando faltava espaço — e, com a tela em 125%, a barra virava uma
  fileira de símbolos. Agora o nome é a **última** coisa a sair: primeiro
  some a régua do zoom, depois o texto fica mais junto, depois os botões
  − e +; só numa janela menor que qualquer tamanho de uso é que sobra só o
  ícone. Com nomes a barra pede 1118px e agora cabe em 830.
- **O "fit" virou ícone.** Era a única palavra em inglês da barra. A função é
  a mesma (ajustar à janela) e o nome aparece ao passar o mouse.

## 3.50

- **A barra do preview cabe numa linha só.** Ela quebrava em duas fileiras e o
  zoom caía sozinho embaixo. Agora é uma linha; quando a janela aperta, os
  botões secundários viram só ícone (o nome continua no passar do mouse) em
  vez de sumir para fora da tela.
- **Fim do "IN" e do "OUT".** O botão de marcar um trecho agora diz **Marcar**
  e, com o trecho aberto, **Até aqui** — o mesmo que ele faz, sem nome de
  ilha de edição. O texto de ajuda do **M** mudou junto.
- **Fonte sem acento não passa mais calada.** Se a fonte que você escolher não
  desenhar Á, Ç, Ã ou "!", o card avisa antes: fonte de demonstração costuma
  carimbar "DEMO" no lugar do acento, e isso só apareceria no vídeo pronto.
  Testado na Integral CF demo (carimba todos) e nas 15 fontes do app (nenhum
  alarme falso).

## 3.49

- **Os ajustes da headline ficam junto dela.** "Onde a headline fica", "Legenda
  começa" e "Headline fica na tela" estavam no bloco Conteúdo, várias telas
  abaixo — quem escolhia o estilo da headline no Visual não os encontrava.
  Agora aparecem logo abaixo dos modelos de headline.

## 3.48

- **Estilo novo: "Abertura em cheio".** A headline abre no centro da tela e
  fica sozinha nos primeiros segundos; a legenda só começa quando ela sai.
  Está pronto como modelo em Estilos, e os dois controles também ficaram
  soltos para você combinar do seu jeito: "Onde a headline fica" (no alto ou
  no centro) e "Legenda começa" (junto com a fala ou depois da headline).
- **As janelas feias do navegador saíram.** Criar preset, renomear, apagar,
  editar a headline e publicar no Instagram abriam a caixa do Chrome, com o
  "127.0.0.1 diz" em cima. Agora são janelas do próprio app, no tema.

## 3.47

- **A tela de estilo do vídeo agora mostra de qual marca ele é — e deixa
  trocar.** Um vídeo sai com a marca que estava ativa na hora em que você
  importou; se você trocar de marca depois, o vídeo antigo continua com a
  anterior e não havia como perceber antes de renderizar. Agora aparece
  "Marca deste vídeo" no topo, com a lista das suas marcas: escolher outra
  troca as cores e o texto do card final ali mesmo, e "Salvar e refazer a
  Fase 2" refaz o vídeo com ela — sem reimportar nada.

## 3.46

- **Trocar a categoria de um arquivo na Biblioteca voltou a funcionar.** Dava
  "unknown route": a tela chamava uma rota que o app não repassava. Pelo
  mesmo motivo, a barra de progresso da atualização (3.45) também não teria
  funcionado — as duas foram corrigidas, e agora um teste confere todas as
  rotas de uma vez.
- **O yt-dlp saiu do produto.** Ele só serviria para editar a partir de um
  link, coisa que o app não faz, e o diagnóstico ficava acusando falta dele
  em toda instalação.

## 3.45

- **A atualização agora mostra a barra de progresso.** Você clica, vê o
  download enchendo (com os MB), depois "Instalando…" — e o app só fecha no
  fim, na hora de reabrir. Antes ele sumia na hora e você ficava sem saber
  se estava acontecendo alguma coisa.
- **As caixas de seleção pararam de abrir brancas no tema escuro.** A lista
  do menu é desenhada pelo Windows, não pelo app, e faltava dizer a ele que
  o tema é escuro. Aproveitei e deixei todas com a mesma altura, o mesmo
  canto e a mesma seta — eram quatro estilos diferentes espalhados.
- **A tela de Configurações ficou alinhada.** Os cartões da mesma linha
  agora têm a mesma altura, com os botões no rodapé; a última linha não
  estica mais os cartões; e a barra "Avançado" termina na mesma linha que
  eles.

## 3.44

- **O aviso de versão nova agora mostra o que muda.** Em vez de só "Nova
  versão disponível", a janela lista as primeiras novidades da versão —
  assim dá para decidir se vale atualizar agora sem abrir o site.
- Esta é a versão para testar o atualizador de um clique da 3.43: estando na
  3.43, atualizar para cá não passa por nenhuma tela do instalador.

## 3.43

- **Atualizar virou um clique.** O aviso de versão nova agora aparece
  sozinho ao abrir o app (uma vez por versão — quem diz "agora não" só é
  perguntado quando sair outra), e a instalação roda em silêncio: acabaram
  as telas de idioma, pasta, avançar e concluir. O único clique que sobra é
  a autorização do Windows. O app fecha, atualiza e reabre sozinho.
- Quem abrir o instalador na mão também não é mais perguntado sobre idioma,
  e a pasta só é perguntada na primeira instalação.

## 3.42

- **Quando a importação falha, o app diz por quê.** Antes, qualquer causa
  mostrava a mesma frase ("não consegui ler nenhum vídeo desse envio").
  Agora vem o motivo: envio interrompido no meio, arquivo que não é vídeo
  (com a extensão), ou arquivo que não está mais no disco.
- **E fica registrado.** Cada tentativa de importação grava uma linha em
  `Projetos/.ativavid/import-log.jsonl` com a hora, os nomes dos arquivos,
  os tamanhos e o desfecho. Só isso — nada do conteúdo dos vídeos. Assim,
  se der erro de novo, dá para saber o que aconteceu sem depender de
  reproduzir na hora.

## 3.41

- **"Transcrição ruim ou vazia" agora diz o que está errado.** Antes, três
  vídeos parados na Fila mostravam a mesma frase — "confira o áudio" — com
  causas diferentes. Agora o app mede o áudio e conta: *"o áudio está quase
  mudo (volume médio -53 dB, pico -33 dB — fala normal fica perto de -20
  dB). Confira se o microfone gravou."* ou *"o vídeo tem só 3s e quase
  nenhuma fala — curto demais para virar um corte."*

## 3.40

- **As chaves passam a ser lidas de onde a tela de Integrações grava.**
  Cinco partes do app (trilha da ElevenLabs, busca de imagens do Pexels e do
  Google, b-roll e transcrição) procuravam a chave só numa pasta que, numa
  instalação normal, nem existe — funcionavam apenas porque o app repassava
  a chave ao abrir. Quando esse repasse falha, o sintoma é mudo: o vídeo sai
  sem música e a ficha diz "geração falhou", mandando você conferir uma
  chave que está certa.

## 3.39

- **A Biblioteca avisa quando os takes guardados não vão entrar no vídeo.**
  No estilo com quadro limpo e b-roll em "Quando necessário" — que é o
  padrão — o app não insere nada, de propósito. Quem guardasse takes só
  descobriria isso depois do vídeo pronto. Agora a aba Vídeos diz na hora
  que eles não vão entrar e o que mudar em Estilos para usá-los.

## 3.38

- **Vídeo com take de apoio voltou a usar o renderizador rápido.** Desde que
  os takes de vídeo passaram a entrar (3.34), esses vídeos caíam no
  renderizador antigo: no mesmo vídeo de teste, 217 segundos contra 69 — e é
  o caminho onde um render já morreu por causa de um quadro lento. Agora o
  renderizador rápido desenha o take direto no cartão.
- O take entra no cartão do mesmo jeito de antes (mesmo enquadramento, mesmo
  arredondamento) e, se ele for mais curto que a janela, congela no último
  quadro em vez de piscar.

## 3.37

- **Render não morre mais porque a máquina estava ocupada.** Havia um prazo
  de 30 segundos por quadro: se um único quadro demorasse mais que isso —
  o que acontece quando você está com o Chrome e outros programas abertos e
  o vídeo é 4K — o render inteiro era perdido, depois de minutos de
  trabalho. O prazo subiu para 2 minutos por quadro. Render saudável não
  fica mais lento com isso; só muda quanto tempo o app espera antes de
  desistir.

## 3.36

- **Trecho que pede um pedaço que o arquivo não tem agora é barrado — e
  aparece na ficha.** Esse tipo de erro nunca deu mensagem: o vídeo saía
  "pronto", com um pedaço mudo e travado, e a culpa parecia ser da gravação.
  Foi o que aconteceu no seu vídeo de 3 partes. A causa daquele caso já foi
  corrigida na 3.35; esta versão fecha a porta para a família inteira do
  problema, venha o engano de onde vier.
- O trecho que passa do fim do arquivo é aparado; o que está inteiro fora é
  removido; e a ficha do vídeo passa a dizer, em uma linha, quantos trechos
  foram tirados e de qual arquivo.

## 3.35

- **Vídeo em várias partes: consertado o corte que ficava mudo e travado.**
  Quando o nome do arquivo tinha espaço (`Parte 1.mov`), o app trocava as
  falas de um take pelas de outro — e montava o corte pedindo pedaços que
  não existem naquele arquivo. Resultado: só a primeira parte tinha som, a
  segunda travava no meio e a agulha do preview não chegava no fim, porque a
  timeline ficava com o triplo da duração real. No seu vídeo de 3 partes:
  eram 12 trechos pedindo tempo inexistente; agora são zero.
- **O take agora entra na hora da palavra que ele ilustra.** Antes o app
  pegava as três palavras mais repetidas do vídeo inteiro e espalhava os
  takes em fatias iguais — o take caía em qualquer lugar menos no momento
  da piada. Agora ele procura, na fala, a palavra que está no nome do
  arquivo e entra logo depois dela. Um take chamado
  `humor--cavalo-patada.mp4` entra quando você diz "patada".
- Quem manda é o **nome do arquivo**, não a categoria: a categoria diz o
  papel do take (humor, meme, CTA) e serve para você achar na Biblioteca; o
  nome diz o que o take mostra e é o que casa com a fala. Vale nomear
  descrevendo: `cavalo-patada`, `celular-quebrado`, `cliente-feliz`.
- Dois takes nunca entram colados (folga de 2,6s), e take que não casa com
  nada continua entrando espaçado, como antes — o b-roll não some só porque
  o nome não bateu.

## 3.34

- **O b-roll estava procurando a sua biblioteca na pasta errada — e por isso
  nunca usava nada dela.** Seus projetos ficam no E: (a pasta do C: é só um
  atalho), mas a busca de imagens olhava uma pasta Biblioteca vazia no C:.
  Nenhuma foto sua jamais foi encontrada. Agora ele lê a biblioteca de
  verdade. (Era o mesmo engano que a versão 3.03 corrigiu na trilha e que
  tinha ficado aqui.)
- **Os vídeos da Biblioteca agora entram no vídeo como take de apoio.** Antes
  o app aceitava só foto: o clipe era descartado sem avisar. Agora o take
  toca no cartão, sem som (para não passar por cima da sua fala), com até
  2,5s de janela — foto continua com 1,6s, porque uma ação precisa de tempo
  para ser lida.
- Nesses vídeos o app usa o renderizador antigo, que é mais lento, e diz isso
  no log em vez de entregar o vídeo sem o take.
- **Para usar isso**: em Estilos, o b-roll precisa estar em "Sempre" ou
  "Raro". No padrão ("Quando necessário") com o layout limpo, o app não
  insere nada — é o talking-head limpo de sempre.

## 3.33

- **Só um som toca por vez na Biblioteca.** Dar play numa trilha pausa a que
  estava tocando — antes três ficavam tocando por cima uma da outra e não
  dava para comparar duas músicas.
- **Aba de Vídeos.** Os takes de apoio saíram de dentro das imagens e ganharam
  acervo próprio, com categorias que dizem o PAPEL do take: viral, meme,
  humor, reação, CTA, abertura, transição, produto, bancada. É por aí que
  você acha o take na hora — "deu uma patada" → humor. Cada take toca na
  própria tela, para você lembrar o que é antes de classificar.
- **Nenhuma pausa morta sobrevive ao corte, venha ela de onde vier.** A 3.32
  consertou as pausas que voltavam quando a IA mandava manter uma frase
  inteira; sobrava um segundo caminho — o trecho que a IA pede e que o app
  aceita inteiro nunca era dividido. Agora a regra vale para qualquer trecho
  nos modos que cortam. Medido em 6 vídeos seus: **os 2,1s que ainda
  sobravam foram a zero**, e num render completo do vídeo que mais sofria o
  resultado foi zero pausa, zero take baixo e zero emenda estourada.

## 3.32

- **As pausas mortas que sobravam no meio do vídeo sumiram.** Quando a IA
  pedia para manter uma frase inteira, o app devolvia o trecho junto com as
  pausas de dentro — e depois avisava você, na ficha do vídeo, sobre essas
  mesmas pausas. Eram três medidas discordando: o corte tira pausa a partir
  de 0,4s, o aviso acusa a partir de 0,4s, mas a restauração colava tudo que
  fosse menor que 0,8s. Agora as três combinam.
- Medido em 6 vídeos seus: **11,2s de silêncio morto viraram 2,1s**. Num
  deles (o mesmo vídeo renderizado dos dois jeitos) foram 3 pausas somando
  1,6s para nenhuma, com o vídeo saindo 2,4s mais curto e sem nenhuma emenda
  estourada.
- O preço é ter mais pontos de corte — o vídeo fica mais seco e mais rápido.
  Nos vídeos que já não tinham pausa sobrando, nada muda.

## 3.31

- **A Biblioteca foi refeita: cada acervo tem a sua aba.** Imagens, trilhas
  sonoras e efeitos sonoros estavam na mesma tela, um embaixo do outro — com
  171 trilhas, achar qualquer coisa virava rolagem. Agora são três abas com
  a contagem de cada uma.
- **Categorias viram filtro.** Cada aba mostra as categorias com quantos
  arquivos tem em cada, e a lista fica agrupada por categoria. Nas trilhas,
  cada grupo diz o clima que o app usa para escolher a música (agitado,
  médio, calmo).
- **Dá para trocar a categoria de um arquivo pela tela.** Isso muda de
  verdade em que vídeo ele pode entrar — a categoria é o começo do nome do
  arquivo, que é o que o app lê na hora de escolher a trilha.
- **Os efeitos sonoros do app agora aparecem e tocam na tela**, cada um
  dizendo onde é usado (o clique de cada palavra da legenda, o risco da
  ênfase, o whoosh da manchete). Quatro deles não são usados por nada hoje e
  estão marcados assim.
- **E você pode trocar um efeito pelo seu.** A categoria do efeito é a vaga
  que ele ocupa: um arquivo em `whoosh` entra no lugar do whoosh nos
  próximos vídeos. Vale para clique, risco, pop, corte e whoosh.

## 3.30

- **No preview, o círculo de ênfase não fechava.** O laço parava no meio do
  arco de baixo e ficava aberto — só no preview: o vídeo final sempre saiu
  com o laço fechado. Ou seja, o que você via ao editar não era o que ia
  para o vídeo. Agora os dois fecham (medido: a sobreposição entre o preview
  e o vídeo subiu de 0,66 para 0,92 do desenho).
- **O marca-texto sumia depois de entrar.** No estilo marca-texto, a faixa
  amarela era desenhada só durante a animação de entrada e depois
  desaparecia — a palavra ficava sem realce pelo resto da legenda. Agora ela
  entra e fica, e bate exatamente com o preview (a faixa começa e termina
  nos mesmos pixels em todos os quadros conferidos).
- **E a faixa do marca-texto estava 130 pixels mais estreita** que a do
  preview (65 de cada lado). A ponta arredondada dela é esticada junto com
  o desenho, virando uma elipse — nós desenhávamos um círculo. O erro caiu
  para 2 pixels.
- **O círculo de ênfase volta ao tamanho que tinha até a 3.28.** A mudança
  de tamanho da 3.29 estava errada e foi desfeita. O que enganou a medição:
  no preview o arco de baixo do laço passa ATRÁS das letras e não aparece,
  então comparar a base visível dava 36 pixels de diferença que não existem.
  Medindo as PONTAS do laço, que o texto não cobre, os dois motores batem
  (1281 e 1258 contra 1281 e 1256 do preview). O tamanho de sempre estava
  certo. A suavização melhor da 3.29 continua.

## 3.29

- **O risco de ênfase voltou ao tamanho do desenho original.** (Este item estava errado e foi desfeito na 3.30.) Desde que o
  renderizador próprio entrou (20/08), o círculo saía 33% mais alto e 36
  pixels mais baixo que o projetado — e como ele desenha quase todos os
  vídeos, era o que aparecia em quase todos. Medido quadro a quadro contra
  o preview: agora o topo bate exatamente e a base fica dentro de 4 pixels.
- **E ficou mais liso**: a suavização subiu para o nível do preview também
  nas partes inclinadas do laço (0,239 contra 0,241 do navegador; antes do
  conserto de ontem era zero).

## 3.28

- **O traço de ênfase (o círculo e o marca-texto) saiu do serrilhado.** Ele
  era desenhado sem suavização e a borda ficava em degraus — visível porque
  o círculo é uma elipse deitada. Agora é desenhado em resolução maior e
  reduzido, com a mesma suavidade do preview do navegador (medido: 541
  pixels de transição contra 649 do navegador; antes eram zero). Sem custo
  de tempo no render.

## 3.27

- **Um vídeo não quebra mais por causa de sobra de outro.** Quando a pasta
  de trabalho do render não conseguia ser apagada (acontece com dois vídeos
  processando ao mesmo tempo), o vídeo seguinte morria na hora de montar os
  gráficos. Agora a sobra é limpa peça por peça e o render segue.

## 3.26

- **O plano B da IA não some mais dependendo de como o app foi iniciado.**
  A chave do Groq (usada quando a IA principal responde algo ilegível) só
  era procurada no ambiente do processo; agora também é lida do seu arquivo
  de chaves. Sem isso, um vídeo podia sair "sem IA" com a chave certa
  guardada.
- **A espera pela IA local de música cabe no prazo do vídeo**: antes ela
  podia passar do tempo que o render aguarda e o esforço era jogado fora
  bem quando o motor ia liberar.

## 3.25

- **O aviso de pausa volta a aparecer em "Edição leve" e "Vídeo completo".**
  A 3.17 calou os dois junto com "Sem cortes", mas esses dois modos cortam
  silêncio — neles, pausa sobrando é defeito do corte, e era justamente o
  único defeito que a Edição leve consegue produzir.
- **A IA local de música espera a vez.** Com dois vídeos processando ao
  mesmo tempo, o segundo desistia cedo e pegava trilha da biblioteca; agora
  ele aguarda o motor liberar (uma composição leva ~90s).
- **O card diz por que a trilha veio da biblioteca** — "outro vídeo ocupou o
  motor", "a máquina não tinha folga de memória" ou "o motor não está
  instalado" — em vez de acusar uma falha genérica da IA.

## 3.24

Uma auditoria completa das versões 3.15 a 3.23 encontrou defeitos que os
testes não pegavam. Os que mais importam:

- **Correções feitas no editor voltavam atrás.** Desde a 3.18, um erro de
  indentação fazia todo vídeo de fonte única passar pelo caminho de "vários
  takes": o corte que você salvou no preview era reprocessado por cima (o
  trecho de gancho removido voltava) e o título podia mudar sozinho a cada
  reprocesso.
- **A Fila podia ficar em branco.** Um trecho em silêncio absoluto gravava
  um número infinito no diagnóstico do corte, e a lista inteira de vídeos
  parava de carregar por causa de um único projeto.
- **O nivelamento de volume errava o alvo em vídeos com vários takes**:
  media cada trecho contra a voz do primeiro take, podendo estourar o
  volume do trecho errado. Agora cada take é medido contra ele mesmo.
- **Instalação da IA de música interrompida ficava "pronta" para sempre**,
  sem botão de reparo e sem nunca compor. Agora o app reconhece a
  instalação pela metade e oferece continuar de onde parou.
- **Apagar um trecho com o vídeo tocando podia apagar o trecho errado**: a
  timeline rolava sozinha durante o arrasto. E clicar num trecho já
  removido não joga mais a reprodução para frente.
- Miudezas: aviso de "voz mais baixa" não aparece mais para trecho mudo, o
  painel Agora não perde a rolagem, o progresso da instalação sobrevive a
  uma falha de rede, e nada de janelas de comando piscando na tela.

## 3.23

- **A IA local de música agora se instala pelo aplicativo.** Em
  Configurações → Música dos vídeos aparece o estado (instalada, não
  instalada ou indisponível por falta de placa NVIDIA) e um botão que baixa
  as 4,8 GB uma única vez, com barra de progresso — o download acontece em
  segundo plano e nunca no meio de um vídeo. Antes, esse motor só existia
  se alguém o montasse à mão.

## 3.22

- **Dá para posicionar a agulha clicando no próprio take.** Depois do
  primeiro corte, os takes cobrem a linha do tempo inteira e só a régua fina
  do topo movia a agulha — mas o botão Cortar exige a agulha dentro do take,
  então cortar de novo virava um exercício de mira. Agora clicar (ou
  arrastar) sobre o take leva a agulha junto, e o take continua sendo
  selecionado como antes.

## 3.21

- **Cards do mesmo tamanho de novo.** Com vários avisos preenchidos (corte,
  trilha, marca, IA), a ficha esticava o card até quase o dobro da altura e
  a lista de Recentes virava uma escada. Cada informação agora ocupa no
  máximo duas linhas — o essencial vem no começo da frase, e o texto
  completo aparece ao passar o mouse.

## 3.20

- **O botão "..." dos cards voltou ao lugar.** A nota da trilha trazia o
  nome do arquivo — uma palavra longa sem espaços, que não quebrava linha e
  esticava o card até empurrar o menu (apagar, abrir pasta) para fora. Agora
  a ficha quebra textos longos, e a nota diz o que interessa: "Trilha da sua
  biblioteca (anúncio)" em vez do nome do arquivo.

## 3.19

- **"O que saiu do corte" agora vem fechado.** Aberto, ele ocupava meia
  tela (15 linhas num vídeo normal) e empurrava a timeline e a legenda para
  baixo. Um clique no título abre quando você quiser conferir, e a escolha
  fica lembrada enquanto o app estiver aberto.

## 3.18

- **Fim do trecho que soa mais baixo no meio do vídeo.** O app reforçava só
  as falas bem abaixo da média — e o próprio reforço deixava as vizinhas
  para trás, fazendo um trecho normal parecer abafado. Agora, depois de
  decidir os cortes, ele nivela: quem ficou mais de 5 dB abaixo dos outros
  recebe um complemento (com o mesmo teto de sempre). Num vídeo real, o
  pior desnível caiu de 6,3 dB para 2,1 dB e os avisos de revisão zeraram.

## 3.17

- **O aviso de pausa no corte agora respeita o modo escolhido.** Em "Sem
  cortes", "Vídeo completo" e "Edição leve" as pausas são o que você pediu
  — o card parou de marcá-las como problema (o primeiro vídeo real a
  receber o aviso era justamente um "Sem cortes"). Nos modos que cortam, o
  aviso continua; e voz mais baixa que o resto continua sendo apontada em
  qualquer modo, porque isso é defeito em todos.

## 3.16

- **O painel "Agora" mostra a fila inteira.** Ele listava só três e resumia
  o resto em "+2 na fila" — justamente quando você manda vários vídeos de
  uma vez é que quer ver todos. Agora aparecem todos, com a contagem no
  título, e a lista rola dentro do próprio painel para não empurrar o
  restante da tela.

## 3.15

- **O card agora avisa o que sobrou no corte.** O app sempre conferiu o
  corte pronto (pausa morta, trecho com voz mais baixa, emenda estourada) e
  jogava o resultado fora no fim do render. Agora a ficha mostra, por
  exemplo, "2 pausas somando 1,3s (a 1ª aos 0:22) · 1 trecho com a voz 9 dB
  mais baixa" — com o minuto, para você ir direto ao ponto no editor. Só
  aparece quando incomoda de verdade (0,8s de pausa ou 6 dB de queda).

## 3.14

- **O diagnóstico parou de acusar chave que existe.** "Rodar checagem"
  dizia "Sem chave da ElevenLabs" e "Sem chave da Pexels" mesmo com as duas
  configuradas e funcionando: ele procurava as chaves na pasta do programa,
  não onde a tela de Integrações as grava. Acontecia em toda instalação.

## 3.13

- **O aviso não cobre mais as abas na tela de edição.** Ali o cabeçalho é
  mais alto que no painel, e o aviso (que subiu para o topo na 3.10) caía
  em cima de Edição / Estilo / Visual. Agora ele se posiciona logo abaixo
  do cabeçalho de verdade, mesmo quando ele quebra linha em tela estreita.

## 3.12

- **A trilha da IA local não segura mais o render.** Em teste de render
  completo, o vídeo esperava até 2,5 minutos pela música: quando a máquina
  estava apertada, o motor adiava o começo e só compunha no fim. Agora ele
  reaproveita a folga de memória assim que ela aparece — a espera caiu para
  ~28 segundos — e tem prazo máximo: se travar, o vídeo sai com trilha da
  Biblioteca em vez de ficar parado.

## 3.11

- **Atualizar é sempre dentro do app, por qualquer caminho.** A pastilha de
  versão na barra de título ainda abria o navegador (a correção da 3.08 só
  pegou o botão de Configurações, porque a lógica estava copiada em três
  lugares). Agora as três portas chamam o mesmo instalador interno.
- O botão "Baixar pelo navegador" saiu da janela de aviso. O navegador
  continua sendo a rede de segurança silenciosa: só entra se o download
  dentro do app falhar.

## 3.10

- **Os avisos agora aparecem no topo, no centro da tela**, com cara de
  cartão de notificação (ícone, borda de destaque e entrada animada). No
  rodapé eles passavam despercebidos justamente quando importavam — chave
  salva, motor trocado, erro do servidor.

## 3.09

- **Cada vídeo ganha uma trilha com timbre próprio.** O pedido de música
  antes era um texto fixo por tipo de vídeo, e vídeos do mesmo tipo saíam
  com a mesma "banda". Agora cada projeto sorteia instrumento em destaque,
  textura e um ajuste de andamento — o clima continua o mesmo, muda a
  roupa. O sorteio é fixo por projeto, então refazer a Fase 2 continua
  reaproveitando a trilha em vez de gerar (e cobrar) outra.

## 3.08

- **Atualizar não abre mais o navegador.** Em Configurações → Atualizações,
  o botão agora baixa o instalador e o executa dentro do app (o ATIVAVID
  fecha e reabre sozinho), como a janela de aviso já fazia. O navegador só
  entra se o download falhar.

## 3.07

- **Toda trilha gerada passa a ficar guardada na Biblioteca**, com a
  etiqueta do tipo do vídeo (`viral--`, `humor--`…) e a marca de quem
  compôs (`ia` para o ElevenLabs, `mg` para a IA local). A cada vídeo o
  acervo cresce — e é dele que sai a música quando as duas IAs falham.
  Trilha reaproveitada ou que já veio da Biblioteca não vira cópia.

## 3.06

- **A IA local de música agora cede a vez para o render.** Compor uma trilha
  custa ~4GB de memória e metade da placa de vídeo; se a máquina estiver
  apertada, ou a placa ocupada, ou outro vídeo já estiver compondo, o motor
  desiste na hora e a música vem do ElevenLabs ou da sua biblioteca — o
  render nunca fica mais lento por causa da trilha.

## 3.05

- **Você escolhe quem compõe a música** em Configurações → Música dos vídeos:
  *IA local primeiro* (grátis, não gasta créditos, a nuvem fica de reserva),
  *Nuvem primeiro* (ElevenLabs, como antes) ou *Só a nuvem*. Em qualquer
  opção, a biblioteca de trilhas fecha a fila.

## 3.04

- **Motor local de música (MusicGen).** Quando o ElevenLabs falha, a IA
  local compõe a trilha DESTE vídeo na GPU, com o mesmo clima que o
  ElevenLabs receberia — na RTX 3050, 30s em ~67s, rodando em paralelo com
  o preparo do vídeo. A ordem agora é: ElevenLabs → motor local →
  biblioteca de trilhas. O motor é opcional (pasta `MotorMusica` ao lado da
  `Biblioteca`); sem ele instalado, nada muda e nada pesa na instalação.

## 3.03

- **As trilhas do plano B apareciam vazias quando os Projetos moram em outro
  disco.** Com `Projetos` sendo um atalho (junction) para outro drive, o
  pipeline procurava as músicas na biblioteca errada. Agora a pasta de
  trilhas vem da mesma raiz que a tela Biblioteca usa.

## 3.02

- **A trilha do plano B agora combina com o clima do vídeo.** Faixas com
  etiqueta no nome (`viral--`, `humor--`, `educacional--`…) são casadas com
  o tipo do vídeo em três degraus: mesmo tipo → mesmo clima
  (agitado/médio/calmo) → qualquer uma, com rodízio dentro do degrau.
- **A tela Biblioteca mostra as trilhas**: lista com play, etiqueta de clima
  e tamanho, botão "Adicionar músicas" (upload cai direto em
  `Biblioteca/Trilhas` preservando a etiqueta). Música nunca entra no
  b-roll de imagens.

## 3.01

- **Trilha sonora ganhou plano B: a sua biblioteca de músicas.** Quando a
  geração por IA falha (créditos do ElevenLabs esgotados, rede fora), o
  vídeo não sai mais mudo: o app usa uma música da pasta
  `ATIVAVID/Biblioteca/Trilhas` — rodiziando entre elas, ajustada ao tamanho
  do vídeo com fade — e a ficha do card conta qual foi usada. Basta deixar
  seus MP3s (royalty-free) na pasta uma vez.

## 3.00

- O campo "Rodapé fixo do post" estava branco no tema escuro — vestiu o tema
  como os campos vizinhos (e perdeu o sublinhado vermelho do corretor)

## 2.99

- **Instalação nova não trava mais os primeiros vídeos.** Sem o texto da
  marca preenchido, todos os jobs paravam em "Revisar: falta o texto da
  marca (card final)" — cinco de cinco no primeiro uso de um cliente. Agora
  o vídeo sai normalmente SEM o card final, e a ficha avisa: "Card final
  desligado: sem texto da marca — preencha em Estilos para o card voltar"

## 2.98

- **Erro "Bad request syntax" ao importar — consertado na raiz.** Em algumas
  situações (ex.: licença em validação), o servidor respondia sem consumir a
  requisição e a conexão reaproveitada quebrava a importação seguinte com um
  erro ilegível. Aconteceu com um cliente em trial. Agora nenhuma rota
  consegue mais envenenar a conexão — e a mensagem real (ex.: estado da
  licença) aparece no lugar do erro de sintaxe

- **Rodapé fixo do post.** Campo novo na tela de Estilo: um bloco
  institucional (endereço, serviços, cidade) que sai no FIM de toda legenda,
  entre o texto do vídeo e as hashtags. A legenda agora monta sempre na
  ordem: corpo variável escrito pela IA sobre o vídeo → rodapé fixo da marca
  → suas hashtags. A IA é proibida de mexer no rodapé e nas hashtags

## 2.97

- **A trilha de IA parou de ser cobrada em dobro.** Cada "Salvar e refazer",
  cada versão do "Gerar 5 versões" e cada reprocesso gerava uma música NOVA
  no ElevenLabs — foi assim que os créditos do plano evaporaram em dias.
  Agora o refazer reaproveita a trilha que o vídeo já tem; só gera de novo
  se o corte ficou mais longo que a música ou se o clima do estilo mudou

## 2.96

- **A frase de SEO local virou obrigatória e concreta.** Com o campo "SEO
  local" preenchido, a legenda passa a exigir da IA uma frase de busca de
  verdade — que conecta o assunto do vídeo ao serviço mais ligado a ele e à
  cidade ("troca de tela em Campinas é aqui na loja"), no jeito que o
  cliente digitaria no Google — em vez de uma menção genérica

## 2.95

- Os campos "Palavras de destaque da marca", "Hashtags do post" e "SEO local"
  agora ocupam a linha inteira da tela de Estilo, com letra e altura maiores —
  são listas, não cabiam em coluna estreita

## 2.94

- A configuração técnica do "Publicar — Instagram" (IG User ID + token) saiu
  da tela de Integrações — pedia dados de desenvolvedor e confundia. O motor
  de publicação continua pronto por dentro, aguardando um caminho de conexão
  simples ("Entrar com Instagram") para voltar à interface

## 2.93

- **Publicar no Instagram direto do app.** Menu "⋯" de qualquer vídeo pronto
  → "Publicar no Instagram": o app envia o Reel pela API oficial da Meta
  (upload direto do arquivo, sem link público) com a legenda do post — suas
  hashtags e SEO incluídos — e o card mostra "publicado ✓" com o link.
  Conecte em Integrações → "Publicar — Instagram" (IG User ID + token da
  Meta, com botão Testar que confirma a conta). Publicação SEMPRE pede
  confirmação — nada sai sozinho

- **Instalação em computador novo consertada.** Na primeira instalação, o
  assistente instalava as dependências mas não as enxergava logo em seguida
  (o PATH do Windows só vale para janelas novas) e parava com "ainda não
  terminou a instalação". Agora o caminho é recarregado na hora e o uv tem
  instalador reserva — máquina zerada instala de ponta a ponta

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
