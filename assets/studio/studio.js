/* Hub shell: sidebar + previews + BYOK scaffold */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const state = {
  jobs: [],
  jobsLoaded: false,   // primeira resposta do /api/jobs ja chegou?
  view: "import",
  pendingDeleteId: null,
  pendingRenameId: null,
  pendingRenameCurrent: "",
  pendingFiles: null,
  // Caminhos escolhidos no dialogo NATIVO. Excludente com pendingFiles: ou a
  // tela tem os bytes (upload) ou tem os caminhos (import direto).
  pendingPaths: null,
  pendingDuration: null,
  pendingRecommended: null,
  uploads: {},
  brandActive: null,
  projFilter: "todos",
  projBusca: "",
  doneBusca: "",
  // 5.0.43: ids que o servidor achou pelo que foi DITO (transcricao e
  // legenda do post), para o termo em `termo`. Soma-se a busca por titulo.
  buscaFala: { termo: "", ids: new Set() },
  libraryRoot: "",
  libraryData: null,
  libAba: "image",
  libCat: "",
  presetBrandId: "padrao",
};

// Hidrata a lista com o retrato da ultima resposta: a tela pinta na hora e
// o /api/jobs de verdade substitui em seguida (voltar do preview recarrega
// a pagina — "some todos e demora segundos pra carregar", 02/09).
try {
  const _cache = JSON.parse(localStorage.getItem("ativavid.jobs.cache") || "null");
  if (Array.isArray(_cache) && _cache.length) state.jobs = _cache;
} catch { /* retrato ausente ou corrompido: segue vazio */ }

const STATUS_LABEL = {
  importing: "Importando",
  queued: "Aguardando",
  processing: "Processando",
  done: "Concluído",
  needs_review: "Revisar",
  error: "Erro",
};

const TECH_LEAK = /overlay|remotion|ffmpeg|ffprobe|nvenc|nvdec|prores|loudnorm|compose|render_engine|fallback_full|full.?remotion|h264|libx264|qsv|amf|tonemap|cpu cut|working.?master|single.?pass|encoder|node\.js|\bnode\b|python|traceback|file ".+?", line \d+|helpers\\|cmd \/c |cmd failed|exception|uv run|render\.py|\\\\|\/helpers\//i;

const VIEW_COPY = {
  import: ["Início", "Escolha vídeos ou uma pasta. Cada subpasta vira um vídeo."],
  fila: ["Fila", "Acompanhe o processamento dos seus vídeos."],
  done: ["Concluídos", "Vídeos prontos para abrir, ajustar ou exportar."],
  projetos: ["Projetos", "Todo trabalho que ainda pode ser reaberto, revisado ou refeito."],
  estilo: ["Estilos", "Como os vídeos da sua marca normalmente devem parecer."],
  biblioteca: ["Biblioteca", "Arquivos reutilizáveis que a IA pode usar nos vídeos."],
  presets: ["Empresas", "Cada empresa tem identidade, perfil e presets de edição próprios. Clique numa para trabalhar nela."],
  roteiro: ["Roteiro", "A IA escreve o que gravar: ganchos que param o scroll, roteiro por blocos, CTA e legenda."],
  aulas: ["Aulas", "Aprenda a usar o ATIVAVID em vídeos curtos: do primeiro vídeo ao Multiplicador."],
  ia: ["IA", "A inteligência que corta, escreve e legenda — sessão do navegador e modelo."],
  integracoes: ["Integrações", "Serviços externos que o pipeline chama: transcrição, voz e b-roll."],
  licenca: ["Licença", "Status da assinatura e contas."],
  sistema: ["Configurações", "Máquina, pastas, atualizações e diagnóstico."],
  // aliases antigos → redirecionados em setView (links salvos continuam abrindo)
  keys: ["IA", "Sessão do navegador e chaves de API."],
  marca: ["Empresas", "Cada empresa tem identidade, perfil e presets de edição próprios."],
  doutor: ["Configurações", "Desempenho e pastas."],
};

/* O aviso nasce no TOPO, no centro: em pe embaixo ele passava despercebido
 * ("ali quase nunca da pra ver" — 27/08), ainda mais numa tela larga onde o
 * olho esta no conteudo. A mensagem continua entrando como TEXTO (nunca
 * innerHTML): metade das chamadas passa recado de erro do servidor. */
function toast(msg, ms) {
  const t = $("#toast");
  let corpo = t.querySelector(".toast-msg");
  if (!corpo) {
    t.innerHTML = '<span class="toast-ico" aria-hidden="true"></span>'
      + '<span class="toast-msg"></span>';
    corpo = t.querySelector(".toast-msg");
  }
  corpo.textContent = msg;
  t.classList.remove("hidden");
  t.classList.remove("toast-in");
  void t.offsetWidth;  // reinicia a animacao quando um aviso segue o outro
  t.classList.add("toast-in");
  clearTimeout(toast._tm);
  toast._tm = setTimeout(() => t.classList.add("hidden"), ms || 2800);
}

function applyBusy(j) {
  const qa = j && j.quickApply;
  return !!(qa && (qa.status === "queued" || qa.status === "running"));
}

function applyDismissed(qa) {
  if (!qa) return false;
  if (qa.dismissedAt) return true;
  // reserva local: o POST pode nao ter chegado ainda quando o poll repinta
  const key = applyAckKey(qa);
  if (!key) return false;
  try { return localStorage.getItem(key + ":dis") === "1"; } catch { return false; }
}

function applyFailed(j) {
  const qa = j && j.quickApply;
  // `acknowledgedAt` NAO decide isto: a tela marca ack sozinha ao mostrar o
  // toast da falha. So o clique em Dispensar (dismissedAt) tira o cartaz —
  // antes ele voltava no poll seguinte, para sempre.
  return !!(qa && qa.status === "failed" && !applyDismissed(qa));
}

function applyCompleted(j) {
  const qa = j && j.quickApply;
  return !!(qa && qa.status === "completed");
}

function jobInFila(j) {
  if (["importing", "queued", "processing", "needs_review", "error"].includes(j.status)) return true;
  const qa = j && j.quickApply;
  return !!(qa && ["queued", "running", "failed"].includes(qa.status));
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function looksTechnical(s) {
  return TECH_LEAK.test(String(s || ""));
}

function queueCopy(j, view) {
  const qa = j && j.quickApply;
  if (applyBusy(j)) {
    const stageText = (qa && qa.stageLabel) || "Aplicando edição...";
    const bits = [stageText];
    if (qa && qa.elapsedLabel) bits.push(qa.elapsedLabel);
    if (qa && qa.etaLabel) bits.push(qa.etaLabel);
    return { badge: "ATUALIZANDO", text: bits.join(" · ") };
  }
  if (applyFailed(j) && view !== "done") {
    const text = (qa && qa.stageLabel) || "Não foi possível atualizar o vídeo.";
    return { badge: "REVISAR", text };
  }

  const status = String(j.status || "");
  const stage = String(j.stage || "");
  const raw = `${j.message || ""} ${j.stageLabel || ""} ${stage} ${j.reason || ""}`;
  const blob = raw.toLowerCase();

  if (status === "done" || stage === "done") {
    return { badge: "CONCLUÍDO", text: "Vídeo concluído" };
  }
  if (status === "importing") {
    const pct = Number.isFinite(Number(j.progress)) ? ` ${Math.round(Number(j.progress))}%` : "";
    return { badge: "IMPORTANDO", text: `Importando vídeo...${pct}` };
  }
  if (status === "error" || status === "needs_review" || stage === "error") {
    if (/cancel/i.test(raw) || stage === "cancelled" || j.reason === "cancelled") {
      return { badge: "CANCELADO", text: "Cancelado pelo usuário" };
    }
    if (j.reason === "missing_brand_copy" || /marca|end.?card|card final/i.test(raw)) {
      return { badge: "REVISAR", text: "Falta o texto do card final em Estilos" };
    }
    const friendly = String(j.message || "").trim();
    const text = friendly && !TECH_LEAK.test(friendly)
      ? friendly
      : "Não foi possível concluir este vídeo.";
    return { badge: "ERRO", text };
  }
  if (status === "queued" || stage === "queued") {
    return { badge: "NA FILA", text: "Aguardando na fila" };
  }

  const finishing = stage === "exporting"
    || /export|encode|loudnorm|compose|mux|cleanup|valid|finaliz/i.test(blob);
  const captions = stage === "visuals" || stage === "preview"
    || /caption|legenda|overlay|hook|end.?card|zoom|efeito|insert/i.test(blob);
  const editing = stage === "rendering" || stage === "waiting_render"
    || /renderiz|remotion|visual/i.test(blob);
  const preparing = ["transcribing", "analyzing", "planning", "cutting"].includes(stage)
    || /transcrib|analis|planning|cut|corte|prepar/i.test(blob);

  const eta = j.etaLabel ? ` · ${j.etaLabel}` : "";
  if (finishing) return { badge: "PROCESSANDO", text: `Finalizando vídeo...${eta}` };
  if (captions) return { badge: "PROCESSANDO", text: `Aplicando legendas e efeitos...${eta}` };
  if (editing) return { badge: "PROCESSANDO", text: `Aplicando edição...${eta}` };
  // O PASSO, quando o pipeline diz qual é. As quatro etapas da primeira
  // metade — ouvir, planejar, cortar — mostravam a mesma frase
  // ("Preparando vídeo..."), e essa metade leva minutos: quem olha não
  // sabia se andou. Cada uma tem nome próprio agora; o genérico fica só
  // para quando o passo não chegou.
  const PASSO = {
    analyzing: "Olhando o vídeo",
    transcribing: "Ouvindo o que foi falado",
    planning: "Escolhendo os cortes",
    cutting: "Cortando o vídeo",
  };
  if (PASSO[stage]) {
    return { badge: "PROCESSANDO", text: `${PASSO[stage]}...${eta}` };
  }
  if (preparing) return { badge: "PROCESSANDO", text: `Preparando vídeo...${eta}` };
  return { badge: "PROCESSANDO", text: `Preparando vídeo...${eta}` };
}

function jobWhenLabel(j) {
  const ready = j.finishedAtLabel || "";
  if (ready) return ready;
  const iso = j.finishedAt || (j.status === "done" ? j.updatedAt : "") || j.createdAt || "";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const d = new Date(t);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function jobHeadline(j, view) {
  const text = queueCopy(j, view).text;
  if (applyBusy(j) || (applyFailed(j) && view !== "done")) return text;
  const when = jobWhenLabel(j);
  if (when && (j.status === "done" || j.stage === "done")) {
    // A hora de conclusao agora vive na linha de periodo (inicio -> fim), que
    // diz mais. Repetir aqui deixava a mesma hora duas vezes no card.
    if (periodoLabel(j)) return text;
    return `${text} · ${when}`;
  }
  return text;
}

function jobDetail() {
  return "";
}

// 5.0.48: GET igual em voo e UM pedido so. No arranque o hub disparava o
// mesmo /api/settings, /api/brands e /api/license varias vezes (44 pedidos
// no lab; 11 chamadas a /api/settings no codigo), cada um remontando a
// resposta no servidor. Quem chega enquanto o primeiro ainda nao voltou
// recebe a MESMA promessa; quando ela assenta, o mapa esvazia — nao e
// cache, e so "nao pedir duas vezes ao mesmo tempo".
const _getEmVoo = new Map();
async function api(path, opts) {
  const metodo = String((opts && opts.method) || "GET").toUpperCase();
  if (metodo === "GET") {
    const emVoo = _getEmVoo.get(path);
    if (emVoo) return emVoo;
    const p = _apiCru(path, opts).finally(() => _getEmVoo.delete(path));
    _getEmVoo.set(path, p);
    return p;
  }
  return _apiCru(path, opts);
}

async function _apiCru(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (res.status === 403 && (data.error === "license_required" || data.error === "update_required")) {
    // Antes, so o upload por arrastar tratava isto. Pelo seletor de pasta — que
    // e o caminho padrao — o cliente via um toast escrito "license_required" e
    // nenhum caminho para assinar.
    renderLicense(data.license || {});
    if (data.error === "update_required" || data.license?.update?.force) openUpdateDialog(data.license);
    else openLicenseDialog(data.license);
    throw new Error(mensagemDeBloqueio(data));
  }
  if (res.status === 403 && data.error === "forbidden") {
    // O servidor disse que esta sessao NAO e admin. Ate a 5.0.31 a tela
    // guardava o `isAdmin` de quando abriu e deixava o painel de contas
    // (criar, liberar dias, revogar) aberto por cima do "forbidden" — print
    // de um PC de cliente em 04/09. Rebaixa aqui, no unico lugar por onde
    // toda resposta passa, e o painel some.
    if (state.auth && state.auth.isAdmin) {
      state.auth = { ...state.auth, isAdmin: false };
      try { syncLicenseChrome(); } catch { /* a tela pode nem estar montada */ }
      try { applyAccountChrome(state.auth); } catch { /* idem */ }
    }
    throw new Error(data.message || "Login de admin necessário.");
  }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

/** Texto em portugues para o 403 do gate — nunca o codigo de erro cru. */
function mensagemDeBloqueio(data) {
  const L = (data && data.license) || {};
  if (data?.error === "update_required" || L.update?.force) {
    return L.update?.message || "Atualize o ATIVAVID para continuar.";
  }
  if (L.message) return L.message;
  if (L.mode === "trial") return "Seu período de teste acabou — assine para continuar.";
  return "Precisa de assinatura ativa para editar.";
}


function estiloCarregou(fr) {
  try {
    const doc = fr.contentDocument;
    return !!(doc && doc.body && doc.body.children.length > 0);
  } catch {
    return false;      // outra origem = pagina de erro do navegador
  }
}

function mostrarFalhaDoEstilo() {
  const aviso = $("#estiloFalha");
  if (!aviso) return;
  aviso.classList.remove("hidden");
  const btn = $("#btnEstiloRetry");
  if (btn && !btn.dataset.wired) {
    btn.dataset.wired = "1";
    btn.onclick = () => {
      const velho = $("#estiloFrame");
      if (!velho) return;
      aviso.classList.add("hidden");
      // Trocar so o `src` nao basta: o Chrome deixa o frame preso na
      // propria pagina de erro (contentDocument continua nulo, medido).
      // Um iframe NOVO comeca limpo.
      const fr = document.createElement("iframe");
      fr.id = "estiloFrame";
      fr.className = velho.className;
      fr.title = velho.title;
      fr.dataset.loaded = "1";
      fr.onload = () => {
        if (!estiloCarregou(fr)) {
          mostrarFalhaDoEstilo();
          return;
        }
        fr.dataset.ok = "1";
        aviso.classList.add("hidden");
        applyThemeToIframes(
          document.documentElement.getAttribute("data-theme") || "dark");
      };
      velho.replaceWith(fr);
      fr.src = estiloFrameSrc();
      setTimeout(() => {
        if (fr.dataset.ok !== "1") mostrarFalhaDoEstilo();
      }, 6000);
    };
  }
}

function goHome() {
  setView("import");
}

function setView(name) {
  // `keys` era o nome antigo da tela de IA — links e atalhos salvos ainda
  // chegam por ele, então continua valendo como apelido.
  if (name === "keys") name = "ia";
  // "marca" virou Presets na 4.19 (a tela era a mesma coisa, com outros
  // nomes). Link salvo e botao antigo continuam abrindo.
  if (name === "marca") name = "presets";
  if (name === "doutor") name = "sistema";
  state.view = name;
  $$(".sb-item[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$("[data-view-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.viewPanel !== name));
  const [title, sub] = VIEW_COPY[name] || ["ATIVAVID", ""];
  $("#wsTitle").textContent = title;
  $("#wsSub").textContent = sub;
  document.body.classList.toggle("view-estilo-on", name === "estilo");
  document.body.classList.toggle("view-roteiro-on", name === "roteiro");
  if (name === "ia") loadLlm().catch(() => {});
  if (name === "integracoes") refreshHealth().catch(() => {});
  if (name === "licenca") loadLicenca().catch((e) => toast(e.message));
  if (name === "sistema") {
    loadSistema().catch((e) => toast(e.message));
    // Roda a checagem ao ABRIR: o card mostrava duas acoes e nenhum
    // resultado, e quem chega aqui quer saber se esta tudo bem.
    runDoutor().catch(() => {
      const r = $("#doutorResumo");
      if (r) r.textContent = "Não deu para rodar a checagem agora.";
    });
  }
  if (name === "projetos") {
    wireEspacoDosProjetos();
    avisarEspaco().catch(() => {});
  }
  if (name === "biblioteca") loadLibraryUi().catch(() => {});
  if (name === "roteiro") loadRoteiroUi().catch((e) => toast(e.message));
  if (name === "aulas") loadAulasUi().catch((e) => toast(e.message));
  else aulasPausar();   // "saiu da aba de aulas pausa o video"
  if (name === "presets") {
    loadEmpresaUi().catch(() => {});
    // A identidade e o formato moram aqui desde a 4.19 — quem preenche os
    // dois e `loadBrandsUi`, que antes so rodava ao abrir a tela de Marca.
    loadBrandsUi().catch(() => {});
  }
  if (name === "estilo") {
    loadBrandsUi().catch(() => {});
    barraDoEstilo();
    const fr0 = $("#estiloFrame");
    if (fr0 && fr0.dataset.loaded === "1") {
      // O iframe fica montado entre as visitas. Sem esta troca, "Editar
      // estilo" num preset reabria o editor no alvo da visita anterior.
      const atual = new URL(fr0.src, location.origin)
        .searchParams.get("presetId") || "";
      if (atual !== (state.editPresetId || "")) fr0.src = estiloFrameSrc();
    }
    const fr = $("#estiloFrame");
    if (fr && !fr.dataset.loaded) {
      fr.dataset.loaded = "1";
      fr.onload = () => {
        // `load` dispara MESMO com conexao recusada — o Chrome carrega a
        // propria pagina de erro nele. So o conteudo diz se deu certo: a
        // pagina de erro fica noutra origem e o contentDocument some.
        if (!estiloCarregou(fr)) {
          mostrarFalhaDoEstilo();
          return;
        }
        fr.dataset.ok = "1";
        const aviso = $("#estiloFalha");
        if (aviso) aviso.classList.add("hidden");
        const t = document.documentElement.getAttribute("data-theme") || "dark";
        applyThemeToIframes(t);
        mandarAlvoAoEstilo();
      };
      fr.src = estiloFrameSrc();
      // O iframe não dispara erro quando o servidor recusa a conexão: ele
      // simplesmente fica em branco. Sem este relógio a tela some calada.
      setTimeout(() => {
        if (fr.dataset.ok !== "1") mostrarFalhaDoEstilo();
      }, 8000);
    } else {
      applyThemeToIframes(document.documentElement.getAttribute("data-theme") || "dark");
    }
    // Se o editor ja estava carregado, o `onload` acima nao dispara de novo —
    // por isso a entrega tambem acontece aqui.
    mandarAlvoAoEstilo();
  }
  renderJobs();
  try {
    localStorage.setItem("ativavid-hub-view", name);
    const url = new URL(location.href);
    if (name === "import") url.searchParams.delete("view");
    else url.searchParams.set("view", name);
    history.replaceState(null, "", url.pathname + (url.search || "") + url.hash);
  } catch { /* ignore */ }
}

// Seção do editor que os quadros de "Identidade visual" pediram. Fica guardada
// porque o iframe só aceita a mensagem depois de carregar, e recarregar o
// `src` para embutir o destino perderia ajuste ainda não salvo no editor.
let alvoNoEstilo = "";

function mandarAlvoAoEstilo() {
  const fr = $("#estiloFrame");
  if (!alvoNoEstilo || !fr || fr.dataset.ok !== "1" || !fr.contentWindow) return;
  const alvo = alvoNoEstilo;
  alvoNoEstilo = "";           // só uma vez: senão a próxima visita rola sozinha
  try {
    fr.contentWindow.postMessage({ type: "ativavid-ir-para", alvo }, "*");
  } catch { /* iframe indisponível: o editor abre no topo, como antes */ }
}

/* O que a barra de Estilos diz que esta sendo editado.
 *
 * Sao dois alvos e eles gravam em lugares diferentes: o ESTILO BASE (que
 * vale para todos os presets) e um PRESET. Sem dizer qual, salvar viraria
 * aposta. */
function barraDoEstilo() {
  const nome = $("#estiloBrandName");
  const titulo = $("#estiloBrandTitulo");
  const voltar = $("#btnEstiloBase");
  const editandoPreset = !!state.editPresetId;
  if (titulo) {
    titulo.textContent = editandoPreset ? "Editando o preset" : "Editando o estilo base";
  }
  if (nome && editandoPreset) nome.textContent = state.editPresetNome || "Preset";
  if (voltar) voltar.classList.toggle("hidden", !editandoPreset);
  const hint = $("#brandHint");
  if (hint && editandoPreset) {
    hint.textContent = "Salvar aqui muda só este preset — o estilo base e os outros presets ficam como estão.";
  }
}

function estiloFrameSrc() {
  // A marca ATIVA, e nao mais o que estava escolhido num seletor: o
  // seletor deixava editar o estilo de uma marca sem ativa-la.
  const id = (state.brandActive && state.brandActive.id) || "";
  const q = new URLSearchParams({ embed: "1" });
  if (id) q.set("brandId", id);
  // Com preset, o editor edita AQUELE preset e salva nele. Sem preset,
  // edita o estilo base — que e o caminho de sempre.
  if (state.editPresetId) q.set("presetId", state.editPresetId);
  q.set("t", String(Date.now()));
  return `/estilo-padrao?${q.toString()}`;
}

function jobRecency(j) {
  const t = Date.parse(j.finishedAt || j.updatedAt || j.createdAt || 0);
  return Number.isFinite(t) ? t : 0;
}

/** Contador do menu. `data-zero` some com o ponto no sidebar recolhido. */
function setCount(sel, n) {
  const el = $(sel);
  if (!el) return;
  el.textContent = String(n);
  el.dataset.zero = n ? "0" : "1";
}

function byRecency(a, b) {
  return jobRecency(b) - jobRecency(a) || String(b.id).localeCompare(String(a.id));
}

// 5.0.48: Concluidos ordenados por escolha — mais recentes (padrao), melhor
// nota do corte, ou mais longos. Com 300 videos, "qual foi o melhor deste
// mes" e uma pergunta que a lista tem de responder sem abrir um por um.
const DONE_SORT_KEY = "ativavid.doneSort";
state.doneSort = (() => { try { return localStorage.getItem(DONE_SORT_KEY) || "recentes"; } catch { return "recentes"; } })();
function ordemDosProntos() {
  const nota = (j) => Number(j.score && j.score.overall) || 0;
  const dur = (j) => Number(j.durationSec) || 0;
  if (state.doneSort === "nota") return (a, b) => nota(b) - nota(a) || byRecency(a, b);
  if (state.doneSort === "duracao") return (a, b) => dur(b) - dur(a) || byRecency(a, b);
  return byRecency;
}

/* Workspace por EMPRESA (5.0.0): "ativa" = so os videos da marca ativa
 * (o card do rodape); "all" = todas. Video sem marca (projeto antigo, nunca
 * renderizado) aparece em todos, para nao sumir de lugar nenhum. */
const WS_MARCA_KEY = "ativavid.wsMarca";
state.wsMarca = (() => { try { return localStorage.getItem(WS_MARCA_KEY) || "ativa"; } catch { return "ativa"; } })();
function setWsMarca(modo) {
  state.wsMarca = modo === "all" ? "all" : "ativa";
  try { localStorage.setItem(WS_MARCA_KEY, state.wsMarca); } catch { /* ignore */ }
}
function jobNaMarca(j) {
  if (state.wsMarca === "all") return true;
  const ativa = state.brandActive && state.brandActive.id;
  if (!ativa) return true;
  return !j.brandId || j.brandId === ativa;
}
function nomeDaMarca(id) {
  const b = (state.brands || []).find((x) => x.id === id);
  return b ? (b.name || b.id) : (id || "");
}
function jobsDoWorkspace() {
  return state.jobs.filter(jobNaMarca);
}

function filterJobs(kind) {
  if (kind === "fila") {
    return jobsDoWorkspace().filter(jobInFila);
  }
  if (kind === "done") {
    // Busca tambem aqui: sao 183 videos prontos, e sem ela a unica
    // forma de achar um era rolar a lista.
    return jobsDoWorkspace().filter((j) => j.status === "done")
      .filter((j) => casaBusca(j, state.doneBusca))
      .sort(ordemDosProntos());
  }
  if (kind === "projetos") {
    // Projetos é o acervo: TODO trabalho que ainda existe em disco, em
    // qualquer estado. A Fila e os Concluídos são recortes disto.
    const f = state.projFilter || "todos";
    return jobsDoWorkspace()
      .filter((j) => {
        if (f === "ativos") return jobInFila(j) && j.status !== "error";
        if (f === "prontos") return j.status === "done";
        if (f === "parados") return j.status === "error" || j.status === "needs_review";
        return true;
      })
      .filter((j) => casaBusca(j, state.projBusca))
      .sort(byRecency);
  }
  return [...jobsDoWorkspace()].sort(byRecency).slice(0, 8);
}

/* O que o usuario procura e o que ele LE no cartao: o titulo. A busca
 * olhava so o nome da pasta ("20260829-185156_Elizangela001_08291440_C039")
 * e o arquivo de camera — digitar "lanterna" nao achava
 * "Celular na lanterna?".
 *
 * Uma funcao so para Projetos e Concluidos: duas buscas com regras
 * diferentes na mesma lista seria pior que uma busca fraca. */
function casaBusca(j, termo) {
  const q = String(termo || "").trim().toLowerCase();
  if (!q) return true;
  const fala = state.buscaFala;
  if (fala && fala.termo.toLowerCase() === q && fala.ids.has(String(j.id))) return true;
  return [j.title, j.name, jobFolderName(j)]
    .some((x) => String(x || "").toLowerCase().includes(q));
}

// A busca pelo que foi dito mora no servidor (le a transcricao de cada
// projeto, com cache). Com 3+ letras, pergunta a ele com um pequeno atraso;
// a lista responde na hora pelo titulo e completa quando a fala chega.
let _buscaFalaTimer = null;
function buscarNaFala(termo) {
  const q = String(termo || "").trim();
  clearTimeout(_buscaFalaTimer);
  if (q.length < 3) {
    state.buscaFala = { termo: "", ids: new Set() };
    return;
  }
  _buscaFalaTimer = setTimeout(async () => {
    try {
      const r = await api(`/api/jobs/buscar?q=${encodeURIComponent(q)}`);
      state.buscaFala = { termo: q, ids: new Set((r.ids || []).map(String)) };
      renderJobs();
    } catch { /* sem servidor: fica a busca por titulo */ }
  }, 250);
}

function jobFolderName(j) {
  const raw = String(j.projectDir || j.editDir || j.name || j.id || "").replace(/[\\/]+$/, "");
  const parts = raw.split(/[/\\]/).filter(Boolean);
  return parts[parts.length - 1] || String(j.id || "");
}

// Versoes CONCLUIDAS do mesmo arquivo de origem (fonteStem vem do
// jobs_view). "Gerar 5 versoes" cria 5 projetos irmaos — comparar e o
// proximo passo natural.
function versoesDaFonte(j) {
  const stem = j && j.fonteStem;
  if (!stem) return [];
  return state.jobs
    .filter((x) => x.status === "done" && x.fonteStem === stem && x.final)
    .sort((a2, b2) => String(a2.finishedAt || "").localeCompare(String(b2.finishedAt || "")));
}

function abrirComparar(id) {
  const j = state.jobs.find((x) => x.id === id);
  const versoes = versoesDaFonte(j);
  if (versoes.length < 2) { toast("Só existe uma versão pronta deste vídeo"); return; }
  const grid = $("#cmpGrid");
  if (!grid) return;
  $("#cmpTitle").textContent = `Comparar versões — ${j.fonteStem} (${versoes.length})`;
  grid.innerHTML = "";
  versoes.slice(0, 6).forEach((v) => {
    const folder = encodeURIComponent(jobFolderName(v));
    const nome = String(v.final).split(/[\\/]/).pop() || "";
    const cell = document.createElement("div");
    cell.className = "cmp-cell";
    const meta = [
      v.modoLabel ? `Modo: ${v.modoLabel}` : "Modo: Dinâmico",
      v.styleLabel ? `Estilo: ${v.styleLabel}` : "",
      duracoesLabel(v) || "",
      v.corteResumo ? `Saiu: ${v.corteResumo}` : "",
    ].filter(Boolean).join("<br>");
    cell.innerHTML = `
      <video controls preload="metadata" src="/p/${folder}/media/${encodeURIComponent(nome)}"></video>
      <div class="cmp-nome">${escapeHtml(displayTitle(v))}</div>
      <div class="cmp-meta">${meta}</div>`;
    grid.appendChild(cell);
  });
  $("#dlgCompare")?.showModal();
}

function jobLinks(j) {
  const folder = encodeURIComponent(jobFolderName(j));
  return {
    editor: j.editorUrl || `/p/${folder}/fase1`,
    estilo: j.estiloUrl || `/p/${folder}/estilo`,
    final: j.finalUrl || `/p/${folder}/fase2`,
  };
}

/** Segundos -> "1:23" ou "26s". Vazio quando nao ha numero. */
function fmtDuracao(seg) {
  const n = Number(seg);
  if (!Number.isFinite(n) || n <= 0) return "";
  const t = Math.round(n);
  if (t < 60) return `${t}s`;
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

/** "27s → 26s" quando as duas existem; so a que houver quando falta uma. */
function duracoesLabel(j) {
  const orig = fmtDuracao(j.sourceDurationSec);
  const fim = fmtDuracao(j.durationSec);
  if (orig && fim) return orig === fim ? fim : `${orig} → ${fim}`;
  return fim || orig || "";
}

/** A ficha do video pronto, em linhas rotuladas.
 *  Desenho pedido pelo usuario: o NOME manda no card, e o resto e conferencia
 *  — original, editado, formato, estilo, inicio e fim, cada um com o seu
 *  rotulo. Antes tudo isso era uma linha so ("1:07 → 52s · 9:16") mais um
 *  "Video concluido" que nao dizia nada que o selo ja nao dissesse. */
/* O card precisa dizer quando o video saiu SEM o planejamento por IA.
 * Sem isto o unico sinal era uma linha no log do pipeline, que ninguem abre --
 * e por dois dias os videos sairam com o titulo tirado das primeiras palavras
 * da fala sem nada na tela indicar a diferenca. */
function avisoIaHtml(j) {
  const t = String(j.iaAviso || "").trim();
  if (!t) return "";
  return `<p class="pc-aviso-ia">${escapeHtml(t)}</p>`;
}

function fichaHtml(j) {
  const linhas = [];
  const orig = fmtDuracao(j.sourceDurationSec);
  const fim = fmtDuracao(j.durationSec);
  if (orig) linhas.push(["Vídeo original", orig]);
  if (fim) linhas.push(["Vídeo editado", fim]);
  const fmt = j.formatLabel || ((j.hasFinal || j.status === "done" || j.hasCut) ? "9:16" : "");
  const est = String(j.styleLabel || "").trim();
  if (fmt || est) {
    linhas.push(["Formato", fmt || "—"]);
    if (est) linhas.push(["Estilo", est]);
  }
  // O modo de edicao muda o CORTE (leve = heuristico, sem IA) e era invisivel
  // no card — o estilo aparecia, o modo nao, e "por que a minutagem nao muda"
  // ficava sem resposta na tela.
  if (j.modoLabel) linhas.push(["Modo", j.modoLabel]);
  // O que o corte tirou, em uma linha ("32s silêncio · 9s repetição") — a
  // resposta da pergunta que o usuario fez a cada video de 24-25/08.
  if (j.corteResumo) linhas.push(["Saiu", j.corteResumo]);
  // Qual IA fez o plano do corte. A linha diz o NOME e nada mais — o
  // porque (plano B, sessao caida) fica no `title`, que aparece ao passar
  // o mouse. Ele pediu assim em 31/08: a ficha tinha virado um paragrafo
  // de justificativa por video.
  if (j.iaNota) linhas.push(["IA", j.iaNota, j.iaDetalhe]);
  if (j.corteQualidade) linhas.push(["Revisar no corte", j.corteQualidade]);
  // Por que ESTE video demorou o triplo. O motivo ficava so no
  // `timing.json`; aparece em menos de um quinto dos videos.
  if (j.motorNota) linhas.push(["Render", j.motorNota]);
  // Trabalho que ele fez no editor e que nunca virou video: 12 projetos
  // estavam assim, o mais antigo de 13/08, sem nada na tela dizendo.
  if (j.pedidoNota) linhas.push(["Pendente", j.pedidoNota]);
  // Trecho que pedia tempo inexistente no arquivo. Sem esta linha o
  // defeito e mudo: o video sai pronto com pedaco sem som e travado.
  if (j.corteNota) linhas.push(["Corte", j.corteNota]);
  if (j.fonteNota) linhas.push(["Fonte", j.fonteNota]);
  if (j.midiaNota) linhas.push(["Mídia", j.midiaNota]);
  if (j.legendaNota) linhas.push(["Legenda", j.legendaNota]);
  if (j.trilhaNota) linhas.push(["Trilha", j.trilhaNota, j.trilhaDetalhe]);
  if (j.cardFinalNota) linhas.push(["Marca", j.cardFinalNota]);
  // A nota do corte (gancho, clareza, ritmo, CTA) e a dica mais util dela.
  // Ate aqui as duas so existiam no painel do preview — o card, que e onde
  // o usuario olha a fila, nao mostrava nenhuma. Uma dica so: duas ou tres
  // viram parede de texto e ninguem le.
  if (j.score && Number.isFinite(Number(j.score.overall))) {
    const dica = (j.score.tips || []).filter(Boolean)[0] || "";
    linhas.push(["Nota do corte",
      `${Math.round(Number(j.score.overall))}/100${dica ? ` · ${dica}` : ""}`]);
  }
  if (j.publicadoLink) linhas.push(["Instagram", "publicado ✓"]);
  else if (j.publicando) linhas.push(["Instagram", "publicando…"]);
  else if (j.publicacaoErro) linhas.push(["Instagram", `falhou: ${j.publicacaoErro}`]);
  const ini = String(j.startedAtLabel || j.createdAtLabel || "");
  const fin = String(j.finishedAtLabel || "");
  if (ini) linhas.push(["Início", ini]);
  if (fin) linhas.push(["Final", fin]);
  if (!linhas.length) return "";
  // title com o valor inteiro: a ficha e apertada e um texto longo pode
  // quebrar em varias linhas — passar o mouse mostra tudo de uma vez.
  return `<dl class="pc-ficha">${linhas.map(([k, v, detalhe]) => {
    // O `title` mostra o que nao coube: o detalhe, quando a linha tem um,
    // ou o proprio valor quando ele e longo demais para a coluna.
    const dica = detalhe ? `${v} — ${detalhe}` : (String(v).length > 40 ? v : "");
    return `<div><dt>${escapeHtml(k)}</dt><dd${dica
      ? ` title="${escapeHtml(dica)}"` : ""}>${escapeHtml(v)}</dd></div>`;
  }).join("")}</dl>`;
}

/** "21/08 08:22 → 08:33". So repete a data quando o dia virou. */
function periodoLabel(j) {
  const ini = String(j.startedAtLabel || j.createdAtLabel || "");
  const fim = String(j.finishedAtLabel || "");
  if (!ini && !fim) return "";
  if (!fim) return `Início ${ini}`;
  if (!ini) return `Fim ${fim}`;
  const [dIni, hIni] = ini.split(" · ");
  const [dFim, hFim] = fim.split(" · ");
  if (dIni && dFim && dIni === dFim) return `${dIni} · ${hIni} → ${hFim}`;
  return `${ini} → ${fim}`;
}

function cardSig(j, opts) {
  // o modo do workspace entra na assinatura: o chip da marca depende dele
  const _ws = `${state.wsMarca}:${j.brandId || ""}`;
  const links = jobLinks(j);
  const qa = j.quickApply || {};
  // o menu muda quando ha estilo copiado ("Colar estilo (de X)"): sem isto
  // o card nao repinta depois do copiar
  const clip = estiloCopiado();
  return [
    _ws,
    clip ? `clip:${clip.folder}` : "",
    j.id, j.status, j.title || j.name, Math.round(Number(j.progress) || 0), j.hasFinal, j.hasThumb, j.finishedAt, j.finishedAtLabel,
    j.startedAtLabel || "", j.durationSec || "", j.sourceDurationSec || "", (j.temLegenda || j.legenda) ? "L" : "",
    j.styleLabel || "",
    j.iaAviso || "",
    j.modoLabel || "",
    j.corteResumo || "",
    j.iaNota || "",
    j.iaDetalhe || "",
    j.publicadoLink || "",
    j.publicando ? "pub" : "",
    j.publicacaoErro || "",
    j.trilhaNota || "",
    j.trilhaDetalhe || "",
    (j.score && (j.score.tips || [])[0]) || "",
    j.corteQualidade || "",
    j.motorNota || "",
    j.pedidoNota || "",
    j.corteNota || "",
    j.fonteNota || "",
    j.midiaNota || "",
    j.cardFinalNota || "",
    versoesDaFonte(j).length,
    j.stage, j.message, j.reason || "", j.localPoster || j.thumbUrl, links.editor, links.estilo, links.final,
    opts && opts.compact ? "1" : "0",
    qa.status || "", qa.stage || "", qa.elapsedLabel || "", qa.etaLabel || "", qa.stageLabel || "",
    opts && opts.view ? opts.view : "",
  ].join("\t");
}

function cardProgressPct(j) {
  const pct = Number(j.progress);
  if (!Number.isFinite(pct)) return null;
  if (j.status === "processing") return Math.max(1, Math.min(99, pct));
  return Math.max(0, Math.min(100, pct));
}

function cardProgressHtml(j) {
  if (applyBusy(j)) {
    return `<div class="pc-progress indeterminate" aria-hidden="true"><span></span></div>`;
  }
  if (j.status !== "importing" && j.status !== "processing") return "";
  const pct = cardProgressPct(j);
  if (pct == null) {
    return `<div class="pc-progress indeterminate" aria-hidden="true"><span></span></div>`;
  }
  return `<div class="pc-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct)}"><span style="width:${pct}%"></span></div>`;
}

function patchCardProgress(el, j) {
  const html = cardProgressHtml(j);
  const old = el.querySelector(".pc-progress");
  if (!html) {
    if (old) old.remove();
    return;
  }
  const pct = cardProgressPct(j);
  if (old) {
    const wantIndet = pct == null;
    if (wantIndet !== old.classList.contains("indeterminate")) {
      const wrap = document.createElement("div");
      wrap.innerHTML = html;
      old.replaceWith(wrap.firstElementChild);
      return;
    }
    if (pct != null) {
      old.setAttribute("aria-valuenow", String(Math.round(pct)));
      const span = old.querySelector("span");
      if (span) span.style.width = `${pct}%`;
    }
    return;
  }
  const wrap = document.createElement("div");
  wrap.innerHTML = html;
  const node = wrap.firstElementChild;
  const anchor = el.querySelector(".pc-actions");
  if (anchor) anchor.insertAdjacentElement("beforebegin", node);
  else el.querySelector(".pc-body")?.appendChild(node);
}

function cardThumbSrc(j) {
  if (j.localPoster) return j.localPoster;
  if (j.thumbUrl && (String(j.thumbUrl).startsWith("data:") || String(j.thumbUrl).startsWith("blob:"))) {
    return j.thumbUrl;
  }
  if (j.id && !String(j.id).startsWith("tmp-")) {
    return `${j.thumbUrl || `/api/jobs/${j.id}/thumb`}?t=${encodeURIComponent(j.hasThumb || j.id)}`;
  }
  return "";
}

function chipTone(j, view) {
  const copy = queueCopy(j, view);
  if (copy.badge === "ATUALIZANDO") return "updating";
  if (copy.badge === "REVISAR") return "needs_review";
  return j.status;
}

// Concluído sem rename manual: o arquivo entregue é NOMEADO pela headline,
// então o stem dele é o melhor título humano que temos ("IMG_3987" não diz
// nada; "Essa película aguenta martelada" diz tudo).
function displayTitle(j) {
  const manual = j.titleLocked && j.title;
  if (!manual && j.status === "done" && j.final) {
    const base = String(j.final).split(/[\\/]/).pop() || "";
    const stem = base.replace(/\.[^.]+$/, "").trim();
    if (stem && !/^(final|cut)$/i.test(stem)) return stem.slice(0, 80);
  }
  return j.title || j.name || "Vídeo";
}

// Motivos que NÃO adiantam reprocessar: o arquivo de origem está quebrado
// ou sumiu. Card assim precisa de saída ("Apagar"), não de "Tentar de novo".
const DEAD_END_REASONS = new Set(["arquivo_corrompido", "source_missing"]);

function isDeadEnd(j) {
  return DEAD_END_REASONS.has(String((j && j.reason) || ""));
}

/** Ações que tiram o card do limbo. Um card com aviso sempre tem o que fazer. */
function stuckActionsHtml(j, safeId) {
  if (isDeadEnd(j)) {
    return `<button type="button" class="chip-btn ghostish" data-act="delete" data-id="${safeId}"
      data-name="${escapeHtml(displayTitle(j))}" title="O arquivo não abre — apague e importe de novo">Apagar</button>`;
  }
  if (applyFailed(j)) {
    // Reprocessar aqui é seguro: o rerun mantém os cortes manuais.
    return `<button type="button" class="chip-btn" data-act="retry" data-id="${safeId}"
        title="Refazer este vídeo mantendo os seus cortes">Aplicar de novo</button>
      <button type="button" class="chip-btn ghostish" data-act="ackapply" data-id="${safeId}"
        title="Manter o vídeo como está e tirar este aviso">Dispensar</button>`;
  }
  return "";
}

/** O menu ⋯ do card. Funcao propria porque o `patchCard` precisa REFAZER ele:
 *  montado uma vez e congelado, "Ver vídeo final" ficava desabilitado para
 *  sempre e "Copiar legenda do post" nunca aparecia depois que a legenda
 *  ficava pronta. */
/* ---- Copiar / colar estilo entre videos (03/09) ------------------------
 * O estilo de um projeto vive em <edit>/preview_style.json (o que a aba
 * Estilo salva) e o "Aplicar" refaz o visual via /api/jobs/requeue-folder.
 * Copiar = ler esse arquivo do card de origem; colar = gravar o mesmo
 * payload no destino e manda-lo a fila. A area de transferencia fica no
 * localStorage para sobreviver a recarga do hub. */
const ESTILO_COPIADO_KEY = "ativavid.estilo.copiado";

function pastaDoProjeto(j) {
  return String((j && j.projectDir) || "").split(/[\\/]/).filter(Boolean).pop() || "";
}

function estiloCopiado() {
  try {
    const c = JSON.parse(localStorage.getItem(ESTILO_COPIADO_KEY) || "null");
    return c && c.payload && c.folder ? c : null;
  } catch { return null; }
}

function baseDoProjeto(j) {
  // jobLinks ja sabe codificar a pasta: /p/<enc>/estilo -> /p/<enc>
  return String(jobLinks(j).estilo || "").replace(/\/estilo$/, "");
}

async function copiarEstiloDoCard(j) {
  const base = baseDoProjeto(j);
  if (!base) { toast("Não achei a pasta deste vídeo"); return; }
  let payload = null;
  try {
    const r = await fetch(`${base}/media/preview_style.json?v=${Date.now()}`);
    if (r.ok) payload = await r.json();
  } catch { /* trata abaixo */ }
  if (!payload || payload.type !== "style-setup") {
    toast("Este vídeo ainda não tem um estilo salvo — abra \"Alterar estilo\" nele, salve uma vez e copie de novo.", 6000);
    return;
  }
  const de = displayTitle(j);
  try {
    localStorage.setItem(ESTILO_COPIADO_KEY, JSON.stringify({ de, folder: pastaDoProjeto(j), payload }));
  } catch { toast("Não consegui guardar o estilo copiado"); return; }
  toast(`Estilo de "${de}" copiado — nos outros vídeos use "Colar estilo"`, 4500);
  // O menu de onde veio o clique esta ESTACIONADO no body (openCardMenu);
  // repintar o card com ele la fora deixava o card novo sem menu (lab,
  // 03/09). Devolve todos antes de repintar.
  closeCardMenus();
  renderJobs();
}

async function colarEstiloNoCard(j) {
  const c = estiloCopiado();
  if (!c) { toast("Nada copiado ainda — use \"Copiar estilo\" num vídeo pronto"); return; }
  const base = baseDoProjeto(j);
  const folder = pastaDoProjeto(j);
  if (!base || !folder) { toast("Não achei a pasta deste vídeo"); return; }
  try {
    const s = await fetch(`${base}/api/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...c.payload, type: "style-setup" }),
    });
    if (!s.ok) throw new Error("não deu para gravar o estilo");
    const rq = await fetch("/api/jobs/requeue-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder, extraSources: [] }),
    });
    if (!rq.ok) {
      const body = await rq.json().catch(() => ({}));
      throw new Error(body.error || "não deu para enviar à fila");
    }
    toast(`Estilo de "${c.de}" aplicado — refazendo o visual de "${displayTitle(j)}"`, 4500);
    refreshJobs().catch(() => {});
  } catch (e) {
    toast(`Colar estilo falhou: ${e.message || e}`, 5000);
  }
}

function cardMenuHtml(j, opts) {
  const view = opts && opts.view;
  const compact = !!(opts && opts.compact);
  const links = jobLinks(j);
  const canFinal = j.hasFinal || j.status === "done";
  const copy = queueCopy(j, view);
  const title = displayTitle(j);
  const safeId = escapeHtml(j.id);
  const menuKey = escapeHtml(`${j.id}:${compact ? "c" : "f"}`);
  return `<div class="pc-more" data-menu-host="${menuKey}">
      <button type="button" class="chip-btn ghostish pc-more-btn" data-act="menu" data-id="${safeId}" data-menu-key="${menuKey}" aria-label="Mais ações" aria-expanded="false" aria-haspopup="menu">⋯</button>
      <div class="pc-menu hidden" data-menu="${menuKey}" role="menu">
        <button type="button" role="menuitem" data-act="folder" data-id="${safeId}">Abrir pasta</button>
        ${(j.temLegenda || j.legenda) ? `<button type="button" role="menuitem" data-act="copylegenda" data-id="${safeId}">Copiar legenda do post</button>` : ""}
        <button type="button" role="menuitem" data-act="copyname" data-id="${safeId}">Copiar nome</button>
        ${canFinal ? `<button type="button" role="menuitem" data-act="srt" data-id="${safeId}">Salvar legenda .srt</button>` : ""}
        ${j.pedidoTipo === "correcoes" ? `<button type="button" role="menuitem" data-act="aplicar-pendentes" data-id="${safeId}">Aplicar correções pendentes</button>` : ""}
        <a role="menuitem" href="${escapeHtml(links.final)}" ${canFinal ? "" : "class=\"disabled\""}>Ver vídeo final</a>
        <a role="menuitem" href="${escapeHtml(links.editor)}">Editar</a>
        <a role="menuitem" href="${escapeHtml(links.estilo)}" data-id="${safeId}">Alterar estilo</a>
        ${j.status === "done" ? `<button type="button" role="menuitem" data-act="copystyle" data-id="${safeId}">Copiar estilo</button>` : ""}
        ${(() => {
          // SEMPRE visivel: escondido ate alguem copiar, ninguem descobria
          // ("nao tem colar estilo", 03/09). Sem nada copiado fica
          // desabilitado com a dica; no proprio video de origem tambem.
          const c = estiloCopiado();
          if (c && c.folder !== pastaDoProjeto(j)) {
            return `<button type="button" role="menuitem" data-act="pastestyle" data-id="${safeId}">Colar estilo (de ${escapeHtml(c.de)})</button>`;
          }
          const dica = c ? "é o vídeo de origem" : "copie um estilo primeiro";
          return `<button type="button" role="menuitem" class="disabled" disabled title="${dica}">Colar estilo — ${dica}</button>`;
        })()}
        ${j.status === "done" && j.publicadoLink
          ? `<a role="menuitem" href="${escapeHtml(j.publicadoLink)}" target="_blank" rel="noopener">Ver no Instagram</a>`
          : ""}
        ${j.status === "done" && versoesDaFonte(j).length >= 2
          ? `<button type="button" role="menuitem" data-act="compare" data-id="${safeId}">Comparar ${versoesDaFonte(j).length} versões</button>`
          : ""}
        ${j.status === "done" ? `<button type="button" role="menuitem" data-act="retry" data-id="${safeId}">Tentar novamente</button>` : ""}
        ${(copy.badge === "ERRO" || copy.badge === "REVISAR" || j.detail)
          ? `<button type="button" role="menuitem" data-act="detail" data-id="${safeId}">Ver detalhe</button>`
          : ""}
        ${j.temLog ? `<button type="button" role="menuitem" data-act="log" data-id="${safeId}">Abrir o log deste vídeo</button>` : ""}
        <button type="button" role="menuitem" class="danger" data-act="delete" data-id="${safeId}" data-name="${escapeHtml(title)}">Apagar</button>
      </div>
    </div>`;
}

function cardHtml(j, opts) {
  const compact = !!(opts && opts.compact);
  const enter = !!(opts && opts.enter);
  const view = opts && opts.view;
  const canFinal = j.hasFinal || j.status === "done";
  const links = jobLinks(j);
  const editor = links.editor;
  const estilo = links.estilo;
  const busy = j.status === "processing" || j.status === "queued" || j.status === "importing";
  const headline = jobHeadline(j, view);
  const title = displayTitle(j);
  const fmt = j.formatLabel || (canFinal || j.hasCut ? "9:16" : "");
  // "27s → 26s": a duracao de ORIGEM e a entregue. So a final nao diz nada
  // sobre o trabalho do corte, que e o que o app faz.
  const dur = j.durationLabel || duracoesLabel(j);
  const metaBits = [dur, fmt].filter(Boolean);
  // Em "Todas as empresas" cada card diz de quem e (5.0.0).
  if (state.wsMarca === "all" && j.brandId) metaBits.unshift(nomeDaMarca(j.brandId));
  // No card PRONTO a ficha substitui a linha de meta, a mensagem e o periodo.
  const pronto = j.status === "done" && !applyBusy(j);
  const copy = queueCopy(j, view);
  const chipLabel = copy.badge;
  const tone = chipTone(j, view);
  const thumb = cardThumbSrc(j);
  const progress = cardProgressHtml(j);
  const safeId = escapeHtml(j.id);
  const menuKey = escapeHtml(`${j.id}:${compact ? "c" : "f"}`);
    const updating = applyBusy(j);
    const primary = j.status === "done" || updating
    ? `<a class="chip-btn primary${canFinal ? "" : " disabled"}" href="${escapeHtml(links.final)}"${updating ? ' title="Ainda estou atualizando este vídeo. Este é o final anterior."' : ""}>${updating ? "Ver anterior" : "Visualizar"}</a>`
    : busy
      ? `<button type="button" class="chip-btn" data-act="cancel" data-id="${safeId}">Cancelar</button>`
      : isDeadEnd(j)
        // "Tentar novamente" num arquivo quebrado é beco sem saída: o caminho
        // real é importar o arquivo bom de novo.
        ? `<button type="button" class="chip-btn primary" data-act="reimport" data-id="${safeId}">Importar de novo</button>`
        : `<button type="button" class="chip-btn" data-act="retry" data-id="${safeId}">Tentar novamente</button>`;
  const menu = cardMenuHtml(j, opts);
  const thumbImg = thumb
    ? `<img src="${thumb}" alt="" loading="lazy"
        onload="this.previousElementSibling.classList.add('hidden')"
        onerror="this.style.display='none'">`
    : "";
  return `<article class="project-card ${j.status}${compact ? " compact" : ""}${enter ? " pc-enter" : ""}" data-card-id="${safeId}" data-card-sig="${escapeHtml(cardSig(j, opts))}">
    <div class="pc-thumb">
      <div class="pc-thumb-fallback${thumb ? "" : " skeleton"}">${fmt || "9:16"}</div>
      ${thumbImg}
    </div>
    <div class="pc-body">
      <div class="pc-top${pronto ? " empilhado" : ""}">
        <div class="pc-title-block">
          <button type="button" class="pc-name pc-name-btn" data-act="rename" data-id="${safeId}"
            data-title="${escapeHtml(title)}" title="Clique para renomear">${escapeHtml(title)}</button>
          ${pronto ? "" : (metaBits.length ? `<div class="pc-when">${escapeHtml(metaBits.join(" · "))}</div>` : "")}
        </div>
        <span class="chip ${escapeHtml(tone)}">${escapeHtml(chipLabel)}</span>
      </div>
      ${pronto ? "" : (headline ? `<div class="pc-msg">${escapeHtml(headline)}</div>` : "")}
      ${pronto ? fichaHtml(j) : ""}
      ${avisoIaHtml(j)}
      ${progress}
      <div class="pc-actions">
        ${primary}
        ${(() => { const s = stuckActionsHtml(j, safeId); return s ? `<span class="pc-stuck" data-stuck-sig="${escapeHtml(s)}">${s}</span>` : ""; })()}
        ${menu}
      </div>
    </div>
  </article>`;
}

function closeCardMenus(scope) {
  const hosts = scope ? $$("[data-menu-host]", scope) : $$("[data-menu-host]");
  const ids = scope ? new Set(hosts.map((h) => h.dataset.menuHost)) : null;
  $$(".pc-menu").forEach((m) => {
    const id = m.dataset.menu || "";
    if (ids && !ids.has(id)) return;
    m.classList.add("hidden");
    m.classList.remove("pc-menu-open");
    m.style.top = "";
    m.style.left = "";
    if (m.dataset.parked === "1") {
      const host = document.querySelector(`[data-menu-host="${CSS.escape(id)}"]`);
      if (host) host.appendChild(m);
      delete m.dataset.parked;
    }
  });
  const btns = scope ? $$(".pc-more-btn[aria-expanded='true']", scope) : $$(".pc-more-btn[aria-expanded='true']");
  btns.forEach((b) => b.setAttribute("aria-expanded", "false"));
}

function openCardMenu(btn) {
  const id = btn.dataset.id;
  const key = btn.dataset.menuKey || id;
  if (!id || !key) return;
  const host = btn.closest(".pc-more") || document.querySelector(`[data-menu-host="${CSS.escape(key)}"]`);
  const menu = (host && host.querySelector(".pc-menu"))
    || document.querySelector(`.pc-menu[data-menu="${CSS.escape(key)}"]`);
  if (!menu) return;
  const alreadyOpen = menu.dataset.parked === "1" && !menu.classList.contains("hidden");
  closeCardMenus();
  if (alreadyOpen) return;

  document.body.appendChild(menu);
  menu.dataset.parked = "1";
  menu.classList.remove("hidden");
  menu.classList.add("pc-menu-open");
  btn.setAttribute("aria-expanded", "true");

  const r = btn.getBoundingClientRect();
  const mw = Math.max(menu.offsetWidth || 0, 176);
  const mh = menu.offsetHeight || 168;
  const pad = 8;
  let top = r.bottom + 6;
  let left = r.right - mw;
  if (top + mh > window.innerHeight - pad) top = r.top - mh - 6;
  if (left < pad) left = pad;
  if (left + mw > window.innerWidth - pad) left = window.innerWidth - pad - mw;
  top = Math.min(Math.max(pad, top), Math.max(pad, window.innerHeight - pad - mh));
  left = Math.min(Math.max(pad, left), Math.max(pad, window.innerWidth - pad - mw));
  menu.style.top = `${Math.round(top)}px`;
  menu.style.left = `${Math.round(left)}px`;
}

/* Quantos videos a EMPRESA ATIVA esconde nesta lista (5.0.12). Vazio por
 * filtro de empresa nao e vazio por falta de video: com "Uander" ativa e
 * 291 videos na Prime Camp, o Inicio dizia "seus videos aparecem aqui
 * assim que o primeiro ficar pronto". */
function escondidosPorEmpresa(view) {
  if (state.wsMarca === "all" || !(state.brandActive && state.brandActive.id)) return 0;
  const outros = (state.jobs || []).filter((x) => !jobNaMarca(x));
  if (view === "fila") return outros.filter(jobInFila).length;
  if (view === "done") return outros.filter((x) => x.status === "done").length;
  return outros.length;
}

function renderInto(boxId, emptyId, jobs, opts) {
  const _vazio = emptyId ? $(`#${emptyId}`) : null;
  // o texto de fabrica ('Nenhum video pronto ainda.') so existe no
  // HTML; guardar antes de escrever por cima e o que permite voltar
  if (_vazio && !_vazio.dataset.textoOriginal) {
    _vazio.dataset.textoOriginal = _vazio.textContent.trim();
  }
  const box = $(`#${boxId}`);
  if (!box) return;
  const empty = emptyId ? $(`#${emptyId}`) : null;
  const sig = jobs.map((j) => cardSig(j, opts)).join("\n");
  if (!jobs.length) {
    // Vazio por BUSCA nao e vazio por falta de video: dizer "nenhum video
    // pronto ainda" para quem tem 183 e a tela mentindo. (Defeito que a
    // propria busca criou, na 3.94.)
    const termo = String((opts && opts.busca) || "").trim();
    const escondidos = termo ? 0 : escondidosPorEmpresa(String((opts && opts.view) || ""));
    const sigVazio = termo ? `empty:${termo}` : (escondidos ? `empty:emp:${escondidos}:${state.brandActive.id}` : "empty");
    if (box.dataset.cardSig === sigVazio) return;
    closeCardMenus(box);
    box.innerHTML = "";
    box.dataset.cardSig = sigVazio;
    if (empty) {
      empty.classList.remove("hidden");
      if (termo) {
        empty.innerHTML = `Nenhum resultado para <strong></strong>.
          <button type="button" class="ghost-btn ghost-btn--sm" data-limpar-busca="${
            escapeHtml(String((opts && opts.view) || ""))}">Limpar a busca</button>`;
        empty.querySelector("strong").textContent = `“${termo}”`;
      } else if (!state.jobsLoaded) {
        // Antes da primeira resposta do servidor a lista esta vazia porque
        // ainda NAO CHEGOU, nao porque nao existe: dizer "nenhum video
        // pronto" para quem tem 250 e mentir por 2s a cada volta do preview
        // (02/09).
        empty.textContent = "Carregando os vídeos…";
      } else if (escondidos) {
        empty.innerHTML = `Nenhum vídeo de <strong></strong> aqui.
          <button type="button" class="ghost-btn ghost-btn--sm" data-ver-todas>Ver todas as empresas (${escondidos})</button>`;
        empty.querySelector("strong").textContent = state.brandActive.name || state.brandActive.id;
      } else if (empty.dataset.textoOriginal) {
        empty.textContent = empty.dataset.textoOriginal;
      }
    }
    return;
  }
  if (empty) empty.classList.add("hidden");
  if (box.dataset.cardSig === sig) return;
  syncCards(box, jobs, opts);
  box.dataset.cardSig = sig;
}

function syncCards(box, jobs, opts) {
  // Menu aberto vive no body (openCardMenu). Um patch com ele la fora
  // recria o card SEM menu e deixa o antigo orfao — devolve os menus
  // deste box antes de mexer em qualquer card.
  closeCardMenus(box);
  const existing = new Map(
    [...box.querySelectorAll("[data-card-id]")].map((el) => [el.dataset.cardId, el])
  );
  const seen = new Set();
  const nextNodes = [];
  for (const j of jobs) {
    seen.add(String(j.id));
    let el = existing.get(String(j.id));
    const nextSig = cardSig(j, opts);
    if (!el) {
      const wrap = document.createElement("div");
      wrap.innerHTML = cardHtml(j, { ...opts, enter: true });
      el = wrap.firstElementChild;
      el.addEventListener("animationend", () => el.classList.remove("pc-enter"), { once: true });
    } else if (el.dataset.cardSig !== nextSig) {
      patchCard(el, j, opts);
    }
    nextNodes.push(el);
  }
  existing.forEach((el, id) => {
    if (!seen.has(id)) {
      closeCardMenus(el);
      el.remove();
    }
  });
  const current = [...box.querySelectorAll("[data-card-id]")];
  const sameOrder = current.length === nextNodes.length
    && nextNodes.every((el, i) => current[i] === el);
  if (!sameOrder) nextNodes.forEach((el) => box.appendChild(el));
}

function patchCard(el, j, opts) {
  const view = opts && opts.view;
  const copy = queueCopy(j, view);
  const compact = !!(opts && opts.compact);
  // No card PRONTO quem manda e a ficha: a linha de meta, a mensagem e o
  // periodo somem. Declarado AQUI porque o bloco da mensagem, mais abaixo, ja
  // consulta — `const` no meio da funcao dava ReferenceError.
  const pronto = j.status === "done" && !applyBusy(j);
  el.classList.remove("pc-enter");
  el.className = `project-card ${j.status}${compact ? " compact" : ""}`;
  el.dataset.cardId = String(j.id);
  el.dataset.cardSig = cardSig(j, opts);
  const chip = el.querySelector(".chip");
  if (chip) {
    chip.className = `chip ${chipTone(j, view)}`;
    chip.textContent = copy.badge;
  }
  const name = el.querySelector(".pc-name");
  if (name) {
    const title = j.title || j.name || "Vídeo";
    name.textContent = title;
    name.dataset.title = title;
    name.dataset.id = j.id;
  }
  let msg = el.querySelector(".pc-msg");
  if (copy.text && !pronto) {
    if (!msg) {
      msg = document.createElement("div");
      msg.className = "pc-msg";
      const anchor = el.querySelector(".pc-progress") || el.querySelector(".pc-actions");
      if (anchor) anchor.insertAdjacentElement("beforebegin", msg);
      else el.querySelector(".pc-body")?.appendChild(msg);
    }
    msg.textContent = jobHeadline(j, view);
  } else if (msg) {
    msg.remove();
  }
  let ficha = el.querySelector(".pc-ficha");
  if (pronto) {
    const html = fichaHtml(j);
    if (html) {
      const wrap = document.createElement("div");
      wrap.innerHTML = html;
      const nova = wrap.firstElementChild;
      if (ficha) ficha.replaceWith(nova);
      else {
        const anchor = el.querySelector(".pc-progress") || el.querySelector(".pc-actions");
        if (anchor) anchor.insertAdjacentElement("beforebegin", nova);
        else el.querySelector(".pc-body")?.appendChild(nova);
      }
    } else if (ficha) {
      ficha.remove();
    }
    el.querySelector(".pc-msg")?.remove();
    el.querySelector(".pc-periodo")?.remove();
    el.querySelector(".pc-when")?.remove();
    el.querySelector(".pc-top")?.classList.add("empilhado");
  } else {
    if (ficha) ficha.remove();
    el.querySelector(".pc-top")?.classList.remove("empilhado");
  }

  // Duracoes (origem -> entregue) e formato.
  const metaTxt = pronto ? "" : [
    j.durationLabel || duracoesLabel(j),
    j.formatLabel || ((j.hasFinal || j.status === "done" || j.hasCut) ? "9:16" : ""),
  ].filter(Boolean).join(" · ");
  let meta = el.querySelector(".pc-when");
  if (metaTxt) {
    if (!meta) {
      meta = document.createElement("div");
      meta.className = "pc-when";
      el.querySelector(".pc-title-block")?.appendChild(meta);
    }
    meta.textContent = metaTxt;
  } else if (meta) {
    meta.remove();
  }

  // Inicio -> fim (so fora do card pronto — la a ficha ja diz).
  const perTxt = "";
  let per = el.querySelector(".pc-periodo");
  if (perTxt) {
    if (!per) {
      per = document.createElement("div");
      per.className = "pc-periodo";
      const depoisDaMsg = el.querySelector(".pc-msg");
      if (depoisDaMsg) depoisDaMsg.insertAdjacentElement("afterend", per);
      else {
        const anchor = el.querySelector(".pc-progress") || el.querySelector(".pc-actions");
        if (anchor) anchor.insertAdjacentElement("beforebegin", per);
        else el.querySelector(".pc-body")?.appendChild(per);
      }
    }
    per.textContent = perTxt;
  } else if (per) {
    per.remove();
  }

  // O menu era congelado no estado em que o card nasceu. Refeito aqui — menos
  // quando esta ABERTO, para nao sumir debaixo do clique do usuario.
  const host = el.querySelector(".pc-more");
  if (host && !host.querySelector(".pc-menu:not(.hidden)")) {
    const wrap = document.createElement("div");
    wrap.innerHTML = cardMenuHtml(j, opts);
    const novoMenu = wrap.firstElementChild;
    if (novoMenu) host.replaceWith(novoMenu);
  }

  patchCardProgress(el, j);
  const actions = el.querySelector(".pc-actions");
  if (actions) {
    const busy = j.status === "processing" || j.status === "queued" || j.status === "importing";
    const links = jobLinks(j);
    const first = actions.querySelector(":scope > a.chip-btn, :scope > button.chip-btn");
    if (j.status === "done" || applyBusy(j)) {
      const canFinal = j.hasFinal || j.status === "done";
      const href = links.final;
      const updating = applyBusy(j);
      const label = updating ? "Ver anterior" : "Visualizar";
      if (!first || first.tagName !== "A" || first.dataset.viewFinal !== "1") {
        const a = document.createElement("a");
        a.className = "chip-btn primary";
        a.href = href;
        a.dataset.viewFinal = "1";
        a.textContent = label;
        a.title = updating ? "Ainda estou atualizando este vídeo. Este é o final anterior." : "";
        if (!canFinal) a.classList.add("disabled");
        if (first) first.replaceWith(a);
        else actions.insertBefore(a, actions.firstChild);
      } else {
        first.href = href;
        first.textContent = label;
        first.className = "chip-btn primary";
        first.title = updating ? "Ainda estou atualizando este vídeo. Este é o final anterior." : "";
        first.classList.toggle("disabled", !canFinal);
      }
    } else {
      // Mesmo rótulo que o cardHtml usaria — senão o patch reescreve o botão
      // de "Importar de novo" (arquivo quebrado) de volta para "Tentar novamente".
      const act = busy ? "cancel" : (isDeadEnd(j) ? "reimport" : "retry");
      const label = busy ? "Cancelar" : (isDeadEnd(j) ? "Importar de novo" : "Tentar novamente");
      const cls = act === "reimport" ? "chip-btn primary" : "chip-btn";
      if (first && (first.tagName === "A" || first.dataset.act === "open-final")) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = cls;
        b.dataset.act = act;
        b.dataset.id = j.id;
        b.textContent = label;
        first.replaceWith(b);
      } else if (first) {
        first.className = cls;
        first.dataset.act = act;
        first.dataset.id = j.id;
        first.textContent = label;
      }
    }
    // Botões de saída (Aplicar de novo / Dispensar / Apagar) aparecem e somem
    // junto com o aviso — o patch precisa acompanhar, senão sobra botão morto.
    const stuckWanted = stuckActionsHtml(j, escapeHtml(j.id));
    const stuckHost = actions.querySelector(".pc-stuck");
    if (stuckWanted) {
      if (stuckHost) {
        if (stuckHost.dataset.stuckSig !== stuckWanted) {
          stuckHost.innerHTML = stuckWanted;
          stuckHost.dataset.stuckSig = stuckWanted;
        }
      } else {
        const span = document.createElement("span");
        span.className = "pc-stuck";
        span.innerHTML = stuckWanted;
        span.dataset.stuckSig = stuckWanted;
        const anchor = actions.querySelector(":scope > a.chip-btn, :scope > button.chip-btn");
        if (anchor) anchor.after(span);
        else actions.insertBefore(span, actions.firstChild);
      }
    } else if (stuckHost) {
      stuckHost.remove();
    }
  }
  const img = el.querySelector(".pc-thumb img");
  const fallback = el.querySelector(".pc-thumb-fallback");
  const src = cardThumbSrc(j);
  if (src) {
    if (fallback) fallback.classList.remove("skeleton");
    if (img) {
      if (img.getAttribute("src") !== src) img.src = src;
    } else {
      const node = document.createElement("img");
      node.alt = "";
      node.loading = "lazy";
      node.onload = () => fallback?.classList.add("hidden");
      node.onerror = () => { node.style.display = "none"; };
      node.src = src;
      el.querySelector(".pc-thumb")?.appendChild(node);
    }
  } else if (fallback) {
    fallback.classList.add("skeleton");
    fallback.classList.remove("hidden");
  }
}

/* "Comece por aqui" (5.0.11): guia de 3 passos so enquanto nao ha video
 * nenhum. O estado de cada passo vem do que ja existe: perfil da empresa
 * ativa, alguma aula concluida, algum video. */
const COMECE_KEY = "ativavid.comece.ocultar";
function renderComece() {
  const box = $("#comece");
  if (!box) return;
  let oculto = false;
  try { oculto = localStorage.getItem(COMECE_KEY) === "1"; } catch { /* ignore */ }
  const mostrar = !oculto && !!state.jobsLoaded && (state.jobs || []).length === 0;
  box.classList.toggle("hidden", !mostrar);
  if (!mostrar) return;
  const feitos = {
    empresa: !!(state.brandActive && state.brandActive.perfilOk),
    aula: !!(state.aulas && state.aulas.feitas && state.aulas.feitas.size > 0),
    video: false,
  };
  for (const li of box.querySelectorAll("[data-passo]")) {
    const ok = !!feitos[li.dataset.passo];
    li.classList.toggle("feito", ok);
    const n = li.querySelector(".comece-n");
    if (n) n.textContent = ok ? "✓" : String([...li.parentElement.children].indexOf(li) + 1);
  }
}

function wireComece() {
  const box = $("#comece");
  if (!box || box.dataset.wired) return;
  box.dataset.wired = "1";
  $("#comeceOcultar")?.addEventListener("click", () => {
    try { localStorage.setItem(COMECE_KEY, "1"); } catch { /* ignore */ }
    box.classList.add("hidden");
  });
  $("#comeceImportar")?.addEventListener("click", () => $("#btnPick")?.click());
}

function renderJobs() {
  renderComece();
  const fila = filterJobs("fila");
  const done = filterJobs("done");
  setCount("#countFila", fila.length);
  setCount("#countDone", done.length);
  const verFila = $("#btnVerFila");
  if (verFila) {
    const busy = state.jobs.filter((j) =>
      ["importing", "queued", "processing"].includes(j.status) || applyBusy(j)
    ).length;
    verFila.textContent = busy ? `Ver fila (${busy})` : "Ver fila";
    // Fila vazia: o botao leva a outra tela vazia — pior que botao
    // nenhum. Some junto com a lista.
    verFila.classList.toggle("hidden", !fila.length);
  }

  const counts = state.jobs.reduce((a, j) => {
    a[j.status] = (a[j.status] || 0) + 1;
    return a;
  }, {});
  setCount("#countProjetos", jobsDoWorkspace().length);
  const meta = $("#queueMeta");
  if (meta) {
    const workView = ["import", "fila", "done", "projetos"].includes(state.view);
    meta.hidden = !workView;
    if (state.jobs.length) {
      meta.innerHTML = Object.entries(counts).map(([k, v]) =>
        `<button type="button" class="meta-jump" data-view="${k === "done" ? "done" : "fila"}">${v} ${escapeHtml(STATUS_LABEL[k] || k)}</button>`
      ).join(`<span class="meta-dot">·</span>`);
      if (!meta.dataset.wired) {
        meta.dataset.wired = "1";
        meta.addEventListener("click", (e) => {
          const b = e.target.closest("[data-view]");
          if (b) setView(b.dataset.view);
        });
      }
    } else {
      meta.textContent = "Nenhum projeto";
    }
  }

  renderHomeNow();
  renderInto("jobListRecent", "emptyRecent", filterJobs("recent"),
             { compact: true, view: "recent" });
  renderInto("jobListFila", "emptyFila", fila, { view: "fila" });
  renderInto("jobListDone", "emptyDone", done,
             { view: "done", busca: state.doneBusca });
  if (state.view === "projetos") {
    renderInto("jobListProjetos", "emptyProjetos",
               filterJobs("projetos"),
               { view: "projetos", busca: state.projBusca });
  }
}

function wireProjetos() {
  const seg = $("#projFilter");
  if (seg && !seg.dataset.wired) {
    seg.dataset.wired = "1";
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("[data-proj]");
      if (!b) return;
      state.projFilter = b.dataset.proj;
      seg.querySelectorAll("[data-proj]").forEach((x) => {
        const on = x === b;
        x.classList.toggle("on", on);
        x.setAttribute("aria-selected", on ? "true" : "false");
      });
      renderJobs();
    });
  }
  const busca = $("#projSearch");
  if (busca && !busca.dataset.wired) {
    busca.dataset.wired = "1";
    busca.addEventListener("input", () => {
      state.projBusca = busca.value;
      buscarNaFala(busca.value);
      renderJobs();
    });
  }
  const ordem = $("#doneSort");
  if (ordem && !ordem.dataset.wired) {
    ordem.dataset.wired = "1";
    ordem.value = state.doneSort;
    ordem.addEventListener("change", () => {
      state.doneSort = ordem.value;
      try { localStorage.setItem(DONE_SORT_KEY, state.doneSort); } catch { /* sem storage */ }
      renderJobs();
    });
  }
  const buscaDone = $("#doneSearch");
  if (buscaDone && !buscaDone.dataset.wired) {
    buscaDone.dataset.wired = "1";
    buscaDone.addEventListener("input", () => {
      state.doneBusca = buscaDone.value;
      buscarNaFala(buscaDone.value);
      renderJobs();
    });
  }
}

// Faixa "Agora": o que está rodando, com a FASE real (o message do job já é
// o rótulo do estágio do pipeline) e a barra. Com trabalho ativo o hero de
// importar encolhe (classe home-working no body) — o palco é do progresso.
function renderHomeNow() {
  const host = $("#homeNow");
  if (!host) return;
  const actives = state.jobs.filter((j) =>
    ["importing", "queued", "processing"].includes(j.status) || applyBusy(j));
  document.body.classList.toggle("home-working", actives.length > 0);
  if (!actives.length) {
    host.classList.add("hidden");
    host.innerHTML = "";
    return;
  }
  host.classList.remove("hidden");
  const sig = actives.map((j) => `${j.id}|${j.message}|${j.progress || ""}`).join("~");
  if (host.dataset.sig === sig) return;
  host.dataset.sig = sig;
  // TODAS as ativas, nao as tres primeiras: cortar em 3 e resumir o resto
  // em "+2 na fila" escondia justamente o que o usuario quer olhar quando
  // manda varios videos de uma vez (pedido de 27/08). A lista rola dentro
  // do proprio painel, entao 20 na fila nao empurram a tela.
  const titulo = actives.length > 1
    ? `Agora <span class="home-now-count">${actives.length} na fila</span>`
    : "Agora";
  // Guarda onde a lista estava: o painel repinta a cada tick de progresso e
  // sem isto a rolagem voltava ao topo sozinha — com a fila longa (o caso
  // que a 3.16 quis atender) ficava impossivel olhar o fim da lista.
  const rolagem = host.querySelector(".home-now-list")?.scrollTop || 0;
  host.innerHTML = `<div class="home-now-title">${titulo}</div>`
    + `<div class="home-now-list">` + actives.map((j) => `
    <div class="home-now-row" data-id="${escapeHtml(j.id)}">
      <div class="home-now-name">${escapeHtml(displayTitle(j))}</div>
      <div class="home-now-stage">${escapeHtml(j.message || "Processando…")}</div>
      ${cardProgressHtml(j)}
    </div>`).join("") + `</div>`;
  const lista = host.querySelector(".home-now-list");
  if (lista && rolagem) lista.scrollTop = rolagem;
  if (!host.dataset.wired) {
    host.dataset.wired = "1";
    host.addEventListener("click", (e) => {
      const b = e.target.closest("[data-view]");
      if (b) setView(b.dataset.view);
    });
  }
}

function applyAckKey(qa) {
  const id = qa && (qa.taskId || qa.finishedAt);
  return id ? `ativavid-apply-ack:${id}` : "";
}

function hasApplyAck(qa) {
  if (!qa) return false;
  if (qa.acknowledgedAt) return true;
  const key = applyAckKey(qa);
  if (!key) return false;
  try { return localStorage.getItem(key) === "1"; } catch { return false; }
}

function markApplyAck(qa) {
  if (!qa) return;
  const key = applyAckKey(qa);
  if (key) {
    try { localStorage.setItem(key, "1"); } catch { /* ignore */ }
  }
  fetch("/api/apply-ack", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ taskId: qa.taskId || "", projectId: qa.projectId || "" }),
  }).catch(() => {});
}

function maybeToastApply(prevJobs, nextJobs) {
  const prevMap = new Map((prevJobs || []).map((j) => [String(j.id), j]));
  for (const j of nextJobs || []) {
    const qa = j.quickApply;
    if (!qa || hasApplyAck(qa)) continue;
    const was = (prevMap.get(String(j.id)) || {}).quickApply || {};
    const justFinished = was.status === "running" || was.status === "queued";
    if (!justFinished) continue;
    if (qa.status === "completed") {
      markApplyAck(qa);
      const title = j.title || j.name || "Vídeo";
      toast(`Vídeo atualizado\n${title} está pronto.`, 4500);
    } else if (qa.status === "failed") {
      markApplyAck(qa);
      toast("Não foi possível aplicar as alterações. Seu vídeo anterior foi mantido.", 5000);
    }
  }
}

async function refreshJobs() {
  const data = await api("/api/jobs");
  const incoming = data.jobs || [];
  // "error" fica: o card de importacao que falhou era apagado pelo poll de 2s
  // — o erro piscava e sumia, e o lote parecia nunca ter existido. Ele so sai
  // quando o usuario age (Tentar novamente / Apagar), como qualquer erro.
  const locals = state.jobs.filter(
    (j) => (j.status === "importing" || j.status === "error") && String(j.id).startsWith("tmp-")
  );
  const incomingIds = new Set(incoming.map((j) => j.id));
  const next = [...locals.filter((j) => !incomingIds.has(j.id)), ...incoming];
  maybeToastApply(state.jobs, next);
  state.jobs = next;
  state.jobsLoaded = true;
  // Retrato da lista para a PROXIMA abertura do hub pintar na hora (voltar
  // do preview recarrega a pagina; o /api/jobs leva 1-2s com 250 projetos)
  try { localStorage.setItem("ativavid.jobs.cache", JSON.stringify(incoming)); } catch { /* cheio/bloqueado */ }
  renderJobs();
}

async function refreshHealth() {
  const el = $("#sbHint");
  let ver = null;
  try {
    const h = await api("/api/health");
    ver = String(h.version || "?").replace(/^v/i, "");
    if (h.license) renderLicense(h.license);
  } catch {
    if (el) el.textContent = "Versão sistema: —";
    return;
  }
  applyAppVersion(ver);
}

function applyAppVersion(ver) {
  const v = String(ver || "?").replace(/^v/i, "");
  const el = $("#sbHint");
  if (el) el.textContent = `Versão sistema: ${v}`;
  const label = $("#tbVersionLabel");
  if (label) label.textContent = `v${v}`;
}

function fmtValidUntil(v) {
  if (!v) return "—";
  const raw = String(v).slice(0, 10);
  try {
    const d = new Date(v);
    if (!Number.isNaN(d.getTime())) return d.toLocaleDateString("pt-BR");
  } catch { /* ignore */ }
  return raw;
}

function syncLicenseChrome() {
  const lic = state.license || {};
  const auth = state.auth || {};
  const logged = !!auth.loggedIn;
  const isAdmin = !!(logged && auth.isAdmin);
  const entitled = !!lic.entitled || ["licensed", "account", "trial", "open"].includes(lic.mode);
  const needsPay = !isAdmin && lic.configured && !lic.entitled && lic.mode !== "open";
  // QUEM ESTA NO TESTE TAMBEM PODE COMPRAR. Ate a 4.42 a faixa de compra
  // dependia de `!entitled`, e no trial ele ESTA entitled: quem se
  // convenceu no segundo dia nao tinha botao nenhum: precisava esperar o
  // teste vencer e ser barrado para poder pagar. Venda perdida por
  // desenho.
  const noTeste = lic.mode === "trial";
  const mostraCompra = needsPay || (!isAdmin && lic.configured && noTeste);

  const panel = $("#licenseAdminPanel");
  if (panel) {
    const justOpened = isAdmin && panel.hidden;
    panel.hidden = !isAdmin;
    if (justOpened) {
      loadAccessList().catch(() => {});
      loadDeviceList().catch(() => {});
      // O registro de aberturas ("onde vou ver o log?") mora no mesmo
      // painel: e aqui que ele libera dispositivo e revoga conta.
      loadAberturas().catch(() => {});
      wireAberturas();
    }
  }
  const pay = $("#licAccountStrip");
  if (pay) pay.hidden = !mostraCompra;
  // Sem link configurado o plano levaria a um toast de desculpa; melhor
  // nao existir. Quem ja pagou entra pela conta.
  const btnComprar = $("#btnLicenseCheckout");
  if (btnComprar) btnComprar.hidden = !lic.checkoutUrl;
  const btnMensal = $("#btnLicenseMensal");
  if (btnMensal) btnMensal.hidden = !lic.checkoutUrlMensal;
  if (mostraCompra) {
    const title = $("#licPayTitle");
    const hint = $("#licPayHint");
    if (title) title.textContent = lic.planLabel || "ATIVAVID Pro";
    if (hint) {
      const d = lic.trialDaysLeft;
      hint.textContent = noTeste
        ? (d === 1
            ? "Seu teste acaba amanhã. Assine agora e não perca o acesso."
            : `Seu teste acaba em ${d ?? "poucos"} dias. Assine agora e não `
              + "perca o acesso.")
        : (lic.message || "Assine ou ative uma chave neste PC.");
    }
    void noTeste;   // os planos falam por si: nome, preco e observacao
  }
}

/* Contato do dono da solucao. Fica no codigo (nao numa tela de ajuste)
 * porque e identidade do produto, nao preferencia de usuario. */
const SUPORTE = {
  dono: "Prime Camp",
  zap: "5519987680453",
  numero: "(19) 98768-0453",
};

/* O cartao de suporte aparece SO com licenca ativa.
 *
 * "pode deixar bem escondido esse numero, apenas pra quem for pagar ou
 * contratar a licenca" (30/08). Teste, bloqueado e sem configuracao nao
 * veem — e `licensed` e o unico estado que significa cliente pagante.
 *
 * A mensagem ja leva o identificador da maquina: e a primeira coisa que
 * o suporte pergunta e o cliente nao sabe onde achar. */
/* O registro de aberturas, agrupado por maquina.
 *
 * "onde vou ver o log?" (30/08). Uma linha por abertura seria ilegivel —
 * o app abre varias vezes por dia. O que responde "esta compartilhando?"
 * e QUANTAS maquinas existem e com que frequencia cada uma abre.
 *
 * Sem o SQL aplicado a tela diz isso, com a instrucao: tabela vazia
 * pareceria defeito. */
async function loadAberturas() {
  const cap = $("#adminAberturasCaption");
  const lista = $("#adminAberturasList");
  const vazio = $("#adminAberturasEmpty");
  const tabela = $("#adminAberturasTable");
  if (!cap || !lista) return;
  let d;
  try {
    d = await api("/api/admin/aberturas");
  } catch {
    return;
  }
  cap.hidden = false;
  lista.hidden = false;
  if (!d || d.ok === false) {
    if (tabela) { tabela.hidden = true; tabela.innerHTML = ""; }
    if (vazio) {
      vazio.hidden = false;
      vazio.textContent = (d && d.message)
        || "Não deu para ler o registro agora.";
    }
    return;
  }
  const linhas = d.maquinas || [];
  if (!linhas.length) {
    if (tabela) { tabela.hidden = true; tabela.innerHTML = ""; }
    if (vazio) {
      vazio.hidden = false;
      vazio.textContent = "Nenhuma abertura registrada ainda — o registro "
        + "começa a chegar quando alguém abrir a versão 4.27 ou mais nova.";
    }
    return;
  }
  if (vazio) vazio.hidden = true;
  if (!tabela) return;
  tabela.hidden = false;
  // O cliente dita o codigo curto; aqui ele encontra a maquina. Sem isto,
  // achar um PC no meio da lista e trabalho de conferir hexadecimal na
  // tela.
  const busca = $("#adminAberturasBusca");
  const caixaBusca = $("#adminAberturasBuscaBox");
  if (caixaBusca) caixaBusca.hidden = linhas.length < 2;
  const filtro = String((busca && busca.value) || "").trim().toLowerCase();
  const visiveis = filtro
    ? linhas.filter((m) => String(m.deviceId || "").toLowerCase().includes(filtro)
        || String(m.host || "").toLowerCase().includes(filtro)
        || String(m.email || "").toLowerCase().includes(filtro)
        || codigoDoPc(m.deviceId).toLowerCase().includes(filtro))
    : linhas;
  // "30/08/2026, 21:59:13" em cada celula empurrava a tabela para fora da
  // caixa. Dia, mes e hora respondem tudo que essa coluna precisa
  // responder; o ano so aparece quando NAO e deste ano.
  const anoAtual = new Date().getFullYear();
  const quando = (iso) => {
    if (!iso) return "—";
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return "—";
    const d = dt.toLocaleDateString("pt-BR", {
      day: "2-digit", month: "2-digit",
      ...(dt.getFullYear() === anoAtual ? {} : { year: "2-digit" }),
    });
    const h = dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    return `${d} ${h}`;
  };
  // Dia e hora curtos: a coluna e estreita e o ano nao ajuda a decidir nada.
  const dia = (iso) => {
    if (!iso) return "—";
    const dt = new Date(iso);
    return Number.isNaN(dt.getTime()) ? "—"
      : dt.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  };
  // O trial comeca no PRIMEIRO CONTATO com o servidor, nao na instalacao.
  // Ver "1a abertura" e "Trial" lado a lado e o que responde "esse PC esta
  // instalado ha dias e ainda mostra 4 dias".
  // STATUS, nao "quanto trial sobra": quem pagou um ano via "acabou" na
  // coluna de trial (print de 04/09). O servidor ja decide o plano.
  const status = (m) => {
    const p = m.plano || {};
    if (p.tipo === "bloqueado") return `<span class="lic-tag-bloq">bloqueado</span>`;
    if (p.tipo === "vencido") return `<span class="lic-tag-bloq">vencido</span>`
      + `<span class="cel-sub">em ${dia(p.ate)}</span>`;
    if (p.tipo === "licenca") return `<span class="lic-tag-ok">${escapeHtml(p.rotulo)}</span>`
      + `<span class="cel-sub">até ${dia(p.ate)}</span>`;
    if (p.tipo === "trial") return `${escapeHtml(p.rotulo)}`
      + `<span class="cel-sub">desde ${dia(m.trialInicio)}</span>`;
    if (p.tipo === "trial_fim") return `<span class="lic-tag-bloq">trial acabou</span>`;
    return "—";
  };
  if (!visiveis.length) {
    tabela.innerHTML = `<p class="hint" style="padding:14px">Nenhum computador `
      + `com "${escapeHtml(filtro)}".</p>`;
    return;
  }
  tabela.innerHTML = `<table class="admin-tbl"><thead><tr>
      <th class="col-maq">Máquina</th><th class="col-quem">Quem</th>
      <th class="col-n">Aberturas</th><th class="col-data">1ª abertura</th>
      <th class="col-data">Última</th><th class="col-trial">Status</th>
      <th class="col-ver">Versão</th><th class="col-acao"></th>
    </tr></thead><tbody>${visiveis.map((m) => {
      // O e-mail (conta vinculada, liberacao ou login na abertura) e o que
      // responde "de quem e esse PC?" — vem do servidor, mesmo sem
      // nenhuma abertura no log.
      const nome = escapeHtml(m.email || m.host || "—");
      const quem = escapeHtml([m.email ? m.host : null, m.usuario, m.licenca]
        .filter(Boolean).join(" · ") || "—");
      const acao = m.bloqueado ? "unblock" : "block";
      const rotulo = m.bloqueado ? "Desbloquear" : "Bloquear";
      const classe = m.bloqueado ? "ghost-btn ghost-btn--sm" : "ghost-btn ghost-btn--sm preset-del";
      const id = escapeHtml(m.deviceId || "");
      return `<tr${m.bloqueado ? ' class="is-bloqueado"' : ""}>
        <td class="col-maq" title="${id}">
            <strong class="maq-cod">${escapeHtml(codigoDoPc(m.deviceId))}</strong>${
          m.bloqueado ? ' <span class="lic-tag-bloq">bloqueado</span>' : ""}
            <span class="maq-id">${id}</span></td>
        <td class="col-quem" title="${escapeHtml([m.host, m.usuario].filter(Boolean).join(" · "))}">${nome}${
          quem !== "—" ? `<span class="cel-sub">${quem}</span>` : ""}</td>
        <td class="col-n">${m.aberturas || 0}</td>
        <td class="col-data">${quando(m.primeira)}</td>
        <td class="col-data">${quando(m.ultima)}</td>
        <td class="col-trial">${status(m)}</td>
        <td class="col-ver">${escapeHtml(m.versao || "—")}</td>
        <td class="col-acao"><button type="button" class="${classe}" data-bloq="${acao}"
             data-dev="${id}">${rotulo}</button></td>
      </tr>`;
    }).join("")}</tbody></table>`;
}

function wireAberturas() {
  const busca = $("#adminAberturasBusca");
  if (busca && !busca.dataset.wired) {
    busca.dataset.wired = "1";
    busca.addEventListener("input", () => { loadAberturas().catch(() => {}); });
  }
  const tabela = $("#adminAberturasTable");
  if (tabela && !tabela.dataset.wired) {
    tabela.dataset.wired = "1";
    tabela.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-bloq]");
      if (!btn) return;
      const dev = btn.dataset.dev || "";
      const bloquear = btn.dataset.bloq === "block";
      if (bloquear) {
        const ok = await pedirConfirmacao(
          "Bloquear este computador?",
          `O ATIVAVID para de funcionar em ${dev}. Ficar offline ou atrasar `
          + "o relógio não devolve o acesso. Dá para desbloquear aqui mesmo.",
          "Bloquear", true);
        if (!ok) return;
      }
      try {
        const r = await api("/api/admin/devices", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: bloquear ? "block" : "unblock", deviceId: dev,
            motivo: bloquear ? "compartilhamento" : "",
          }),
        });
        if (r && r.ok === false) throw new Error(r.message || "falhou");
        // O bloqueio pode ter sido gravado e mesmo assim nao valer: se o
        // SQL novo nao foi aplicado, o servidor segue respondendo
        // "liberado" e so o app 4.27+ barra. Bloqueio que depende da boa
        // vontade do cliente precisa AVISAR, nao ficar mudo.
        if (r && r.avisoServidor) toast(r.avisoServidor, 9000);
        else toast(bloquear ? "Computador bloqueado" : "Computador liberado");
        await loadAberturas();
      } catch (err) {
        toast(err.message || "Não deu para aplicar");
      }
    });
  }
  const btnLocal = $("#btnAberturasLocal");
  if (btnLocal && !btnLocal.dataset.wired) {
    btnLocal.dataset.wired = "1";
    btnLocal.onclick = async () => {
      try {
        await api("/api/open-path", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: "~/ATIVAVID/aberturas.jsonl" }),
        });
      } catch (e) {
        toast(e.message || "Não achei o registro desta máquina");
      }
    };
  }
}

/* O codigo curto do PC — o que da para ditar no telefone.
 *
 * O id inteiro e `win-8256b455-cd50-4270-b5b2-43...`: ninguem le isso em
 * voz alta sem errar. O primeiro bloco depois do `win-` ja separa as
 * maquinas dele com folga, e o botao Copiar manda o id COMPLETO, que e o
 * que o painel precisa para bloquear ou liberar. */
function codigoDoPc(id) {
  const cru = String(id || "").trim();
  if (!cru) return "";
  const semPrefixo = cru.replace(/^(win|av)-/i, "");
  const bloco = semPrefixo.split("-")[0] || semPrefixo;
  return bloco.slice(0, 8).toUpperCase();
}

/* Escreve o codigo do PC nos dois lugares onde o cliente pode estar: a
 * tela da licenca e a janela que abre quando ele esbarra no bloqueio.
 * Ate a 4.37 nao existia NENHUM: o id so aparecia no dialogo de admin e
 * no botao de suporte de quem ja paga — justamente quem nao precisa
 * pedir nada. */
function mostrarCodigoDoPc(lic) {
  const id = String((lic && lic.deviceId)
    || (state.license && state.license.deviceId) || "");
  const cod = codigoDoPc(id);
  const pares = [["#licenseDevice", "#licPcCod", "#licPcFull"],
                 ["#licDlgPcBox", "#licDlgPcCod", "#licDlgPcFull"]];
  for (const [caixa, elCod, elFull] of pares) {
    const box = $(caixa);
    if (!box) continue;
    box.hidden = !cod;
    const c = $(elCod);
    if (c) c.textContent = cod || "—";
    const f = $(elFull);
    if (f) f.textContent = id;
  }
}

async function copiarCodigoDoPc() {
  const id = String((state.license && state.license.deviceId) || "");
  if (!id) return;
  try {
    await navigator.clipboard.writeText(id);
    toast("Código do computador copiado — cole na mensagem do suporte");
  } catch {
    toast("Não consegui copiar. O código está na tela, abaixo do botão.");
  }
}

function renderSuporte(lic) {
  const box = $("#licSuporte");
  if (!box) return;
  // `licensed` (chave) e `account` (assinatura) sao os dois estados de
  // cliente pagante. `trial` e `open` NAO: um esta testando, o outro e
  // maquina sem licenca exigida.
  const modo = String((lic && lic.mode) || "");
  const pago = !!(lic && lic.entitled) && (modo === "licensed" || modo === "account");
  box.hidden = !pago;
  if (!pago) return;
  const num = $("#licSuporteNum");
  if (num) num.textContent = SUPORTE.numero;
  const btn = $("#btnSuporteZap");
  if (btn) {
    const quem = (lic && (lic.accountEmail || lic.licenseKeyHint)) || "";
    const msg = `Ola! Suporte ATIVAVID.\nMaquina: ${(lic && lic.deviceId) || "?"}`
      + (quem ? `\nConta: ${quem}` : "")
      + `\nVersao: ${(lic && lic.appVersion) || ""}`;
    btn.href = `https://wa.me/${SUPORTE.zap}?text=${encodeURIComponent(msg)}`;
    btn.target = "_blank";
  }
}

function renderLicense(lic) {
  // O ESTADO entra primeiro, antes de qualquer desenho. O `return` logo
  // abaixo (quando o painel de Licenca ainda nao existe na tela) deixava
  // `state.license` velho: a janela do bloqueio mostrava os planos, porque
  // ela usa o payload recem-chegado, e o clique ia buscar o link no estado
  // vazio — "Assinatura indisponivel agora" com o link configurado.
  state.license = lic;
  renderSuporte(lic);
  mostrarCodigoDoPc(lic);
  const hint = $("#licenseHint");
  const device = null;   // o codigo do PC agora mora em mostrarCodigoDoPc
  const badge = $("#licenseBadge");
  const card = $("#licenseStatusCard");
  if (!hint) return;
  const mode = lic.mode || "open";
  const upd = lic.update || {};
  const until = fmtValidUntil(lic.validUntil);
  let badgeText = "—";
  let tone = "neutral";
  let title = "Carregando…";
  if (mode === "update_required" || upd.force) {
    title = upd.message || lic.message || "Atualize o ATIVAVID para continuar.";
    badgeText = "Atualizar";
    tone = "bad";
  } else if (mode === "account") {
    title = `Assinatura ativa até ${until}`;
    badgeText = "Ativa";
    tone = "ok";
  } else if (mode === "open") {
    title = "Modo aberto — licença não exigida neste PC.";
    badgeText = "Aberto";
    tone = "neutral";
  } else if (!lic.configured) {
    // Instalacao sem a config embutida (ou resposta sem o campo): dizer
    // "modo aberto" aqui era mentira num PC que esta BLOQUEADO.
    title = lic.message || "Esta instalação está sem a configuração de licença. Reinstale o ATIVAVID pelo instalador oficial.";
    badgeText = "Sem config";
    tone = "bad";
  } else if (mode === "error") {
    title = lic.message || lic.error || "Não foi possível verificar a licença.";
    badgeText = "Erro";
    tone = "bad";
  } else if (mode === "trial") {
    title = `Trial · ${lic.trialDaysLeft ?? "?"} dia(s) restantes`;
    badgeText = "Trial";
    tone = "warn";
  } else if (mode === "licensed") {
    title = `Licença ativa até ${until}`;
    badgeText = "Ativa";
    tone = "ok";
  } else {
    title = lic.message || "Sem licença ativa";
    badgeText = "Bloqueada";
    tone = "bad";
  }
  if (upd.updateAvailable && !upd.force && (tone === "ok" || tone === "warn")) {
    title += ` · v${String(upd.latestVersion || "").replace(/^v/i, "")} disponível`;
  }
  hint.textContent = title;
  if (badge) badge.textContent = badgeText;
  if (card) card.dataset.tone = tone;
  void device;
  const advDev = $("#licAdvDeviceHint");
  if (advDev && lic.deviceId) {
    advDev.hidden = false;
    advDev.textContent = `Este PC: ${lic.deviceId}`;
  }
  const deviceInput = $("#adminDeviceId");
  if (deviceInput && lic.deviceId && !deviceInput.value) {
    deviceInput.placeholder = lic.deviceId;
  }
  if (state.auth) applyAccountChrome(state.auth);
  else {
    renderWorkspaceCard();
    syncLicenseChrome();
  }
  const soft = $("#updateSoftHint");
  if (soft) {
    if (upd.updateAvailable && !upd.force) {
      soft.hidden = false;
      soft.textContent = upd.message || `Nova versão ${upd.latestVersion || ""} disponível.`;
    } else {
      soft.hidden = true;
    }
  }
}

/* Aviso automatico de versao nova. Guarda a versao dispensada no
 * localStorage: aparecer a cada abertura vira ruido, e ruido treina o
 * usuario a fechar sem ler. */
function avisarVersaoNova(up, atual) {
  const nova = String(up.latestVersion || "").replace(/^v/i, "");
  if (!nova) return;
  let adiada = "";
  try { adiada = localStorage.getItem("ativavid.updateAdiado") || ""; } catch { /* modo restrito */ }
  if (adiada === nova) return;
  openUpdateDialog({
    appVersion: atual,
    update: { ...up, updateAvailable: true, latestVersion: nova },
  });
}

function openUpdateDialog(lic) {
  const dlg = $("#dlgUpdate");
  if (!dlg) return;
  const L = lic || state.license || {};
  const upd = L.update || {};
  state.updateLatest = String(upd.latestVersion || "").replace(/^v/i, "");
  const title = $("#updDlgTitle");
  const hint = $("#updDlgHint");
  const meta = $("#updDlgMeta");
  if (title) {
    title.textContent = upd.force ? "Atualização obrigatória" : "Nova versão disponível";
  }
  if (hint) {
    // O que o usuario precisa saber ANTES de clicar: e um clique so, o
    // Windows vai pedir autorizacao uma vez, e o app volta sozinho.
    hint.textContent = upd.force
      ? (upd.message || L.message || "Atualize para continuar usando o ATIVAVID.")
      : "É um clique: o ATIVAVID fecha, atualiza e reabre sozinho. "
        + "O Windows pede sua autorização uma vez.";
  }
  if (meta) {
    const cur = L.appVersion || upd.appVersion || "";
    const latest = upd.latestVersion || "";
    meta.textContent = [cur && `Atual: v${String(cur).replace(/^v/i, "")}`, latest && `Nova: v${String(latest).replace(/^v/i, "")}`]
      .filter(Boolean)
      .join(" · ") || "";
  }
  // O que muda na versao nova, direto do changelog da release.
  const notas = $("#updDlgNotas");
  if (notas) {
    const lista = Array.isArray(upd.notes) ? upd.notes : [];
    notas.innerHTML = lista.map((x) => `<li>${escapeHtml(x)}</li>`).join("");
    notas.hidden = !lista.length;
  }
  const later = $("#btnUpdLater");
  if (later) later.hidden = !!upd.force;
  // Esconder o "Agora não" nao bastava: o Esc fecha showModal() do mesmo jeito,
  // e ai nao sobrava nenhum caminho visivel para baixar a atualizacao.
  if (!dlg.dataset.escWired) {
    dlg.dataset.escWired = "1";
    dlg.addEventListener("cancel", (e) => {
      if (dlg.dataset.forced === "1") e.preventDefault();
    });
  }
  dlg.dataset.forced = upd.force ? "1" : "0";
  if (!dlg.open) dlg.showModal();
}

/**
 * Atualizar é DENTRO do app: o servidor baixa o instalador e o executa (o
 * instalador derruba o ATIVAVID e o reabre). O navegador só entra se o
 * download falhar.
 *
 * Esta função existe porque o conserto anterior pegou UMA das portas: a
 * pastilha de versão na barra de título continuou mandando para o GitHub
 * ("o botão ao lado do sol e lua ainda baixa em navegador" — 27/08), com
 * a mesma lógica copiada em outro lugar. Agora toda porta chama daqui.
 */
/* Enche a barra ate o instalador assumir. O app so fecha no FIM (o
 * instalador derruba ele para trocar os arquivos), entao a barra cobre
 * justamente o buraco que existia entre o clique e o app voltar. */
async function acompanharAtualizacao() {
  const caixa = $("#updDlgBarra");
  const fill = $("#updDlgBarraFill");
  const txt = $("#updDlgBarraTxt");
  const tubo = caixa && caixa.querySelector(".upd-barra-tubo");
  if (!caixa || !fill) return;
  caixa.hidden = false;
  const notas = $("#updDlgNotas");
  if (notas) notas.hidden = true;
  for (let i = 0; i < 1200; i += 1) {          // ~6 min de teto
    let p = null;
    try { p = await api("/api/update/progresso"); } catch { /* segue */ }
    if (p) {
      if (p.estado === "baixando") {
        const pct = Number(p.pct || 0);
        if (p.total > 0) {
          if (tubo) tubo.classList.remove("indeterminada");
          fill.style.width = `${Math.max(2, pct)}%`;
          const mb = (n) => (Number(n || 0) / 1048576).toFixed(0);
          if (txt) txt.textContent = `Baixando… ${pct}% (${mb(p.baixado)} de ${mb(p.total)} MB)`;
        } else {
          if (tubo) tubo.classList.add("indeterminada");
          if (txt) txt.textContent = "Baixando…";
        }
      } else if (p.estado === "instalando") {
        if (tubo) tubo.classList.remove("indeterminada");
        fill.style.width = "100%";
        if (txt) {
          txt.textContent = "Instalando… o ATIVAVID fecha e reabre sozinho.";
        }
        return true;
      } else if (p.estado === "erro") {
        if (txt) txt.textContent = `Falhou: ${p.erro || "erro no download"}`;
        return false;
      }
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

async function instalarAtualizacao(btn) {
  // Atualizar FECHA o app — e um render no meio recomeça do zero (caso
  // real de 02/09: um vídeo de 11min estava há 55min renderizando e a
  // atualização o reiniciou sem aviso). Com a fila ocupada, avisa antes.
  try {
    const js = await api("/api/jobs");
    const ocupados = (js.jobs || []).filter((j) =>
      j.status === "processing" || j.status === "importing").length;
    if (ocupados > 0) {
      const ok = await pedirConfirmacao(
        "Atualizar agora?",
        `Tem ${ocupados} vídeo${ocupados > 1 ? "s" : ""} sendo editado`
        + ` agora. Atualizar fecha o ATIVAVID e ess${ocupados > 1 ? "es"
          : "e"} vídeo recomeça do zero depois.`,
        "Atualizar mesmo assim", true);
      if (!ok) return false;
    }
  } catch { /* fila indisponível não trava a atualização */ }
  const rotulo = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "Baixando…"; }
  else toast("Baixando a atualização…", 8000);
  try {
    const res = await api("/api/update/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "instalar" }),
    });
    if (!res.ok) throw new Error(res.error || "não deu para baixar");
    if (btn) btn.textContent = "Atualizando…";
    const h = $("#updDlgHint");
    if (h) h.textContent = "Não feche o ATIVAVID — ele fecha e reabre sozinho.";
    if (res.assincrono) {
      const foi = await acompanharAtualizacao();
      if (!foi) throw new Error("o download não terminou");
      return true;
    }
    toast(res.message
      || "Instalador aberto — o app fecha e reabre sozinho.", 6000);
    return true;
  } catch (err) {
    toast(`${err.message} — abrindo o navegador`, 6000);
    await openUpdateDownload(state.license).catch(() => {});
    if (btn) { btn.disabled = false; btn.textContent = rotulo; }
    return false;
  }
}

async function openUpdateDownload(lic) {
  const L = lic || state.license || {};
  const upd = L.update || {};
  let url = "";
  try {
    // O VERIFICADOR primeiro, sempre. `upd.downloadUrl` vem junto da licenca e
    // apontava para a v0.1.24 — uma politica que ficou parada. O aviso dizia
    // "Nova versao 2.50" (do verificador) e o botao baixava a 0.1.24, porque
    // cada metade lia uma fonte diferente. O verificador ja resolve os dois
    // casos: quando o update e OBRIGATORIO ele devolve a URL da propria
    // politica, entao usar so ele nao perde nada.
    try {
      const check = await api("/api/update/check");
      url = (check.downloadUrl || check.releaseUrl || "").trim();
    } catch { /* offline: cai no que veio com a licenca */ }
    if (!url) url = (upd.downloadUrl || "").trim();
    await api("/api/update/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(url ? { url } : {}),
    });
    toast("Abrindo download…");
  } catch (e) {
    toast(e.message || "Não abriu o download");
  }
}

function openLicenseDialog(lic) {
  const dlg = $("#dlgLicense");
  if (!dlg) return;
  const L = lic || state.license || {};
  if (L.mode === "update_required" || (L.update && L.update.force)) {
    openUpdateDialog(L);
    return;
  }
  // 4.94: sem cadastro nao ha trial. A janela vira um convite ("crie sua
  // conta") e nao um bloqueio — quem acabou de instalar nao fez nada errado.
  const cadastro = !!L.signupRequired;
  $("#licDlgTitle").textContent = cadastro
    ? `Crie sua conta para testar ${L.trialDaysTotal || 7} dias grátis`
    : (L.mode === "blocked" ? "Ative o ATIVAVID" : "Licença");
  $("#licDlgHint").textContent = L.message || "Entre com a conta liberada ou escolha um plano.";
  // Plano sem link configurado so levaria a um toast de desculpa; melhor
  // nao existir. Os dois somem juntos? Entao a janela vira so o login.
  const anual = $("#btnLicDlgAnual");
  if (anual) {
    anual.hidden = !L.checkoutUrl;
    anual.dataset.url = L.checkoutUrl || "";
  }
  const mensal = $("#btnLicDlgMensal");
  if (mensal) {
    mensal.hidden = !L.checkoutUrlMensal;
    mensal.dataset.url = L.checkoutUrlMensal || "";
  }
  // Ja logado nao precisa da saida de login.
  const login = $("#btnLicDlgLogin");
  if (login) {
    login.hidden = !!state.auth?.loggedIn;
    login.textContent = cadastro ? "Criar conta grátis" : "Entrar na minha conta";
    login.dataset.modo = cadastro ? "signup" : "login";
  }
  // O codigo do PC ENTRA aqui: e esta janela que abre quando ele esbarra
  // no bloqueio, e e nesse instante que ele precisa dizer quem e.
  mostrarCodigoDoPc(L);
  if (!dlg.open) dlg.showModal();
}

/* A ativacao por CHAVE saiu do app na 4.46, a pedido dele: toda compra
 * cria a conta sozinha pelo webhook da Stripe, e liberar na mao e por
 * conta (Licenca -> Contas, `/api/admin/access`). Sobrava um caminho
 * paralelo, com campo proprio, para a minoria — e ele era o botao
 * vermelho da janela de bloqueio, na frente de "assinar".
 * A rota `/api/license/activate` continua no servidor: chave antiga
 * ja ativada segue valendo, so nao ha mais onde digitar uma nova. */
function openCheckout(url) {
  const u = url || state.license?.checkoutUrl;
  if (!u) {
    // "Configure o Checkout URL em Sistema → Licença" era instrução de
    // desenvolvedor aparecendo para o cliente que clicou em Assinar.
    toast("Assinatura indisponível agora. Fale com o suporte para liberar o acesso.");
    return;
  }
  window.open(u, "_blank", "noopener");
}

function parseProtectedRanges(text) {
  const out = [];
  const chunks = String(text || "").split(/[,;\n]+/);
  for (const chunk of chunks) {
    const m = chunk.trim().match(/(\d{1,2}):(\d{2})(?:\.(\d+))?\s*[-–]\s*(\d{1,2}):(\d{2})(?:\.(\d+))?/);
    if (!m) continue;
    const toSec = (mm, ss, frac) => Number(mm) * 60 + Number(ss) + (frac ? Number(`0.${frac}`) : 0);
    const start = toSec(m[1], m[2], m[3]);
    const end = toSec(m[4], m[5], m[6]);
    if (end > start) out.push({ start, end });
  }
  return out;
}

/* Cartoes que sao PACOTE: uma intencao de corte + um tipo de conteudo,
 * os dois ja existentes no motor. O "Viral" nasceu assim; os tres de
 * 4.23 seguem o mesmo desenho, entao nenhum deles pede codigo novo no
 * planejador — o tipo de conteudo e que muda as regras do corte
 * (`app/content_type.py`).
 *
 * Um `data-intent` que NAO esteja aqui tem de ser um valor de
 * `app/editing_intent.py::INTENTS`, senao o servidor descarta a escolha
 * calado e cai no recomendado. */
const PACOTES_DE_MODO = {
  viral: { intent: "dynamic", tipo: "viral" },
  tutorial: { intent: "dynamic", tipo: "educational" },
  anuncio: { intent: "dynamic", tipo: "ad" },
  depoimento: { intent: "complete", tipo: "review" },
};

function collectImportIntent() {
  const mode = document.querySelector(".intent-card.on")?.dataset.intent || "dynamic";
  const realMode = PACOTES_DE_MODO[mode]?.intent || mode;
  return {
    editingIntent: realMode,
    preserveHook: !!$("#protHook")?.checked,
    preserveCTA: !!$("#protCta")?.checked,
    preserveCompleteSentences: !!$("#protSentence")?.checked,
    preserveContext: !!$("#protContext")?.checked,
    protectedRanges: parseProtectedRanges($("#protRanges")?.value || ""),
    brandStyleSource: $("#useBrandStyle")?.checked ? "default" : "custom",
    contentType: $("#importContentType")?.value || null,
    // Knobs do CORTE na importacao (pedido de 25/08: "mais opcoes de
    // edicao"). Vazio = padrao do modo; ambos ja sao _CUT_STYLE_KEYS, entao
    // mudar num refazer replaneja o corte.
    rhythm: $("#importRhythm")?.value || null,
    speechClean: $("#importSpeechClean")?.value || null,
    brandId: ($("#importBrandSelect")?.value) || state.brandActive?.id || null,
    brandPresetId: $("#importPresetSelect")?.value || null,
    sourceDurationSec: state.pendingDuration || null,
  };
}

function applyIntentDefaults(mode, recommended) {
  const rec = $("#importRecommend");
  if (rec) {
    rec.classList.toggle("hidden", !recommended || recommended !== mode);
    rec.textContent = recommended === mode ? "Recomendado para este vídeo" : "";
  }
  $$(".intent-card").forEach((c) => c.classList.toggle("on", c.dataset.intent === mode));
  const loose = mode === "shorts" || mode === "viral";
  if ($("#protHook")) $("#protHook").checked = !loose;
  if ($("#protCta")) $("#protCta").checked = !loose;
  if ($("#protSentence")) $("#protSentence").checked = true;
  if ($("#protContext")) $("#protContext").checked = true;
  // cartao-pacote também define o tipo de conteúdo — um clique, o pacote todo
  const pacote = PACOTES_DE_MODO[mode];
  if (pacote && $("#importContentType")) $("#importContentType").value = pacote.tipo;
}

// A duracao so serve para RECOMENDAR um preset (>=90s vira "complete"), entao
// desistir e barato. Sem o prazo, porem, nao era: um .MOV que o webview nao
// sabe decodificar — HEVC/HLG do iPhone, que e a maior parte do material real —
// nao dispara `loadedmetadata` NEM `error`, a promessa nunca assentava e o
// `await` em openImportDialog segurava o dialogo para sempre. O usuario via o
// overlay de arraste na tela e nada acontecia.
const PRAZO_DURACAO_MS = 4000;

function probeVideoDuration(file) {
  return new Promise((resolve) => {
    let pronto = false;
    let url = null;
    const encerrar = (valor) => {
      if (pronto) return;
      pronto = true;
      if (url) URL.revokeObjectURL(url);
      resolve(valor);
    };
    try {
      url = URL.createObjectURL(file);
      const v = document.createElement("video");
      v.preload = "metadata";
      v.onloadedmetadata = () => {
        const d = Number(v.duration);
        encerrar(Number.isFinite(d) ? d : null);
      };
      v.onerror = () => encerrar(null);
      setTimeout(() => encerrar(null), PRAZO_DURACAO_MS);
      v.src = url;
    } catch {
      encerrar(null);
    }
  });
}

const VIDEO_EXTS = new Set([".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp", ".mts", ".m2ts"]);
const SKIP_IMPORT_DIRS = new Set(["edit", "node_modules", ".git", "__pycache__", "remotion"]);
const SKIP_IMPORT_FILES = new Set(["cut.mp4", "final.mp4", "base.mp4", "cut_proxy.mp4"]);
const FILE_REL = new WeakMap();

function fileExt(name) {
  const n = String(name || "").toLowerCase();
  const i = n.lastIndexOf(".");
  return i >= 0 ? n.slice(i) : "";
}

function isVideoFile(file) {
  if (!file) return false;
  const name = String(file.name || "").toLowerCase();
  if (SKIP_IMPORT_FILES.has(name) || name.endsWith(".prenorm.mp4")) return false;
  if (VIDEO_EXTS.has(fileExt(name))) return true;
  return String(file.type || "").startsWith("video/");
}

function fileRelPath(file) {
  return String(FILE_REL.get(file) || file.webkitRelativePath || file.relativePath || "").replace(/\\/g, "/");
}

function shouldSkipRel(rel) {
  const parts = String(rel || "").split("/").filter(Boolean);
  return parts.some((p) => SKIP_IMPORT_DIRS.has(p.toLowerCase()) || (p.startsWith(".") && p !== "."));
}

function filterImportVideos(files) {
  return [...files].filter((f) => isVideoFile(f) && !shouldSkipRel(fileRelPath(f)));
}

function fileFolderKey(file) {
  const rel = fileRelPath(file);
  if (!rel || !rel.includes("/")) return "";
  const parts = rel.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

function folderTitle(key, files) {
  if (key) {
    const last = key.split("/").filter(Boolean).pop();
    if (last) return last;
  }
  return friendlyFileTitle(files[0]);
}

function sortVideos(files) {
  return [...files].sort((a, b) => {
    const byName = String(a.name || "").localeCompare(String(b.name || ""), undefined, { numeric: true, sensitivity: "base" });
    if (byName) return byName;
    return (a.lastModified || 0) - (b.lastModified || 0);
  });
}

function groupVideosByFolder(files) {
  const map = new Map();
  for (const f of files) {
    const key = fileFolderKey(f);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(f);
  }
  return [...map.entries()].map(([key, list]) => ({
    key,
    title: folderTitle(key, list),
    files: sortVideos(list),
  }));
}

function planImportBatches(files) {
  const groups = groupVideosByFolder(files);
  const mergeLoose = !!$("#mergeTakes")?.checked;
  const batches = [];
  for (const g of groups) {
    if (g.key) {
      batches.push({
        files: g.files,
        title: g.title,
        merge: g.files.length > 1,
      });
      continue;
    }
    if (mergeLoose && g.files.length > 1) {
      batches.push({
        files: g.files,
        title: `${friendlyFileTitle(g.files[0])} (+${g.files.length - 1})`,
        merge: true,
      });
      continue;
    }
    for (const f of g.files) {
      batches.push({ files: [f], title: friendlyFileTitle(f), merge: false });
    }
  }
  return batches;
}

function readDirEntries(reader) {
  return new Promise((resolve, reject) => {
    const all = [];
    const next = () => {
      reader.readEntries((batch) => {
        if (!batch.length) return resolve(all);
        all.push(...batch);
        next();
      }, reject);
    };
    next();
  });
}

function entryToFile(entry, rel) {
  return new Promise((resolve, reject) => {
    entry.file((file) => {
      FILE_REL.set(file, rel);
      resolve(file);
    }, reject);
  });
}

async function collectEntry(entry, prefix, out) {
  const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
  if (entry.isFile) {
    out.push(await entryToFile(entry, rel));
    return;
  }
  if (!entry.isDirectory) return;
  const name = String(entry.name || "").toLowerCase();
  if (SKIP_IMPORT_DIRS.has(name) || name.startsWith(".")) return;
  const children = await readDirEntries(entry.createReader());
  for (const child of children) await collectEntry(child, rel, out);
}

async function collectDroppedFiles(dt) {
  const items = [...(dt.items || [])];
  const hasDir = items.some((it) => {
    const entry = it.webkitGetAsEntry?.();
    return !!(entry && entry.isDirectory);
  });
  if (hasDir) {
    const listed = [...(dt.files || [])];
    if (listed.length && listed.some((f) => f.webkitRelativePath)) {
      return filterImportVideos(listed);
    }
    // `webkitGetAsEntry()` e `getAsFile()` so valem ANTES do primeiro await: o
    // DataTransfer e neutralizado assim que o handler do drop devolve o
    // controle ao navegador, e dali em diante os dois devolvem null. Como a
    // varredura de pasta e assincrona, a PRIMEIRA pasta consumia o unico
    // momento valido e as demais sumiam sem aviso — arrastando 3 subpastas de
    // uma vez, so uma entrava. Por isso tudo e colhido de uma vez, sincrono.
    const entradas = items.map((it) => ({
      entry: it.webkitGetAsEntry?.() || null,
      file: it.getAsFile?.() || null,
    }));
    const out = [];
    for (const e of entradas) {
      if (e.entry) await collectEntry(e.entry, "", out);
      else if (e.file) out.push(e.file);
    }
    return filterImportVideos(out);
  }
  return filterImportVideos([...(dt.files || [])]);
}

async function openImportDialog(fileList) {
  const files = filterImportVideos(fileList);
  if (!files.length) {
    toast("Nenhum vídeo encontrado nessa pasta");
    return;
  }
  state.pendingFiles = files;
  state.pendingDuration = files.length === 1 ? await probeVideoDuration(files[0]) : null;
  const recommended = (state.pendingDuration || 0) >= 90 ? "complete" : "dynamic";
  state.pendingRecommended = recommended;
  // O destaque NUNCA era resetado: a importacao seguinte herdava o modo da
  // anterior, em silencio. Caso real (24/08): o usuario usou "Edicao leve"
  // ao meio-dia e as importacoes da tarde herdaram o modo leve enquanto ele
  // trocava o TIPO (Viral -> Educativo) esperando o corte mudar -- no modo
  // leve o corte e heuristico e saiu identico tres vezes (70,4s). Cada
  // abertura comeca no recomendado.
  applyIntentDefaults(recommended, recommended);
  const groups = groupVideosByFolder(files);
  const folderGroups = groups.filter((g) => g.key);
  const fromFolder = folderGroups.length > 0;
  const hint = $("#importHint");
  if (hint) {
    if (fromFolder) {
      const merged = folderGroups.filter((g) => g.files.length > 1).length;
      hint.textContent = `${files.length} vídeo${files.length > 1 ? "s" : ""} em ${folderGroups.length} pasta${folderGroups.length > 1 ? "s" : ""}${merged ? ` · ${merged} vão ser juntados` : ""}`;
    } else {
      const names = files.map((f) => f.name).slice(0, 3).join(", ");
      const extra = files.length > 3 ? ` +${files.length - 3}` : "";
      hint.textContent = `${files.length} arquivo${files.length > 1 ? "s" : ""}: ${names}${extra}`;
    }
  }
  const folderHint = $("#importFolderHint");
  if (folderHint) {
    folderHint.classList.toggle("hidden", !fromFolder);
    folderHint.textContent = fromFolder
      ? "Cada subpasta vira um vídeo. Se tiver mais de um arquivo na mesma pasta, eles entram juntos."
      : "";
  }
  const mergeWrap = $("#mergeTakesWrap");
  if (mergeWrap) mergeWrap.classList.toggle("hidden", fromFolder || files.length < 2);
  applyIntentDefaults(recommended, recommended);
  loadImportPresets().catch(() => {});
  try {
    $("#dlgImport").showModal();
  } catch {
    await uploadFiles(files, collectImportIntent());
  }
}

/** A API da janela nativa, quando a tela roda dentro do app. No navegador
 *  comum ela nao existe e tudo cai no `<input type=file>` de sempre. */
function apiNativa() {
  const api = window.pywebview && window.pywebview.api;
  return (api && typeof api.escolher_pasta === "function") ? api : null;
}

/** Multiplicador de criativos: variações de gancho, conteúdo e CTA viram TODAS
 *  as combinações na fila (3×3×3 = 27). Dentro do app os arquivos entram por
 *  CAMINHO (escolher_videos, sem upload); arrastar entrega File e sobe por
 *  multipart — o servidor aceita os dois misturados no mesmo lote. */
const MULTI_PAPEIS = ["gancho", "corpo", "cta"];
const MULTI_TETO = 48;

function wireMultiplicador() {
  const dlg = $("#dlgMulti");
  const btn = $("#btnMultiplicador");
  if (!dlg || !btn) return;
  const itens = { gancho: [], corpo: [], cta: [] };
  const inputM = document.createElement("input");
  inputM.type = "file";
  inputM.accept = "video/*,.mov,.mp4,.m4v,.mkv,.webm";
  inputM.multiple = true;
  let papelAtivo = "gancho";
  let enviando = false;

  const render = () => {
    let total = 1;
    for (const papel of MULTI_PAPEIS) {
      const lista = dlg.querySelector(`.multi-box[data-papel="${papel}"] .multi-lista`);
      lista.innerHTML = "";
      itens[papel].forEach((it, i) => {
        const chip = document.createElement("div");
        chip.className = "multi-chip";
        const nome = document.createElement("span");
        nome.className = "nome";
        nome.textContent = it.name;
        nome.title = it.path || it.name;
        const tirar = document.createElement("button");
        tirar.type = "button";
        tirar.className = "tirar";
        tirar.textContent = "×";
        tirar.title = "Tirar este vídeo";
        tirar.onclick = () => { itens[papel].splice(i, 1); render(); };
        chip.append(nome, tirar);
        lista.appendChild(chip);
      });
      total *= itens[papel].length;
    }
    const completo = MULTI_PAPEIS.every((p) => itens[p].length > 0);
    const conta = $("#multiConta");
    if (conta) {
      if (!completo) {
        conta.textContent = "Arraste vídeos para as caixas ou use Escolher vídeos — precisa de pelo menos 1 em cada.";
      } else if (total > MULTI_TETO) {
        conta.textContent = `${itens.gancho.length} × ${itens.corpo.length} × ${itens.cta.length} = ${total} combinações — passou do teto de ${MULTI_TETO}, tire alguma variação.`;
      } else {
        const min = Math.max(3, Math.round(total * 2.5));
        conta.textContent = `${itens.gancho.length} gancho(s) × ${itens.corpo.length} conteúdo(s) × ${itens.cta.length} CTA(s) = ${total} vídeo${total > 1 ? "s" : ""} na fila (~${min} min de processamento).`;
      }
    }
    const go = $("#btnMultiGo");
    if (go) go.disabled = enviando || !completo || total > MULTI_TETO;
  };

  const addFiles = (papel, fileList) => {
    filterImportVideos(fileList).forEach((f) => itens[papel].push({ name: f.name, file: f }));
    render();
  };

  dlg.querySelectorAll(".multi-box").forEach((box) => {
    const papel = box.dataset.papel;
    box.querySelector(".multi-add").onclick = async () => {
      const nat = apiNativa();
      if (nat && typeof nat.escolher_videos === "function") {
        const paths = (await nat.escolher_videos()) || [];
        for (const p of paths) {
          const name = String(p).split(/[\\/]/).pop();
          if (!itens[papel].some((it) => it.path === p)) itens[papel].push({ name, path: p });
        }
        render();
      } else {
        papelAtivo = papel;
        inputM.click();
      }
    };
    box.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.stopPropagation();
      box.classList.add("drag-over");
    });
    box.addEventListener("dragleave", () => box.classList.remove("drag-over"));
    box.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      box.classList.remove("drag-over");
      if (e.dataTransfer) addFiles(papel, [...(e.dataTransfer.files || [])]);
    });
  });
  inputM.addEventListener("change", () => {
    addFiles(papelAtivo, inputM.files);
    inputM.value = "";
  });

  btn.onclick = () => {
    MULTI_PAPEIS.forEach((p) => { itens[p] = []; });
    enviando = false;
    render();
    dlg.showModal();
    loadMultiPresets().catch(() => {});
  };
  const btnCancel = $("#btnMultiCancel");
  if (btnCancel) btnCancel.onclick = () => dlg.close();

  const btnGo = $("#btnMultiGo");
  if (btnGo) btnGo.onclick = async () => {
    if (enviando) return;
    enviando = true;
    render();
    // A marca e o preset escolhidos na janela valem para TODAS as
    // combinacoes (4.95). `resolve_for_edit` le brandId/brandPresetId do
    // intent de cada projeto — o mesmo caminho do import normal.
    const brandSel = $("#multiBrandSelect");
    const presetSel = $("#multiPresetSelect");
    const intent = {
      editingIntent: "complete",
      preserveHook: true,
      preserveCTA: true,
      preserveCompleteSentences: true,
      preserveContext: true,
      contentType: $("#multiContentType")?.value || "ad",
      brandStyleSource: "default",
      brandId: (brandSel && brandSel.value) || state.brandActive?.id || null,
      brandPresetId: (presetSel && presetSel.value) || null,
    };
    const fd = new FormData();
    const papeis = {};
    for (const papel of MULTI_PAPEIS) {
      papeis[papel] = itens[papel].map((it) => {
        if (it.path) return { caminho: it.path };
        fd.append("file", it.file, it.name);
        return { arquivo: it.name };
      });
    }
    fd.append("papeis", JSON.stringify(papeis));
    fd.append("intent", JSON.stringify(intent));
    btnGo.textContent = "Criando…";
    try {
      const r = await api("/api/multiplicador", { method: "POST", body: fd });
      dlg.close();
      toast(`✓ ${r.total} combinações na fila — gancho → conteúdo → CTA`, 5000);
      setView("fila");
      await refreshJobs();
    } catch (err) {
      toast(err.message || "Falha ao criar as combinações", 5000);
    } finally {
      enviando = false;
      btnGo.textContent = "Criar combinações";
      render();
    }
  };
}

/** Importa por CAMINHO: nada de bytes subindo por HTTP.
 *
 *  O app e desktop e os arquivos ja estao no disco — a tela subia 1,5 GB para
 *  127.0.0.1 para importar o que estava ali do lado. O servidor sempre soube
 *  importar por caminho (`_ingest_paths`, que varre subpasta e faz um video
 *  por pasta); ninguem usava. */
async function importarPorCaminho(paths, intent) {
  const lista = (paths || []).filter(Boolean);
  if (!lista.length) return;
  let plano = null;
  try {
    plano = await api("/api/import-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: lista }),
    });
  } catch { /* o servidor decide de novo na hora de importar */ }
  const grupos = (plano && plano.grupos) || [];
  if (plano && !grupos.length) {
    toast("Nenhum vídeo encontrado nessa pasta");
    return;
  }
  toast(grupos.length > 1
    ? `Importando ${plano.total} vídeo(s) em ${grupos.length} projeto(s)…`
    : "Importando…");
  try {
    const r = await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: lista, intent: intent || null }),
    });
    const n = ((r && r.jobs) || []).length;
    if (!n) throw new Error("não consegui importar nenhum vídeo desses caminhos");
    setView("fila");
  } catch (err) {
    toast(err.message || "Falha ao importar");
  }
  await refreshJobs();
}

/** Abre o dialogo de importacao para CAMINHOS (sem File objects). */
async function abrirImportPorCaminho(paths) {
  const lista = (paths || []).filter(Boolean);
  if (!lista.length) return;
  let plano = null;
  try {
    plano = await api("/api/import-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: lista }),
    });
  } catch { /* segue sem o resumo */ }
  const grupos = (plano && plano.grupos) || [];
  if (plano && !grupos.length) {
    toast("Nenhum vídeo encontrado nessa pasta");
    return;
  }
  state.pendingFiles = null;
  state.pendingPaths = lista;
  state.pendingDuration = null;
  const recommended = "dynamic";
  state.pendingRecommended = recommended;
  const hint = $("#importHint");
  if (hint) {
    hint.textContent = grupos.length
      ? `${plano.total} vídeo${plano.total > 1 ? "s" : ""} → ${grupos.length} projeto${grupos.length > 1 ? "s" : ""}`
      : `${lista.length} item(ns) selecionado(s)`;
  }
  const folderHint = $("#importFolderHint");
  if (folderHint) {
    const juntos = grupos.filter((g) => g.n > 1).length;
    folderHint.classList.remove("hidden");
    folderHint.textContent = juntos
      ? `Cada subpasta vira um vídeo — ${juntos} com mais de um arquivo entram juntos.`
      : "Cada subpasta vira um vídeo.";
  }
  const mergeWrap = $("#mergeTakesWrap");
  if (mergeWrap) mergeWrap.classList.add("hidden");
  applyIntentDefaults(recommended, recommended);
  loadImportPresets().catch(() => {});
  try {
    $("#dlgImport").showModal();
  } catch {
    await importarPorCaminho(lista, collectImportIntent());
  }
}

function friendlyFileTitle(file) {
  return String(file?.name || "Vídeo").replace(/\.[^.]+$/, "") || "Vídeo";
}

function captureFilePoster(file, tmpId) {
  if (!file || !String(file.type || "").startsWith("video/")) return;
  try {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.muted = true;
    v.preload = "metadata";
    const done = (poster) => {
      URL.revokeObjectURL(url);
      const job = state.jobs.find((j) => j.id === tmpId);
      if (!job || job.status !== "importing") return;
      if (poster) job.localPoster = poster;
      renderJobs();
    };
    v.onloadeddata = () => {
      try {
        v.currentTime = Math.min(0.4, (v.duration || 1) * 0.05);
      } catch {
        done(null);
      }
    };
    v.onseeked = () => {
      try {
        const c = document.createElement("canvas");
        const w = v.videoWidth || 360;
        const h = v.videoHeight || 640;
        c.width = 360;
        c.height = Math.max(1, Math.round(360 * (h / w)));
        c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
        done(c.toDataURL("image/jpeg", 0.72));
      } catch {
        done(null);
      }
    };
    v.onerror = () => done(null);
    v.src = url;
  } catch { /* ignore */ }
}

function postFormProgress(url, formData, { onProgress, tmpId } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    if (tmpId) state.uploads[tmpId] = xhr;
    xhr.open("POST", url);
    xhr.upload.onprogress = (e) => {
      if (typeof onProgress !== "function") return;
      if (e.lengthComputable && e.total > 0) onProgress(e.loaded / e.total);
      else onProgress(null);
    };
    xhr.onload = () => {
      if (tmpId) delete state.uploads[tmpId];
      let data = {};
      try { data = JSON.parse(xhr.responseText || "{}"); } catch { data = {}; }
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data });
    };
    xhr.onerror = () => {
      if (tmpId) delete state.uploads[tmpId];
      // "falha no upload" e o que ele viu no PC bloqueado (31/08): a
      // conexao caiu no meio do envio e o motivo verdadeiro — licenca —
      // estava no corpo do 403 que nunca chegou. Quando o app JA sabe
      // que a licenca nao vale, o recado e esse, nao "upload".
      const L = state.license || {};
      if (L.configured && L.entitled === false) {
        reject(Object.assign(
          new Error(L.message || "Licença bloqueada — ative para continuar"),
          { licenca: L }));
        return;
      }
      reject(new Error("a conexão caiu no meio do envio"));
    };
    xhr.onabort = () => {
      if (tmpId) delete state.uploads[tmpId];
      reject(Object.assign(new Error("cancelado"), { aborted: true }));
    };
    xhr.send(formData);
  });
}

function upsertLocalJob(job) {
  const i = state.jobs.findIndex((j) => j.id === job.id);
  if (i >= 0) state.jobs[i] = { ...state.jobs[i], ...job };
  else state.jobs.unshift(job);
}

function removeLocalJob(id) {
  state.jobs = state.jobs.filter((j) => j.id !== id);
  delete state.uploads[id];
}

async function uploadFiles(fileList, intent) {
  const files = [...fileList];
  if (!files.length) return;
  try {
    const lic = await api("/api/license");
    renderLicense(lic);
    if (lic.configured && !lic.entitled) {
      if (lic.mode === "update_required" || lic.update?.force) {
        openUpdateDialog(lic);
        toast("Atualize o app para editar");
      } else {
        openLicenseDialog(lic);
        toast("Precisa de licença para editar");
      }
      return;
    }
  } catch { /* ignore — servidor decide */ }
  const batches = planImportBatches(files);
  if (!batches.length) {
    toast("Nenhum vídeo encontrado nessa pasta");
    return;
  }
  const now = Date.now();
  const locals = batches.map((b, i) => ({
    id: `tmp-${now}-${i}`,
    name: b.title,
    title: b.title,
    status: "importing",
    progress: 0,
    createdAt: new Date(now - i).toISOString(),
    updatedAt: new Date(now - i).toISOString(),
    hasThumb: false,
    _files: b.files,
    _merge: !!b.merge,
  }));
  locals.forEach((job, i) => {
    upsertLocalJob(job);
    captureFilePoster(batches[i].files[0], job.id);
  });
  renderJobs();
  const merged = batches.filter((b) => b.merge).length;
  toast(
    merged
      ? `Importando ${files.length} vídeos em ${batches.length} pasta${batches.length > 1 ? "s" : ""}…`
      : `Importando ${files.length} vídeo${files.length > 1 ? "s" : ""}…`
  );

  for (const local of locals) {
    if (!state.jobs.some((j) => j.id === local.id)) continue;
    const fd = new FormData();
    for (const f of local._files) fd.append("files", f, f.name);
    if (intent) fd.append("intent", JSON.stringify(intent));
    if (local.title) fd.append("title", local.title);
    try {
      const { ok, status, data } = await postFormProgress(
        `/api/jobs${local._merge ? "?merge=1" : ""}`,
        fd,
        {
          tmpId: local.id,
          onProgress: (ratio) => {
            const job = state.jobs.find((j) => j.id === local.id);
            if (!job || job.status !== "importing") return;
            job.progress = ratio == null ? null : Math.round(ratio * 100);
            if (uploadFiles._progressRaf) return;
            uploadFiles._progressRaf = requestAnimationFrame(() => {
              uploadFiles._progressRaf = 0;
              renderJobs();
            });
          },
        }
      );
      if (status === 403 && (data.error === "license_required" || data.error === "update_required")) {
        renderLicense(data.license || {});
        if (data.error === "update_required" || data.license?.update?.force) openUpdateDialog(data.license);
        else openLicenseDialog(data.license);
        removeLocalJob(local.id);
        renderJobs();
        toast(data.error === "update_required" ? "Atualização obrigatória" : "Licença necessária");
        return;
      }
      if (!ok) throw new Error(data.error || "falha no upload");
      const created = (data.jobs || [])[0];
      if (!created) {
        // O servidor respondeu sem criar nada. Antes o card era removido em
        // silencio e o lote sumia da tela sem uma palavra — quem arrastou uma
        // pasta so notava contando os videos depois.
        throw new Error(
          data.error || `Não consegui importar "${local.title || "esse lote"}"`
        );
      }
      if (created) {
        const prev = state.jobs.find((j) => j.id === local.id) || {};
        removeLocalJob(local.id);
        upsertLocalJob({
          ...created,
          createdAt: prev.createdAt || created.createdAt,
          localPoster: prev.localPoster,
          status: created.status === "queued" ? "queued" : created.status,
        });
      } else {
        removeLocalJob(local.id);
      }
      renderJobs();
    } catch (err) {
      if (err.aborted) {
        removeLocalJob(local.id);
        renderJobs();
        continue;
      }
      // POR QUE falhou? Uma importacao recusada por licenca podia chegar
      // aqui de varias formas (403 sem corpo, conexao caindo no meio,
      // resposta vazia) e todas viravam o mesmo card vermelho com "falha
      // no upload" — que foi o que ele viu no PC bloqueado (31/08), sem
      // uma palavra sobre licenca. Perguntar custa um GET pequeno e so
      // acontece quando algo ja deu errado.
      const lic = err.licenca || await api("/api/license").catch(() => null);
      if (lic && lic.configured && lic.entitled === false) {
        renderLicense(lic);
        if (lic.mode === "update_required" || lic.update?.force) openUpdateDialog(lic);
        else openLicenseDialog(lic);
        removeLocalJob(local.id);
        renderJobs();
        toast(lic.message || "Licença bloqueada — ative para continuar", 7000);
        return;
      }
      const job = state.jobs.find((j) => j.id === local.id);
      if (job) {
        job.status = "error";
        job.message = err.message || "Falha ao importar";
        job.progress = null;
      }
      renderJobs();
      toast(err.message);
    }
  }
  await refreshJobs();
}

function wireDrop() {
  const zone = $("#dropZone");
  const input = $("#fileInput");
  const folderInput = $("#folderInput");
  $("#btnPick").onclick = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const nat = apiNativa();
    if (nat) {
      const paths = await nat.escolher_videos();
      if (paths && paths.length) await abrirImportPorCaminho(paths);
      return;
    }
    input.click();
  };
  const btnFolder = $("#btnPickFolder");
  if (btnFolder) {
    btnFolder.onclick = async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const nat = apiNativa();
      if (nat) {
        const paths = await nat.escolher_pasta();
        if (paths && paths.length) await abrirImportPorCaminho(paths);
        return;
      }
      if (folderInput) folderInput.click();
    };
  }
  zone.addEventListener("click", (e) => {
    if (e.target.closest("button")) return;
    input.click();
  });
  // Quem fecha o overlay de arraste precisa ser alcancavel dos DOIS lados.
  // Ele so era escondido pelo handler de `drop` da `window`; mas o drop na
  // propria zona chama stopPropagation() logo abaixo — de proposito, para a
  // pasta nao ser varrida duas vezes — entao aquele handler nunca rodava e o
  // "Solte para importar" ficava na tela para sempre. Como a zona e o banner
  // inteiro e o overlay tem pointer-events:none, soltar no alvo obvio caia
  // sempre nesse caminho.
  const overlayArraste = $("#dropAnywhere");
  let dragDepth = 0;
  const fecharArraste = () => {
    dragDepth = 0;
    overlayArraste?.classList.add("hidden");
  };

  ["dragenter", "dragover"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.add("drag");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.remove("drag");
    })
  );
  zone.addEventListener("drop", (e) => {
    // Sem isto o drop subia para o handler de `window` (o alvo gigante do
    // #dropAnywhere) e a MESMA pasta era varrida duas vezes. A segunda
    // varredura pega um DataTransfer ja neutralizado, entao ela devolve so o
    // que sobrou — os videos soltos — e ainda sobrescreve `state.pendingFiles`
    // com essa lista menor. Era o caminho para "arrastei a pasta e so vieram
    // os videos soltos".
    e.stopPropagation();
    fecharArraste();
    collectDroppedFiles(e.dataTransfer)
      .then((files) => openImportDialog(files))
      .catch((err) => toast(err.message));
  });
  input.addEventListener("change", () => {
    openImportDialog(input.files)
      .then(() => {
        if (state.presetIntent) {
          document.querySelector(`.intent-card[data-intent="${state.presetIntent}"]`)?.click();
          state.presetIntent = null;
        }
      })
      .catch((err) => toast(err.message));
    input.value = "";
  });
  const btnPodcast = $("#btnPickPodcast");
  if (btnPodcast) {
    btnPodcast.onclick = () => {
      state.presetIntent = "clips";
      input.click();
    };
  }
  wireMultiplicador();
  // Arrastar arquivo para QUALQUER lugar da janela abre a importação — o
  // overlay dá o alvo gigante; sem ele o usuário tinha que acertar o card.
  const anywhere = overlayArraste;
  if (anywhere) {
    window.addEventListener("dragenter", (e) => {
      // Com o Multiplicador aberto, as caixas dele são o alvo do arrasto —
      // o overlay "Solte para importar" cobriria as caixas e roubaria o drop.
      if ($("#dlgMulti")?.open) return;
      const types = (e.dataTransfer && e.dataTransfer.types) || [];
      if (![...types].includes("Files")) return;
      dragDepth += 1;
      anywhere.classList.remove("hidden");
    });
    window.addEventListener("dragleave", () => {
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) anywhere.classList.add("hidden");
    });
    window.addEventListener("dragover", (e) => e.preventDefault());
    window.addEventListener("drop", (e) => {
      e.preventDefault();
      fecharArraste();
      // Drop numa caixa do Multiplicador é tratado lá (stopPropagation);
      // drop fora das caixas com o diálogo aberto não vira importação.
      if ($("#dlgMulti")?.open) return;
      if (!e.dataTransfer) return;
      collectDroppedFiles(e.dataTransfer)
        .then((files) => { if (files && files.length) openImportDialog(files); })
        .catch((err) => toast(err.message));
    });
  }
  if (folderInput) {
    folderInput.addEventListener("change", () => {
      openImportDialog(folderInput.files).catch((err) => toast(err.message));
      folderInput.value = "";
    });
  }
  $$(".intent-card").forEach((card) => {
    card.addEventListener("click", () => applyIntentDefaults(card.dataset.intent, state.pendingRecommended));
  });
  const btnGo = $("#btnImportGo");
  if (btnGo) {
    btnGo.onclick = async () => {
      const files = state.pendingFiles || [];
      const paths = state.pendingPaths || null;
      $("#dlgImport")?.close();
      try {
        if (paths) await importarPorCaminho(paths, collectImportIntent());
        else await uploadFiles(files, collectImportIntent());
      } catch (err) {
        toast(err.message);
      } finally {
        state.pendingFiles = null;
        state.pendingPaths = null;
      }
    };
  }
  // "Gerar 3 versões": o mesmo vídeo em Dinâmico + Vídeo completo + Sem
  // cortes, três projetos na fila, para comparar lado a lado. Nasceu de uso
  // real: o usuário importou o MESMO vídeo seis vezes num dia (24/08)
  // trocando modo/estilo na mão para comparar as minutagens.
  const btnTrio = $("#btnImportTrio");
  if (btnTrio) {
    btnTrio.onclick = async () => {
      const files = state.pendingFiles || [];
      const paths = state.pendingPaths || null;
      $("#dlgImport")?.close();
      const base = collectImportIntent();
      try {
        // 5 versoes (pedido de 25/08: "falta mais" no trio): os tres niveis
        // de tesoura + Shorts + o pacote Viral (dinamico com tipo viral).
        const versoes = [
          { editingIntent: "dynamic" },
          { editingIntent: "complete" },
          { editingIntent: "intact" },
          { editingIntent: "shorts" },
          { editingIntent: "dynamic", contentType: "viral" },
        ];
        for (const extra of versoes) {
          const intent = { ...base, ...extra };
          if (paths) await importarPorCaminho(paths, intent);
          else await uploadFiles(files, intent);
        }
        toast("5 versões na fila: Dinâmico, Completo, Sem cortes, Shorts e Viral");
      } catch (err) {
        toast(err.message);
      } finally {
        state.pendingFiles = null;
        state.pendingPaths = null;
      }
    };
  }
  $("#cmpClose")?.addEventListener("click", () => {
    const dlg = $("#dlgCompare");
    $("#cmpGrid")?.querySelectorAll("video").forEach((v) => v.pause());
    $("#cmpGrid") && ($("#cmpGrid").innerHTML = "");
    dlg?.close();
  });
  $("#cmpPlayAll")?.addEventListener("click", () => {
    $("#cmpGrid")?.querySelectorAll("video").forEach((v) => { v.currentTime = 0; v.play().catch(() => {}); });
  });
  const btnCancel = $("#btnImportCancel");
  if (btnCancel) {
    btnCancel.onclick = () => {
      state.pendingFiles = null;
      state.pendingPaths = null;
      $("#dlgImport")?.close();
    };
  }
  const btnStyle = $("#btnImportStyle");
  if (btnStyle) {
    btnStyle.onclick = () => {
      if ($("#useBrandStyle")) $("#useBrandStyle").checked = false;
      toast("Depois de importar, abra Estilo neste vídeo para ajustar só ele.");
    };
  }
}

/** Copia texto. `false` se nao deu — e ai quem chamou TEM de dar outra saida.
 *
 * Dois caminhos porque um so nao cobre: a `clipboard` API precisa de contexto
 * seguro E da janela em foco, e a janela do app e um WebView; o `execCommand`
 * e velho mas funciona sem essas duas condicoes, desde que o campo esteja
 * focado na hora. */
async function copiarTexto(texto) {
  const t = String(texto || "");
  if (!t) return false;
  try {
    await navigator.clipboard.writeText(t);
    return true;
  } catch { /* segue para o caminho velho */ }
  const ta = document.createElement("textarea");
  ta.value = t;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.top = "0";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  let ok = false;
  try {
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, t.length);
    ok = document.execCommand("copy");
  } catch { ok = false; }
  ta.remove();
  return ok;
}

/** Ultimo recurso do copiar: mostra o texto ja selecionado, para o Ctrl+C.
 *  Um "nao consegui copiar" sozinho e beco sem saida — o usuario queria o
 *  texto, nao o aviso. */
function mostrarTextoParaCopiar(titulo, dica, texto) {
  const dlg = $("#dlgJobDetail");
  const body = $("#detailBody");
  if (!dlg || !body) return false;
  const t = $("#detailTitle");
  const h = $("#detailHint");
  if (t) t.textContent = titulo;
  if (h) h.textContent = dica;
  body.textContent = texto;
  dlg.showModal();
  try {
    const r = document.createRange();
    r.selectNodeContents(body);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(r);
  } catch { /* selecionar e cortesia, nao requisito */ }
  return true;
}

function showJobDetail(id) {
  const j = state.jobs.find((x) => x.id === id);
  if (!j) return;
  const copy = queueCopy(j, state.view);
  const qa = j.quickApply || {};
  const parts = [];
  if (copy.text) parts.push(copy.text);
  if (j.message && j.message !== copy.text) parts.push(String(j.message));
  if (qa.stageLabel && qa.stageLabel !== copy.text) parts.push(String(qa.stageLabel));
  if (qa.detail) parts.push(String(qa.detail));
  if (j.detail) parts.push(String(j.detail));
  const text = parts.filter(Boolean).join("\n\n") || copy.text || "Sem detalhe neste vídeo.";
  const title = $("#detailTitle");
  const body = $("#detailBody");
  const dlg = $("#dlgJobDetail");
  if (!dlg || !body) return;
  if (title) title.textContent = j.title || j.name || "Detalhes do erro";
  body.textContent = text;
  try {
    dlg.showModal();
  } catch {
    toast(text.slice(0, 120));
  }
}

function askRename(id, current) {
  const dlg = $("#dlgRename");
  const input = $("#renameInput");
  if (!dlg || !input) return;
  state.pendingRenameId = id;
  state.pendingRenameCurrent = current || "";
  input.value = current || "";
  try {
    dlg.showModal();
  } catch {
    return;
  }
  requestAnimationFrame(() => {
    input.focus();
    input.select();
  });
}

async function confirmRename() {
  const id = state.pendingRenameId;
  const current = state.pendingRenameCurrent || "";
  const title = ($("#renameInput")?.value || "").trim();
  const dlg = $("#dlgRename");
  if (dlg?.open) dlg.close();
  state.pendingRenameId = null;
  state.pendingRenameCurrent = "";
  if (!id || !title || title === current) return;
  await api("/api/jobs/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, title }),
  });
  toast("Nome atualizado");
  await refreshJobs();
}

function askDelete(id, name) {
  state.pendingDeleteId = id;
  $("#deleteName").textContent = name || id;
  $("#dlgDelete").showModal();
}

async function confirmDelete() {
  const id = state.pendingDeleteId;
  if (!id) return;
  $("#dlgDelete").close();
  state.pendingDeleteId = null;
  // O servidor distingue TRES desfechos: foi para a Lixeira; saiu da lista mas
  // os arquivos FICARAM no disco (a reciclagem falhou, ou a pasta nao passou na
  // guarda de seguranca). A tela dizia "foi para a Lixeira" nos tres — e ai o
  // usuario ia procurar na Lixeira para restaurar e nao achava, ou contava com
  // um espaco em disco que nunca foi liberado.
  const r = await api("/api/jobs/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  if (r && r.recycled) {
    toast("Projeto foi para a Lixeira");
  } else if (r && r.removedFromList) {
    toast(
      (r.warning
        ? `Tirei da lista, mas os arquivos ficaram no disco: ${r.warning}`
        : "Tirei da lista, mas os arquivos ficaram no disco"),
      6000
    );
  } else {
    toast("Projeto removido");
  }
  await refreshJobs();
}

function wireList() {
  document.addEventListener("click", async (e) => {
    const nav = e.target.closest("[data-view]");
    if (nav && nav.dataset.view) {
      e.preventDefault();
      closeCardMenus();
      // Chegar em Estilos por aqui (menu, atalho de identidade) e sempre
      // o ESTILO BASE. So o "Editar estilo" de um preset, que nao passa
      // por `data-view`, aponta o editor para um preset.
      if (nav.dataset.view === "estilo") {
        state.editPresetId = "";
        state.editPresetNome = "";
      }
      setView(nav.dataset.view);
      return;
    }
    const btn = e.target.closest("[data-act]");
    if (!btn) {
      if (!e.target.closest(".pc-menu")) closeCardMenus();
      return;
    }
    const id = btn.dataset.id;
    const act = btn.dataset.act;
    if (act === "menu") {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      openCardMenu(btn);
      return;
    }
    closeCardMenus();
    try {
      // Job LOCAL (tmp-): o servidor nunca soube dele, entao as acoes nao
      // podem bater na API — dariam 404. "Tentar novamente" re-sobe os
      // arquivos, que continuam no objeto (job._files); "Apagar" remove da
      // tela. O "cancel" ja tinha o proprio caminho local, mais abaixo.
      if (String(id).startsWith("tmp-") && act !== "cancel") {
        const job = state.jobs.find((x) => x.id === id);
        if (act === "retry" && job && job._files && job._files.length) {
          const files = job._files;
          removeLocalJob(id);
          renderJobs();
          await uploadFiles(files, null);
          return;
        }
        if (act === "delete" || act === "retry") {
          removeLocalJob(id);
          renderJobs();
          if (act === "delete") toast("Importação descartada");
          else toast("Não tenho mais os arquivos — importe de novo");
          return;
        }
      }
      if (act === "log") {
      // O log conta o que o render fez: tempos por etapa, motor usado,
      // por que caiu para o caminho lento. Ate a 4.11 ele era apagado.
      api("/api/jobs/open-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      }).catch((e) => toast(e.message || "Não achei o log deste vídeo"));
      return;
    }
    if (act === "folder") {
        await api("/api/jobs/open-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
      } else if (act === "aplicar-pendentes") {
        // 5.0.46: 7 projetos tinham correcao rapida salva e nunca aplicada
        // (o mais velho de 18/08). A linha "Pendente" dizia; agora tambem
        // resolve, sem abrir o editor. Mesma rota que o botao do editor.
        const job = state.jobs.find((x) => String(x.id) === String(id));
        const pasta = pastaDoProjeto(job);
        const r = await api(`/p/${encodeURIComponent(pasta)}/api/corrections`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ op: "apply" }),
        });
        if (r && r.ok === false) throw new Error(r.error || "não consegui aplicar");
        toast("Aplicando as correções pendentes — o card mostra o andamento", 5000);
        setTimeout(() => refreshJobs().catch(() => {}), 1500);
      } else if (act === "srt") {
        // 5.0.43: legenda como arquivo, na pasta de entrega — YouTube e
        // LinkedIn aceitam .srt; leitor de tela tambem.
        const r = await api("/api/jobs/srt", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        toast(`Legenda .srt salva (${r.blocos || 0} blocos) — abrindo a pasta`, 5000);
        await api("/api/jobs/open-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
      } else if (act === "copyname") {
        // o nome COMPLETO (com o ✅ de aprovado): ele cria a pasta de
        // entrega com esse nome (03/09)
        const jn = state.jobs.find((x) => String(x.id) === String(id));
        const nome = jn ? displayTitle(jn) : "";
        toast((await copiarTexto(nome)) ? `Nome copiado: ${nome}` : "Não consegui copiar o nome", 2600);
      } else if (act === "copystyle") {
        // so `id` existe neste escopo — `job` nao ("job is not defined",
        // print de 03/09: o copiar quebrava e o colar nunca acendia)
        await copiarEstiloDoCard(state.jobs.find((x) => String(x.id) === String(id)));
      } else if (act === "pastestyle") {
        await colarEstiloNoCard(state.jobs.find((x) => String(x.id) === String(id)));
      } else if (act === "copylegenda") {
        // Este botao NUNCA teve handler: a cadeia de acoes tratava folder,
        // open-final, retry, reimport, ackapply, cancel, detail e rename — e
        // `copylegenda` caia fora dela. O botao existia no card desde sempre e
        // o clique nao fazia nada.
        const job = state.jobs.find((x) => x.id === id);
        // O arquivo FRESCO primeiro: `job.legenda` e um retrato tirado quando o
        // pipeline terminou, e uma correcao de palavra aplicada depois tambem
        // conserta a legenda.txt — copiar o retrato entregava o texto com o
        // erro que o usuario acabou de corrigir.
        let texto = String((job && job.legenda) || "").trim();
        try {
          const r = await fetch(`/api/jobs/${id}/legenda`);
          if (r.ok) {
            const fresco = (await r.text()).trim();
            if (fresco) texto = fresco;
          }
        } catch { /* sem servidor, fica o retrato */ }
        if (!texto) {
          toast("Este vídeo ainda não tem legenda de post");
        } else if (await copiarTexto(texto)) {
          toast("✓ Legenda copiada");
        } else if (mostrarTextoParaCopiar(
          "Legenda do post",
          "Não consegui copiar sozinho. O texto está selecionado — Ctrl+C.",
          texto)) {
          /* o texto esta na tela; nao ha beco sem saida */
        } else {
          toast("Não consegui copiar a legenda");
        }
      } else if (act === "open-final") {
        const job = state.jobs.find((x) => x.id === id);
        if (job) location.href = jobLinks(job).final;
      } else if (act === "retry") {
        const job = state.jobs.find((x) => x.id === id);
        const wasApplyFail = applyFailed(job);
        await api("/api/jobs/retry", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        toast(wasApplyFail ? "Refazendo o vídeo com os seus cortes" : "De volta à fila");
        setView("fila");
        await refreshJobs();
      } else if (act === "publicar-ig") {
        const job = state.jobs.find((x) => x.id === id);
        const titulo = job ? displayTitle(job) : "este vídeo";
        // Publicar e para FORA — confirmacao explicita sempre.
        const okPub = await pedirConfirmacao(
          `Publicar "${titulo}" no Instagram agora?`,
          "A legenda do post, com as suas hashtags, vai junto.",
          "Publicar");
        if (!okPub) return;
        try {
          const r = await api("/api/jobs/publicar-instagram", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id }),
          });
          if (!r.ok && r.error) throw new Error(r.error);
          toast("Publicando no Instagram… acompanhe pela ficha do card", 6000);
          setTimeout(() => refreshJobs().catch(() => {}), 4000);
        } catch (err) {
          toast(err.message || "Não deu para publicar", 6000);
        }
      } else if (act === "compare") {
        abrirComparar(id);
      } else if (act === "reimport") {
        // O arquivo antigo não abre: abre o seletor para o usuário trazer a
        // cópia boa. O card quebrado continua ali para ele apagar.
        toast("Escolha o arquivo do vídeo de novo", 4000);
        $("#fileInput")?.click();
      } else if (act === "ackapply") {
        const job = state.jobs.find((x) => x.id === id);
        const qa = job && job.quickApply;
        if (qa) {
          const key = applyAckKey(qa);
          if (key) { try { localStorage.setItem(key + ":dis", "1"); } catch { /* ignore */ } }
          try {
            await fetch("/api/apply-ack", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ taskId: qa.taskId || "", projectId: qa.projectId || "", dismiss: true }),
            });
          } catch { /* a reserva local ja segura a tela */ }
        }
        toast("Aviso dispensado — o vídeo continua como está");
        await refreshJobs();
      } else if (act === "cancel") {
        if (String(id).startsWith("tmp-")) {
          const xhr = state.uploads[id];
          if (xhr) xhr.abort();
          removeLocalJob(id);
          renderJobs();
          toast("Importação cancelada");
          return;
        }
        await api("/api/jobs/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        toast("Edição cancelada");
        await refreshJobs();
      } else if (act === "detail") {
        showJobDetail(id);
      } else if (act === "rename") {
        askRename(id, btn.dataset.title || "");
      } else if (act === "delete") {
        askDelete(id, btn.dataset.name || "");
      }
    } catch (err) {
      toast(err.message);
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeCardMenus();
  });
  // 5.0.46: "/" leva o cursor a busca da tela (Concluidos ou Projetos);
  // Esc dentro dela limpa. Fora de campo de texto, para nao roubar a barra
  // de quem digita.
  document.addEventListener("keydown", (e) => {
    const alvo = e.target;
    const digitando = alvo && (alvo.tagName === "INPUT" || alvo.tagName === "TEXTAREA"
      || alvo.isContentEditable);
    if (e.key === "/" && !digitando && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const campo = $(state.view === "projetos" ? "#projSearch" : "#doneSearch");
      if (campo && campo.offsetParent !== null) {
        e.preventDefault();
        campo.focus();
        campo.select();
      }
    } else if (e.key === "Escape" && digitando && (alvo.id === "doneSearch" || alvo.id === "projSearch")) {
      if (alvo.value) {
        alvo.value = "";
        alvo.dispatchEvent(new Event("input", { bubbles: true }));
      } else {
        alvo.blur();
      }
    }
  });
  // NAO passar a referencia direta: o listener recebe o Event como `scope`
  // e `$$("[data-menu-host]", event)` estoura (TypeError em todo resize,
  // visto no laboratorio em 03/09)
  window.addEventListener("resize", () => closeCardMenus());
  // O scroll tambem entrega o Event como `scope` (TypeError a cada rolagem,
  // 31 no console do lab em 05/09) — mesma armadilha do resize, corrigida
  // na 5.0.45. Sem isto os menus dos cards nao fechavam ao rolar.
  window.addEventListener("scroll", () => closeCardMenus(), true);

  const formRename = $("#formRename");
  if (formRename) {
    formRename.addEventListener("submit", (e) => {
      e.preventDefault();
      confirmRename().catch((err) => toast(err.message));
    });
  }
  $("#btnRenameCancel")?.addEventListener("click", () => {
    state.pendingRenameId = null;
    state.pendingRenameCurrent = "";
    $("#dlgRename")?.close();
  });
  $("#btnDeleteConfirm").onclick = () => confirmDelete().catch((err) => toast(err.message));
  $("#btnDeleteCancel").onclick = () => {
    state.pendingDeleteId = null;
    $("#dlgDelete").close();
  };
  const btnDetailClose = $("#btnDetailClose");
  if (btnDetailClose) {
    btnDetailClose.onclick = () => $("#dlgJobDetail")?.close();
  }
  const btnDetailCopy = $("#btnDetailCopy");
  if (btnDetailCopy) {
    btnDetailCopy.onclick = async () => {
      const text = $("#detailBody")?.textContent || "";
      toast(await copiarTexto(text) ? "Copiado" : "Não consegui copiar");
    };
  }
}

async function loadLlm() {
  const cfg = await api("/api/llm-proxy");
  let gw = { ok: false, message: "" };
  try {
    gw = await api("/api/llm-gateway");
  } catch {
    /* older server */
  }
  $("#llmBase").value = cfg.baseUrl || "http://127.0.0.1:4850/v1";
  fillModelSelect(cfg.model || "", []);
  await refreshProviders();
  if (gw.ok) {
    $("#llmConnPill").textContent = gw.viaSession ? "Sessão OK" : "Online";
    $("#llmConnPill").className = "conn-pill on";
    $("#llmStatus").textContent = gw.message || "Pronto para chat";
    try {
      await refreshModels(false);
    } catch (e) {
      $("#llmStatus").textContent = e.message || "Falha ao listar modelos";
    }
  } else {
    $("#llmConnPill").textContent = "Sem sessão";
    $("#llmConnPill").className = "conn-pill bad";
    $("#llmStatus").textContent = gw.message || "Capture Gemini ou ChatGPT com a extensão";
  }
}

function setLlmStatus(cfg, extra) {
  const pill = $("#llmConnPill");
  if (extra) {
    $("#llmStatus").textContent = extra;
    pill.textContent = "Salvo";
    pill.className = "conn-pill on";
    return;
  }
  pill.textContent = "Pronto";
  pill.className = "conn-pill";
  $("#llmStatus").textContent = "Sessão web → /v1";
}

function fillModelSelect(selected, models) {
  const sel = $("#llmModel");
  const opts = ['<option value="">— escolha um modelo —</option>'];
  for (const m of models) {
    const id = typeof m === "string" ? m : m.id;
    opts.push(`<option value="${escapeHtml(id)}"${id === selected ? " selected" : ""}>${escapeHtml(id)}</option>`);
  }
  if (selected && !models.some((m) => (m.id || m) === selected)) {
    opts.push(`<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)}</option>`);
  }
  sel.innerHTML = opts.join("");
}

// "Abrir site" era `<a target="_blank">` no WebView2, que nao trata janela
// nova: cada clique despejava mais uma guia no navegador do usuario. Agora o
// clique pede ao servidor, que abre UMA guia no navegador padrao; o botao
// trava por 2s para o clique duplo nao abrir duas.
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-open-site]");
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  setTimeout(() => { btn.disabled = false; }, 2000);
  try {
    await api("/api/llm-proxy/open-site", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: btn.dataset.openSite }),
    });
  } catch (err) {
    toast(`Não consegui abrir o site: ${err.message || err}`, 4000);
  }
});

async function refreshProviders() {
  const data = await api("/api/llm-proxy/sessions");
  const providers = data.providers || [];
  $("#providerGrid").innerHTML = providers
    .map((p) => {
      const ready = !!p.ready;
      const hasCookies = !!p.configured;
      const cls = ready ? "ok" : hasCookies ? "warn" : "";
      const meta = p.hint || (hasCookies ? `${p.cookieCount} cookies` : "Não capturado");
      return `<article class="provider-card ${cls}" data-provider="${escapeHtml(p.id)}">
        <div class="pc-name">${escapeHtml(p.name)}</div>
        <div class="pc-meta">${escapeHtml(meta)}</div>
        <div class="pc-actions-row">
          <button type="button" class="chip-btn" data-open-site="${escapeHtml(p.id)}">Abrir site</button>
        </div>
      </article>`;
    })
    .join("");
}

async function refreshModels(toastOk) {
  // Prefer embedded gateway directly (same origin)
  let models = [];
  const direct = await fetch("/v1/models");
  const payload = await direct.json().catch(() => ({}));
  if (direct.ok && Array.isArray(payload.data)) {
    models = payload.data;
  } else {
    const res = await fetch("/api/llm-proxy/models");
    const data = await res.json().catch(() => ({}));
    if (!data.ok) {
      const err = data.error || payload.error?.message || "falha ao listar";
      $("#llmModelsList").innerHTML = `<li class="hint">${escapeHtml(err)}</li>`;
      throw new Error(err);
    }
    models = data.models || [];
  }
  const list = $("#llmModelsList");
  const cur = $("#llmModel").value;
  fillModelSelect(cur || "", models);
  const selected = $("#llmModel").value;
  list.innerHTML = models.length
    ? models.map((m) => {
      const id = m.id || m;
      const active = id === selected ? " is-active" : "";
      return `<li class="${active.trim()}" data-model="${escapeHtml(id)}" title="${escapeHtml(id)}">${escapeHtml(id)}</li>`;
    }).join("")
    : `<li class="hint">Gateway respondeu, mas sem modelos.</li>`;
  list.querySelectorAll("[data-model]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const id = chip.getAttribute("data-model") || "";
      $("#llmModel").value = id;
      list.querySelectorAll("[data-model]").forEach((c) => {
        c.classList.toggle("is-active", c === chip);
      });
    });
  });
  if (toastOk) toast(`${models.length} modelo(s)`);
  return models;
}

async function testLlm() {
  $("#llmStatus").textContent = "Testando…";
  try {
    const models = await refreshModels(false);
    if (!models.length) {
      throw new Error("Nenhum modelo — capture a sessão na extensão");
    }
    const model = $("#llmModel").value || models[0].id || models[0];
    const res = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content: "Responda só: ok" }],
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error?.message || data.error || `HTTP ${res.status}`);
    }
    const reply = data.choices?.[0]?.message?.content || "(vazio)";
    $("#llmConnPill").textContent = "Sessão OK";
    $("#llmConnPill").className = "conn-pill on";
    $("#llmStatus").textContent = `IA respondeu: ${String(reply).slice(0, 120)}`;
    toast("IA OK");
  } catch (e) {
    $("#llmConnPill").textContent = "Falha";
    $("#llmConnPill").className = "conn-pill bad";
    $("#llmStatus").textContent = e.message || "falha no teste";
    throw e;
  }
}

function setAuthDialogMode(mode) {
  const m = mode === "signup" ? "signup" : "login";
  if ($("#authMode")) $("#authMode").value = m;
  $$(".dlg-login-tab").forEach((t) => t.classList.toggle("active", t.dataset.authMode === m));
  const title = $("#loginDlgTitle");
  const hint = $("#loginDlgHint");
  const btn = $("#btnAuthLogin");
  if (m === "signup") {
    if (title) title.textContent = "Criar conta";
    if (hint) hint.textContent = "Crie sua conta. Depois o admin libera os dias de acesso neste e-mail.";
    if (btn) btn.textContent = "Criar conta";
    if ($("#authPassword")) $("#authPassword").autocomplete = "new-password";
    if ($("#authRememberWrap")) $("#authRememberWrap").hidden = true;
  } else {
    if (title) title.textContent = "Entrar na conta";
    if (hint) hint.textContent = "Use o e-mail e a senha da sua conta. Admin libera os dias de acesso.";
    if (btn) btn.textContent = "Entrar";
    if ($("#authPassword")) $("#authPassword").autocomplete = "current-password";
    if ($("#authRememberWrap")) $("#authRememberWrap").hidden = false;
  }
}

function openLoginDialog(mode) {
  const dlg = $("#dlgLogin");
  if (!dlg) return;
  const err = $("#loginErr");
  if (err) {
    err.hidden = true;
    err.textContent = "";
  }
  if ($("#authPassword")) {
    $("#authPassword").value = "";
    $("#authPassword").type = "password";
  }
  try {
    const remembered = localStorage.getItem("ativavid-auth-email") || "";
    const rememberOn = localStorage.getItem("ativavid-auth-remember") !== "0";
    if ($("#authRemember")) $("#authRemember").checked = rememberOn;
    if ($("#authEmail") && remembered && rememberOn) $("#authEmail").value = remembered;
  } catch { /* ignore */ }
  setAuthDialogMode(mode || "login");
  if (!dlg.open) dlg.showModal();
  setTimeout(() => {
    const email = $("#authEmail");
    if (email && !email.value) email.focus();
    else $("#authPassword")?.focus();
  }, 30);
}

function closeLoginDialog() {
  const dlg = $("#dlgLogin");
  if (dlg?.open) dlg.close();
}

function licenseSidebarMeta(lic) {
  const L = lic || state.license || {};
  const mode = L.mode || "open";
  if (mode === "update_required" || L.update?.force) {
    return { text: "Atualize o app", tone: "bad" };
  }
  if (mode === "account") {
    const until = L.validUntil ? String(L.validUntil).slice(0, 10) : "—";
    return { text: `Conta até ${until}`, tone: "ok" };
  }
  if (mode === "licensed") {
    const until = L.validUntil ? String(L.validUntil).slice(0, 10) : "—";
    return { text: `Licença até ${until}`, tone: "ok" };
  }
  if (mode === "trial") {
    return { text: `Trial · ${L.trialDaysLeft ?? "?"} dia(s)`, tone: "warn" };
  }
  if (mode === "blocked") return { text: "Licença bloqueada", tone: "bad" };
  if (mode === "error") return { text: "Licença: erro", tone: "bad" };
  if (mode === "open" || !L.configured) return { text: "Modo aberto", tone: "neutral" };
  return { text: L.message || "Sem licença ativa", tone: "bad" };
}

function initialsFromEmail(email) {
  const local = String(email || "").split("@")[0] || "";
  const parts = local.split(/[._\-\s]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (local.slice(0, 2) || "?").toUpperCase();
}

function displayNameFromEmail(email) {
  const local = String(email || "").split("@")[0] || "Conta";
  return local
    .split(/[._\-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ") || "Conta";
}

function openLicAccountDialog(email) {
  const dlg = $("#dlgLicAccount");
  if (!dlg) return;
  const title = $("#licAccountDlgTitle");
  if (title) title.textContent = email ? "Editar acesso" : "Nova conta";
  if ($("#adminLicEmail")) $("#adminLicEmail").value = email || "";
  if (!email) {
    if ($("#adminLicPassword")) $("#adminLicPassword").value = "";
    if ($("#adminLicNotes")) $("#adminLicNotes").value = "";
  }
  const msg = $("#adminFormMsg");
  if (msg) {
    msg.hidden = true;
    msg.textContent = "";
  }
  if (!dlg.open) dlg.showModal();
  setTimeout(() => {
    if (email) $("#adminLicDays")?.focus();
    else $("#adminLicEmail")?.focus();
  }, 30);
}

function closeLicAccountDialog() {
  const dlg = $("#dlgLicAccount");
  if (dlg?.open) dlg.close();
}

function adminOut(x) {
  const el = $("#adminLicOut");
  if (!el) return;
  el.textContent = typeof x === "string" ? x : JSON.stringify(x, null, 2);
}

/** Plano em uma linha curta — o rodapé é estreito e não pode cortar texto. */
function workspacePlanMeta(lic) {
  const L = lic || state.license || {};
  const mode = L.mode || "open";
  if (mode === "update_required" || L.update?.force) {
    return { text: "Atualização pendente", tone: "bad" };
  }
  if (mode === "account" || mode === "licensed") {
    return { text: `${L.planLabel || "Plano Pro"} · Ativo`, tone: "ok" };
  }
  if (mode === "trial") {
    const d = L.trialDaysLeft;
    return { text: `Trial · ${d ?? "?"} ${d === 1 ? "dia" : "dias"}`, tone: "warn" };
  }
  if (mode === "blocked") return { text: "Licença bloqueada", tone: "bad" };
  if (mode === "error") return { text: "Licença indisponível", tone: "bad" };
  if (mode === "open" || !L.configured) return { text: "Modo aberto", tone: "neutral" };
  return { text: "Sem plano ativo", tone: "bad" };
}

/** Iniciais do workspace: 2 letras, das primeiras palavras do nome. */
function initialsFromName(nome) {
  const partes = String(nome || "").trim().split(/[\s._-]+/).filter(Boolean);
  if (partes.length >= 2) return (partes[0][0] + partes[1][0]).toUpperCase();
  return (String(nome || "AV").slice(0, 2) || "AV").toUpperCase();
}

/**
 * Rodapé do sidebar. Mostra o WORKSPACE (a marca ativa), não a pessoa
 * logada — o ATIVAVID é um app de produção, e quem assina o vídeo é a
 * marca. A conta continua a um clique, dentro do menu.
 */
function renderWorkspaceCard() {
  const btn = $("#btnWorkspace");
  if (!btn) return;
  const marca = state.brandActive || {};
  const nome = state.wsMarca === "all" ? "Todas as empresas" : (marca.name || "Meu workspace");
  const plano = workspacePlanMeta(state.license);
  const nameEl = $("#wsName");
  const planEl = $("#wsPlan");
  const txt = $("#wsAvatarTxt");
  const img = $("#wsAvatarImg");
  if (nameEl) nameEl.textContent = nome;
  if (planEl) planEl.textContent = plano.text;
  if (txt) txt.textContent = initialsFromName(nome);
  // Logo da marca quando existir; senão, iniciais na cor de destaque dela.
  if (img) {
    const logo = marca.logoUrl || "";
    img.classList.toggle("hidden", !logo);
    if (logo && img.getAttribute("src") !== logo) img.src = logo;
  }
  const avatar = $("#wsAvatar");
  if (avatar) avatar.style.setProperty("--ws-tint", marca.accent || "");
  btn.dataset.tone = plano.tone;
  btn.title = `${nome} · ${plano.text}`;
  const head = $("#wsMenuHead");
  if (head) head.textContent = nome;
  const logged = !!(state.auth && state.auth.loggedIn);
  const sair = $("#wsMenuSair");
  if (sair) sair.hidden = !logged;
  const contaLab = $("#wsMenuContaLabel");
  if (contaLab) {
    contaLab.textContent = logged
      ? (state.auth.email || "Minha conta")
      : "Entrar na conta";
  }
}

/**
 * Gaveta do menu (<=620px). Fora dessa faixa o CSS ignora `sb-open`, entao
 * a classe pode ficar pendurada sem efeito — mas fechamos no resize para o
 * estado nao voltar sozinho quando a janela encolhe de novo.
 */
function wireGaveta() {
  const burger = $("#btnBurger");
  const scrim = $("#sbScrim");
  const sidebar = $(".sidebar");
  if (!burger || burger.dataset.wired) return;
  burger.dataset.wired = "1";
  const abrir = (on) => {
    document.body.classList.toggle("sb-open", on);
    burger.setAttribute("aria-expanded", on ? "true" : "false");
    burger.setAttribute("aria-label", on ? "Fechar menu" : "Abrir menu");
  };
  burger.addEventListener("click", (e) => {
    e.stopPropagation();
    abrir(!document.body.classList.contains("sb-open"));
  });
  if (scrim) scrim.addEventListener("click", () => abrir(false));
  if (sidebar) {
    // navegar fecha a gaveta: em tela pequena ela cobre o conteudo
    sidebar.addEventListener("click", (e) => {
      if (e.target.closest(".sb-item")) abrir(false);
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") abrir(false);
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 620) abrir(false);
  });
}

/* Trocar a empresa ativa: presets, estilos, roteiro e o filtro do
 * workspace seguem juntos. Usado pelo menu do rodape e pelos cards da
 * tela de Empresas. */
async function ativarEmpresa(id) {
  try {
    if (!state.brandActive || state.brandActive.id !== id) {
      await api("/api/brands", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "activate", id }) });
    }
    setWsMarca("ativa");
    state.libDono = "empresa";
    await loadBrandsUi();
    loadImportPresets().catch(() => {});
    if (state.view === "presets") loadEmpresaUi().catch(() => {});
    if (state.view === "biblioteca") loadLibraryUi().catch(() => {});
    toast(`Empresa ativa: ${nomeDaMarca(id)}`);
  } catch (err) {
    toast(err.message || "Não consegui trocar a empresa");
  }
}

/* Lista de empresas no menu do workspace (5.0.0). */
function renderWsMarcas() {
  const box = $("#wsMarcas");
  if (!box) return;
  const brands = state.brands || [];
  const ativa = state.brandActive && state.brandActive.id;
  const item = (id, nome, on, extra) => `
    <button type="button" class="ws-menu-item ws-marca${on ? " on" : ""}" role="menuitemradio" aria-checked="${on ? "true" : "false"}" data-ws-marca="${escapeHtml(id)}">
      <span class="ws-marca-dot" aria-hidden="true"></span><span>${escapeHtml(nome)}</span>${extra || ""}
    </button>`;
  const todas = state.wsMarca === "all";
  box.innerHTML = `<p class="ws-menu-sub">Empresa</p>`
    + item("__all__", "Todas as empresas", todas, `<span class="ws-marca-n">${state.jobs.length}</span>`)
    + brands.map((b) => {
      const n = state.jobs.filter((j) => !j.brandId || j.brandId === b.id).length;
      return item(b.id, b.name || b.id, !todas && b.id === ativa, `<span class="ws-marca-n">${n}</span>`);
    }).join("");
}

function closeWorkspaceMenu() {
  const menu = $("#wsMenu");
  const btn = $("#btnWorkspace");
  if (menu) menu.classList.add("hidden");
  if (btn) btn.setAttribute("aria-expanded", "false");
}

function wireWorkspaceMenu() {
  const btn = $("#btnWorkspace");
  const menu = $("#wsMenu");
  if (!btn || !menu || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    // Recolhido, o card vira só o avatar — abrir o menu ali é a única
    // forma de chegar em conta/licença sem expandir o sidebar.
    const abrir = menu.classList.contains("hidden");
    if (abrir) renderWsMarcas(); // contagens por empresa sempre frescas
    menu.classList.toggle("hidden", !abrir);
    btn.setAttribute("aria-expanded", abrir ? "true" : "false");
  });
  menu.addEventListener("click", async (e) => {
    const marca = e.target.closest("[data-ws-marca]");
    if (marca) {
      e.stopPropagation();
      const id = marca.dataset.wsMarca;
      if (id === "__all__") {
        setWsMarca("all");
        renderWsMarcas(); renderWorkspaceCard(); renderJobs();
        toast("Mostrando todas as empresas");
        return;
      }
      await ativarEmpresa(id);
      return;
    }
    const item = e.target.closest("[data-ws]");
    if (!item) return;
    e.stopPropagation();
    closeWorkspaceMenu();
    const acao = item.dataset.ws;
    const logado = !!(state.auth && state.auth.loggedIn);
    if (acao === "conta") {
      if (logado) openLicAccountDialog(state.auth.email || "");
      else openLoginDialog();
      return;
    }
    if (acao === "licenca") return setView("licenca");
    if (acao === "empresas") return setView("presets");
    if (acao === "updates") {
      try {
        const res = await api("/api/update/check");
        if (res.force || res.updateAvailable) {
          openUpdateDialog({ update: res, mode: res.force ? "update_required" : "open", message: res.message });
        } else {
          toast(res.message || "Você está no build atual");
        }
      } catch (err) {
        toast(err.message || "Não foi possível verificar");
      }
      return;
    }
    if (acao === "sair") {
      try {
        await api("/api/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        state.auth = { loggedIn: false, isAdmin: false, email: null };
        applyAccountChrome(state.auth);
        toast("Saiu");
      } catch (err) {
        toast(err.message || "Falha ao sair");
      }
    }
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#wsMenu") && !e.target.closest("#btnWorkspace")) closeWorkspaceMenu();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeWorkspaceMenu();
  });
}

function applyAccountChrome(st) {
  const logged = !!st?.loggedIn;
  const email = st?.email || "";
  renderWorkspaceCard();
  // O "Avançado" fica RECOLHIDO, inclusive para admin. Eu o abria sozinho para
  // preencher a tela — mas encher espaço não é motivo para escancarar chave de
  // API e jargão de diagnóstico toda vez que se abre Configurações.
  const openBtn = $("#btnOpenLogin");
  const logoutBtn = $("#btnAuthLogout");
  if (openBtn) openBtn.hidden = logged;
  if (logoutBtn) logoutBtn.hidden = !logged;
  const label = $("#authEmailLabel");
  if (label) {
    if (logged) {
      label.textContent = st.isAdmin ? email || "Admin" : email || "—";
    } else {
      label.textContent = "Entre pela barra lateral para gerenciar a conta.";
    }
  }
  syncLicenseChrome();
}

function fmtAccessUntil(v) {
  if (!v) return "—";
  try {
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return String(v).slice(0, 10);
    return d.toLocaleDateString("pt-BR");
  } catch {
    return String(v).slice(0, 10);
  }
}

function renderAccessList(data) {
  const empty = $("#adminAccessEmpty");
  const table = $("#adminAccessTable");
  if (!empty || !table) return;
  if (!data || data.ok === false) {
    if ($("#adminAccessList")) $("#adminAccessList").hidden = false;
    if ($("#adminAccessCaption")) $("#adminAccessCaption").hidden = false;
    empty.hidden = false;
    table.hidden = true;
    empty.textContent = (data && (data.message || data.error)) || "Falha ao listar. Rode supabase/rpc_admin.sql se ainda não rodou.";
    return;
  }
  const rows = Array.isArray(data.access) ? data.access : [];
  const caption = $("#adminAccessCaption");
  const box = $("#adminAccessList");
  // Contas viraram caminho secundário: a venda é por dispositivo. Sem nenhuma
  // conta, a seção inteira some em vez de ocupar espaço com um vazio.
  if (!rows.length) {
    empty.hidden = true;
    table.hidden = true;
    if (caption) caption.hidden = true;
    if (box) box.hidden = true;
    return;
  }
  if (caption) caption.hidden = false;
  if (box) box.hidden = false;
  empty.hidden = true;
  table.hidden = false;
  table.innerHTML = `
    <table class="access-table">
      <thead>
        <tr><th>E-mail</th><th>Status</th><th>Até</th><th>PCs</th><th></th></tr>
      </thead>
      <tbody>
        ${rows.map((r) => {
          const email = escapeHtml(r.email || "—");
          // "active"/"revoked" vem cru do banco: a tela é em português.
          const stRaw = String(r.status || "");
          const st = escapeHtml(stRaw);
          const stLabel = escapeHtml(
            stRaw === "active" ? "Ativo" : stRaw === "revoked" ? "Revogado" : (stRaw || "—")
          );
          const until = escapeHtml(fmtAccessUntil(r.valid_until));
          // "PCs" = quantos estao VINCULADOS de fato, sobre o limite. So o
          // limite ("1") fazia parecer que o PC do cliente ja estava na
          // conta quando ele nem tinha entrado com o e-mail (03/09).
          const vinculados = Array.isArray(r.devices) ? r.devices : null;
          const limite = String(r.max_devices ?? "—");
          const pcs = vinculados === null
            ? escapeHtml(limite)
            : `${vinculados.length} de ${escapeHtml(limite)}`
              + (vinculados.length
                ? `<span class="cel-sub">${escapeHtml((r.codigos || vinculados.map(codigoDoPc)).join(", "))}</span>`
                : `<span class="cel-sub">nenhum PC entrou com esta conta</span>`);
          const pcsTitulo = vinculados && vinculados.length ? escapeHtml(vinculados.join("\n")) : "";
          const rawEmail = String(r.email || "").replace(/"/g, "&quot;");
          const pending = r.user_id ? "" : " <span class=\"hint\">(sem login ainda)</span>";
          return `<tr class="access-row" data-email="${rawEmail}" title="Abrir para editar">
            <td title="${email}">${email}${pending}</td>
            <td><span class="access-st ${st}">${stLabel}</span></td>
            <td>${until}</td>
            <td title="${pcsTitulo}">${pcs}</td>
            <td class="access-acoes"><button type="button" class="ghost-btn access-revoke" data-email="${rawEmail}">Revogar</button>
              <button type="button" class="ghost-btn preset-del access-delete" data-email="${rawEmail}" title="Apaga a liberação e o login">Apagar</button></td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
  table.querySelectorAll(".access-row").forEach((row) => {
    row.onclick = (ev) => {
      if (ev.target.closest(".access-revoke, .access-delete")) return;
      const email = row.getAttribute("data-email") || "";
      openLicAccountDialog(email);
    };
  });
  // Apagar de verdade: liberacao, vinculo dos PCs e o login. Revogar so
  // desliga o acesso e deixa a linha — para e-mail digitado errado e lixo.
  table.querySelectorAll(".access-delete").forEach((btn) => {
    btn.onclick = async () => {
      const email = btn.getAttribute("data-email") || "";
      if (!email) return;
      const ok = await pedirConfirmacao(
        `Apagar a conta ${email}?`,
        "Some a liberação, o login (e-mail e senha) e o vínculo dos PCs. "
        + "O cliente só volta se você liberar de novo. Não dá para desfazer.",
        "Apagar", true,
      );
      if (!ok) return;
      try {
        const data = await api("/api/admin/access", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "delete", email }),
        });
        adminOut(data);
        toast(data.ok ? (data.message || "Conta apagada") : (data.message || "Falha ao apagar"));
        await loadAccessList();
      } catch (e) {
        toast(e.message || "Falha ao apagar");
      }
    };
  });
  table.querySelectorAll(".access-revoke").forEach((btn) => {
    btn.onclick = async () => {
      const email = btn.getAttribute("data-email") || "";
      if (!email) return;
      if ($("#adminLicEmail")) $("#adminLicEmail").value = email;
      try {
        const data = await api("/api/admin/access", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "revoke", email }),
        });
        adminOut(data);
        toast(data.ok ? (data.message || "Revogado") : (data.message || "Falha"));
        await loadAccessList();
      } catch (e) {
        toast(e.message || "Falha ao revogar");
      }
    };
  });
}

function devMsg(txt) {
  const el = $("#adminDevMsg");
  if (!el) return;
  el.textContent = txt || "";
  el.hidden = !txt;
}

function abrirDlgDispositivo(open) {
  const dlg = $("#dlgLicDevice");
  if (!dlg) return;
  if (open) {
    devMsg("");
    if (!dlg.open) dlg.showModal();
    $("#adminDevId")?.focus();
  } else if (dlg.open) {
    dlg.close();
  }
}

/** Dias que faltam — o que decide se você renova hoje ou daqui a um mês. */
function diasRestantes(until) {
  if (!until) return null;
  const d = new Date(until);
  if (Number.isNaN(d.getTime())) return null;
  return Math.ceil((d.getTime() - Date.now()) / 86400000);
}

function renderDeviceList(data) {
  const empty = $("#adminDevEmpty");
  const table = $("#adminDevTable");
  if (!empty || !table) return;
  if (!data || data.ok === false) {
    empty.hidden = false;
    table.hidden = true;
    empty.textContent = (data && (data.message || data.error)) || "Falha ao listar dispositivos.";
    return;
  }
  const rows = Array.isArray(data.devices) ? data.devices : [];
  if (!rows.length) {
    empty.hidden = false;
    table.hidden = true;
    empty.innerHTML = `Nenhum dispositivo liberado ainda. `
      + `<button type="button" class="export-btn export-btn--sm" id="btnDevEmptyOpen">Liberar dispositivo</button>`;
    $("#btnDevEmptyOpen")?.addEventListener("click", () => abrirDlgDispositivo(true));
    return;
  }
  empty.hidden = true;
  table.hidden = false;
  table.innerHTML = `
    <table class="access-table">
      <thead>
        <tr><th>Dispositivo</th><th>Dono</th><th>Vale até</th><th>Último uso</th><th></th></tr>
      </thead>
      <tbody>
        ${rows.map((r) => {
          const id = String(r.device_id || "");
          const idCurto = id.length > 22 ? id.slice(0, 10) + "…" + id.slice(-6) : id;
          const dias = diasRestantes(r.valid_until);
          // O estado que importa: vencido, vencendo, ou tranquilo.
          let tom = "active";
          let quando = fmtAccessUntil(r.valid_until);
          if (!r.valid_until) { tom = "revoked"; quando = "sem acesso"; }
          else if (dias !== null && dias <= 0) { tom = "revoked"; quando = `venceu ${quando}`; }
          else if (dias !== null && dias <= 15) { tom = "warn"; quando = `${quando} (${dias}d)`; }
          // Dono = conta vinculada, senao o e-mail digitado no "Liberar
          // dispositivo", senao quem estava logado ao abrir (o servidor
          // junta os tres em `email`). Ate a 4.92 so a conta contava e um
          // PC liberado pelo ID saia "—" mesmo com e-mail preenchido.
          const dono = escapeHtml(r.account_email || r.email || r.label || "—");
          const seg = id.replace(/"/g, "&quot;");
          const cod = escapeHtml(r.codigo || codigoDoPc(id));
          return `<tr class="access-row">
            <td class="mono" title="${escapeHtml(id)}"><strong class="maq-cod">${cod}</strong> <span class="cel-sub">${escapeHtml(idCurto)}</span></td>
            <td>${dono}</td>
            <td><span class="access-st ${tom}">${escapeHtml(quando)}</span></td>
            <td>${escapeHtml(fmtAccessUntil(r.last_seen))}</td>
            <td><button type="button" class="ghost-btn dev-renew" data-dev="${seg}">Renovar</button></td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
  table.querySelectorAll(".dev-renew").forEach((b) => {
    b.addEventListener("click", () => {
      abrirDlgDispositivo(true);
      const inp = $("#adminDevId");
      if (inp) inp.value = b.dataset.dev || "";
    });
  });
}

async function loadDeviceList() {
  try {
    const data = await api("/api/admin/devices");
    renderDeviceList(data);
    return data;
  } catch (e) {
    renderDeviceList({ ok: false, message: e.message || "Falha ao listar" });
    return null;
  }
}

/** Baixar só vira ação principal quando existe atualização de verdade. */
function marcarBotaoDeUpdate(up) {
  const btn = document.getElementById("btnUpdateOpen");
  if (!btn) return;
  const tem = !!(up && (up.updateAvailable || up.force));
  btn.classList.toggle("export-btn", tem);
  btn.classList.toggle("ghost-btn", !tem);
  btn.textContent = tem ? "Atualizar agora" : "Reinstalar a última versão";
}

async function loadAccessList() {
  const empty = $("#adminAccessEmpty");
  const table = $("#adminAccessTable");
  // Sem "Carregando…": a lista de contas é secundária e só aparece quando tem
  // conteúdo. O aviso ficava visível junto com a tabela já preenchida.
  void empty;
  void table;
  try {
    const data = await api("/api/admin/access");
    renderAccessList(data);
    return data;
  } catch (e) {
    renderAccessList({ ok: false, message: e.message || "Falha ao listar" });
    throw e;
  }
}

async function refreshAuthUi() {
  const prev = state.auth && state.auth.loggedIn ? { ...state.auth } : null;
  try {
    const remote = await api("/api/auth");
    state.auth = {
      loggedIn: !!remote.loggedIn,
      isAdmin: !!remote.isAdmin,
      email: remote.email || null,
    };
  } catch {
    // Não apaga o estado local se o GET falhar logo após o login
    if (prev) state.auth = prev;
    else state.auth = { loggedIn: false, isAdmin: false, email: null };
  }
  applyAccountChrome(state.auth);
  return state.auth;
}

function wireForms() {
  $("#formKeys").onsubmit = async (e) => {
    e.preventDefault();
    const body = {};
    const g = ($("#keyGroq")?.value || "").trim();
    const px = ($("#keyPx")?.value || "").trim();
    const fp = ($("#keyFreepik")?.value || "").trim();
    if (g) body.GROQ_API_KEY = g;
    if (px) body.PEXELS_API_KEY = px;
    if (fp) body.FREEPIK_API_KEY = fp;

    if (!Object.keys(body).length) {
      toast("Cole pelo menos uma chave antes de salvar");
      $("#keysStatus").textContent = "Nada para salvar";
      return;
    }
    try {
      const res = await api("/api/keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const ok = [];
      if (res.keys?.GROQ_API_KEY) ok.push("Groq");
      if (res.keys?.PEXELS_API_KEY) ok.push("Pexels");
      if (res.keys?.FREEPIK_API_KEY) ok.push("Freepik");
      $("#keysStatus").textContent = ok.length ? `Salvo: ${ok.join(", ")}` : "Salvo.";
      toast(ok.length ? `Chaves salvas (${ok.join(", ")})` : "Chaves salvas");
      refreshHealth();
    } catch (err) {
      $("#keysStatus").textContent = err.message || "Falha ao salvar";
      toast(err.message || "Falha ao salvar chaves");
    }
  };

  $("#formLlm").onsubmit = async (e) => {
    e.preventDefault();
    const body = {
      baseUrl: $("#llmBase").value.trim() || "http://127.0.0.1:4850/v1",
      mode: "session",
      model: $("#llmModel").value.trim(),
    };
    const res = await api("/api/llm-proxy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setLlmStatus(res.config || {}, "Modelo salvo");
    toast("Salvo");
    try {
      await testLlm();
    } catch (err) {
      $("#llmStatus").textContent = err.message;
    }
    refreshHealth();
  };

  $("#btnLlmTest").onclick = () =>
    testLlm().catch((err) => {
      const msg = err.message || "falha no teste";
      $("#llmStatus").textContent = msg;
      toast(msg.length > 90 ? "Sessão incompleta — recapture com o site aberto" : msg);
    });
  $("#btnOpenExt").onclick = async () => {
    try {
      const data = await api("/api/llm-proxy/open-extension", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const hint = $("#extPathHint");
      if (hint && data.path) {
        hint.hidden = false;
        hint.textContent = `Pasta: ${data.path} — carregue esta pasta no Chrome/Edge (não a de Program Files).`;
      }
      toast("Pasta estável aberta — carregue em chrome://extensions");
    } catch {
      toast("Abra manualmente %USERPROFILE%\\ATIVAVID\\extension\\llm-session");
    }
  };

  const btnAud = $("#btnAuditoria");
  ligarRefazerDaAuditoria();
  if (btnAud) btnAud.onclick = () => rodarAuditoria().catch((e) => toast(e.message));
  const btnDoutorRun = $("#btnDoutorRun");
  if (btnDoutorRun) btnDoutorRun.onclick = () => runDoutor().catch((err) => toast(err.message));
  const btnCopy = $("#btnDoutorCopy");
  if (btnCopy) {
    btnCopy.onclick = async () => {
      const data = await api("/api/doutor/copy");
      try {
        await navigator.clipboard.writeText(data.text || "");
        toast("Diagnóstico copiado");
      } catch {
        toast("Não consegui copiar — selecione o texto na tela");
      }
    };
  }
  document.querySelectorAll("[data-key-toggle]").forEach((btn) => {
    btn.onclick = () => {
      const id = btn.getAttribute("data-key-toggle");
      const input = id && document.getElementById(id);
      if (!input) return;
      input.type = input.type === "password" ? "text" : "password";
    };
  });
  document.querySelectorAll("[data-key-test]").forEach((btn) => {
    btn.onclick = async () => {
      const service = btn.getAttribute("data-key-test");
      $("#keysStatus").textContent = `Testando ${service}…`;
      const body = { service };
      const g = ($("#keyGroq")?.value || "").trim();
      const px = ($("#keyPx")?.value || "").trim();
      if (service === "groq" && g) body.GROQ_API_KEY = g;
      if (service === "pexels" && px) body.PEXELS_API_KEY = px;
      const fp = ($("#keyFreepik")?.value || "").trim();
      if (service === "freepik" && fp) body.FREEPIK_API_KEY = fp;
      try {
        const res = await api("/api/keys/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        // `hint` diz o que o "OK" nao diz: chave valida com creditos
        // esgotados falha na trilha do mesmo jeito (caso real, 26/08).
        const rotulo = res.ok ? (res.hint ? `${service}: ${res.hint}` : `${service}: OK`)
          : `${service}: falhou`;
        $("#keysStatus").textContent = rotulo;
        toast(rotulo, res.hint ? 6000 : 2500);
      } catch (e) {
        $("#keysStatus").textContent = e.message;
        toast(e.message);
      }
    };
  });
  const btnSavePerf = $("#btnSavePerf");
  if (btnSavePerf) {
    btnSavePerf.onclick = async () => {
      const performanceProfile = $("#perfProfile").value;
      await api("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ performanceProfile }),
      });
      toast("Perfil salvo — reinicie o ATIVAVID para aplicar os workers leves");
      loadSistema().catch(() => {});
    };
  }
  // Motor local de musica: 4,8 GB que NAO vem no instalador. Sem esta tela o
  // cliente escolhia "IA local primeiro" e nada acontecia — o launcher saia
  // com "motor nao instalado" e a trilha vinha da nuvem, em silencio.
  const btnMotor = $("#btnInstalarMotorMusica");
  if (btnMotor && !btnMotor.dataset.wired) {
    btnMotor.dataset.wired = "1";
    btnMotor.onclick = async () => {
      btnMotor.disabled = true;
      try {
        await api("/api/musica/motor", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "instalar" }),
        });
        toast("Baixando a IA local de música — pode deixar rodando", 6000);
        acompanharMotorMusica();
      } catch (e) {
        toast(e.message || "Não deu para começar a instalação");
        btnMotor.disabled = false;
      }
    };
  }
  const btnPacote = $("#btnBaixarPacote");
  if (btnPacote && !btnPacote.dataset.wired) {
    btnPacote.dataset.wired = "1";
    btnPacote.onclick = async () => {
      btnPacote.disabled = true;
      try {
        await api("/api/biblioteca/pacote", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "baixar" }),
        });
        toast("Baixando trilhas e efeitos — pode deixar rodando", 6000);
        acompanharPacote();
      } catch (e) {
        toast(e.message || "Não deu para começar o download");
        btnPacote.disabled = false;
      }
    };
  }
  const btnHwBench = $("#btnHwBench");
  if (btnHwBench) {
    btnHwBench.onclick = async () => {
      btnHwBench.disabled = true;
      const prev = $("#hwAccelHint");
      if (prev) prev.textContent = "Testando encoders (uns 10s)…";
      try {
        const data = await api("/api/hardware/bench", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        if (data && data.public) applyHardwareCard(data.public);
        toast(data && data.public && data.public.friendly ? data.public.friendly : "Teste concluído");
      } catch (e) {
        toast(e.message || "Falha no teste de hardware");
      } finally {
        btnHwBench.disabled = false;
      }
    };
  }
  const btnLiberarEspaco = $("#btnLiberarEspaco");
  if (btnLiberarEspaco) {
    // dica com o quanto da para recuperar (medicao barata, roda ao abrir)
    api("/api/espaco").then((m) => {
      const h = $("#espacoHint");
      if (h && m && m.totalGb >= 0.5) {
        h.textContent = `Dá para liberar ~${m.totalGb} GB ` +
          `(${m.duplicatasGb} GB de cópias duplicadas + ${m.intermediariosGb} GB de intermediários de projetos entregues).`;
      }
    }).catch(() => {});
    btnLiberarEspaco.onclick = async () => {
      btnLiberarEspaco.disabled = true;
      btnLiberarEspaco.textContent = "Liberando…";
      try {
        const r = await api("/api/espaco/liberar", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        toast(`✓ ${r.totalGb || 0} GB liberados (${r.deduplicadoGb || 0} GB deduplicados, ${r.removidoGb || 0} GB de intermediários)`, 7000);
        const h = $("#espacoHint");
        if (h) h.textContent = "";
      } catch (e) {
        toast(e.message || "Não deu para liberar espaço");
      } finally {
        btnLiberarEspaco.disabled = false;
        btnLiberarEspaco.textContent = "Liberar espaço";
      }
    };
  }
  const btnClearCache = $("#btnClearCache");
  if (btnClearCache) {
    btnClearCache.onclick = async () => {
      const res = await api("/api/cache/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      toast(`Cache limpo · ${res.freedGb || 0} GB`);
      loadSistema().catch(() => {});
    };
  }
  const btnSaveRoot = $("#btnSaveRoot");
  if (btnSaveRoot) {
    btnSaveRoot.onclick = async () => {
      const projectsRoot = $("#projectsRootInput").value.trim() || null;
      await api("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectsRoot }),
      });
      toast("Pasta salva — reinicie o app para aplicar");
    };
  }
  // 5.0.9: pasta de Entregas — vale na hora, sem reiniciar
  const btnEsc = $("#btnEntregasEscolher");
  if (btnEsc && !btnEsc.dataset.wired) {
    btnEsc.dataset.wired = "1";
    btnEsc.onclick = async () => {
      const nat = apiNativa();
      if (!nat) { toast("Escolha a pasta digitando o caminho (o seletor só existe dentro do app)"); return; }
      try {
        const r = await nat.escolher_pasta();
        const pasta = Array.isArray(r) ? r[0] : r;
        if (pasta && $("#entregasRootInput")) $("#entregasRootInput").value = String(pasta);
      } catch (e) {
        toast(e.message || "Não consegui abrir o seletor de pasta");
      }
    };
  }
  const chkAuto = $("#entregasAutoChk");
  if (chkAuto && !chkAuto.dataset.wired) {
    chkAuto.dataset.wired = "1";
    chkAuto.addEventListener("change", async () => {
      try {
        await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entregasAuto: !!chkAuto.checked }) });
        toast(chkAuto.checked ? "✓ Cada vídeo pronto vai para Entregas" : "Entregas só pelo botão Reunir");
      } catch (e) {
        toast(e.message || "Não consegui salvar");
        chkAuto.checked = !chkAuto.checked;
      }
    });
  }
  const btnSaveEnt = $("#btnSaveEntregas");
  if (btnSaveEnt && !btnSaveEnt.dataset.wired) {
    btnSaveEnt.dataset.wired = "1";
    btnSaveEnt.onclick = async () => {
      const entregasRoot = ($("#entregasRootInput")?.value || "").trim() || null;
      try {
        const r = await api("/api/settings", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entregasRoot }),
        });
        const efetiva = (r.settings && r.settings.entregasRootEfetiva) || "";
        if ($("#entregasRootHint")) $("#entregasRootHint").textContent = efetiva ? `Em uso: ${efetiva}` : "";
        toast(entregasRoot ? "✓ Entregas passam a ir para essa pasta" : "✓ Entregas voltam para o padrão, ao lado dos Projetos");
      } catch (e) {
        toast(e.message || "Não consegui salvar");
      }
    };
  }
  const btnLicAdvOpen = $("#btnLicAdvOpen");
  if (btnLicAdvOpen) {
    btnLicAdvOpen.onclick = () => {
      const dlg = $("#dlgLicAdv");
      try { dlg?.showModal(); } catch { /* ignore */ }
    };
  }
  const btnLicAccountOpen = $("#btnLicAccountOpen");
  if (btnLicAccountOpen) {
    btnLicAccountOpen.onclick = () => openLicAccountDialog("");
  }
  const btnLicAccountClose = $("#btnLicAccountClose");
  if (btnLicAccountClose) {
    btnLicAccountClose.onclick = () => closeLicAccountDialog();
  }
  const btnLicAdvClose = $("#btnLicAdvClose");
  if (btnLicAdvClose) {
    btnLicAdvClose.onclick = () => {
      const dlg = $("#dlgLicAdv");
      try { dlg?.close(); } catch { /* ignore */ }
    };
  }
  const btnLicRef = $("#btnLicenseRefresh");
  if (btnLicRef) {
    btnLicRef.onclick = async () => {
      const res = await api("/api/license/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      renderLicense(res);
      toast(res.entitled ? "Licença OK" : "Sem licença ativa");
    };
  }
  const btnSaveLic = $("#btnSaveLicenseCfg");
  if (btnSaveLic) {
    btnSaveLic.onclick = async () => {
      try {
        const patch = {
          supabaseUrl: ($("#supabaseUrlInput")?.value || "").trim(),
          checkoutUrl: ($("#checkoutUrlInput")?.value || "").trim(),
        };
        // Password vazio no form não deve apagar a anon key já salva
        const anonTyped = ($("#supabaseAnonInput")?.value || "").trim();
        if (anonTyped) patch.supabaseAnonKey = anonTyped;
        await api("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        });
        toast("Configuração salva");
        const res = await api("/api/license/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        renderLicense(res);
        await refreshAuthUi();
      } catch (e) {
        toast(e.message || "Falha ao salvar");
      }
    };
  }

  const btnAuthLogin = $("#btnAuthLogin");
  const formLogin = $("#formLogin");
  $$(".dlg-login-tab").forEach((tab) => {
    tab.onclick = () => setAuthDialogMode(tab.dataset.authMode || "login");
  });
  const doLogin = async (e) => {
    if (e) e.preventDefault();
    const err = $("#loginErr");
    if (err) {
      err.hidden = true;
      err.textContent = "";
    }
    const mode = ($("#authMode")?.value || "login") === "signup" ? "signup" : "login";
    const endpoint = mode === "signup" ? "/api/auth/signup" : "/api/auth/login";
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: ($("#authEmail")?.value || "").trim(),
          password: $("#authPassword")?.value || "",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        const detail = data.message || data.error_description || data.error || "";
        throw new Error(
          detail && !["auth_failed", "signup_failed"].includes(String(detail))
            ? String(detail)
            : (mode === "signup" ? "Não foi possível criar a conta." : "E-mail ou senha inválidos.")
        );
      }
      if ($("#authPassword")) $("#authPassword").value = "";
      try {
        const emailSaved = (data.email || ($("#authEmail")?.value || "").trim() || "");
        if ($("#authRemember")?.checked && emailSaved) {
          localStorage.setItem("ativavid-auth-email", emailSaved);
          localStorage.setItem("ativavid-auth-remember", "1");
        } else {
          localStorage.removeItem("ativavid-auth-email");
          localStorage.setItem("ativavid-auth-remember", "0");
        }
      } catch { /* ignore */ }
      const loggedIn = data.loggedIn !== false && !!(data.email || data.isAdmin || mode === "login");
      if (loggedIn || data.access_token || mode === "login" || data.loggedIn) {
        state.auth = {
          loggedIn: true,
          isAdmin: !!data.isAdmin,
          email: data.email || ($("#authEmail")?.value || "").trim() || null,
        };
        // signup sem sessão (confirm email)
        if (mode === "signup" && data.loggedIn === false) {
          state.auth.loggedIn = false;
        }
      }
      applyAccountChrome(state.auth || { loggedIn: false });
      if (state.auth?.loggedIn) {
        closeLoginDialog();
        toast(data.message || (mode === "signup" ? "Conta criada" : "Login OK"));
        try {
          const lic = await api("/api/license/refresh", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          });
          renderLicense(lic);
        } catch {
          try {
            const lic = await api("/api/license");
            renderLicense(lic);
          } catch { /* ignore */ }
        }
        applyAccountChrome(state.auth);
        if (data.isAdmin) setView("licenca");
      } else {
        toast(data.message || "Conta criada — confirme o e-mail e entre.");
        setAuthDialogMode("login");
      }
    } catch (errLogin) {
      const msg = errLogin.message || "Falha no login";
      if (err) {
        err.hidden = false;
        err.textContent = msg;
      }
      toast(msg);
    }
  };
  if (formLogin) formLogin.onsubmit = doLogin;
  else if (btnAuthLogin) btnAuthLogin.onclick = doLogin;

  ["btnHomeLogin", "btnOpenLogin"].forEach((id) => {
    const el = $(`#${id}`);
    if (!el) return;
    el.onclick = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const st = state.auth || {};
      if (st.loggedIn) setView("licenca");
      else openLoginDialog();
    };
  });
  wireWorkspaceMenu();
  ["btnLoginClose"].forEach((id) => {
    const el = $(`#${id}`);
    if (el) el.onclick = () => closeLoginDialog();
  });

  const btnAuthLogout = $("#btnAuthLogout");
  if (btnAuthLogout) {
    btnAuthLogout.onclick = async () => {
      try {
        await api("/api/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        state.auth = { loggedIn: false, isAdmin: false, email: null };
        applyAccountChrome(state.auth);
        toast("Saiu");
      } catch (e) {
        toast(e.message || "Falha ao sair");
      }
    };
  }

  const btnAdminSaveSrv = $("#btnAdminLicSaveSrv");
  if (btnAdminSaveSrv) {
    btnAdminSaveSrv.onclick = async () => {
      try {
        const srv = ($("#supabaseServiceInput")?.value || "").trim();
        if (!srv) {
          toast("Cole a service_role do Supabase (Settings → API)");
          $("#supabaseServiceInput")?.focus();
          return;
        }
        if (!srv.startsWith("eyJ") && !srv.startsWith("sb_")) {
          toast("Isso não parece uma service_role (começa com eyJ…)");
          return;
        }
        const res = await api("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ supabaseServiceRoleKey: srv }),
        });
        if ($("#supabaseServiceInput")) $("#supabaseServiceInput").value = "";
        const hint = $("#adminServiceHint");
        if (hint) {
          hint.hidden = false;
          hint.textContent = "Salva neste PC.";
        }
        const createHint = $("#adminCreateHint");
        if (createHint) {
          createHint.textContent = "Service role ok — pode criar contas Auth.";
        }
        adminOut(res.settings ? { ok: true, hasServiceRole: !!res.settings.hasServiceRole } : res);
        toast("Service role salva");
        const dlg = $("#dlgLicAdv");
        try { dlg?.close(); } catch { /* ignore */ }      } catch (e) {
        toast(e.message || "Falha ao salvar");
      }
    };
  }
  $$("#adminDayPresets [data-days]").forEach((btn) => {
    btn.onclick = () => {
      if ($("#adminLicDays")) $("#adminLicDays").value = btn.dataset.days || "7";
    };
  });
  const btnAdminCreateAccount = $("#btnAdminCreateAccount");
  if (btnAdminCreateAccount) {
    btnAdminCreateAccount.onclick = async () => {
      try {
        const email = ($("#adminLicEmail")?.value || "").trim();
        if (!email) {
          toast("Informe o e-mail do cliente");
          return;
        }
        const password = ($("#adminLicPassword")?.value || "").trim();
        const data = await api("/api/admin/access", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "create",
            email,
            password: password || undefined,
            days: Number($("#adminLicDays")?.value || 7),
            maxDevices: Number($("#adminLicMaxDev")?.value || 1),
            notes: ($("#adminLicNotes")?.value || "").trim(),
          }),
        });
        adminOut(data);
        if (data.error === "service_role_required") {
          const dlg = $("#dlgLicAdv");
          const box = $("#adminSrvBox");
          if (box) box.hidden = false;
          try { dlg?.showModal(); } catch { /* ignore */ }
          $("#supabaseServiceInput")?.focus();
          toast("Cole e salve a service_role em Avançado");
          return;
        }
        if (data.ok && data.password) {
          toast(`Conta criada — senha: ${data.password}`);
        } else {
          toast(data.ok ? (data.message || "Conta pronta") : (data.message || "Falha"));
        }
        if (data.ok) {
          if ($("#adminLicPassword")) $("#adminLicPassword").value = "";
          await loadAccessList();
          closeLicAccountDialog();
        }
      } catch (e) {
        adminOut(String(e.message || e));
        toast(e.message || "Falha ao criar conta");
      }
    };
  }
  const btnAdminGrant = $("#btnAdminGrantAccess");
  if (btnAdminGrant) {
    btnAdminGrant.onclick = async () => {
      try {
        const email = ($("#adminLicEmail")?.value || "").trim();
        if (!email) {
          toast("Informe o e-mail do cliente");
          return;
        }
        const data = await api("/api/admin/access", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "grant",
            email,
            days: Number($("#adminLicDays")?.value || 7),
            maxDevices: Number($("#adminLicMaxDev")?.value || 1),
            notes: ($("#adminLicNotes")?.value || "").trim(),
          }),
        });
        adminOut(data);
        toast(data.ok ? (data.message || "Acesso liberado") : (data.message || "Falha"));
        if (data.ok) {
          await loadAccessList();
          closeLicAccountDialog();
        }
      } catch (e) {
        adminOut(String(e.message || e));
        toast(e.message || "Falha ao liberar");
      }
    };
  }
  // Liberar pelo ID do dispositivo: o cliente le o ID na tela de Licenca e
  // manda. Nao precisa criar conta nem digitar chave.
  $("#btnLicDeviceOpen")?.addEventListener("click", () => abrirDlgDispositivo(true));
  $("#btnLicDeviceClose")?.addEventListener("click", () => abrirDlgDispositivo(false));
  $("#adminDevDayPresets")?.addEventListener("click", (e) => {
    const d = e.target?.dataset?.days;
    if (d && $("#adminDevDays")) $("#adminDevDays").value = d;
  });

  const chamaDevice = async (action, falhaMsg) => {
    const deviceId = ($("#adminDevId")?.value || "").trim();
    if (!deviceId) {
      devMsg("Informe o ID do dispositivo.");
      return;
    }
    try {
      const data = await api("/api/admin/devices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          deviceId,
          days: Number($("#adminDevDays")?.value || 365),
          email: ($("#adminDevEmail")?.value || "").trim(),
          notes: ($("#adminDevNotes")?.value || "").trim(),
        }),
      });
      adminOut(data);
      devMsg(data.message || "");
      toast(data.ok ? (data.message || "Pronto") : (data.message || falhaMsg));
      if (data.ok) {
        await loadDeviceList();
        if (action === "grant") $("#adminDevId").value = "";
      }
    } catch (e) {
      adminOut(String(e.message || e));
      devMsg(String(e.message || e));
      toast(e.message || falhaMsg);
    }
  };
  $("#btnAdminGrantDevice")?.addEventListener("click", () => chamaDevice("grant", "Falha ao liberar"));
  $("#btnAdminReleaseDevice")?.addEventListener("click", () => chamaDevice("release", "Falha ao desvincular"));

  const btnAdminListAccess = $("#btnAdminListAccess");
  if (btnAdminListAccess) {
    btnAdminListAccess.onclick = async () => {
      try {
        const data = await loadAccessList();
        loadAberturas().catch(() => {});
        adminOut(data);
        const n = (data.access || []).length;
        toast(data.ok ? `${n} acesso(s)` : (data.message || "Falha"));
      } catch (e) {
        adminOut(String(e.message || e));
        toast(e.message || "Falha ao listar");
      }
    };
  }
  const btnAdminRevoke = $("#btnAdminRevokeAccess");
  if (btnAdminRevoke) {
    btnAdminRevoke.onclick = async () => {
      try {
        const email = ($("#adminLicEmail")?.value || "").trim();
        if (!email) {
          toast("Informe o e-mail para revogar");
          return;
        }
        const data = await api("/api/admin/access", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "revoke", email }),
        });
        adminOut(data);
        toast(data.ok ? (data.message || "Revogado") : (data.message || "Falha"));
        if (data.ok) {
          await loadAccessList();
          closeLicAccountDialog();
        }
      } catch (e) {
        adminOut(String(e.message || e));
        toast(e.message || "Falha ao revogar");
      }
    };
  }
  const btnAdminCreate = $("#btnAdminLicCreate");
  if (btnAdminCreate) {
    btnAdminCreate.onclick = async () => {
      try {
        const srv = ($("#supabaseServiceInput")?.value || "").trim();
        if (srv) {
          await api("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ supabaseServiceRoleKey: srv }),
          });
          $("#supabaseServiceInput").value = "";
        }
        const data = await api("/api/admin/licenses", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: ($("#adminLicEmail")?.value || "").trim(),
            days: Number($("#adminLicDays")?.value || 365),
            maxDevices: Number($("#adminLicMaxDev")?.value || 1),
            notes: ($("#adminLicNotes")?.value || "").trim(),
          }),
        });
        adminOut(data);
        if (data.ok && data.licenseKey) {
          toast("Licença criada: " + data.licenseKey);
        } else {
          toast(data.message || data.error?.message || "Falha ao criar");
        }
      } catch (e) {
        adminOut(String(e.message || e));
        toast(e.message || "Falha ao criar");
      }
    };
  }
  const btnAdminList = $("#btnAdminLicList");
  if (btnAdminList) {
    btnAdminList.onclick = async () => {
      try {
        const data = await api("/api/admin/licenses");
        adminOut(data);
        toast(data.ok ? `${(data.licenses || []).length} licença(s)` : "Falha ao listar");
      } catch (e) {
        adminOut(String(e.message || e));
        toast(e.message || "Falha ao listar");
      }
    };
  }
  const btnAdminRelease = $("#btnAdminDeviceRelease");
  if (btnAdminRelease) {
    btnAdminRelease.onclick = async () => {
      try {
        const deviceId = ($("#adminDeviceId")?.value || "").trim();
        if (!deviceId) {
          toast("Informe o Device ID");
          return;
        }
        const data = await api("/api/admin/devices", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "release", deviceId }),
        });
        adminOut(data);
        toast(data.ok ? "PC liberado" : (data.message || "Falha"));
      } catch (e) {
        adminOut(String(e.message || e));
        toast(e.message || "Falha ao liberar");
      }
    };
  }
  // Quem foi liberado por CONTA (o caminho recomendado) nao tem chave nenhuma
  // para digitar: sem esta saida ele ficava preso olhando o campo de chave.
  const btnDlgLogin = $("#btnLicDlgLogin");
  if (btnDlgLogin) {
    btnDlgLogin.onclick = () => {
      const dlg = $("#dlgLicense");
      if (dlg?.open) dlg.close();
      // "Criar conta gratis" (trial so com cadastro) abre direto no cadastro.
      openLoginDialog(btnDlgLogin.dataset.modo === "signup" ? "signup" : "login");
    };
  }
  // Cada plano abre o SEU link (precos diferentes na Stripe), tanto no
  // painel de Licenca quanto na janela do bloqueio.
  for (const id of ["#btnLicenseCheckout", "#btnLicDlgAnual"]) {
    const b = $(id);
    if (b) b.onclick = () => openCheckout(b.dataset.url || undefined);
  }
  for (const id of ["#btnLicenseMensal", "#btnLicDlgMensal"]) {
    const b = $(id);
    if (b) {
      b.onclick = () => openCheckout(b.dataset.url || state.license?.checkoutUrlMensal);
    }
  }
  for (const id of ["#btnLicDlgPcCopiar", "#btnLicPcCopiar"]) {
    const b = $(id);
    if (b) b.onclick = () => { copiarCodigoDoPc().catch(() => {}); };
  }

  // "Atualizar agora": o servidor baixa o exe e o executa — o instalador
  // derruba o app e o reabre. Um clique no lugar do ciclo
  // navegador -> download -> achar o exe -> rodar.
  const btnUpdInstalar = $("#btnUpdInstalar");
  if (btnUpdInstalar) {
    btnUpdInstalar.onclick = () => instalarAtualizacao(btnUpdInstalar);
  }
  const btnUpdLater = $("#btnUpdLater");
  if (btnUpdLater) {
    btnUpdLater.onclick = () => {
      // Nao perguntar de novo por ESTA versao (a proxima volta a avisar).
      try {
        const nova = String(((state.license || {}).update || {}).latestVersion
          || state.updateLatest || "").replace(/^v/i, "");
        if (nova) localStorage.setItem("ativavid.updateAdiado", nova);
      } catch { /* modo restrito */ }
      const dlg = $("#dlgUpdate");
      if (dlg?.open) dlg.close();
    };
  }
  const btnUpdate = $("#btnUpdateCheck");
  if (btnUpdate) {
    btnUpdate.onclick = async () => {
      try {
        await api("/api/license/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        }).then((lic) => renderLicense(lic)).catch(() => {});
      } catch { /* ignore */ }
      const res = await api("/api/update/check");
      $("#updateHint").textContent = res.message || "Não foi possível verificar.";
      marcarBotaoDeUpdate(res);
      if (res.force) {
        openUpdateDialog({ update: res, mode: "update_required", message: res.message });
        toast("Atualização obrigatória");
      } else {
        toast(res.updateAvailable ? "Há atualização" : "Você está no build atual");
      }
    };
  }
  // Atualizar é DENTRO do app: o servidor baixa o instalador e o executa
  // (o instalador derruba o ATIVAVID e o reabre). O navegador só entra se
  // o download falhar — antes este botão SEMPRE mandava o usuário para o
  // GitHub achar o .exe na mão, enquanto a janela de aviso já fazia tudo
  // sozinha: dois caminhos para a mesma coisa, e o pior deles em Ajustes.
  const btnUpdateOpen = $("#btnUpdateOpen");
  if (btnUpdateOpen) {
    btnUpdateOpen.onclick = () => instalarAtualizacao(btnUpdateOpen);
  }
  // O formato de saida morava na tela de Marca. Ele grava na marca ativa,
  // e por isso vai pelo `action: "format"` — `save_brand` troca o arquivo
  // inteiro pelo corpo do pedido, entao mandar so o formato daqui apagaria
  // o estilo base junto.
  const btnBase = $("#btnEstiloBase");
  if (btnBase) {
    btnBase.onclick = () => {
      state.editPresetId = "";
      state.editPresetNome = "";
      barraDoEstilo();
      const fr = $("#estiloFrame");
      if (fr) fr.src = estiloFrameSrc();
      loadBrandsUi().catch(() => {});
    };
  }
  const selFmt = $("#exportPresetSelect");
  if (selFmt) {
    selFmt.onchange = async () => {
      try {
        await api("/api/brands", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "format", exportPreset: selFmt.value }),
        });
        toast("Formato salvo");
        await loadBrandsUi();
      } catch (e) {
        toast(e.message || "Falha ao salvar o formato");
      }
    };
  }
  const painel = $("#libraryPanel");
  if (painel && !painel.dataset.wiredDel) {
    painel.dataset.wiredDel = "1";
    painel.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-libdel]");
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();   // senao o clique tambem TOCA o efeito
      const rel = btn.dataset.libdel;
      const nome = rel.split("/").pop();
      const ok = await pedirConfirmacao(
        "Apagar este arquivo?",
        `"${nome}" vai para a Lixeira do Windows — dá para trazer de volta por lá.`,
        "Apagar", true);
      if (!ok) return;
      try {
        const r = await api("/api/library/remover", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rel }),
        });
        toast(r.lixeira ? "Foi para a Lixeira" : "Apagado");
        await loadLibraryUi();
      } catch (err) {
        toast(err.message || "Não deu para apagar");
      }
    });
  }
  const chkSfx = $("#sfxDoUsuario");
  if (chkSfx) {
    // Estado real do servidor: a caixa desmarcada de HTML mentiria para
    // quem ja tivesse ligado a troca.
    api("/api/settings")
      .then((cfg) => { chkSfx.checked = !!(cfg && cfg.sfxDoUsuario); })
      .catch(() => {});
    chkSfx.onchange = async () => {
      try {
        await api("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sfxDoUsuario: !!chkSfx.checked }),
        });
        toast(chkSfx.checked
          ? "Seus efeitos entram nos próximos vídeos"
          : "Voltou para os efeitos do app");
        // Os selos "toca no vídeo" de cada arquivo mudam junto.
        loadLibraryUi().catch(() => {});
      } catch (e) {
        chkSfx.checked = !chkSfx.checked;
        toast(e.message || "Não deu para salvar");
      }
    };
  }
  const btnLib = $("#btnLibraryRefresh");
  if (btnLib) {
    btnLib.onclick = async () => {
      const lib = await api("/api/library");
      toast(`${lib.items?.length || 0} na biblioteca`);
      try {
        await api("/api/open-path", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: lib.root }),
        });
      } catch {
        $("#libraryHint").textContent = `Abra: ${lib.root}`;
      }
      loadBrandsUi().catch(() => {});
    };
  }
  $("#btnSidebar").onclick = () => {
    document.body.classList.add("sb-collapsed");
    try { localStorage.setItem("ativavid-sb-collapsed", "1"); } catch { /* ignore */ }
  };
  const home = $("#btnHome");
  if (home) {
    home.onclick = () => {
      if (document.body.classList.contains("sb-collapsed")) {
        document.body.classList.remove("sb-collapsed");
        try { localStorage.setItem("ativavid-sb-collapsed", "0"); } catch { /* ignore */ }
        return;
      }
      goHome();
    };
  }
}

/* A auditoria dos videos ENTREGUES. Diferente do Diagnostico, que olha a
 * instalacao: aqui se conferem os projetos que ja sairam.
 *
 * Nao roda sozinha ao abrir a tela (leva ~11s e le 187 projetos) — o
 * Diagnostico roda porque e barato e e a primeira pergunta de quem chega
 * aqui; esta e uma pergunta que se faz de propósito. */
async function rodarAuditoria() {
  const out = $("#auditoriaOut");
  const resumo = $("#auditoriaResumo");
  const btn = $("#btnAuditoria");
  if (!out) return;
  if (btn) { btn.disabled = true; btn.textContent = "Conferindo…"; }
  if (resumo) resumo.textContent = "Lendo os projetos…";
  out.classList.add("carregando");
  let d;
  try {
    d = await api("/api/auditoria");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Conferir de novo"; }
    out.classList.remove("carregando");
  }
  if (!d || d.ok === false) {
    if (resumo) resumo.textContent = `Não deu para conferir: ${(d && d.erro) || "sem detalhe"}`;
    out.innerHTML = "";
    return;
  }
  const itens = d.itens || [];
  out.innerHTML = itens.map((it) => `<article class="doutor-item aviso">
      <header class="doutor-item-top">
        <span class="doutor-dot" aria-hidden="true"></span>
        <h5 class="t">${escapeHtml(String(it.projeto || "").slice(0, 46))}</h5>
        <button type="button" class="ghost-btn ghost-btn--sm doutor-refazer"
                data-refazer="${escapeHtml(String(it.projeto || ""))}"
                title="Recria este vídeo com o pipeline de hoje">Refazer</button>
      </header>
      <p class="d">${escapeHtml((it.problemas || []).join(" · "))}</p>
    </article>`).join("") || "";
  if (resumo) {
    resumo.textContent = itens.length
      ? `${itens.length} de ${d.total} projeto(s) com alguma marca — `
        + (d.resumo || []).map((r) => `${r.projetos} ${r.tipo}`).join(" · ")
      : `${d.total} projetos conferidos, nenhuma marca.`;
    resumo.classList.toggle("doutor-atencao", itens.length > 0);
  }
}

/* "Refazer": poe o projeto de volta na fila com o pipeline de hoje.
 *
 * As duas familias mais comuns da auditoria — rotulo errado no EDL e pausa
 * morta sobrando — foram consertadas em 29/08. Os videos antigos ficaram
 * como estavam, e refazer resolve. Sem isto a auditoria so acusa.
 *
 * Pede confirmacao: SUBSTITUI o video entregue e ocupa a fila por alguns
 * minutos. */
async function refazerProjeto(pasta) {
  const ok = await pedirConfirmacao(
    "Refazer este vídeo?",
    "Ele volta para a fila e é recriado com o pipeline de hoje — o que "
    + "estiver torto é corrigido. O vídeo atual é substituído no fim, e "
    + "isso leva alguns minutos.",
    "Refazer");
  if (!ok) return;
  const r = await fetch("/api/jobs/requeue-folder", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({folder: pasta}),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.error) {
    toast(d.error || "Não deu para refazer este vídeo");
    return;
  }
  toast("Na fila — o vídeo vai ser recriado");
  refreshJobs().catch(() => {});
}

/* "Limpar a busca" no vazio: sem isto o usuario tem de achar o campo de
 * novo, e o campo esta fora da lista que ele esta olhando. */
document.addEventListener("click", (e) => {
  const todas = e.target.closest("[data-ver-todas]");
  if (todas) {
    setWsMarca("all");
    renderWsMarcas(); renderWorkspaceCard(); renderJobs();
    return;
  }
  const b = e.target.closest("[data-limpar-busca]");
  if (!b) return;
  const view = b.dataset.limparBusca;
  const campo = $(view === "done" ? "#doneSearch" : "#projSearch");
  if (campo) campo.value = "";
  if (view === "done") state.doneBusca = "";
  else state.projBusca = "";
  renderJobs();
});

function ligarRefazerDaAuditoria() {
  const out = $("#auditoriaOut");
  if (!out || out.dataset.wired) return;
  out.dataset.wired = "1";
  out.addEventListener("click", (e) => {
    const b = e.target.closest("[data-refazer]");
    if (!b) return;
    refazerProjeto(b.dataset.refazer).catch((err) => toast(err.message));
  });
}

const DOUTOR_ROTULO = {ok: "ok", aviso: "atenção", bloqueio: "impede"};

/* A checagem roda sozinha ao abrir Configuracoes e o resultado nasce
 * ABERTO. O resumo no topo diz o veredito em uma linha — e o unico numero
 * que a maioria vai ler. */
async function runDoutor() {
  const out = $("#doutorOut");
  if (!out) return;
  const resumo = $("#doutorResumo");
  const btn = $("#btnDoutorRun");
  if (btn) { btn.disabled = true; btn.textContent = "Checando…"; }
  if (resumo) resumo.textContent = "Verificando a instalação…";
  out.classList.add("carregando");
  let data;
  try {
    data = await api("/api/doutor");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Checar novamente"; }
    out.classList.remove("carregando");
  }
  const itens = data.itens || [];
  const conta = {ok: 0, aviso: 0, bloqueio: 0};
  out.innerHTML = itens
    .map((it) => {
      const nivel = it.nivel || "ok";
      const mark = nivel === "ok" ? "ok" : nivel === "aviso" ? "aviso" : "bloqueio";
      conta[mark]++;
      return `<article class="doutor-item ${mark}">
        <header class="doutor-item-top">
          <span class="doutor-dot" aria-hidden="true"></span>
          <h5 class="t">${escapeHtml(it.titulo || nivel)}</h5>
          <span class="doutor-tag">${DOUTOR_ROTULO[mark]}</span>
        </header>
        <p class="d">${escapeHtml(it.detalhe || "")}</p>
        ${it.solucao ? `<p class="s">${escapeHtml(it.solucao)}</p>` : ""}
        ${it.acao ? `<button type="button" class="ghost-btn ghost-btn--sm doutor-acao"
          data-acao="${escapeHtml(it.acao)}">${escapeHtml(it.acaoTexto || "Instalar")}</button>` : ""}
      </article>`;
    })
    .join("") || "<p class='hint'>Sem itens.</p>";
  if (resumo) {
    // O que importa primeiro e o que IMPEDE; depois o que merece atencao.
    resumo.textContent = conta.bloqueio
      ? `${conta.bloqueio} item(ns) impedem o funcionamento — veja abaixo.`
      : conta.aviso
        ? `Tudo funciona; ${conta.aviso} ponto(s) merecem atenção.`
        : `${conta.ok} verificação(ões), tudo certo.`;
    resumo.classList.toggle("doutor-ruim", conta.bloqueio > 0);
    resumo.classList.toggle("doutor-atencao", !conta.bloqueio && conta.aviso > 0);
  }
  // O cabecalho da tela ("Tudo funcionando corretamente") vinha do
  // /api/system e nao do Diagnostico: na maquina de uma cliente (04/09) o
  // topo dizia tudo certo enquanto o cartao logo abaixo pedia ATENCAO. Quem
  // acabou de checar e quem fala.
  const topo = $("#sysStatusLine");
  if (topo) {
    topo.textContent = conta.bloqueio
      ? `${conta.bloqueio} item(ns) impedem o funcionamento — veja o Diagnóstico`
      : conta.aviso
        ? `Tudo funciona; ${conta.aviso} ponto(s) merecem atenção — veja o Diagnóstico`
        : "Tudo funcionando corretamente";
  }
  $("#btnDoutorCopy")?.classList.toggle("hidden", !itens.length);
  wireAcoesDoDoutor(out);
}

/* O botao que o diagnostico desenha (5.0.25).
 *
 * Ele: "aqui nao deveria mostrar se a IA local esta instalada... porque
 * assim o cliente poderia baixar por aqui nessa checagem". A instalacao e a
 * MESMA de Configuracoes > Musica dos videos — a rota, o progresso e o
 * acompanhamento sao os de la; o que muda e de onde se clica. */
function wireAcoesDoDoutor(out) {
  if (!out || out.dataset.acoesWired) return;
  out.dataset.acoesWired = "1";
  out.addEventListener("click", async (e) => {
    const btn = e.target.closest(".doutor-acao");
    if (!btn) return;
    const acao = btn.dataset.acao;
    if (acao !== "instalar_musica" && acao !== "baixar_pacote") return;
    btn.disabled = true;
    try {
      if (acao === "instalar_musica") {
        await api("/api/musica/motor", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "instalar" }),
        });
        toast("Baixando a IA local de música — pode deixar rodando", 6000);
        acompanharMotorMusica();
      } else {
        // Biblioteca de trilhas vazia numa maquina sem NVIDIA: o video sai
        // mudo de musica. O mesmo pacote do cartao de Configuracoes.
        await api("/api/biblioteca/pacote", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "baixar" }),
        });
        toast("Baixando trilhas e efeitos — pode deixar rodando", 6000);
        acompanharPacote();
      }
      btn.textContent = "Baixando…";
      // o card de Configuracoes ja sabe acompanhar; aqui basta reavaliar
      // quando terminar
      setTimeout(() => rodarDoutor().catch(() => {}), 4000);
    } catch (err) {
      toast(err.message || "Não deu para começar o download");
      btn.disabled = false;
    }
  });
}

async function loadLicenca() {
  try {
    const lic = await api("/api/license");
    renderLicense(lic);
  } catch { /* ignore */ }
  await refreshAuthUi().catch(() => {});
  try {
    const s = await api("/api/settings");
    const box = $("#adminSrvBox");
    if (box) box.hidden = false;
    const createHint = $("#adminCreateHint");
    if (createHint) {
      createHint.textContent = s.hasServiceRole
        ? "Service role já configurada neste PC."
        : "Cole a service_role uma vez para criar contas Auth.";
    }
    const srvHint = $("#adminServiceHint");
    if (srvHint) {
      if (s.hasServiceRole) {
        srvHint.hidden = false;
        srvHint.textContent = "Já salva neste PC (cole outra para substituir).";
      } else {
        srvHint.hidden = true;
      }
    }
  } catch { /* ignore */ }
  if (state.auth && state.auth.isAdmin) {
    await loadAccessList().catch(() => {});
    await loadDeviceList().catch(() => {});
  }
}

function applySistemaData(data) {
  const hint = $("#sysMachineHint");
  const status = $("#sysStatusLine");
  const m = data.machine || {};
  const perf = data.performance || {};
  const s = data.settings || {};
  if (status) {
    status.textContent = m.error
      ? "Há um aviso — veja Avançado se precisar"
      : "Tudo funcionando corretamente";
  }
  if (hint) {
    const base =
      `${m.os || "?"} ${m.osRelease || ""} · ${m.cores || "?"} núcleos · RAM ${m.ramGb ?? "?"} GB · `
      + `encoder ${(m.accel && m.accel.preferredEncoder) || "libx264"} · disco ${m.diskFreeGb ?? "?"} GB`;
    hint.textContent = m.error ? `${base} (aviso: ${m.error})` : base;
  }
  if ($("#sysPerfHint")) {
    $("#sysPerfHint").textContent = "Motor de render: Automático.";
  }
  if ($("#sysLaneHint")) {
    $("#sysLaneHint").textContent = "Acompanhe o processamento dos seus vídeos.";
  }
  if ($("#sysMetricProfile")) $("#sysMetricProfile").textContent = perf.label || "—";
  if ($("#sysMetricJobs")) $("#sysMetricJobs").textContent = String(perf.parallelJobs ?? "—");
  if ($("#sysMetricProxy")) {
    $("#sysMetricProxy").textContent = perf.proxyEnabled ? `${perf.proxyHeight}p` : "off";
  }
  if ($("#perfProfile") && s.performanceProfile) $("#perfProfile").value = s.performanceProfile || "auto";
  pintarMotorMusica().then((d) => {
    if (d && d.rodando) acompanharMotorMusica();
  }).catch(() => {});
  // O motor de música não se escolhe mais (só a IA local compõe desde a
  // saída do ElevenLabs em 02/09/2026) — a dica é fixa no HTML.
  loadHardwareCard().catch(() => {});
  if ($("#projectsRootHint") && m.projectsRoot) {
    $("#projectsRootHint").textContent = m.projectsRoot || "";
  }
  if ($("#projectsRootInput") && !$("#projectsRootInput").value) {
    $("#projectsRootInput").value = s.projectsRoot || m.projectsRoot || "";
  }
  if ($("#entregasRootInput") && document.activeElement !== $("#entregasRootInput")) {
    $("#entregasRootInput").value = s.entregasRoot || "";
  }
  if ($("#entregasRootHint")) $("#entregasRootHint").textContent = s.entregasRootEfetiva ? `Em uso: ${s.entregasRootEfetiva}` : "";
  if ($("#entregasAutoChk")) $("#entregasAutoChk").checked = s.entregasAuto !== false;
  if ($("#supabaseUrlInput")) $("#supabaseUrlInput").value = s.supabaseUrl || "";
  if ($("#supabaseAnonInput")) $("#supabaseAnonInput").value = s.supabaseAnonKey || "";
  if ($("#checkoutUrlInput")) $("#checkoutUrlInput").value = s.checkoutUrl || "";
  const srvHint = $("#adminServiceHint");
  if (srvHint) {
    if (s.hasServiceRole) {
      srvHint.hidden = false;
      srvHint.textContent = "Já salva neste PC (cole outra para substituir).";
    } else {
      srvHint.hidden = true;
    }
  }
  const createHint = $("#adminCreateHint");
  if (createHint) {
    createHint.textContent = s.hasServiceRole
      ? "Service role já configurada neste PC."
      : "Cole a service_role uma vez para criar contas Auth.";
  }
}

async function loadSistemaFromDoutor() {
  // Fallback: mesmos dados do Diagnóstico (quando /api/system falha)
  const [doutor, settings] = await Promise.all([
    api("/api/doutor"),
    api("/api/settings").catch(() => ({})),
  ]);
  const itens = doutor.itens || [];
  const sys = itens.find((i) => /^Sistema\s/i.test(i.titulo || ""));
  const accel = itens.find((i) => /Aceleração|libx264|nvenc|qsv|amf/i.test(i.titulo || ""));
  const perfil = itens.find((i) => /Perfil/i.test(i.titulo || ""));
  let cores = "?", ram = "?", disk = "?", enc = "libx264", os = "Windows", osRel = "";
  if (sys && sys.detalhe) {
    const d = String(sys.detalhe);
    const cm = d.match(/CPU\s+(\d+)/i);
    const rm = d.match(/RAM\s+([\d.]+)/i);
    const dm = d.match(/Disco[^\d]*([\d.]+)/i);
    if (cm) cores = cm[1];
    if (rm) ram = rm[1];
    if (dm) disk = dm[1];
  }
  if (sys && sys.titulo) {
    const tm = String(sys.titulo).replace(/^Sistema\s+/i, "").trim().split(/\s+/);
    if (tm[0]) os = tm[0];
    if (tm[1]) osRel = tm[1];
  }
  if (accel && accel.titulo) {
    const em = String(accel.titulo).match(/:\s*(\S+)/);
    if (em) enc = em[1];
    else if (/libx264/i.test(accel.titulo)) enc = "libx264";
  }
  let label = "—", jobs = "—", proxyOn = true, proxyH = 540;
  if (perfil) {
    const pm = String(perfil.titulo || "").match(/Perfil[^:]*:\s*(.+)$/i);
    if (pm) label = pm[1].trim();
    const jd = String(perfil.detalhe || "");
    const jm = jd.match(/Jobs[^=]*=(\d+)/i);
    if (jm) jobs = jm[1];
  }
  applySistemaData({
    machine: {
      os, osRelease: osRel, cores, ramGb: ram, diskFreeGb: disk,
      projectsRoot: settings.projectsRoot || "",
      accel: { preferredEncoder: enc },
    },
    performance: {
      label,
      parallelJobs: jobs,
      proxyEnabled: proxyOn,
      proxyHeight: proxyH,
    },
    settings: settings || {},
  });
}

function applyHardwareCard(pub) {
  const hint = $("#hwAccelHint");
  const det = $("#hwAccelDetail");
  if (!hint) return;
  const gpu = pub.gpu || "GPU não detectada";
  const enc = pub.encoder || "libx264";
  const on = pub.acceleration === "on";
  hint.textContent = on
    ? `${gpu} · Ativa`
    : `${gpu} · CPU`;
  if (det) {
    const fps = pub.benchmarkFps != null ? ` · ${pub.benchmarkFps} FPS no teste` : "";
    det.textContent = `Encoder: ${enc} · Concurrency: ${pub.concurrency ?? "—"} · Modo: ${pub.mode || "auto"}${fps}`;
  }
}

async function loadHardwareCard() {
  try {
    const res = await fetch("/api/hardware");
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.public) applyHardwareCard(data.public);
  } catch { /* ignore */ }
}

/** Estado do motor local de musica no card de Configuracoes. */
async function pintarMotorMusica() {
  const linha = $("#musicMotorEstado");
  const btn = $("#btnInstalarMotorMusica");
  const barra = $("#musicMotorBarra");
  if (!linha || !btn) return null;
  let d = {};
  try {
    d = await api("/api/musica/motor");
  } catch {
    // Nao apaga o texto: durante a instalacao o servidor pode demorar a
    // responder, e limpar a linha parecia que o download tinha sumido.
    return null;
  }
  const gb = (d.mbTotal / 1000).toFixed(1).replace(".", ",");
  if (d.rodando) {
    linha.textContent = d.texto || "Baixando…";
    btn.classList.add("hidden");
    if (barra) {
      barra.classList.remove("hidden");
      const span = barra.querySelector("span");
      if (span) span.style.width = `${Math.round((d.fracao || 0) * 100)}%`;
    }
  } else if (d.instalado) {
    linha.textContent = `IA local instalada (${d.gb} GB) — compõe sem gastar créditos.`;
    btn.classList.add("hidden");
    barra?.classList.add("hidden");
  } else if (d.incompleta && d.gpu) {
    // Download interrompido (app fechado, internet caiu): a pasta existe mas
    // o motor nao esta pronto. Sem este caminho o cliente ficava com um
    // motor que nunca compoe e nenhum botao para consertar.
    linha.textContent = d.erro
      ? `A instalação parou: ${d.erro}. Dá para continuar de onde parou.`
      : "Instalação incompleta — dá para continuar de onde parou.";
    btn.textContent = "Continuar instalação";
    btn.classList.remove("hidden");
    btn.disabled = false;
    barra?.classList.add("hidden");
  } else if (!d.gpu) {
    // Dizer QUAL placa foi encontrada: "ele tem placa de video sim" (04/09)
    // — a mensagem antiga so falava do que faltava, e nao dava para saber
    // se o app tinha visto a placa errada ou nao tinha visto nenhuma.
    linha.textContent = "IA local indisponível: precisa de placa NVIDIA "
      + (d.gpuNome ? `— aqui encontrei ${d.gpuNome}. ` : "— não encontrei placa aqui. ")
      + "Sem ela, uma trilha levaria uns 9 minutos, então entra uma música da Biblioteca.";
    btn.classList.add("hidden");
    barra?.classList.add("hidden");
  } else {
    // O que faria o download MORRER no meio, dito ANTES do clique: 4,8 GB
    // de espera para terminar em erro e pior que nao oferecer (5.0.26).
    const falta = !d.uv
      ? "falta o `uv`, que monta o ambiente — reinstale o ATIVAVID"
      : (d.livreGb && d.livreGb < (d.precisaGb || 7))
        ? `só há ${String(d.livreGb).replace(".", ",")} GB livres no disco do motor `
          + `(precisa de uns ${d.precisaGb || 7}) — use "Liberar espaço"`
        : "";
    linha.textContent = d.erro
      ? `A instalação falhou: ${d.erro}`
      : falta
        ? `IA local não instalada — ${falta}.`
        : `IA local não instalada — são ${gb} GB, baixados uma vez só.`;
    btn.textContent = "Instalar IA local";
    btn.classList.toggle("hidden", !!falta);
    btn.disabled = false;
    barra?.classList.add("hidden");
  }
  return d;
}

/* O pacote de trilhas e efeitos (5.0.29).
 *
 * A IA local so roda em placa NVIDIA. Sem ela o plano B sempre foi "deixe
 * MP3s em Biblioteca/Trilhas" — uma pasta que nasce VAZIA, entao o video
 * saia sem trilha nenhuma e ninguem sabia o que fazer. Aqui o acervo do
 * dono do app desce de uma vez, com barra, e nada do usuario e
 * sobrescrito. */
async function pintarPacoteBiblioteca() {
  const linha = $("#pacoteEstado");
  const btn = $("#btnBaixarPacote");
  const barra = $("#pacoteBarra");
  if (!linha || !btn) return null;
  let d = {};
  try {
    d = await api("/api/biblioteca/pacote");
  } catch {
    return null;      // como o motor: nao apaga o texto no meio do download
  }
  const gb = ((d.mbTotal || 370) / 1000).toFixed(2).replace(".", ",");
  if (d.rodando || d.estado === "baixando" || d.estado === "instalando") {
    const pct = d.total ? Math.round((d.baixado / d.total) * 100) : 0;
    linha.textContent = d.estado === "instalando"
      ? "Descompactando na sua Biblioteca…"
      : `Baixando o pacote… ${pct}%`;
    btn.classList.add("hidden");
    if (barra) {
      barra.classList.remove("hidden");
      const span = barra.querySelector("span");
      if (span) span.style.width = `${pct}%`;
    }
  } else if (d.estado === "erro" && d.erro) {
    linha.textContent = `O download falhou: ${d.erro}`;
    btn.textContent = "Tentar de novo";
    btn.classList.remove("hidden");
    btn.disabled = false;
    barra?.classList.add("hidden");
  } else {
    const quantos = d.arquivos || 0;
    linha.textContent = d.estado === "pronto" && d.novos
      ? `✓ ${d.novos} arquivo(s) novos na sua Biblioteca (${quantos} no total).`
      : `Sua Biblioteca tem ${quantos} som(ns). O pacote traz trilhas e `
        + `efeitos prontos (${gb} GB, uma vez só).`;
    // Sem URL o pacote ainda nao foi publicado: botao que erra nao aparece.
    btn.classList.toggle("hidden", !d.url);
    btn.textContent = quantos > 0 ? "Completar com o pacote" : "Baixar trilhas e efeitos";
    btn.disabled = false;
    barra?.classList.add("hidden");
  }
  return d;
}

function acompanharPacote() {
  clearInterval(acompanharPacote._t);
  let falhas = 0;
  acompanharPacote._t = setInterval(async () => {
    const d = await pintarPacoteBiblioteca();
    if (!d) {
      if (++falhas < 5) return;
      clearInterval(acompanharPacote._t);
      return;
    }
    falhas = 0;
    if (!d.rodando && d.estado !== "baixando" && d.estado !== "instalando") {
      clearInterval(acompanharPacote._t);
      if (d.estado === "pronto") {
        toast(`Biblioteca completa — ${d.novos || 0} arquivo(s) novos`, 6000);
        // Se ele estiver olhando a Biblioteca, a lista ganha os arquivos na
        // hora; sem isto parecia que o download nao tinha trazido nada.
        if (state.view === "biblioteca") loadLibraryUi().catch(() => {});
        rodarDoutor().catch(() => {});
      }
    }
  }, 2000);
}

/** Enquanto baixa, pergunta o progresso — a instalacao leva minutos. */
function acompanharMotorMusica() {
  clearInterval(acompanharMotorMusica._t);
  let falhas = 0;
  acompanharMotorMusica._t = setInterval(async () => {
    const d = await pintarMotorMusica();
    if (!d) {
      // Um GET perdido nao pode parar o acompanhamento: a instalacao leva
      // minutos e continua no servidor — a barra e que congelava, dando a
      // impressao de travamento. So desiste depois de 5 falhas seguidas.
      if (++falhas < 5) return;
      clearInterval(acompanharMotorMusica._t);
      return;
    }
    falhas = 0;
    if (!d.rodando) {
      clearInterval(acompanharMotorMusica._t);
      if (d.instalado) toast("IA local de música pronta ✓", 5000);
      else if (d.erro) toast(`Instalação falhou: ${d.erro}`, 8000);
    }
  }, 3000);
}

/* O bloco do Supabase e SO do admin (5.0.27).
 *
 * Ele, com o print da tela de um cliente: "Cliente nao pode ver isso".
 * Estavam ali a URL do backend, a anon key e o link de checkout — os tres
 * editaveis. Trocar qualquer um quebra o app daquela maquina.
 *
 * O HTML nasce `hidden`: se esta funcao nao rodar (erro antes dela), o
 * cliente continua sem ver. Mostrar e que exige ser admin. */
function ajustarAvancadoParaOPerfil() {
  const admin = !!(state.auth && state.auth.isAdmin);
  const bloco = $("#sysBackendCfg");
  if (bloco) bloco.hidden = !admin;
  const sub = $("#sysSupportSub");
  if (sub) {
    sub.textContent = admin
      ? "Supabase, reinstalar e teste de desempenho — só se precisar"
      : "Reinstalar e teste de desempenho — só se precisar";
  }
}

async function loadSistema() {
  ajustarAvancadoParaOPerfil();
  pintarPacoteBiblioteca().catch(() => {});
  const hint = $("#sysMachineHint");
  if (hint) hint.textContent = "Detectando…";
  try {
    const ctrl = typeof AbortSignal !== "undefined" && AbortSignal.timeout
      ? { signal: AbortSignal.timeout(8000) }
      : {};
    const res = await fetch("/api/system", ctrl);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || res.statusText || "erro");
    applySistemaData(data);
  } catch (e) {
    try {
      await loadSistemaFromDoutor();
      if (hint && /Detectando|Servidor|Falha/i.test(hint.textContent || "")) {
        /* applySistemaData already set hint */
      }
    } catch (e2) {
      const msg = String(e && e.message ? e.message : e);
      if (hint) {
        hint.textContent = /failed to fetch|networkerror|load failed|aborted|timeout/i.test(msg)
          ? "Não li o hardware aqui — rode o Diagnóstico abaixo (mesmos dados)."
          : `Falha ao detectar: ${msg}`;
      }
    }
  }
  try {
    const up = await api("/api/update/check");
    if ($("#updateHint") && up.message) $("#updateHint").textContent = up.message;
    marcarBotaoDeUpdate(up);
  } catch { /* ignore */ }
  try {
    const cache = await api("/api/cache");
    if ($("#cacheHint")) {
      $("#cacheHint").textContent = `Cache temporário: ${cache.gb ?? 0} GB (originais e finais ficam intactos)`;
    }
    if ($("#sysMetricCache")) $("#sysMetricCache").textContent = `${cache.gb ?? 0} GB`;
  } catch {
    if ($("#cacheHint")) $("#cacheHint").textContent = "Cache: —";
  }
  await loadBrandsUi().catch(() => {});
}

async function loadImportPresets(brandId) {
  const sel = $("#importPresetSelect");
  const hint = $("#importPresetHint");
  if (!sel) return;
  // Marca a vista (4.101): a lista de marcas entra uma vez; trocar recarrega
  // os presets daquela marca — o mesmo desenho do Multiplicador.
  const bsel = $("#importBrandSelect");
  if (bsel && !bsel.dataset.wired) {
    bsel.dataset.wired = "1";
    try {
      const data = await api("/api/brands");
      const brands = data.brands || [];
      const active = brands.find((b) => b.active) || brands[0];
      bsel.innerHTML = brands.map((b) =>
        `<option value="${escapeHtml(b.id)}" ${active && b.id === active.id ? "selected" : ""}>${escapeHtml(b.name || b.id)}</option>`
      ).join("") || `<option value="">Padrão</option>`;
      bsel.onchange = () => loadImportPresets(bsel.value).catch(() => {});
    } catch { /* sem marcas: segue com a ativa */ }
  }
  const bid = brandId || (bsel && bsel.value) || "";
  try {
    const pack = await api(bid ? `/api/brand-presets?brandId=${encodeURIComponent(bid)}` : "/api/brand-presets");
    const presets = pack.presets || [];
    const activeId = pack.activeId || (pack.active && pack.active.id);
    sel.innerHTML = presets.map((p) =>
      `<option value="${escapeHtml(p.id)}" ${p.id === activeId ? "selected" : ""}>${escapeHtml(p.name || p.id)}</option>`
    ).join("") || `<option value="">Padrão</option>`;
    const cur = presets.find((p) => p.id === sel.value) || pack.active || presets[0];
    if (hint) hint.textContent = cur ? `Usar: ${cur.name}` : "Usar: o preset padrão";
    if (cur && cur.contentType && $("#importContentType")) {
      $("#importContentType").value = cur.contentType;
    }
    sel.onchange = () => {
      const p = presets.find((x) => x.id === sel.value);
      if (hint) hint.textContent = p ? `Usar: ${p.name}` : "Usar: o preset padrão";
      if (p && p.contentType && $("#importContentType")) {
        $("#importContentType").value = p.contentType;
      }
    };
  } catch {
    if (hint) hint.textContent = "Usar: o preset padrão";
  }
}

/** Marca + preset da janela do Multiplicador. A marca ativa e o preset
 *  ativo dela vem selecionados; trocar a marca recarrega os presets. */
async function loadMultiPresets() {
  const brandSel = $("#multiBrandSelect");
  const presetSel = $("#multiPresetSelect");
  const hint = $("#multiPresetHint");
  if (!brandSel || !presetSel) return;
  const carregarPresets = async (brandId) => {
    const pack = await api(`/api/brand-presets?brandId=${encodeURIComponent(brandId || "")}`);
    const presets = pack.presets || [];
    const activeId = pack.activeId || (pack.active && pack.active.id);
    presetSel.innerHTML = presets.map((p) =>
      `<option value="${escapeHtml(p.id)}" ${p.id === activeId ? "selected" : ""}>${escapeHtml(p.name || p.id)}</option>`
    ).join("") || `<option value="">Padrão da marca</option>`;
    const aplicar = () => {
      const p = presets.find((x) => x.id === presetSel.value);
      if (hint) hint.textContent = p
        ? `Todas as combinações saem com "${p.name}"${pack.brandName ? ` (${pack.brandName})` : ""}.`
        : "Todas as combinações saem com o padrão da marca.";
      if (p && p.contentType && $("#multiContentType")) $("#multiContentType").value = p.contentType;
    };
    presetSel.onchange = aplicar;
    aplicar();
  };
  const data = await api("/api/brands");
  const brands = data.brands || [];
  const active = brands.find((b) => b.active) || brands[0];
  brandSel.innerHTML = brands.map((b) =>
    `<option value="${escapeHtml(b.id)}" ${active && b.id === active.id ? "selected" : ""}>${escapeHtml(b.name || b.id)}</option>`
  ).join("") || `<option value="">Padrão</option>`;
  brandSel.onchange = () => carregarPresets(brandSel.value).catch(() => {});
  await carregarPresets(active ? active.id : "");
}

async function loadBrandsUi() {
  const data = await api("/api/brands");
  const brands = data.brands || [];
  const active = brands.find((b) => b.active) || brands[0];
  state.brandActive = active || null;
  state.brands = brands;
  renderWsMarcas();
  renderWorkspaceCard();
  renderJobs();
  renderComece();
  renderEmpresaCards();
  preencherEmpresaForm(active);
  if ($("#exportPresetSelect") && active) {
    $("#exportPresetSelect").value = active.exportPreset || "reels";
  }
  const fmtNames = { reels: "Reels/Shorts", youtube: "YouTube 16:9", square: "Quadrado 1:1", feed: "Feed 4:5" };
  const formato = fmtNames[active && active.exportPreset] || "Reels/Shorts";
  if ($("#brandHint")) {
    if (!state.editPresetId) {
      $("#brandHint").textContent = active
        ? `Vale para todos os presets. Sai em ${formato}.` : "";
    }
  }
  if ($("#estiloBrandName") && !state.editPresetId) {
    $("#estiloBrandName").textContent = (active && active.name) || "Padrão";
  }
  const sw = $("#identAccent");
  if (sw) sw.style.background = (active && active.accent) || "var(--accent)";
  if ($("#identAccentVal")) $("#identAccentVal").textContent = (active && active.accent) || "padrão";
  if ($("#identEndCard")) {
    // endCardCopy vem como {line1, line2} — mostra a primeira linha.
    const copy = (active && active.endCardCopy) || null;
    let txt = "—";
    if (typeof copy === "string") txt = copy;
    else if (Array.isArray(copy)) txt = copy[0] || "—";
    else if (copy && typeof copy === "object") txt = copy.line1 || copy.line2 || "—";
    $("#identEndCard").textContent = txt;
  }
  const fr = $("#estiloFrame");
  if (fr && fr.dataset.loaded === "1" && document.body.classList.contains("view-estilo-on")) {
    const cur = new URL(fr.src, location.origin);
    if ((cur.searchParams.get("brandId") || "") !== (active && active.id || "")) {
      fr.src = estiloFrameSrc();
    }
  }
  try {
    const lib = await api("/api/library");
    if ($("#libraryHint")) {
      const n = lib.items?.length || 0;
      $("#libraryHint").textContent = n
        ? `${n} imagem(ns) disponíveis para usar como b-roll`
        : "Coloque fotos dos seus produtos na pasta para a IA usar como b-roll";
    }
  } catch {
    if ($("#libraryHint")) $("#libraryHint").textContent = "";
  }
}

/**
 * Estado de falha de uma tela: diz o que houve e oferece a saída. Sem isto
 * a tela fica muda e parece que o recurso sumiu.
 */
function falhaDaTela(hostId, msg, recarregar) {
  const host = $(`#${hostId}`);
  if (!host) return;
  host.classList.remove("hidden");
  host.innerHTML = "";
  const txt = document.createElement("p");
  txt.className = "falha-msg";
  txt.textContent = msg;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "ghost-btn";
  btn.textContent = "Tentar de novo";
  btn.onclick = () => {
    host.textContent = "Carregando…";
    recarregar().catch(() => {});
  };
  host.append(txt, btn);
}

// Onde cada efeito do app toca hoje - conferido no template (StackedCaptions,
// Main e CustomGraphics). Os quatro sem uso ficam marcados como sobressalentes
// em vez de sumirem: eles existem na pasta e o cliente ia ouvir e nao entender.
const SFX_USO = {
  "caption-click.mp3": "cada palavra da legenda",
  "caption-scratch.mp3": "o risco da \u00eanfase",
  "whoosh.mp3": "entrada de manchete e cart\u00e3o",
  "pop.mp3": "bolha de conversa e formas",
  "cut-click.mp3": "gr\u00e1fico entrando no corte",
  "click.mp3": "sobressalente (nada usa hoje)",
  "click1.mp3": "sobressalente (nada usa hoje)",
  "click2.mp3": "sobressalente (nada usa hoje)",
  "tictac.mp3": "sobressalente (nada usa hoje)",
};

const LIB_ABAS = {
  image: {
    titulo: "imagens",
    um: "imagem",
    kinds: ["image"],
    botao: "Adicionar imagens",
    input: "#libraryFileInput",
    vazio: "Nenhuma imagem ainda. Coloque fotos dos seus produtos, da bancada e dos consertos aqui \u2014 a IA usa como b-roll no meio do v\u00eddeo.",
    pe: "As imagens viram <strong>b-roll</strong>: a IA escolhe pelo que a frase est\u00e1 dizendo. A categoria entra no nome do arquivo (<code>produto--iphone.jpg</code>) e serve para voc\u00ea achar; a IA casa pelo nome inteiro.",
  },
  clip: {
    titulo: "v\u00eddeos",
    um: "v\u00eddeo",
    kinds: ["clip"],
    botao: "Adicionar v\u00eddeos",
    input: "#libraryVideoInput",
    vazio: "Nenhum take ainda. Guarde aqui os v\u00eddeos curtos de apoio \u2014 rea\u00e7\u00e3o, meme, piada, o CTA que voc\u00ea grava separado \u2014 para a IA usar no meio da fala.",
    pe: "Os v\u00eddeos entram como <strong>take de apoio</strong> no meio do v\u00eddeo. A categoria diz o PAPEL do take (rea\u00e7\u00e3o, meme, humor, CTA) e \u00e9 por onde voc\u00ea acha na hora: \u201cdeu uma patada\u201d \u2192 take de humor. A IA casa pelo nome do arquivo, ent\u00e3o vale nomear o que o take mostra (<code>humor--cavalo-patada.mp4</code>).",
  },
  track: {
    titulo: "trilhas",
    um: "trilha",
    kinds: ["track"],
    botao: "Adicionar m\u00fasicas",
    input: "#libraryMusicInput",
    vazio: "Nenhuma trilha ainda. Toda m\u00fasica que a IA comp\u00f5e entra aqui sozinha \u2014 e m\u00fasicas suas (royalty-free) tamb\u00e9m podem ser adicionadas.",
    pe: "As trilhas s\u00e3o o <strong>plano B da m\u00fasica</strong>: quando a IA falha (cr\u00e9ditos, rede), o v\u00eddeo usa uma daqui \u2014 escolhida pela categoria, que \u00e9 o tipo do v\u00eddeo. Trocar a categoria muda de verdade em que v\u00eddeo a m\u00fasica pode entrar.",
  },
  sfx: {
    titulo: "efeitos",
    um: "efeito",
    kinds: ["sfx"],
    botao: "Adicionar efeitos",
    input: "#librarySfxInput",
    vazio: "Nenhum efeito seu ainda \u2014 os do app aparecem na lista acima.",
    pe: "Os efeitos marcados <strong>do app</strong> s\u00e3o os que os v\u00eddeos usam hoje \u2014 d\u00e1 para ouvir todos aqui. A categoria de um efeito seu \u00e9 a <strong>vaga</strong> que ele ocupa: um arquivo em <code>whoosh</code> entra no lugar do whoosh nos pr\u00f3ximos v\u00eddeos, e o mesmo vale para clique, risco, pop e corte.",
  },
};

/**
 * Biblioteca: tres acervos com papeis DIFERENTES no video - imagem vira
 * b-roll, trilha e o plano B da musica, efeito e o som do corte. Antes era
 * uma grade de imagens com as trilhas empilhadas embaixo; com 171 faixas a
 * tela virava um rolo unico sem como achar nada. Agora cada acervo tem aba
 * propria e as CATEGORIAS viram filtro.
 *
 * A categoria nao e enfeite de tela: ela mora no nome do arquivo
 * ("viral--x.mp3"), que e o mesmo contrato que o pipeline le para casar a
 * musica com o tipo do video. Trocar aqui renomeia o arquivo - e muda a
 * escolha do render.
 */
async function loadLibraryUi() {
  const painel = $("#libraryPanel");
  if (!painel) return;
  let lib = { items: [], root: "" };
  try {
    lib = await api("/api/library");
  } catch {
    painel.innerHTML = "";
    $("#libraryHint").textContent = "A biblioteca nao respondeu.";
    falhaDaTela("libraryEmpty",
      "Nao deu para ler a biblioteca \u2014 o ATIVAVID pode estar iniciando ou ter sido fechado.",
      loadLibraryUi);
    return;
  }
  state.libraryRoot = lib.root || "";
  state.libraryData = lib;
  // O estilo decide se o b-roll entra. Sem isto a tela deixava o usuario
  // guardar take achando que ia aparecer no video — e no estilo dele
  // (layout limpo + b-roll no padrao) o pipeline zera os inserts.
  try {
    const pack = await api("/api/brand-presets");
    const presets = pack.presets || [];
    const ativo = presets.find((p) => p.id === (pack.activeId
      || (pack.active && pack.active.id))) || pack.active || presets[0];
    state.libEstilo = (ativo && ativo.style) || {};
  } catch { state.libEstilo = null; }
  const tudo = lib.items || [];
  const conta = (ks) => tudo.filter((i) => ks.includes(i.kind)).length;
  if ($("#libCountImage")) $("#libCountImage").textContent = conta(["image"]);
  if ($("#libCountClip")) $("#libCountClip").textContent = conta(["clip"]);
  if ($("#libCountTrack")) $("#libCountTrack").textContent = conta(["track"]);
  if ($("#libCountSfx")) $("#libCountSfx").textContent = conta(["sfx"]);
  renderLibraryAba();
}

function renderLibraryAba() {
  const painel = $("#libraryPanel");
  const lib = state.libraryData || { items: [] };
  const aba = state.libAba || "image";
  const cfg = LIB_ABAS[aba];
  if (!painel || !cfg) return;
  for (const b of document.querySelectorAll("#libraryTabs .lib-tab")) {
    b.classList.toggle("is-on", b.dataset.libtab === aba);
  }
  const visual = aba === "image" || aba === "clip";
  const todosDaAba = (lib.items || []).filter((i) => cfg.kinds.includes(i.kind));
  // 5.0.2: de quem e. "empresa" = os desta empresa + os comuns (e o que o
  // video dela pode usar); "comum" = so os comuns; "todas" = tudo.
  const ativa = (state.brandActive && state.brandActive.id) || "";
  if (!state.libDono) state.libDono = state.wsMarca === "all" ? "todas" : "empresa";
  const dono = visual ? state.libDono : "todas";
  const itens = todosDaAba.filter((i) => {
    if (dono === "todas") return true;
    if (dono === "comum") return !i.empresa;
    return !i.empresa || i.empresa === ativa;
  });
  renderLibraryDono(visual, todosDaAba, ativa);
  const contagem = new Map();
  for (const it of itens) {
    const k = it.categoria || "";
    contagem.set(k, (contagem.get(k) || 0) + 1);
  }
  // Ordem: primeiro as categorias que o PIPELINE conhece, depois as que o
  // usuario inventou, e "sem categoria" por ultimo.
  const oficiais = ((lib.categorias || {})[aba] || []).filter((k) => contagem.has(k));
  const extras = [...contagem.keys()].filter((k) => k && !oficiais.includes(k)).sort();
  const ordem = [...oficiais, ...extras];
  if (contagem.has("")) ordem.push("");
  const chips = $("#libraryChips");
  if (chips) {
    const marcada = state.libCat || "";
    chips.innerHTML = [
      `<button type="button" class="lib-chip${marcada ? "" : " is-on"}" data-libcat="">Todas <span class="lib-chip-n">${itens.length}</span></button>`,
      ...ordem.map((k) => {
        const on = marcada && marcada === (k || "\u2205") ? " is-on" : "";
        const valor = k || "\u2205";
        return `<button type="button" class="lib-chip${on}" data-libcat="${escapeHtml(valor)}">${escapeHtml(k || "sem categoria")} <span class="lib-chip-n">${contagem.get(k)}</span></button>`;
      }),
    ].join("");
  }
  const filtro = state.libCat || "";
  const filtrados = !filtro
    ? itens
    : itens.filter((i) => (i.categoria || "\u2205") === filtro);
  const empty = $("#libraryEmpty");
  if (empty) {
    empty.textContent = cfg.vazio;
    empty.classList.toggle("hidden", itens.length > 0);
  }
  const pe = $("#libraryFoot");
  if (pe) pe.innerHTML = cfg.pe + libAvisoDoBroll(aba, itens.length);
  const hint = $("#libraryHint");
  if (hint) {
    const nome = filtro === "\u2205" ? "sem categoria" : filtro;
    hint.textContent = itens.length
      ? (filtro
          ? `${filtrados.length} em "${nome}", de ${itens.length} ${cfg.titulo}`
          : `${itens.length} ${itens.length === 1 ? cfg.um : cfg.titulo} \u00b7 ${state.libraryRoot || ""}`)
      : "";
  }
  // O interruptor da troca so faz sentido sobre os efeitos.
  const swi = $("#sfxSwitch");
  if (swi) swi.classList.toggle("hidden", aba !== "sfx");
  const btn = $("#btnLibraryAdd");
  if (btn) {
    const paraOnde = !visual ? "" : (state.libDono === "comum" || !ativa
      ? " (Comum)" : ` (${nomeDaMarca(ativa)})`);
    btn.textContent = cfg.botao + paraOnde;
    btn.title = (filtro && filtro !== "\u2205"
      ? `Entra na categoria "${filtro}"`
      : "Entra sem categoria \u2014 da para classificar depois")
      + (visual ? (state.libDono === "comum" ? ". Vale para todas as empresas."
                   : `. Só para ${nomeDaMarca(ativa) || "esta empresa"}.`) : "");
  }
  // O cabecalho de cada grupo diz o que aquela categoria FAZ: trilha
  // mostra o clima que o pipeline usa para escolher; efeito mostra se a
  // categoria e uma das VAGAS do video ou se o arquivo so fica guardado.
  const vagas = (lib.categorias || {}).sfx || [];
  // A nota do GRUPO sai da mesma verdade do selo de cada item. O servidor
  // j\u00e1 diz a vaga de cada arquivo, e ela conhece os sin\u00f4nimos (`swoosh`
  // ocupa a vaga do `whoosh`); comparando s\u00f3 o NOME da categoria com a
  // lista de vagas, o cabe\u00e7alho do grupo `swoosh` dizia "s\u00f3 guardado"
  // enquanto os itens dele diziam "toca" \u2014 duas etiquetas discordando na
  // mesma tela.
  const vagaDaCategoria = new Map();
  for (const it of (lib.items || [])) {
    if (it.kind !== "sfx" || !it.vaga) continue;
    const k = it.categoria || "";
    if (!vagaDaCategoria.has(k)) vagaDaCategoria.set(k, it.vaga);
  }
  const notas = aba === "track"
    ? Object.fromEntries(Object.entries(lib.clima || {}).map(([k, v]) => [k, `clima ${v}`]))
    : Object.fromEntries([...new Set([...vagas, ...contagem.keys()])].map(
        (k) => [k, (vagas.includes(k) || vagaDaCategoria.has(k))
          ? "entra no v\u00eddeo" : "s\u00f3 guardado"]));
  pararAudio();          // a lista mudou: o que estava tocando saiu do DOM
  painel.innerHTML = (aba === "image" || aba === "clip")
    ? libGradeImagens(filtrados, aba)
    : libListaAudio(filtrados, aba, notas, ordem);
  ligarPlayersDaBiblioteca(painel);
}

/* Seletor "de quem" da Biblioteca (5.0.2), so nas abas de imagem e video. */
function renderLibraryDono(visual, itens, ativa) {
  const box = $("#libraryDono");
  if (!box) return;
  box.classList.toggle("hidden", !visual);
  if (!visual) return;
  const nDesta = itens.filter((i) => !i.empresa || i.empresa === ativa).length;
  const nComum = itens.filter((i) => !i.empresa).length;
  const dono = state.libDono || "empresa";
  const chip = (v, rot, n) => `<button type="button" class="lib-chip${dono === v ? " is-on" : ""}" data-libdono="${v}">${escapeHtml(rot)} <span class="lib-chip-n">${n}</span></button>`;
  box.innerHTML = `<span class="lib-dono-rot">De quem</span>`
    + chip("empresa", `${nomeDaMarca(ativa) || "Esta empresa"} + Comum`, nDesta)
    + chip("comum", "Só Comum", nComum)
    + chip("todas", "Todas as empresas", itens.length);
}

function libSeletorDono(it) {
  if (it.origem === "app" || (it.kind !== "image" && it.kind !== "clip")) return "";
  const ops = [`<option value=""${it.empresa ? "" : " selected"}>Comum</option>`]
    .concat((state.brands || []).map((b) =>
      `<option value="${escapeHtml(b.id)}"${b.id === it.empresa ? " selected" : ""}>${escapeHtml(b.name || b.id)}</option>`));
  if (it.empresa && !(state.brands || []).some((b) => b.id === it.empresa)) {
    ops.push(`<option value="${escapeHtml(it.empresa)}" selected>${escapeHtml(it.empresa)}</option>`);
  }
  return `<select class="lib-dono-sel" data-librel="${escapeHtml(it.rel)}" title="De quem é — move o arquivo">${ops.join("")}</select>`;
}

/* Guardar take nao basta: no layout limpo com o b-roll no padrao o
 * pipeline NAO insere nada (é o talking-head limpo). Quem tem take na
 * Biblioteca precisa saber disso na hora, nao depois do vídeo pronto. */
function libAvisoDoBroll(aba, quantos) {
  if (aba !== "clip" || !quantos) return "";
  const st = state.libEstilo;
  if (!st) return "";
  const modo = String(st.brollMode || "quando_necessario").toLowerCase().trim();
  const layout = String(st.edit || "limpa").toLowerCase().trim();
  const limpo = ["limpa", "clean", "limpo", "moldura", "barra", "desfocado",
                 "degrade"].includes(layout);
  const desligado = ["off", "nenhum", "none", "desligado"].includes(modo);
  const padrao = ["quando_necessario", "auto", ""].includes(modo);
  if (!desligado && !(limpo && padrao)) return "";
  const porque = desligado
    ? "o b-roll está desligado no seu estilo"
    : "seu estilo usa o quadro limpo e o b-roll está em \u201cQuando necessário\u201d";
  const sujeito = quantos > 1
    ? `Estes ${quantos} takes n\u00e3o v\u00e3o entrar`
    : "Este take n\u00e3o vai entrar";
  return `<span class="lib-alerta">${sujeito} nos v\u00eddeos: ${porque}. `
    + `Para us\u00e1-${quantos > 1 ? "los" : "lo"}, mude o b-roll para <strong>Sempre</strong> ou `
    + `<strong>Raro</strong> em Estilos.</span>`;
}

function libTamanho(bytes) {
  return bytes > 1048576
    ? `${(bytes / 1048576).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/* O seletor troca a CATEGORIA renomeando o arquivo (e o que o pipeline le).
 * Item que veio do app nao tem seletor: e asset do produto, nao do usuario. */
/* Apagar um arquivo da Biblioteca. "quero deletar os efeitos que eu nao
 * gostar por ali tambem" (30/08) — com 233 efeitos importados de uma vez,
 * escolher o que fica e trabalho de lista, e ate agora so dava para
 * abrir a pasta no Explorer. Arquivo do app nao tem botao. */
function libBotaoApagar(it) {
  if (it.origem === "app") return "";
  return `<button type="button" class="lib-del" data-libdel="${escapeHtml(it.rel)}"
          title="Apagar — vai para a Lixeira" aria-label="Apagar">✕</button>`;
}

function libSeletorCategoria(it, opcoes) {
  if (it.origem === "app") return "";
  const lista = [...new Set([...(opcoes || []), it.categoria].filter(Boolean))];
  const ops = [
    `<option value=""${it.categoria ? "" : " selected"}>sem categoria</option>`,
    ...lista.map((k) => `<option value="${escapeHtml(k)}"${k === it.categoria ? " selected" : ""}>${escapeHtml(k)}</option>`),
  ];
  return `<select class="lib-cat" data-librel="${escapeHtml(it.rel)}" title="Categoria \u2014 renomeia o arquivo">${ops.join("")}</select>`;
}

function libGradeImagens(itens, aba) {
  if (!itens.length) return "";
  const opcoes = ((state.libraryData || {}).categorias || {})[aba || "image"] || [];
  return `<div class="lib-grid">${itens.map((it) => {
    const src = `/api/library/file?rel=${encodeURIComponent(it.rel)}`;
    // Take se assiste: video da biblioteca vem com controle, para o
    // usuario lembrar o que e o take antes de escolher a categoria.
    const midia = it.kind === "clip"
      ? `<video class="lib-thumb" src="${src}" controls preload="metadata"></video>`
      : `<img class="lib-thumb" src="${src}" alt="" loading="lazy">`;
    const tag = it.empresa ? "" : `<span class="lib-tag-comum">Comum</span>`;
    return `<figure class="lib-item" title="${escapeHtml(it.name)}">
      ${midia}${tag}
      <figcaption><span class="lib-name">${escapeHtml(it.name)}</span><span class="lib-size">${libTamanho(it.bytes)}</span></figcaption>
      <div class="lib-item-cat">${libSeletorCategoria(it, opcoes)}${libSeletorDono(it)}${libBotaoApagar(it)}</div>
    </figure>`;
  }).join("")}</div>`;
}

/* ---------------------------------------------------------------------
 * Player da Biblioteca.
 *
 * O `<audio controls>` do navegador ocupava 240px no canto e deixava o
 * resto da linha vazio — e um menu de tres pontinhos que aqui nao serve
 * para nada. Este e da casa: play, forma de onda no vao, tempo e volume.
 *
 * A onda vem dos PICOS reais do arquivo. Decodificar 242 efeitos de uma
 * vez travaria a pagina, entao cada linha so decodifica quando aparece
 * na tela, de quatro em quatro, e o resultado fica guardado por caminho.
 * ------------------------------------------------------------------ */
const ICO_PLAY = '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M4.5 2.9v10.2l8-5.1z" fill="currentColor"/></svg>';
const ICO_PAUSE = '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M4.6 2.8h2.6v10.4H4.6zM8.8 2.8h2.6v10.4H8.8z" fill="currentColor"/></svg>';

const PICOS = new Map();      // rel -> Float32Array de picos
let audioAtual = null;        // um de cada vez
let linhaAtual = null;
let ctxAudio = null;
const filaPicos = [];
let baixando = 0;

function volumeDaBiblioteca() {
  const v = parseFloat(localStorage.getItem("ativavid-lib-vol"));
  return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0.8;
}

/* Picos por coluna: o maximo absoluto de cada fatia. Media faria um efeito
 * curto (um clique de 0,2s) virar uma linha reta — e o pico e justamente o
 * que se quer ver num efeito sonoro. */
async function picosDoArquivo(rel, src) {
  if (PICOS.has(rel)) return PICOS.get(rel);
  ctxAudio = ctxAudio || new (window.AudioContext || window.webkitAudioContext)();
  const buf = await (await fetch(src)).arrayBuffer();
  const audio = await ctxAudio.decodeAudioData(buf);
  const dados = audio.getChannelData(0);
  const N = 160;
  const passo = Math.max(1, Math.floor(dados.length / N));
  const out = new Float32Array(N);
  let teto = 1e-6;
  for (let i = 0; i < N; i++) {
    let m = 0;
    const ini = i * passo;
    for (let k = ini; k < ini + passo && k < dados.length; k++) {
      const v = Math.abs(dados[k]);
      if (v > m) m = v;
    }
    out[i] = m;
    if (m > teto) teto = m;
  }
  for (let i = 0; i < N; i++) out[i] /= teto;   // normalizado: o pico e 1
  PICOS.set(rel, out);
  return out;
}

function desenharOnda(linha, prog) {
  const cv = linha.querySelector(".lib-onda");
  if (!cv) return;
  const larg = Math.max(40, Math.round(cv.clientWidth));
  const alt = Math.max(18, Math.round(cv.clientHeight));
  const dpr = window.devicePixelRatio || 1;
  if (cv.width !== Math.round(larg * dpr)) {
    cv.width = Math.round(larg * dpr);
    cv.height = Math.round(alt * dpr);
  }
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, larg, alt);
  const picos = PICOS.get(linha.dataset.rel);
  const meio = alt / 2;
  const css = getComputedStyle(document.documentElement);
  const forte = (css.getPropertyValue("--accent") || "#ff3b5c").trim();
  const fraco = "rgba(255,255,255,0.22)";
  if (!picos) {                       // ainda decodificando: uma linha guia
    g.fillStyle = fraco;
    g.fillRect(0, meio - 0.5, larg, 1);
    return;
  }
  const n = picos.length;
  const lb = Math.max(1, (larg / n) * 0.62);
  for (let i = 0; i < n; i++) {
    const x = (i / n) * larg;
    const h = Math.max(1.5, picos[i] * (alt - 3));
    g.fillStyle = (i / n) <= prog ? forte : fraco;
    g.fillRect(x, meio - h / 2, lb, h);
  }
}

function tempoCurto(s) {
  if (!Number.isFinite(s)) return "0:00";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function pararAudio() {
  if (audioAtual) {
    audioAtual.pause();
    audioAtual = null;
  }
  if (linhaAtual) {
    linhaAtual.classList.remove("tocando");
    const b = linhaAtual.querySelector(".lib-play");
    if (b) b.innerHTML = ICO_PLAY;
    desenharOnda(linhaAtual, 0);
    const t = linhaAtual.querySelector(".lib-tempo");
    if (t) t.textContent = tempoCurto(0);
    linhaAtual = null;
  }
}

function tocarLinha(linha) {
  if (linhaAtual === linha) { pararAudio(); return; }
  pararAudio();
  const a = new Audio(linha.dataset.src);
  a.volume = volumeDaBiblioteca();
  audioAtual = a;
  linhaAtual = linha;
  linha.classList.add("tocando");
  const btn = linha.querySelector(".lib-play");
  if (btn) btn.innerHTML = ICO_PAUSE;
  const tempo = linha.querySelector(".lib-tempo");
  a.addEventListener("timeupdate", () => {
    if (audioAtual !== a) return;
    const p = a.duration ? a.currentTime / a.duration : 0;
    desenharOnda(linha, p);
    if (tempo) tempo.textContent = tempoCurto(a.currentTime);
  });
  a.addEventListener("ended", () => { if (audioAtual === a) pararAudio(); });
  a.play().catch(() => pararAudio());
}

/* Decodifica so o que esta na tela, de quatro em quatro. */
function enfileirarPicos(linha) {
  if (PICOS.has(linha.dataset.rel)) { desenharOnda(linha, 0); return; }
  filaPicos.push(linha);
  puxarFila();
}
function puxarFila() {
  while (baixando < 4 && filaPicos.length) {
    const linha = filaPicos.shift();
    if (!linha.isConnected) continue;
    baixando++;
    picosDoArquivo(linha.dataset.rel, linha.dataset.src)
      .then(() => desenharOnda(linha, 0))
      .catch(() => {})
      .finally(() => { baixando--; puxarFila(); });
  }
}

let olhoDasOndas = null;
/* Qual vaga do vídeo este som ocupa — e o aviso de quando ele não ocupa
 * nenhuma.
 *
 * O vídeo tem cinco vagas de efeito (clique, risco, whoosh, pop, corte).
 * Dos 234 efeitos importados pelo usuário, 133 são de categorias sem vaga
 * (impacto, transição, riser): ficam guardados e nunca tocam. A tela não
 * dizia isso — a Biblioteca parecia cheia de som em uso. */
const VAGA_ROTULO = {
  clique: "clique da legenda",
  risco: "risco da legenda",
  whoosh: "whoosh da manchete",
  pop: "pop dos elementos",
  corte: "clique do corte",
};

function selosDoEfeito(it) {
  if (it.kind !== "sfx" || it.origem !== "usuario") return "";
  // `vaga` diz onde ele CABERIA; `tocaNoVideo` diz se ele realmente entra
  // — e com a troca desligada (o padrao desde 4.22) nada entra. O selo
  // seguia so a vaga e prometia som que o render nao toca.
  if (it.vaga && it.tocaNoVideo) {
    const onde = VAGA_ROTULO[it.vaga] || it.vaga;
    return `<span class="lib-selo lib-selo--toca" title="Este som entra no vídeo no lugar do ${escapeHtml(onde)}">toca: ${escapeHtml(onde)}</span>`;
  }
  const cabe = it.vaga
    ? `Cabe na vaga do ${escapeHtml(VAGA_ROTULO[it.vaga] || it.vaga)} — `
      + "ligue \"Usar meus efeitos\" aqui em cima para ele entrar no vídeo"
    : "O vídeo tem vaga para clique, risco, whoosh, pop e corte — "
      + "este som não ocupa nenhuma delas";
  return `<span class="lib-selo lib-selo--guardado" title="${cabe}">só guardado</span>`;
}

function ligarPlayersDaBiblioteca(raiz) {
  const linhas = (raiz || document).querySelectorAll(".lib-track[data-src]");
  if (!linhas.length) return;
  if (!olhoDasOndas && "IntersectionObserver" in window) {
    olhoDasOndas = new IntersectionObserver((ents) => {
      for (const e of ents) {
        if (!e.isIntersecting) continue;
        olhoDasOndas.unobserve(e.target);
        enfileirarPicos(e.target);
      }
    }, {rootMargin: "200px"});
  }
  for (const linha of linhas) {
    if (linha.dataset.ligado) continue;
    linha.dataset.ligado = "1";
    if (olhoDasOndas) olhoDasOndas.observe(linha);
    else enfileirarPicos(linha);
    linha.addEventListener("click", (e) => {
      // o seletor de categoria e o menu tem acao propria — o resto da linha
      // (o nome inclusive) e o play, que e o que o usuario pediu
      if (e.target.closest("select, option, .lib-onda")) return;
      tocarLinha(linha);
    });
    const onda = linha.querySelector(".lib-onda");
    if (onda) {
      onda.addEventListener("click", (e) => {
        const r = onda.getBoundingClientRect();
        const p = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
        if (linhaAtual !== linha) tocarLinha(linha);
        const a = audioAtual;
        if (!a) return;
        const ir = () => { a.currentTime = p * (a.duration || 0); };
        if (a.duration) ir();
        else a.addEventListener("loadedmetadata", ir, {once: true});
      });
    }
  }
  window.addEventListener("resize", () => {
    for (const linha of linhas) if (linha.isConnected) desenharOnda(linha, 0);
  }, {passive: true});
}

/* Audio (trilha e efeito) em lista com play. Vendo TODAS, agrupa por
 * categoria: sem isso, 171 faixas viram um rolo unico. */
function libListaAudio(itens, aba, notas, ordem) {
  if (!itens.length) return "";
  const opcoes = ((state.libraryData || {}).categorias || {})[aba] || [];
  const linha = (it) => {
    const src = `/api/library/file?rel=${encodeURIComponent(it.rel)}`;
    const chip = it.origem === "app"
      ? `<span class="lib-track-tag lib-track-tag--app">do app</span>`
      : "";
    const uso = it.origem === "app" && SFX_USO[it.name]
      ? `<span class="lib-track-uso">${escapeHtml(SFX_USO[it.name])}</span>`
      : "";
    return `<div class="lib-track" title="${escapeHtml(it.name)}"
                 data-src="${src}" data-rel="${escapeHtml(it.rel)}">
      <button type="button" class="lib-play" aria-label="Tocar">${ICO_PLAY}</button>
      <span class="lib-track-name">${escapeHtml(it.name)}</span>
      ${chip}
      ${uso}
      ${selosDoEfeito(it)}
      <canvas class="lib-onda" aria-hidden="true"></canvas>
      <span class="lib-tempo">0:00</span>
      <span class="lib-size">${libTamanho(it.bytes)}</span>
      ${libSeletorCategoria(it, opcoes)}
      ${libBotaoApagar(it)}
    </div>`;
  };
  if (state.libCat) return `<div class="lib-tracks">${itens.map(linha).join("")}</div>`;
  const grupos = new Map();
  for (const it of itens) {
    const k = it.categoria || "";
    if (!grupos.has(k)) grupos.set(k, []);
    grupos.get(k).push(it);
  }
  // mesma ordem dos chips: chip e grupo lado a lado nao podem discordar
  const chaves = (ordem || []).filter((k) => grupos.has(k));
  for (const k of grupos.keys()) if (!chaves.includes(k)) chaves.push(k);
  return chaves.map((k) => {
    const cl = notas[k] ? `<span class="lib-grupo-clima">${escapeHtml(notas[k])}</span>` : "";
    return `<section class="lib-grupo">
      <h3 class="lib-grupo-tit">${escapeHtml(k || "sem categoria")} <span class="lib-grupo-clima">${grupos.get(k).length}</span> ${cl}</h3>
      <div class="lib-tracks">${grupos.get(k).map(linha).join("")}</div>
    </section>`;
  }).join("");
}

/**
 * Presets. O backend (/api/brand-presets) já fazia criar/renomear/duplicar/
 * apagar/definir padrão — só era alcançável pelo seletor da tela de importar.
 */
/* ---- Aulas (5.0.3) -----------------------------------------------------
 * Central de ajuda: a lista vem do Supabase (o admin gere na propria
 * tela), o video toca num embed do YouTube. Sem rede, a ultima lista. */
state.aulas = { lista: [], atualId: "", origem: "", player: null, timer: null, tentativas: 0,
                feitas: new Set(), vel: 1, cc: false, menu: false };
const AULAS_FEITAS_KEY = "ativavid.aulas.feitas";
try { state.aulas.feitas = new Set(JSON.parse(localStorage.getItem(AULAS_FEITAS_KEY) || "[]")); } catch { /* ignore */ }
try { state.aulas.vel = Number(localStorage.getItem("ativavid.aulas.vel") || 1) || 1; } catch { /* ignore */ }

function aulasPausar() {
  const p = state.aulas.player;
  try { if (p && p.pauseVideo && p.getPlayerState && p.getPlayerState() === 1) p.pauseVideo(); } catch { /* ignore */ }
}

function aulaConcluida(id) { return state.aulas.feitas.has(id); }
function aulaMarcar(id, feita) {
  if (!id) return;
  if (feita) state.aulas.feitas.add(id); else state.aulas.feitas.delete(id);
  try { localStorage.setItem(AULAS_FEITAS_KEY, JSON.stringify([...state.aulas.feitas])); } catch { /* ignore */ }
  renderAulas();
  aulaMostrarSobre(aulaAtual());
}

/* m:ss ou h:mm:ss, para a minutagem das aulas. */
function fmtRelogio(seg) {
  const t = Math.max(0, Math.round(Number(seg) || 0));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

/* A descricao como TEXTO ARRUMADO: paragrafos por linha em branco e
 * itens de lista quando a linha (ou o trecho) comeca com ✅ ✔ • - *.
 * Ele colou a descricao do YouTube inteira numa linha so, com um ✅ por
 * item — a tela mostrava um bloco corrido ("legenda fica uma merda"). */
function descricaoHtml(texto) {
  const t = String(texto || "").replace(/\r/g, "").trim();
  if (!t) return "";
  const MARCA = /(?:^|\s)(?=[✅✔☑️•▪️➡️➜→\-\*]\s?)/u;
  const blocos = [];
  for (const par of t.split(/\n{2,}/)) {
    const linhas = par.split("\n").map((l) => l.trim()).filter(Boolean);
    let itens = [];
    const paragrafo = [];
    const flush = () => {
      if (paragrafo.length) { blocos.push(`<p>${paragrafo.map(escapeHtml).join("<br>")}</p>`); paragrafo.length = 0; }
      if (itens.length) { blocos.push(`<ul>${itens.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`); itens = []; }
    };
    for (const linha of linhas) {
      // varios itens numa linha so ("✅ a ✅ b ✅ c") viram varios <li>
      const partes = linha.split(MARCA).map((p) => p.trim()).filter(Boolean);
      const ehLista = partes.length > 1 || /^[✅✔☑️•▪️➡️➜→\-\*]\s?/u.test(linha);
      if (ehLista) {
        // o texto antes do primeiro marcador e paragrafo, nao item
        if (!/^[✅✔☑️•▪️➡️➜→\-\*]/u.test(partes[0])) paragrafo.push(partes.shift());
        if (paragrafo.length) { blocos.push(`<p>${paragrafo.map(escapeHtml).join("<br>")}</p>`); paragrafo.length = 0; }
        for (const p of partes) itens.push(p.replace(/^[✅✔☑️•▪️➡️➜→\-\*]\s?/u, ""));
      } else {
        if (itens.length) { blocos.push(`<ul>${itens.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`); itens = []; }
        paragrafo.push(linha);
      }
    }
    flush();
  }
  return blocos.join("");
}

/* API IFrame do YouTube, carregada uma vez. null = sem rede. */
let _ytApiPromise = null;
function ytApi() {
  if (_ytApiPromise) return _ytApiPromise;
  _ytApiPromise = new Promise((resolve) => {
    if (window.YT && window.YT.Player) { resolve(window.YT); return; }
    const antes = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { if (antes) antes(); resolve(window.YT); };
    const s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    s.onerror = () => { _ytApiPromise = null; resolve(null); };
    document.head.appendChild(s);
    setTimeout(() => resolve(window.YT && window.YT.Player ? window.YT : null), 8000);
  });
  return _ytApiPromise;
}

function aulaAtual() {
  return (state.aulas.lista || []).find((a) => a.id === state.aulas.atualId) || null;
}

/* Aulas NOVAS (5.0.14): o que o admin publicou desde a ultima visita a
 * tela vira um selo no menu, como a Fila. Abrir a tela marca tudo como
 * visto. */
const AULAS_VISTAS_KEY = "ativavid.aulas.vistas";
function aulasVistas() {
  try { return new Set(JSON.parse(localStorage.getItem(AULAS_VISTAS_KEY) || "[]")); } catch { return new Set(); }
}
function aulasMarcarVistas(lista) {
  try { localStorage.setItem(AULAS_VISTAS_KEY, JSON.stringify((lista || []).map((a) => a.id))); } catch { /* ignore */ }
  setCount("#countAulas", 0);
}
async function contarAulasNovas() {
  try {
    const r = await api("/api/aulas");
    const vistas = aulasVistas();
    // primeira vez (nada visto ainda): nao pinta tudo de "novo", so o que
    // chegar daqui em diante
    if (!vistas.size) { aulasMarcarVistas(r.aulas || []); return; }
    const novas = (r.aulas || []).filter((a) => !vistas.has(a.id)).length;
    setCount("#countAulas", novas);
  } catch { /* sem rede, sem selo */ }
}

async function loadAulasUi() {
  const box = $("#aulasItens");
  if (!box) return;
  try {
    const r = await api("/api/aulas");
    state.aulas.lista = r.aulas || [];
    state.aulas.origem = r.origem || "";
    state.aulas.erro = r.erro || "";
    aulasMarcarVistas(state.aulas.lista);
  } catch (e) {
    state.aulas.lista = [];
    state.aulas.erro = e.message || "";
  }
  const admin = !!(state.auth && state.auth.isAdmin);
  $("#aulasAdmin")?.classList.toggle("hidden", !admin);
  if (!state.aulas.atualId && state.aulas.lista.length) state.aulas.atualId = state.aulas.lista[0].id;
  if (state.aulas.atualId && !aulaAtual()) state.aulas.atualId = state.aulas.lista.length ? state.aulas.lista[0].id : "";
  renderAulas();
  abrirAula(state.aulas.atualId, { semRolar: true });
  // minutagem: o servidor busca em segundo plano o que ainda nao tem
  const faltam = (state.aulas.lista || []).some((a) => !a.duracaoSeg);
  if (faltam && state.aulas.tentativas < 3) {
    state.aulas.tentativas += 1;
    setTimeout(() => { if (state.view === "aulas") atualizarMinutagem().catch(() => {}); }, 4000);
  } else if (!faltam) state.aulas.tentativas = 0;
}

async function atualizarMinutagem() {
  const r = await api("/api/aulas");
  const mapa = new Map((r.aulas || []).map((a) => [a.id, a.duracaoSeg || 0]));
  let mudou = false;
  for (const a of state.aulas.lista || []) {
    const d = mapa.get(a.id) || 0;
    if (d && d !== a.duracaoSeg) { a.duracaoSeg = d; mudou = true; }
  }
  if (mudou) { renderAulas(); aulaMostrarSobre(aulaAtual()); }
  if ((state.aulas.lista || []).some((a) => !a.duracaoSeg) && state.aulas.tentativas < 3) {
    state.aulas.tentativas += 1;
    setTimeout(() => { if (state.view === "aulas") atualizarMinutagem().catch(() => {}); }, 6000);
  }
}

function renderAulas() {
  const box = $("#aulasItens");
  const hint = $("#aulasHint");
  if (!box) return;
  const lista = state.aulas.lista || [];
  const admin = !!(state.auth && state.auth.isAdmin);
  if (hint) {
    const total = lista.reduce((s, a) => s + (a.duracaoSeg || 0), 0);
    const feitas = lista.filter((a) => aulaConcluida(a.id)).length;
    const totalTxt = (total ? ` · ${Math.max(1, Math.round(total / 60))} min no total` : "")
      + (feitas ? ` · ${feitas} concluída${feitas === 1 ? "" : "s"}` : "");
    hint.textContent = !lista.length
      ? (admin ? "Nenhuma aula ainda. Cadastre a primeira ao lado." : "As aulas ainda estão sendo gravadas. Volte em breve.")
      : (state.aulas.origem === "cache"
        ? `${lista.length} aula${lista.length === 1 ? "" : "s"}${totalTxt} · sem internet, mostrando a última lista baixada`
        : `${lista.length} aula${lista.length === 1 ? "" : "s"}${totalTxt}`);
  }
  // datalist de secoes para o admin
  const dl = $("#aulasSecoes");
  if (dl) dl.innerHTML = [...new Set(lista.map((a) => a.secao))].map((s) => `<option value="${escapeHtml(s)}">`).join("");
  const porSecao = new Map();
  for (const a of lista) {
    if (!porSecao.has(a.secao)) porSecao.set(a.secao, []);
    porSecao.get(a.secao).push(a);
  }
  box.innerHTML = [...porSecao.entries()].map(([secao, aulas]) => `
    <div class="aulas-secao">
      <p class="aulas-secao-nome">${escapeHtml(secao)}</p>
      ${aulas.map((a, i) => `
        <button type="button" class="aula-item${a.id === state.aulas.atualId ? " on" : ""}${aulaConcluida(a.id) ? " feita" : ""}" data-aula="${escapeHtml(a.id)}">
          <img class="aula-thumb" src="https://i.ytimg.com/vi/${escapeHtml(a.youtubeId)}/mqdefault.jpg" alt="" loading="lazy">
          <span class="aula-txt"><span class="aula-n">${aulaConcluida(a.id) ? "✓" : i + 1}</span><span class="aula-titulo">${escapeHtml(a.titulo)}</span>${a.duracaoSeg ? `<span class="aula-dur">${fmtRelogio(a.duracaoSeg)}</span>` : ""}</span>
        </button>`).join("")}
    </div>`).join("");
}

function aulaMostrarSobre(a) {
  const btn = $("#aulaConcluir");
  if (btn) {
    btn.classList.toggle("hidden", !a);
    const feita = !!(a && aulaConcluida(a.id));
    btn.classList.toggle("on", feita);
    btn.textContent = feita ? "✓ Concluída (desfazer)" : "✓ Concluir aula";
  }
  if ($("#aulaTitulo")) $("#aulaTitulo").textContent = a ? a.titulo : "";
  if ($("#aulaDur")) $("#aulaDur").textContent = a && a.duracaoSeg ? fmtRelogio(a.duracaoSeg) : "";
  const desc = $("#aulaDescricao");
  if (desc) desc.innerHTML = a ? descricaoHtml(a.descricao) : "";
}

function abrirAula(id, opts) {
  const a = (state.aulas.lista || []).find((x) => x.id === id) || null;
  state.aulas.atualId = a ? a.id : "";
  const box = $("#aulasPlayer");
  const vazio = $("#aulasVazio");
  if (vazio) vazio.classList.toggle("hidden", !!a);
  if (box) { box.classList.remove("playing", "ended"); box.classList.toggle("has-video", !!a); }
  $("#aulasFim")?.classList.add("hidden");
  aulaPlayerTempo(0, a ? a.duracaoSeg : 0);
  aulaMostrarSobre(a);
  for (const b of document.querySelectorAll("#aulasItens .aula-item")) {
    b.classList.toggle("on", b.dataset.aula === state.aulas.atualId);
  }
  if (a) aulaCarregarVideo(a, !!(opts && opts.tocar)).catch(() => {});
  if (a && state.auth && state.auth.isAdmin) aulaPreencherForm(a);
  if (a && !(opts && opts.semRolar)) $("#aulasPlayer")?.scrollIntoView({ block: "nearest" });
}

/* O embed do YouTube por baixo da capa. `controls=0` tira a barra do
 * YouTube (com o logo que leva para o site); o que sobra por cima do
 * video (titulo, canal, "Assista no YouTube", cards do fim) fica
 * VISIVEL mas nao clicavel: a capa engole o clique e faz play/pause. */
async function aulaCarregarVideo(a, tocar) {
  const erro = $("#aulasErro");
  const YT = await ytApi();
  if (!YT) {
    if (erro) {
      erro.classList.remove("hidden");
      erro.innerHTML = `Sem conexão com o YouTube agora. <a href="https://www.youtube.com/watch?v=${encodeURIComponent(a.youtubeId)}" target="_blank" rel="noopener">Abrir a aula no navegador</a>`;
    }
    return;
  }
  if (erro) erro.classList.add("hidden");
  if (state.aulas.atualId !== a.id) return;   // trocou de aula enquanto a API carregava
  const vars = { controls: 0, rel: 0, modestbranding: 1, iv_load_policy: 3, fs: 0, playsinline: 1,
                 disablekb: 1, origin: location.origin };
  if (!state.aulas.player) {
    state.aulas.player = new YT.Player("aulasYt", {
      videoId: a.youtubeId, playerVars: vars,
      events: {
        onReady: () => {
          aulaAplicarPrefs();
          aulaPlayerTempo(0, aulaPlayerDuracao());
          if (tocar) state.aulas.player.playVideo();
        },
        onStateChange: (e) => aulaEstado(e.data),
        onError: () => {
          if (erro) {
            erro.classList.remove("hidden");
            erro.textContent = "Este vídeo não permite ser exibido dentro do app. No YouTube Studio, libere a incorporação (Detalhes → Mostrar mais → Permitir incorporação).";
          }
        },
      },
    });
    return;
  }
  const p = state.aulas.player;
  if (!p.cueVideoById) return;
  if (tocar) p.loadVideoById(a.youtubeId); else p.cueVideoById(a.youtubeId);
  aulaAplicarPrefs();
}

/* Legenda do YouTube DESLIGADA por padrao (ele pediu) e a velocidade que a
 * pessoa escolheu. Vale a cada video: o YouTube religa a legenda quando o
 * usuario tem isso salvo na conta. */
function aulaAplicarPrefs() {
  const p = state.aulas.player;
  if (!p) return;
  try {
    if (state.aulas.cc) p.loadModule("captions"); else { p.unloadModule("captions"); p.unloadModule("cc"); }
  } catch { /* ignore */ }
  try { p.setPlaybackRate(state.aulas.vel || 1); } catch { /* ignore */ }
  for (const b of document.querySelectorAll("#aulasVel [data-vel]")) b.classList.toggle("on", Number(b.dataset.vel) === (state.aulas.vel || 1));
  for (const b of document.querySelectorAll("#aulasCc [data-cc]")) b.classList.toggle("on", (b.dataset.cc === "1") === !!state.aulas.cc);
}

function aulaPlayerDuracao() {
  const p = state.aulas.player;
  try { return (p && p.getDuration && p.getDuration()) || (aulaAtual() || {}).duracaoSeg || 0; } catch { return 0; }
}

function aulaPlayerTempo(atual, total) {
  const t = $("#aulasTempo");
  if (t) t.textContent = `${fmtRelogio(atual)} / ${fmtRelogio(total)}`;
  const fill = $("#aulasBarraFill");
  if (fill) fill.style.width = total ? `${Math.min(100, (atual / total) * 100)}%` : "0%";
}

function aulaEstado(st) {
  const box = $("#aulasPlayer");
  const YTS = (window.YT && window.YT.PlayerState) || { PLAYING: 1, PAUSED: 2, ENDED: 0 };
  const tocando = st === YTS.PLAYING;
  if (box) {
    box.classList.toggle("playing", tocando);
    box.classList.toggle("ended", st === YTS.ENDED);
  }
  $("#aulasFim")?.classList.toggle("hidden", st !== YTS.ENDED);
  if (st === YTS.ENDED && state.aulas.atualId && !aulaConcluida(state.aulas.atualId)) aulaMarcar(state.aulas.atualId, true);
  if (state.aulas.timer) { clearInterval(state.aulas.timer); state.aulas.timer = null; }
  if (tocando) {
    aulaAplicarPrefs();
    state.aulas.timer = setInterval(() => {
      const p = state.aulas.player;
      try { aulaPlayerTempo(p.getCurrentTime(), aulaPlayerDuracao()); } catch { /* ignore */ }
    }, 500);
  } else {
    const p = state.aulas.player;
    try { aulaPlayerTempo(st === YTS.ENDED ? aulaPlayerDuracao() : p.getCurrentTime(), aulaPlayerDuracao()); } catch { /* ignore */ }
  }
  // duracao lida do proprio player entra na lista na hora
  const a = aulaAtual();
  const d = aulaPlayerDuracao();
  if (a && d && !a.duracaoSeg) { a.duracaoSeg = Math.round(d); renderAulas(); aulaMostrarSobre(a); }
}

function aulaToggle() {
  const p = state.aulas.player;
  if (!p || !p.getPlayerState) return;
  const YTS = window.YT.PlayerState;
  const st = p.getPlayerState();
  if (st === YTS.PLAYING) p.pauseVideo();
  else { $("#aulasFim")?.classList.add("hidden"); p.playVideo(); }
}

function aulaProxima() {
  const lista = state.aulas.lista || [];
  const i = lista.findIndex((x) => x.id === state.aulas.atualId);
  const prox = lista[i + 1];
  if (prox) abrirAula(prox.id, { tocar: true }); else toast("Esta é a última aula");
}

function aulaAnterior() {
  const lista = state.aulas.lista || [];
  const i = lista.findIndex((x) => x.id === state.aulas.atualId);
  const ant = lista[i - 1];
  if (ant) abrirAula(ant.id, { tocar: true }); else toast("Esta é a primeira aula");
}

function aulaMenu(abrir) {
  state.aulas.menu = abrir == null ? !state.aulas.menu : !!abrir;
  $("#aulasMenu")?.classList.toggle("hidden", !state.aulas.menu);
  $("#aulasEngren")?.classList.toggle("on", state.aulas.menu);
}

function aulaPreencherForm(a) {
  const v = a || {};
  if ($("#aulaId")) $("#aulaId").value = v.id || "";
  if ($("#aulaFTitulo")) $("#aulaFTitulo").value = v.titulo || "";
  if ($("#aulaFLink")) $("#aulaFLink").value = v.youtubeId ? `https://youtu.be/${v.youtubeId}` : "";
  if ($("#aulaFSecao")) $("#aulaFSecao").value = v.secao || "";
  if ($("#aulaFOrdem")) $("#aulaFOrdem").value = v.ordem != null ? v.ordem : 100;
  if ($("#aulaFDesc")) $("#aulaFDesc").value = v.descricao || "";
  $("#aulaApagar")?.classList.toggle("hidden", !v.id);
  const btn = $("#aulaSalvar");
  if (btn) btn.textContent = v.id ? "Salvar alterações" : "Salvar aula";
}

async function aulaAdmin(body) {
  return api("/api/admin/aulas", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
}

function wireAulas() {
  const itens = $("#aulasItens");
  if (itens && !itens.dataset.wired) {
    itens.dataset.wired = "1";
    itens.addEventListener("click", (e) => {
      const b = e.target.closest("[data-aula]");
      if (b) abrirAula(b.dataset.aula, { tocar: true });
    });
  }
  const capa = $("#aulasCapa");
  if (capa && !capa.dataset.wired) {
    capa.dataset.wired = "1";
    // clique no video = play/pause; os botoes da barra tratam o proprio
    capa.addEventListener("click", (e) => {
      if (e.target.closest("#aulasCtl") || e.target.closest("#aulasFim") || e.target.closest("#aulasMenu")) return;
      if (state.aulas.menu) { aulaMenu(false); return; }
      aulaToggle();
    });
    $("#aulasAnterior")?.addEventListener("click", aulaAnterior);
    $("#aulasEngren")?.addEventListener("click", () => aulaMenu());
    $("#aulasVel")?.addEventListener("click", (e) => {
      const b = e.target.closest("[data-vel]");
      if (!b) return;
      state.aulas.vel = Number(b.dataset.vel) || 1;
      try { localStorage.setItem("ativavid.aulas.vel", String(state.aulas.vel)); } catch { /* ignore */ }
      aulaAplicarPrefs();
    });
    $("#aulasCc")?.addEventListener("click", (e) => {
      const b = e.target.closest("[data-cc]");
      if (!b) return;
      state.aulas.cc = b.dataset.cc === "1";
      aulaAplicarPrefs();
    });
    $("#aulasConcluirFim")?.addEventListener("click", () => { aulaMarcar(state.aulas.atualId, true); aulaProxima(); });
    $("#aulaConcluir")?.addEventListener("click", () => {
      const id = state.aulas.atualId;
      if (!id) return;
      const feita = !aulaConcluida(id);
      aulaMarcar(id, feita);
      if (feita) toast("✓ Aula concluída");
    });
    $("#aulasPlay")?.addEventListener("click", aulaToggle);
    $("#aulasPlayBig")?.addEventListener("click", (e) => { e.stopPropagation(); aulaToggle(); });
    $("#aulasDeNovo")?.addEventListener("click", () => { const p = state.aulas.player; if (p) { p.seekTo(0, true); p.playVideo(); } });
    $("#aulasProxima")?.addEventListener("click", aulaProxima);
    $("#aulasBarra")?.addEventListener("click", (e) => {
      const p = state.aulas.player;
      const r = e.currentTarget.getBoundingClientRect();
      const frac = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      const d = aulaPlayerDuracao();
      if (p && d) { p.seekTo(frac * d, true); aulaPlayerTempo(frac * d, d); }
    });
    $("#aulasMudo")?.addEventListener("click", (e) => {
      const p = state.aulas.player;
      if (!p || !p.isMuted) return;
      if (p.isMuted()) p.unMute(); else p.mute();
      e.currentTarget.classList.toggle("muted", p.isMuted());
    });
    $("#aulasTela")?.addEventListener("click", () => {
      const box = $("#aulasPlayer");
      if (!box) return;
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      else box.requestFullscreen().catch(() => {});
    });
    $("#aulasPlayer")?.addEventListener("keydown", (e) => {
      if (e.key === " " || e.key === "k") { e.preventDefault(); aulaToggle(); }
      const p = state.aulas.player;
      if (!p || !p.getCurrentTime) return;
      if (e.key === "ArrowRight") p.seekTo(p.getCurrentTime() + 10, true);
      if (e.key === "ArrowLeft") p.seekTo(Math.max(0, p.getCurrentTime() - 10), true);
    });
  }
  const nova = $("#aulaNova");
  if (nova && !nova.dataset.wired) {
    nova.dataset.wired = "1";
    nova.onclick = () => { aulaPreencherForm(null); $("#aulaFTitulo")?.focus(); };
  }
  const salvar = $("#aulaSalvar");
  if (salvar && !salvar.dataset.wired) {
    salvar.dataset.wired = "1";
    salvar.onclick = async () => {
      const id = $("#aulaId")?.value || "";
      try {
        const r = await aulaAdmin({
          action: "upsert", id, titulo: $("#aulaFTitulo")?.value || "",
          youtube: $("#aulaFLink")?.value || "", secao: $("#aulaFSecao")?.value || "",
          ordem: $("#aulaFOrdem")?.value || "", descricao: $("#aulaFDesc")?.value || "",
        });
        state.aulas.lista = (r.aulas || []).filter((a) => a.ativo !== false);
        state.aulas.origem = "servidor";
        state.aulas.atualId = r.id || id || state.aulas.atualId;
        renderAulas();
        abrirAula(state.aulas.atualId, { semRolar: true });
        toast(id ? "✓ Aula atualizada" : "✓ Aula publicada — já aparece para todo mundo");
      } catch (err) {
        toast(err.message || "Não consegui salvar a aula", 5000);
      }
    };
  }
  const apagar = $("#aulaApagar");
  if (apagar && !apagar.dataset.wired) {
    apagar.dataset.wired = "1";
    apagar.onclick = async () => {
      const id = $("#aulaId")?.value || "";
      if (!id) return;
      const a = (state.aulas.lista || []).find((x) => x.id === id);
      const ok = await pedirConfirmacao("Apagar esta aula?", `"${(a && a.titulo) || "Aula"}" some da lista de todo mundo. O vídeo no YouTube fica.`, "Apagar", true);
      if (!ok) return;
      try {
        const r = await aulaAdmin({ action: "delete", id });
        state.aulas.lista = (r.aulas || []).filter((x) => x.ativo !== false);
        state.aulas.atualId = state.aulas.lista.length ? state.aulas.lista[0].id : "";
        renderAulas();
        abrirAula(state.aulas.atualId, { semRolar: true });
        aulaPreencherForm(aulaAtual());
        toast("Aula apagada");
      } catch (err) {
        toast(err.message || "Não consegui apagar", 5000);
      }
    };
  }
}

/* ---- Tela de Empresas (5.0.1) ------------------------------------------
 * Um card por empresa; clicar ativa. O resto da tela e SEMPRE da empresa
 * ativa: identidade (nome, logo, cor, formato), perfil (o que a IA sabe)
 * e os presets de edicao dela. */
function renderEmpresaCards() {
  const box = $("#empCards");
  if (!box) return;
  const brands = state.brands || [];
  const ativa = state.brandActive && state.brandActive.id;
  const cards = brands.map((b) => {
    const on = b.id === ativa;
    const n = state.jobs.filter((x) => x.brandId === b.id).length;
    // 5.0.47: o card diz o RITMO da empresa, nao so o total — quantos
    // videos prontos nos ultimos 30 dias e a nota media do corte. Para
    // quem atende varias empresas, e a resposta de "quem esta parado".
    const prontos = state.jobs.filter((x) => x.brandId === b.id && x.status === "done");
    const agora = Date.now();
    const em30 = prontos.filter((x) => x.finishedAt && agora - Date.parse(x.finishedAt) < 30 * 864e5).length;
    const notas = prontos.map((x) => Number(x.score && x.score.overall)).filter((v) => Number.isFinite(v) && v > 0);
    const media = notas.length ? Math.round(notas.reduce((a, c) => a + c, 0) / notas.length) : null;
    const ritmo = n ? ` · ${em30} em 30 dias${media !== null ? ` · nota ${media}` : ""}` : "";
    const logo = b.logoUrl
      ? `<img class="emp-card-logo" src="${escapeHtml(b.logoUrl)}" alt="">`
      : `<span class="emp-card-ini" style="--emp-tint:${escapeHtml(b.accent || "")}">${escapeHtml(initialsFromName(b.name || b.id))}</span>`;
    return `<button type="button" class="emp-card${on ? " on" : ""}" data-emp="${escapeHtml(b.id)}" title="${on ? "Empresa ativa" : "Clique para trabalhar nesta empresa"}">
      ${logo}
      <span class="emp-card-nome">${escapeHtml(b.name || b.id)}</span>
      <span class="emp-card-meta">${n} vídeo${n === 1 ? "" : "s"}${ritmo} · ${b.presetCount || 0} preset${b.presetCount === 1 ? "" : "s"}${b.perfilOk ? "" : " · sem perfil"}</span>
      ${on ? `<span class="emp-card-tag">ativa</span>` : ""}
    </button>`;
  });
  cards.push(`<button type="button" class="emp-card emp-card--nova" id="empNova">
    <span class="emp-card-ini">+</span>
    <span class="emp-card-nome">Nova empresa</span>
    <span class="emp-card-meta">Identidade, perfil e presets próprios</span>
  </button>`);
  box.innerHTML = cards.join("");
}

function preencherEmpresaForm(b) {
  const marca = b || {};
  if ($("#empTitulo")) $("#empTitulo").textContent = marca.name || "Empresa";
  if ($("#empNome")) $("#empNome").value = marca.name || "";
  const cor = /^#[0-9a-f]{6}$/i.test(String(marca.accent || "")) ? marca.accent : "#e30004";
  if ($("#empCor")) $("#empCor").value = cor;
  if ($("#empCorVal")) $("#empCorVal").textContent = cor;
  const img = $("#empLogoImg");
  const txt = $("#empLogoTxt");
  const tirar = $("#empLogoRemover");
  const logo = marca.logoUrl || "";
  if (img) { img.classList.toggle("hidden", !logo); if (logo) img.src = logo; }
  if (txt) txt.classList.toggle("hidden", !!logo);
  if (tirar) tirar.classList.toggle("hidden", !logo);
  const del = $("#empApagar");
  if (del) del.disabled = (state.brands || []).length <= 1;
  if ($("#empEntregasNome")) $("#empEntregasNome").textContent = marca.name || "…";
}

async function loadEmpresaPerfil() {
  const grid = $("#rotPerfilGrid");
  if (!grid) return;
  try {
    const emp = await api("/api/roteiro/empresa");
    rotMontarPerfilForm(emp);
    if ($("#rotEmpresaTexto")) $("#rotEmpresaTexto").value = emp.empresa || "";
    if (state.roteiro && state.roteiro.pack) state.roteiro.pack.empresa = emp;
  } catch {
    grid.innerHTML = `<p class="hint">Não consegui ler o perfil da empresa.</p>`;
  }
}

async function loadEmpresaUi() {
  await Promise.all([loadPresetsUi(), loadEmpresaPerfil()]);
}

async function empresaAction(body) {
  return api("/api/brands", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
}

function wireEmpresas() {
  wirePintarPresets();
  const cards = $("#empCards");
  if (cards && !cards.dataset.wired) {
    cards.dataset.wired = "1";
    cards.addEventListener("click", async (e) => {
      if (e.target.closest("#empNova")) {
        const nome = await pedirTexto("Nome da empresa nova", "", "Criar");
        if (!nome || !nome.trim()) return;
        try {
          const r = await empresaAction({ action: "create", name: nome.trim() });
          setWsMarca("ativa");
          await loadBrandsUi();
          await loadEmpresaUi();
          loadImportPresets().catch(() => {});
          toast(`✓ ${r.brand.name} criada e ativa — preencha a identidade e o perfil`);
          $("#empNome")?.focus();
        } catch (err) {
          toast(err.message || "Não consegui criar a empresa");
        }
        return;
      }
      const card = e.target.closest("[data-emp]");
      if (!card) return;
      if (state.brandActive && state.brandActive.id === card.dataset.emp) return;
      await ativarEmpresa(card.dataset.emp);
    });
  }
  const cor = $("#empCor");
  if (cor && !cor.dataset.wired) {
    cor.dataset.wired = "1";
    cor.addEventListener("input", () => { if ($("#empCorVal")) $("#empCorVal").textContent = cor.value; });
  }
  const salvar = $("#empSalvar");
  if (salvar && !salvar.dataset.wired) {
    salvar.dataset.wired = "1";
    salvar.onclick = async () => {
      const id = state.brandActive && state.brandActive.id;
      if (!id) return;
      try {
        await empresaAction({ action: "update", id, name: $("#empNome")?.value || "", accent: $("#empCor")?.value || "" });
        await loadBrandsUi();
        loadImportPresets().catch(() => {});
        toast("✓ Identidade salva");
      } catch (err) {
        toast(err.message || "Não consegui salvar");
      }
    };
  }
  const apagar = $("#empApagar");
  if (apagar && !apagar.dataset.wired) {
    apagar.dataset.wired = "1";
    apagar.onclick = async () => {
      const b = state.brandActive;
      if (!b) return;
      const n = state.jobs.filter((x) => x.brandId === b.id).length;
      const ok = await pedirConfirmacao(
        `Apagar a empresa "${b.name}"?`,
        `Somem a identidade, o perfil e os ${b.presetCount || 0} preset(s) dela. `
          + `Os ${n} vídeo(s) continuam nos Projetos, como "sem empresa". Os roteiros ficam no disco.`,
        "Apagar", true);
      if (!ok) return;
      try {
        await empresaAction({ action: "delete", id: b.id });
        await loadBrandsUi();
        await loadEmpresaUi();
        loadImportPresets().catch(() => {});
        toast(`Empresa apagada — agora a ativa é ${nomeDaMarca(state.brandActive && state.brandActive.id)}`);
      } catch (err) {
        toast(err.message || "Não consegui apagar");
      }
    };
  }
  const logoBox = $("#empLogoBox");
  const logoIn = $("#empLogoInput");
  if (logoBox && logoIn && !logoBox.dataset.wired) {
    logoBox.dataset.wired = "1";
    logoBox.addEventListener("click", () => logoIn.click());
    logoIn.addEventListener("change", () => {
      const f = logoIn.files && logoIn.files[0];
      logoIn.value = "";
      const id = state.brandActive && state.brandActive.id;
      if (!f || !id) return;
      if (f.size > 3 * 1024 * 1024) { toast("A imagem precisa ter até 3 MB"); return; }
      const rd = new FileReader();
      rd.onload = async () => {
        try {
          await empresaAction({ action: "logo", id, dataUrl: String(rd.result || "") });
          await loadBrandsUi();
          toast("✓ Logo salvo");
        } catch (err) {
          toast(err.message || "Não consegui salvar o logo");
        }
      };
      rd.readAsDataURL(f);
    });
  }
  const abrirEnt = $("#empEntregas");
  if (abrirEnt && !abrirEnt.dataset.wired) {
    abrirEnt.dataset.wired = "1";
    abrirEnt.onclick = async () => {
      const id = state.brandActive && state.brandActive.id;
      try {
        await api("/api/entregas/abrir", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ brandId: id || "" }) });
      } catch (err) {
        toast(err.message || "Não consegui abrir a pasta");
      }
    };
  }
  const reunir = $("#empEntregasReunir");
  if (reunir && !reunir.dataset.wired) {
    reunir.dataset.wired = "1";
    reunir.onclick = async () => {
      const b = state.brandActive;
      if (!b) return;
      reunir.disabled = true;
      reunir.textContent = "Contando…";
      try {
        // 5.0.13: conta e pesa antes — 291 videos sao varios GB a mais no disco
        const prev = await api("/api/entregas/reunir", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ brandId: b.id, dryRun: true }) });
        if (!prev.n) { toast("Nenhum vídeo pronto desta empresa para reunir"); return; }
        const gb = (Number(prev.bytes || 0) / 1073741824);
        const peso = gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(Number(prev.bytes || 0) / 1048576)} MB`;
        const ok = await pedirConfirmacao(
          `Reunir ${prev.n} vídeo${prev.n === 1 ? "" : "s"} em Entregas/${b.name}?`,
          `Vai copiar cerca de ${peso} para lá (o que já estiver igual não é copiado de novo). Os projetos não mudam.`,
          "Reunir", false);
        if (!ok) return;
        reunir.textContent = "Reunindo…";
        const r = await api("/api/entregas/reunir", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ brandId: b.id }) });
        toast(r.n ? `✓ ${r.n} vídeo${r.n === 1 ? "" : "s"} em Entregas/${b.name}` : "Nenhum vídeo pronto desta empresa para reunir");
      } catch (err) {
        toast(err.message || "Não consegui reunir");
      } finally {
        reunir.disabled = false;
        reunir.textContent = "Reunir vídeos antigos";
      }
    };
  }
  const tirar = $("#empLogoRemover");
  if (tirar && !tirar.dataset.wired) {
    tirar.dataset.wired = "1";
    tirar.onclick = async () => {
      const id = state.brandActive && state.brandActive.id;
      if (!id) return;
      try {
        await empresaAction({ action: "logo_remove", id });
        await loadBrandsUi();
        toast("Logo removido");
      } catch (err) {
        toast(err.message || "Não consegui tirar o logo");
      }
    };
  }
}

async function loadPresetsUi() {
  const lista = $("#presetList");
  if (!lista) return;
  let pack = { presets: [] };
  try {
    pack = await api("/api/brand-presets");
  } catch {
    lista.innerHTML = "";
    $("#presetsHint").textContent = "Os presets não responderam.";
    falhaDaTela("presetsEmpty",
      "Não deu para ler os presets — o ATIVAVID pode estar iniciando ou ter sido fechado.",
      loadPresetsUi);
    return;
  }
  const presets = pack.presets || [];
  const activeId = pack.activeId || (pack.active && pack.active.id) || "";
  // A marca que o SERVIDOR listou, nao a que a tela acha que esta ativa.
  // `state.brandActive` so e preenchido por `loadBrandsUi()`, entao abrir
  // Presets direto (sem passar pela tela de Marca) deixava isto em "padrao":
  // a tela mostrava os presets da marca ativa e gravava nos da "padrao" —
  // criar, renomear e apagar iam para a marca errada, e a lista na frente do
  // usuario nem se mexia.
  state.presetBrandId = pack.brandId || (state.brandActive && state.brandActive.id) || "padrao";
  const empty = $("#presetsEmpty");
  if (empty) empty.classList.toggle("hidden", presets.length > 0);
  const hint = $("#presetsHint");
  if (hint) {
    // Sem "da marca X": a marca deixou de ser uma tela na 4.19, e o
    // paragrafo fixo acima ja explica o padrao e o Duplicar.
    hint.textContent = presets.length
      ? `${presets.length} preset(s) salvos.`
      : "Nenhum preset salvo ainda. Ajuste o estilo em Estilos e salve a combinação aqui.";
  }
/* Nome de tela de cada id de estilo.
 *
 * O cartao de preset mostrava o id cru — "stacked", "realce",
 * "informational" — numa tela que existe para o usuario ENTENDER o que o
 * preset decide. Os nomes ja existiam em `app/caption_styles.py`,
 * `app/video_layouts.py`, `app/content_type.py` e no catalogo do preview;
 * so esta tela nao os usava.
 *
 * O mapa mora aqui porque e rotulo de tela. Quem impede a copia de
 * apodrecer e `test_nomes_de_estilo_na_tela.py`, que compara cada linha
 * com a fonte de verdade. Estilo novo sem nome aqui quebra o teste — e o
 * pior caso, que e a tela mostrar o id de novo, nao volta calado. */
const NOME_DO_ESTILO = {
  layout: {
    limpa: "Limpo", split: "Tela dividida", split2: "Tela dividida com mídia",
    moldura: "Moldura", barra: "Barra inferior", desfocado: "Fundo desfocado",
    degrade: "Degradê", vinheta: "Vinheta", cinema: "Cinema",
    borda: "Borda da marca",
  },
  legenda: {
    karaoke: "Karaokê", stacked: "Empilhado", impacto: "Impacto",
    scatter: "Disperso", recorte: "Recorte", bolha: "Bolha de conversa",
    simples: "Simples", serifada: "Serifada", classica: "Clássica",
    bloco: "Bloco", metal: "Metálico", vidro: "Vidro",
    traco: "Contorno fino", moldura: "Moldura", eco: "Eco",
    neon: "Neon", degrade: "Degradê", bandeira: "Bandeira", maquina: "Máquina de escrever",
    pilula: "Pílula", etiqueta: "Etiqueta", fitadegrade: "Fita degradê", marcador: "Marca-texto",
    fitadupla: "Fita dupla", etiquetacanto: "Etiqueta recortada",
  },
  manchete: {
    outline: "Contorno", card: "Cartão", realce: "Realce", misto: "Misto",
    sombra: "Sombra dura", sublinhado: "Sublinhado", pilula: "Pílula",
    manchete: "Manchete", carimbo: "Carimbo",
    pergunta: "Pergunta → Resposta", faixa: "Faixa cheia", fita: "Fita",
    neon: "Neon", vazado: "Vazado", gradiente: "Degradê na letra",
    recorte: "Recorte", etiqueta: "Etiqueta", marcador: "Marca-texto",
    linhas: "Entre linhas", riscado: "Riscado", caixas: "Duas caixas",
    quadro: "Quadro",
    nenhuma: "Nenhuma",
  },
  transicao: {
    flash: "Flash", brilho: "Brilho", escurece: "Escurece",
    faixa: "Faixa da marca", nenhuma: "Sem transição",
  },
  ritmo: {
    natural: "Natural", dinamico: "Dinâmico", intenso: "Intenso",
    cirurgico: "Cirúrgico", narrativa: "Narrativa", turbo: "Turbo",
    comercial: "Comercial", calmo: "Calmo",
  },
  tipo: {
    educational: "Educativo", humor: "Humor", sales: "Venda",
    ad: "Anúncio (AIDA)", viral: "Viral", review: "Review",
    institutional: "Institucional", informational: "Informativo",
  },
};

/* O nome, ou o proprio id quando ele for de uma versao mais nova que este
 * mapa. Mostrar o id e feio; esconder o valor seria pior. */
function nomeDoEstilo(eixo, id) {
  const v = String(id || "").trim();
  if (!v) return "";
  return (NOME_DO_ESTILO[eixo] || {})[v.toLowerCase()] || v;
}

  lista.innerHTML = presets.map((p) => {
    const on = p.id === activeId;
    const tipo = p.contentType
      ? escapeHtml(nomeDoEstilo("tipo", p.contentType)) : "—";
    // O que este preset DECIDE. Antes a linha mostrava só um rótulo solto
    // ("viral") e o usuário perguntou para que servia a tela.
    const st = p.style || {};
    const chip = (rot, val) => (val
      ? `<span class="preset-chip"><i>${rot}</i>${escapeHtml(String(val))}</span>`
      : "");
    const cor = (rot, hex) => (/^#[0-9a-f]{3,8}$/i.test(String(hex || ""))
      ? `<span class="preset-chip"><i>${rot}</i><b class="preset-cor" style="background:${escapeHtml(hex)}"></b>${escapeHtml(hex)}</span>`
      : "");
    const chips = [
      chip("layout", nomeDoEstilo("layout", st.edit)),
      chip("legenda", nomeDoEstilo("legenda", st.captions)),
      chip("manchete", nomeDoEstilo("manchete", st.headline)),
      chip("ritmo", nomeDoEstilo("ritmo", st.rhythm)),
      chip("transição", nomeDoEstilo("transicao", st.transicao)),
      cor("cor", st.accent),
      cor("legenda", st.captionAccent),
    ].filter(Boolean).join("");
    return `<article class="preset-row${on ? " on" : ""}" data-preset="${escapeHtml(p.id)}">
      <div class="preset-main">
        <strong class="preset-name">${escapeHtml(p.name || p.id)}</strong>
        <span class="preset-meta">${tipo}${on ? " · padrão" : ""}</span>
        ${chips
          ? `<div class="preset-chips">${chips}</div>`
          : `<div class="preset-chips"><span class="preset-chip preset-chip--vazio">`
            + `não define o visual — usa o estilo base</span></div>`}
      </div>
      <div class="preset-acts">
        <button type="button" class="export-btn export-btn--sm" data-preset-act="edit">Editar estilo</button>
        ${on ? "" : `<button type="button" class="ghost-btn ghost-btn--sm" data-preset-act="default">Usar como padrão</button>`}
        <button type="button" class="ghost-btn ghost-btn--sm" data-preset-act="duplicate">Duplicar</button>
        <button type="button" class="ghost-btn ghost-btn--sm" data-preset-act="copy" title="Copiar este preset para outra empresa">Copiar para…</button>
        <button type="button" class="ghost-btn ghost-btn--sm" data-preset-act="rename">Renomear</button>
        <button type="button" class="ghost-btn ghost-btn--sm preset-del" data-preset-act="delete">Apagar</button>
      </div>
    </article>`;
  }).join("");
}

async function presetAction(action, body) {
  const res = await api("/api/brand-presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ brandId: state.presetBrandId || "padrao", action, ...body }),
  });
  await loadPresetsUi();
  await loadImportPresets().catch(() => {});
  return res;
}

/* "Usar a cor da empresa" nos presets (5.0.23).
 *
 * Preset guarda uma copia inteira do estilo, e os criados antes da 5.0.22
 * congelaram o vermelho de fabrica. Trocar a cor da empresa nao alcancava
 * esses campos e o video saia vermelho — ele apagou e recriou a empresa
 * varias vezes atras disso (04/09). Aqui ele diz "a cor e esta", e a
 * escolha vale para todos os presets de uma vez. */
function wirePintarPresets() {
  const btn = $("#btnPresetsPintar");
  if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.onclick = async () => {
    const bid = state.presetBrandId || (state.brandActive && state.brandActive.id);
    if (!bid) { toast("Escolha uma empresa primeiro"); return; }
    const ok = await pedirConfirmacao(
      "Pintar os presets com a cor da empresa?",
      "Todos os presets desta empresa passam a usar a cor de destaque dela na "
      + "manchete e no realce da legenda. O resto de cada preset fica como está.",
      "Pintar");
    if (!ok) return;
    btn.disabled = true;
    try {
      // pelo helper de sempre: POST cru para /api/brands e o que grava o
      // corpo por cima da empresa ativa (guarda em test_criar_marca.py)
      const r = await empresaAction({ action: "pintar", id: bid });
      await loadPresetsUi();
      loadImportPresets().catch(() => {});
      toast(r.presets
        ? `✓ ${r.presets} preset(s) agora usam ${r.cor}`
        : "Os presets já estavam com a cor da empresa");
    } catch (e) {
      toast(e.message || "Não deu para pintar os presets");
    } finally {
      btn.disabled = false;
    }
  };
}

function wireIdentidade() {
  const grid = $("#identGrid");
  if (!grid || grid.dataset.wired) return;
  grid.dataset.wired = "1";
  // Só anota o destino. Quem troca de tela é o handler de `data-view` em
  // `wireList`, que está no `document` e portanto roda DEPOIS deste — e o
  // `setView("estilo")` dele entrega o destino ao editor.
  grid.addEventListener("click", (e) => {
    const tile = e.target.closest("[data-ident]");
    if (tile) alvoNoEstilo = tile.dataset.ident;
  });
}

/* Espaco recuperavel, avisado onde os projetos estao.
 *
 * Medido na maquina dele em 30/08: 68,4 GB (34,4 de copias duplicadas +
 * 34,0 de intermediarios de projetos entregues). O app ja media isso e
 * so contava numa dica dentro de Configuracoes > Avancado — tela onde
 * ele nao entra.
 *
 * Piso de 20 GB para nao virar paisagem, e "Agora nao" cala por 30 dias. */
const ESPACO_PISO_GB = 20;
const ESPACO_SILENCIO_DIAS = 30;

async function avisarEspaco() {
  const caixa = $("#projEspaco");
  if (!caixa) return;
  try {
    const ate = Number(localStorage.getItem("ativavid-espaco-adiado") || 0);
    if (ate && Date.now() < ate) return;
  } catch { /* sem localStorage: avisa mesmo assim */ }
  let m;
  try {
    m = await api("/api/espaco");
  } catch {
    return;
  }
  const gb = Number((m && m.totalGb) || 0);
  if (!(gb >= ESPACO_PISO_GB)) return;
  const txt = $("#projEspacoTxt");
  if (txt) {
    txt.innerHTML = `Dá para liberar <strong>${gb.toFixed(0)} GB</strong> sem `
      + `perder vídeo nenhum — ${Number(m.duplicatasGb || 0).toFixed(0)} GB de `
      + `cópias repetidas e ${Number(m.intermediariosGb || 0).toFixed(0)} GB de `
      + `arquivos que o app refaz sozinho.`;
  }
  caixa.classList.remove("hidden");
}

function wireEspacoDosProjetos() {
  const caixa = $("#projEspaco");
  if (!caixa || caixa.dataset.wired) return;
  caixa.dataset.wired = "1";
  const btn = $("#btnProjEspaco");
  if (btn) {
    btn.onclick = async () => {
      btn.disabled = true;
      btn.textContent = "Liberando…";
      try {
        const r = await api("/api/espaco/liberar", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        toast(`✓ ${r.totalGb || 0} GB liberados`, 7000);
        caixa.classList.add("hidden");
      } catch (e) {
        toast(e.message || "Não deu para liberar espaço");
      } finally {
        btn.disabled = false;
        btn.textContent = "Liberar espaço";
      }
    };
  }
  const nao = $("#btnProjEspacoNao");
  if (nao) {
    nao.onclick = () => {
      try {
        localStorage.setItem("ativavid-espaco-adiado",
          String(Date.now() + ESPACO_SILENCIO_DIAS * 86400000));
      } catch { /* ignore */ }
      caixa.classList.add("hidden");
    };
  }
}

/* Copiar preset(s) para OUTRA empresa (5.0.4). `id` vazio = todos. */
async function copiarPresetsPara(id, rotulo) {
  const origem = state.presetBrandId || (state.brandActive && state.brandActive.id) || "";
  const outras = (state.brands || []).filter((b) => b.id !== origem);
  if (!outras.length) { toast("Crie outra empresa primeiro (tela Empresas)"); return; }
  const destino = await pedirEmpresa(
    id ? `Copiar "${rotulo}" para qual empresa?` : `Copiar todos os presets de ${nomeDaMarca(origem)} para qual empresa?`,
    outras);
  if (!destino) return;
  try {
    const pack = await presetAction("copy", { id: id || "", to: destino });
    const n = (pack.copiados || []).length;
    toast(`✓ ${n} preset${n === 1 ? "" : "s"} copiado${n === 1 ? "" : "s"} para ${pack.destinoNome || nomeDaMarca(destino)}`);
    loadBrandsUi().catch(() => {});   // a contagem no card da empresa
  } catch (e) {
    toast(e.message || "Não consegui copiar");
  }
}

/** Pergunta uma empresa da lista. Devolve o id ou null. */
function pedirEmpresa(titulo, empresas) {
  return _dlgApp(
    `<h3>${escapeHtml(titulo)}</h3>
     <select class="dlg-input" id="_dlgEmp">${empresas.map((b) =>
       `<option value="${escapeHtml(b.id)}">${escapeHtml(b.name || b.id)}</option>`).join("")}</select>
     <div class="dlg-actions">
       <button type="button" class="ghost-btn" data-nao>Cancelar</button>
       <button type="button" class="export-btn" data-sim>Copiar</button>
     </div>`,
    (d, fechar) => {
      const sel = d.querySelector("#_dlgEmp");
      d.querySelector("[data-sim]").addEventListener("click", () => fechar(sel.value || null));
      setTimeout(() => sel.focus(), 30);
    },
  );
}

function wirePresets() {
  const btnTodos = $("#btnPresetsCopiarTodos");
  if (btnTodos && !btnTodos.dataset.wired) {
    btnTodos.dataset.wired = "1";
    btnTodos.onclick = () => copiarPresetsPara("", "");
  }
  const btnNovo = $("#btnPresetNovo");
  if (btnNovo && !btnNovo.dataset.wired) {
    btnNovo.dataset.wired = "1";
    btnNovo.onclick = async () => {
      const nome = await pedirTexto("Nome do preset novo", "", "Criar");
      if (!nome || !nome.trim()) return;
      try {
        // O estilo BASE e o ponto de partida — e o que a marca ativa
        // desenha hoje. `/api/preset` devolve ele inteiro.
        const base = await api("/api/preset").catch(() => ({}));
        const { brandId: _b, id: _i, brandName: _n, ...estilo } = base || {};
        const pack = await presetAction("create", {
          name: nome.trim(), style: estilo,
        });
        const novo = (pack.presets || []).find((x) => x.name === nome.trim());
        // `create` marca o novo como padrao (comportamento do servidor,
        // o mesmo do editor). Dizer isso e melhor que ele descobrir
        // quando o proximo video sair diferente.
        toast("Preset criado — e já virou o padrão");
        if (novo) {
          state.editPresetId = novo.id;
          state.editPresetNome = novo.name;
          setView("estilo");
        }
      } catch (e) {
        toast(e.message || "Não deu para criar o preset");
      }
    };
  }
  const lista = $("#presetList");
  if (lista && !lista.dataset.wired) {
    lista.dataset.wired = "1";
    lista.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-preset-act]");
      if (!btn) return;
      const row = btn.closest("[data-preset]");
      const id = row && row.dataset.preset;
      if (!id) return;
      const act = btn.dataset.presetAct;
      try {
        if (act === "delete") {
          const okApagar = await pedirConfirmacao(
            "Apagar este preset?",
            "Os vídeos já feitos não mudam — só o preset sai da lista.",
            "Apagar", true);
          if (!okApagar) return;
          await presetAction("delete", { id });
          toast("Preset apagado");
        } else if (act === "rename") {
          const atual = row.querySelector(".preset-name")?.textContent || "";
          const nome = await pedirTexto("Novo nome do preset", atual, "Renomear");
          if (!nome || !nome.trim()) return;
          await presetAction("rename", { id, name: nome.trim() });
          toast("Preset renomeado");
        } else if (act === "duplicate") {
          const atual = row.querySelector(".preset-name")?.textContent || "Preset";
          await presetAction("duplicate", { id, name: `${atual} (cópia)` });
          toast("Preset duplicado");
        } else if (act === "copy") {
          const atual = row.querySelector(".preset-name")?.textContent || "Preset";
          await copiarPresetsPara(id, atual);
        } else if (act === "default") {
          await presetAction("default", { id });
          toast("Preset virou o padrão");
        } else if (act === "edit") {
          // O editor e o mesmo de Estilos; o `presetId` diz o que ele
          // esta editando — e para onde o Salvar vai.
          state.editPresetId = id;
          state.editPresetNome =
            row.querySelector(".preset-name")?.textContent || "";
          setView("estilo");
        }
      } catch (err) {
        toast(err.message || "Não deu para aplicar");
      }
    });
  }
}


/* ---- Janelas do APP, no lugar das do navegador ---------------------------
 * `prompt()` e `confirm()` abrem a caixa do Chrome, com o "127.0.0.1:4850
 * diz" em cima e os botoes do sistema — dentro de um app escuro isso parece
 * outro programa (o usuario mandou print em 29/08: "esse tipo de janela feia
 * nao quero"). Estas usam <dialog>, herdam o tema e devolvem Promise. */
function _dlgApp(html, aoAbrir) {
  return new Promise((resolve) => {
    const d = document.createElement('dialog');
    d.className = 'dlg dlg-app';
    d.innerHTML = html;
    document.body.appendChild(d);
    const fechar = (v) => {
      resolve(v);
      d.close();
      d.remove();
    };
    d.addEventListener('cancel', (e) => { e.preventDefault(); fechar(null); });
    d.querySelector('[data-nao]')?.addEventListener('click', () => fechar(null));
    if (aoAbrir) aoAbrir(d, fechar);
    d.showModal();
  });
}

/** Pergunta um texto. Devolve a string ou null (cancelou). */
function pedirTexto(titulo, valor, rotuloOk) {
  return _dlgApp(
    `<h3>${escapeHtml(titulo)}</h3>
     <input type="text" class="dlg-input" id="_dlgTxt" value="${escapeHtml(valor || '')}" autocomplete="off">
     <div class="dlg-actions">
       <button type="button" class="ghost-btn" data-nao>Cancelar</button>
       <button type="button" class="export-btn" data-sim>${escapeHtml(rotuloOk || 'Salvar')}</button>
     </div>`,
    (d, fechar) => {
      const campo = d.querySelector('#_dlgTxt');
      const ok = () => {
        const v = (campo.value || '').trim();
        fechar(v || null);
      };
      d.querySelector('[data-sim]').addEventListener('click', ok);
      campo.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); ok(); }
      });
      setTimeout(() => { campo.focus(); campo.select(); }, 30);
    },
  );
}

/** Pergunta sim/nao. `perigo` deixa o botao de confirmar vermelho. */
function pedirConfirmacao(titulo, detalhe, rotuloOk, perigo) {
  return _dlgApp(
    `<h3>${escapeHtml(titulo)}</h3>
     ${detalhe ? `<p class="hint">${escapeHtml(detalhe)}</p>` : ''}
     <div class="dlg-actions">
       <button type="button" class="ghost-btn" data-nao>Agora não</button>
       <button type="button" class="${perigo ? 'danger-btn' : 'export-btn'}" data-sim>${escapeHtml(rotuloOk || 'Confirmar')}</button>
     </div>`,
    (d, fechar) => {
      d.querySelector('[data-sim]').addEventListener('click', () => fechar(true));
    },
  ).then((v) => v === true);
}

function wireBiblioteca() {
  const abas = $("#libraryTabs");
  if (abas && !abas.dataset.wired) {
    abas.dataset.wired = "1";
    abas.addEventListener("click", (ev) => {
      const b = ev.target.closest(".lib-tab");
      if (!b) return;
      state.libAba = b.dataset.libtab || "image";
      state.libCat = "";          // filtro de outra aba nao vale nesta
      renderLibraryAba();
    });
  }
  const chips = $("#libraryChips");
  if (chips && !chips.dataset.wired) {
    chips.dataset.wired = "1";
    chips.addEventListener("click", (ev) => {
      const b = ev.target.closest(".lib-chip");
      if (!b) return;
      state.libCat = b.dataset.libcat || "";
      renderLibraryAba();
    });
  }
  const dono = $("#libraryDono");
  if (dono && !dono.dataset.wired) {
    dono.dataset.wired = "1";
    dono.addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-libdono]");
      if (!b) return;
      state.libDono = b.dataset.libdono || "empresa";
      renderLibraryAba();
    });
  }
  // Trocar a categoria RENOMEIA o arquivo no disco: e assim que o pipeline
  // le (o plano B da musica escolhe pelo prefixo do nome).
  const painel = $("#libraryPanel");
  if (painel && !painel.dataset.wired) {
    painel.dataset.wired = "1";
    // Um play por vez. Sem isto, ouvir a terceira trilha deixava as duas
    // anteriores tocando por cima (o usuario mandou print com tres ao
    // mesmo tempo) — e comparar duas musicas fica impossivel. `play` nao
    // borbulha, por isso o listener e de captura.
    painel.addEventListener("play", (ev) => {
      const alvo = ev.target;
      if (!alvo || !("pause" in alvo)) return;
      pararAudio();          // o player da casa nao e um <audio> no DOM
      for (const m of painel.querySelectorAll("audio, video")) {
        if (m !== alvo && !m.paused) m.pause();
      }
    }, true);
    painel.addEventListener("change", async (ev) => {
      const donoSel = ev.target.closest(".lib-dono-sel");
      if (donoSel) {
        donoSel.disabled = true;
        try {
          await api("/api/library/mover", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rel: donoSel.dataset.librel, empresa: donoSel.value || "" }),
          });
          toast(donoSel.value ? `Agora é de ${nomeDaMarca(donoSel.value)}` : "Agora é Comum");
          await loadLibraryUi();
        } catch (err) {
          toast(err.message || "Não consegui mover");
          donoSel.disabled = false;
        }
        return;
      }
      const sel = ev.target.closest(".lib-cat");
      if (!sel) return;
      const rel = sel.dataset.librel;
      const categoria = sel.value || "";
      sel.disabled = true;
      try {
        const r = await api("/api/library/categoria", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rel, categoria }),
        });
        toast(categoria ? `Agora e "${categoria}"` : "Categoria removida");
        if (r && r.name) await loadLibraryUi();
      } catch (err) {
        toast(err.message || "Nao deu para trocar a categoria");
        sel.disabled = false;
      }
    });
  }
  const btn = $("#btnLibraryAdd");
  if (btn && !btn.dataset.wired) {
    btn.dataset.wired = "1";
    btn.onclick = () => {
      const cfg = LIB_ABAS[state.libAba || "image"];
      const input = $(cfg.input);
      if (input) input.click();
    };
  }
  for (const id of ["#libraryFileInput", "#libraryVideoInput",
                    "#libraryMusicInput", "#librarySfxInput"]) {
    const input = $(id);
    if (!input || input.dataset.wired) continue;
    input.dataset.wired = "1";
    input.onchange = async () => {
      const files = [...(input.files || [])];
      if (!files.length) return;
      const aba = state.libAba || "image";
      const kind = (aba === "image" || aba === "clip") ? "" : aba;  // pela extensao
      const cat = (state.libCat && state.libCat !== "\u2205") ? state.libCat : "";
      // imagem/video entram para a empresa ativa, ou para o Comum se a
      // vista "Só Comum" estiver marcada (5.0.2)
      const visual = aba === "image" || aba === "clip";
      const ativa = (state.brandActive && state.brandActive.id) || "";
      const emp = visual && state.libDono !== "comum" ? ativa : "";
      const qs = [kind ? `kind=${kind}` : "",
                  cat ? `categoria=${encodeURIComponent(cat)}` : "",
                  emp ? `empresa=${encodeURIComponent(emp)}` : ""]
        .filter(Boolean).join("&");
      let ok = 0;
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f, f.name);
        try {
          const res = await fetch(`/api/library/upload${qs ? "?" + qs : ""}`,
                                  { method: "POST", body: fd });
          if (res.ok) ok += 1;
        } catch { /* segue para o proximo */ }
      }
      input.value = "";
      toast(ok ? `${ok} arquivo(s) na biblioteca` : "Nada foi enviado");
      await loadLibraryUi().catch(() => {});
    };
  }
}

async function checkCrashRecovery() {
  const data = await api("/api/recovery");
  const jobs = data.recovered || [];
  if (!jobs.length) return;
  const dlg = $("#dlgRecovery");
  const list = $("#recoveryList");
  if (!dlg || !list) {
    toast(`${jobs.length} edição(ões) retomada(s) na fila`);
    return;
  }
  list.textContent = jobs.map((j) => j.title || j.name || j.id).join(", ");
  const close = () => { try { dlg.close(); } catch { /* ignore */ } };
  $("#btnRecoveryOk").onclick = () => {
    close();
    setView("fila");
    toast("Fila retomada");
  };
  $("#btnRecoverySkip").onclick = () => close();
  try { dlg.showModal(); } catch { toast(`${jobs.length} na fila após interrupção`); }
}

function applyThemeToIframes(theme) {
  const fr = $("#estiloFrame");
  try {
    if (fr && fr.contentDocument && fr.contentDocument.documentElement) {
      fr.contentDocument.documentElement.setAttribute("data-theme", theme);
    }
  } catch { /* cross-origin ignore */ }
}

function setTheme(next) {
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("ativavid-theme", next); } catch { /* ignore */ }
  applyThemeToIframes(next);
}

function pyApi() {
  try {
    return window.pywebview && window.pywebview.api;
  } catch {
    return null;
  }
}

function setMaximizedUi(on) {
  document.body.classList.toggle("maximized", !!on);
}

async function wireTitlebar() {
  document.body.classList.add("desktop-app");

  const btnCfg = $("#btnTbConfig");
  if (btnCfg) {
    btnCfg.onclick = () => {
      setView("sistema");
      toast("Sistema · desempenho e atualizações");
    };
  }

  const btnVer = $("#btnTbVersion");
  const refreshVersion = async () => {
    // Mesma fonte da sidebar — e aplica nos dois lugares
    let ver = "?";
    try {
      const h = await api("/api/health");
      ver = String(h.version || "?").replace(/^v/i, "");
    } catch { /* ignore */ }
    applyAppVersion(ver);
    try {
      const up = await api("/api/update/check");
      // O aviso aparece SOZINHO, como o usuario pediu (29/08, comparando
      // com o CapCut): antes so a pastilha de versao mudava de cor e ele
      // precisava descobrir que aquilo era clicavel. Uma vez por versao —
      // quem disse "agora nao" nao e perguntado de novo ate sair outra.
      if (up.updateAvailable && !up.force) avisarVersaoNova(up, ver);
      if (btnVer) {
        btnVer.classList.toggle("update-available", !!up.updateAvailable);
        const tip = up.tooltip
          || (up.updateAvailable
            ? `Atualizar · clique`
            : `v${ver} · clique para checar`);
        btnVer.title = tip;
      }
    } catch {
      if (btnVer) btnVer.title = `v${ver} · clique para checar`;
    }
  };
  if (btnVer) {
    btnVer.onclick = async () => {
      try {
        const up = await api("/api/update/check");
        await refreshVersion();
        if (up.updateAvailable) {
          toast(up.message || "Há atualização");
          if (up.force) {
            openUpdateDialog({
              mode: "update_required",
              message: up.message,
              update: {
                force: true,
                updateAvailable: true,
                latestVersion: up.latestVersion,
                downloadUrl: up.downloadUrl,
                message: up.message,
              },
            });
          }
          if (!up.force) await instalarAtualizacao();
        } else {
          toast(up.message || "Você está no build atual");
        }
      } catch (e) {
        toast(String(e.message || e));
      }
    };
  }
  refreshVersion();

  const drag = document.querySelector(".titlebar-drag");
  if (drag) {
    drag.addEventListener("dblclick", async () => {
      try {
        const maxed = await pyApi()?.toggle_maximize?.();
        setMaximizedUi(maxed);
      } catch { /* ignore */ }
    });
  }

  const min = $("#btnWinMin");
  const max = $("#btnWinMax");
  const close = $("#btnWinClose");
  if (min) {
    min.onclick = async () => {
      try { await pyApi()?.minimize?.(); } catch { /* ignore */ }
    };
  }
  if (max) {
    max.onclick = async () => {
      try {
        const maxed = await pyApi()?.toggle_maximize?.();
        setMaximizedUi(maxed);
      } catch { /* ignore */ }
    };
  }
  if (close) {
    close.onclick = async () => {
      try { await pyApi()?.close?.(); } catch { window.close(); }
    };
  }

  // pywebview.api pode demorar a aparecer — re-tenta e sincroniza max.
  for (let i = 0; i < 60; i++) {
    const apiw = pyApi();
    if (apiw) {
      try {
        if (apiw.is_maximized) setMaximizedUi(await apiw.is_maximized());
      } catch { /* ignore */ }
      break;
    }
    await new Promise((r) => setTimeout(r, 50));
  }
}

function wireTheme() {
  const btn = $("#btnTheme");
  if (btn) {
    btn.onclick = () => {
      const cur = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
      setTheme(cur === "light" ? "dark" : "light");
    };
  }
  window.addEventListener("storage", (e) => {
    if (e.key !== "ativavid-theme" || !e.newValue) return;
    document.documentElement.setAttribute("data-theme", e.newValue);
    applyThemeToIframes(e.newValue);
  });
}

async function boot() {
  wireDrop();
  wireList();
  wireForms();
  wireProjetos();
  wireGaveta();
  wirePresets();
  wireIdentidade();
  wireEmpresas();
  wireAulas();
  wireComece();
  wireBiblioteca();
  wireTheme();
  await wireTitlebar();
  window.addEventListener("message", (e) => {
    if (!e.data || e.data.type !== "ativavid-house-style-saved") return;
    toast(state.editPresetId ? "Preset salvo" : "Estilo padrão salvo");
    if (state.editPresetId) {
      // Volta para a lista: e de la que ele veio, e e la que da para ver
      // o resultado (as pastilhas do cartao mudam).
      state.editPresetId = "";
      state.editPresetNome = "";
      loadPresetsUi().catch(() => {});
      setView("presets");
      return;
    }
    const fr = $("#estiloFrame");
    if (fr) {
      fr.dataset.loaded = "";
      fr.src = estiloFrameSrc();
      fr.dataset.loaded = "1";
    }
  });
  try {
    if (localStorage.getItem("ativavid-sb-collapsed") === "1") {
      document.body.classList.add("sb-collapsed");
    }
  } catch { /* ignore */ }
  let initial = "import";
  try {
    const q = new URLSearchParams(location.search).get("view");
    // Início é a home: / sem ?view= sempre abre Importar (drop + recentes).
    // Só restaura outra tela quando a URL pede (?view=fila etc.).
    if (q && VIEW_COPY[q]) initial = q;
  } catch { /* ignore */ }
  if (!VIEW_COPY[initial]) initial = "import";
  setView(initial);
  await refreshHealth();
  await refreshAuthUi().catch(() => {});
  await loadBrandsUi().catch(() => {});
  contarAulasNovas().catch(() => {});
  try {
    const lic = await api("/api/license");
    renderLicense(lic);
    if (lic.update?.force || lic.mode === "update_required") {
      openUpdateDialog(lic);
    }
  } catch { /* ignore */ }
  try {
    await checkCrashRecovery();
  } catch { /* ignore */ }
  await refreshJobs();
  // Poll adaptativo: o progresso fino de um job RODANDO vem de arquivos que
  // o subprocesso escreve (fora do event bus), então só aí o poll de 2,5s se
  // paga. Ocioso, quem avisa é o SSE (/api/events) — com um watchdog de 20s
  // caso a conexão caia em silêncio. /api/jobs varre o disco no servidor;
  // cada rodada evitada é I/O real economizado.
  let pollBusy = false;
  let sseOk = false;
  let lastRefresh = Date.now();
  const tickRefresh = async () => {
    if (pollBusy) return;
    pollBusy = true;
    lastRefresh = Date.now();
    try {
      await refreshJobs().catch(() => {});
      await refreshHealth().catch(() => {});
    } finally {
      pollBusy = false;
    }
  };
  try {
    const es = new EventSource("/api/events");
    es.onopen = () => { sseOk = true; };
    es.onerror = () => { sseOk = false; };
    es.addEventListener("tick", () => {
      if (!document.hidden) tickRefresh();
    });
  } catch { sseOk = false; }
  const hasActiveWork = () =>
    (state.jobs || []).some((j) => jobInFila(j) || j.status === "processing" || j.applying);
  setInterval(() => {
    if (document.hidden || pollBusy) return;
    if (sseOk && !hasActiveWork() && Date.now() - lastRefresh < 20000) return;
    tickRefresh();
  }, 2500);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) tickRefresh();
  });
}

boot();

/* ======================================================================
 * Roteiro de gravacao (4.97): chat com a IA que conhece a empresa.
 * A rede e a mesma do corte (sessao do navegador -> Groq). A memoria dos
 * chats e local, por marca (/api/roteiro/*). A resposta vem limpa (sem
 * markdown) para ler e gravar; os botoes copiam o roteiro ou so os ganchos.
 * ====================================================================== */
const ROT_OPCOES_KEY = "ativavid.roteiro.opcoes";
const ROT_FRASES = [
  "Pensando nos ganchos…", "Lendo os dados da empresa…", "Cortando o que não para o scroll…",
  "Escrevendo como se fala…", "Ajustando o tempo de cada bloco…", "Fechando o CTA…",
];
state.roteiro = { brandId: null, chatId: null, chatAtual: null, chats: [], enviando: false, pack: null };

function rotOpcoes() {
  return {
    estilo: $("#rotEstilo")?.value || "venda",
    duracao: Number($("#rotDuracao")?.value || 30),
    objetivo: $("#rotObjetivo")?.value || "vendas",
    tom: $("#rotTom")?.value || "direto",
    gatilho: $("#rotGatilho")?.value || "auto",
    nicho: ($("#rotNicho")?.value || "").trim(),
  };
}

function rotGuardarOpcoes() {
  try { localStorage.setItem(ROT_OPCOES_KEY, JSON.stringify(rotOpcoes())); } catch { /* ignore */ }
}

function rotPreencherSelects(pack) {
  const opt = (v, t, sel) => `<option value="${escapeHtml(String(v))}"${sel ? " selected" : ""}>${escapeHtml(t)}</option>`;
  let salvo = {};
  try { salvo = JSON.parse(localStorage.getItem(ROT_OPCOES_KEY) || "{}") || {}; } catch { salvo = {}; }
  const e = $("#rotEstilo");
  if (e) e.innerHTML = (pack.estilos || []).map((x) => opt(x.id, x.nome, x.id === (salvo.estilo || "venda"))).join("");
  const d = $("#rotDuracao");
  if (d) d.innerHTML = (pack.duracoes || [15, 30, 45, 60, 90]).map((x) => opt(x, `${x} s`, Number(x) === Number(salvo.duracao || 30))).join("");
  const o = $("#rotObjetivo");
  if (o) o.innerHTML = Object.entries(pack.objetivos || {}).map(([k, v]) => opt(k, v, k === (salvo.objetivo || "vendas"))).join("");
  const t = $("#rotTom");
  if (t) t.innerHTML = Object.entries(pack.tons || {}).map(([k, v]) => opt(k, v, k === (salvo.tom || "direto"))).join("");
  const g = $("#rotGatilho");
  if (g) g.innerHTML = Object.entries(pack.gatilhos || {}).map(([k, v]) => opt(k, v, k === (salvo.gatilho || "auto"))).join("");
  if ($("#rotNicho") && salvo.nicho && !$("#rotNicho").value) $("#rotNicho").value = salvo.nicho;
}

async function loadRoteiroUi() {
  wireRoteiro();
  const pack = await api("/api/roteiro/chats");
  state.roteiro.pack = pack;
  state.roteiro.brandId = pack.brandId;
  state.roteiro.chats = pack.chats || [];
  if ($("#rotMarcaNome")) $("#rotMarcaNome").textContent = (pack.empresa && pack.empresa.nome) || "Marca";
  if ($("#rotEmpresaTexto") && pack.empresa) $("#rotEmpresaTexto").value = pack.empresa.empresa || "";
  rotMontarPerfilForm(pack.empresa || {});
  rotPreencherSelects(pack);
  rotRenderLista();
  // Sem perfil, a IA escreve no escuro: abre a caixa na primeira vez e
  // deixa o aviso aceso ate preencher (o 1o teste real saiu com "o usuario
  // ainda nao descreveu a empresa" no prompt).
  rotMarcarFalta(pack.empresa || {});
  if (state.roteiro.chatId) await rotAbrir(state.roteiro.chatId);
  else rotRenderMsgs(null);
}

function rotPerfilVazio(emp) {
  const p = emp.perfil || {};
  return !Object.values(p).some((v) => String(v || "").trim()) && !String(emp.empresa || "").trim();
}

function rotMarcarFalta(emp) {
  const falta = rotPerfilVazio(emp);
  const link = $("#rotEmpresaAbrir");
  if (!link) return;
  link.classList.toggle("rot-falta", falta);
  // 5.0.1: o perfil mora em Empresas; o link so leva ate la
  link.textContent = falta ? "Preencher o perfil da empresa (recomendado)" : "Ver o perfil da empresa";
}

/* Perfil com campos (4.99): um textarea curto por campo, rotulo e exemplo
 * vindos do servidor (a lista mora em app/roteiro.py, um lugar so). */
function rotMontarPerfilForm(emp) {
  const grid = $("#rotPerfilGrid");
  if (!grid) return;
  const campos = emp.campos || [];
  const valores = emp.perfil || {};
  grid.innerHTML = campos.map((c) => `
    <label class="ia-form rot-perfil-campo">${escapeHtml(c.rotulo)}
      <textarea rows="2" data-perfil="${escapeHtml(c.id)}" placeholder="${escapeHtml(c.exemplo || "")}">${escapeHtml(valores[c.id] || "")}</textarea>
    </label>`).join("");
}

function rotLerPerfilForm() {
  const out = {};
  document.querySelectorAll("#rotPerfilGrid [data-perfil]").forEach((ta) => {
    const v = (ta.value || "").trim();
    if (v) out[ta.dataset.perfil] = v;
  });
  return out;
}

function rotRenderLista() {
  const box = $("#rotChats");
  if (!box) return;
  const chats = state.roteiro.chats || [];
  if (!chats.length) {
    box.innerHTML = `<p class="hint">Nenhum roteiro ainda.</p>`;
    return;
  }
  box.innerHTML = chats.map((c) => `
    <div class="rot-chat${c.id === state.roteiro.chatId ? " on" : ""}">
      <button type="button" class="rot-chat-abrir" data-id="${escapeHtml(c.id)}" title="${escapeHtml(c.titulo)}">
        <span class="rot-chat-titulo">${escapeHtml(c.titulo)}</span>
        <span class="rot-chat-sub">${escapeHtml(fmtAccessUntil(c.atualizadoEm))} · ${Math.floor((c.mensagens || 0) / 2)} resposta(s)</span>
      </button>
      <button type="button" class="rot-chat-x" data-apagar="${escapeHtml(c.id)}" title="Apagar">×</button>
    </div>`).join("");
}

function rotRenderMsgs(chat) {
  const box = $("#rotMsgs");
  if (!box) return;
  const vazio = $("#rotVazio");
  const msgs = (chat && chat.mensagens) || [];
  box.querySelectorAll(".rot-msg").forEach((m) => m.remove());
  if (vazio) vazio.classList.toggle("hidden", msgs.length > 0);
  msgs.forEach((m, i) => {
    const el = document.createElement("div");
    el.className = `rot-msg rot-${m.role === "user" ? "eu" : "ia"}`;
    const texto = document.createElement("pre");
    texto.className = "rot-txt";
    texto.textContent = m.content || "";
    el.appendChild(texto);
    if (m.role === "assistant") {
      const acoes = document.createElement("div");
      acoes.className = "rot-acoes";
      acoes.innerHTML = `<button type="button" class="ghost-btn ghost-btn--sm" data-copiar="${i}">Copiar roteiro</button>
        <button type="button" class="ghost-btn ghost-btn--sm" data-copiar-ganchos="${i}">Copiar ganchos</button>
        <button type="button" class="ghost-btn ghost-btn--sm" data-refazer="${i}">Outra versão</button>
        <span class="hint">${m.backend === "groq" ? "via Groq" : "via sessão"}</span>`;
      el.appendChild(acoes);
    }
    box.appendChild(el);
  });
  box.scrollTop = box.scrollHeight;
}

const ROT_SECOES = ["GANCHOS", "ROTEIRO PARA GRAVAR", "CTA", "TEXTO NA TELA", "LEGENDA DO POST", "POR QUE PARA O SCROLL", "ÂNGULOS", "ANGULOS"];
function rotCabecalho(linha) {
  const cab = linha.trim().toUpperCase().replace(/:$/, "");
  return ROT_SECOES.find((s) => cab === s || cab.startsWith(s + " ") || cab.startsWith(s + "(")) || null;
}
function rotSecao(texto, nome) {
  const out = [];
  let dentro = false;
  for (const ln of String(texto || "").split("\n")) {
    const cab = rotCabecalho(ln);
    if (cab !== null) { if (dentro) break; dentro = cab === nome; continue; }
    if (dentro) out.push(ln);
  }
  return out.join("\n").trim();
}

async function rotCopiar(texto, rotulo) {
  try {
    await navigator.clipboard.writeText(texto);
    toast(`✓ ${rotulo} copiado`);
  } catch {
    toast("Não consegui copiar — selecione o texto e use Ctrl+C", 3500);
  }
}

async function rotAbrir(id) {
  try {
    const r = await api(`/api/roteiro/chat?id=${encodeURIComponent(id)}&brandId=${encodeURIComponent(state.roteiro.brandId || "")}`);
    state.roteiro.chatId = id;
    state.roteiro.chatAtual = r.chat;
    if (r.chat && r.chat.opcoes) {
      for (const [k, el] of [["estilo", "#rotEstilo"], ["duracao", "#rotDuracao"], ["objetivo", "#rotObjetivo"], ["tom", "#rotTom"], ["gatilho", "#rotGatilho"]]) {
        if (r.chat.opcoes[k] != null && $(el)) $(el).value = String(r.chat.opcoes[k]);
      }
      if ($("#rotNicho")) $("#rotNicho").value = r.chat.opcoes.nicho || "";
    }
    rotRenderLista();
    rotRenderMsgs(r.chat);
  } catch (e) {
    toast(e.message || "Não abri o roteiro");
  }
}

function rotPensando(ligar) {
  const box = $("#rotPensando");
  if (!box) return;
  box.classList.toggle("hidden", !ligar);
  clearInterval(state.roteiro._timer);
  if (ligar) {
    let i = 0;
    const txt = $("#rotPensandoTxt");
    if (txt) txt.textContent = ROT_FRASES[0];
    state.roteiro._timer = setInterval(() => {
      i = (i + 1) % ROT_FRASES.length;
      if (txt) txt.textContent = ROT_FRASES[i];
    }, 2200);
  }
}

async function rotEnviar(mensagemForcada) {
  if (state.roteiro.enviando) return;
  const ta = $("#rotTexto");
  const mensagem = (mensagemForcada || (ta && ta.value) || "").trim();
  if (!mensagem) { toast("Escreva sobre o que é o vídeo"); ta?.focus(); return; }
  state.roteiro.enviando = true;
  rotGuardarOpcoes();
  const btn = $("#rotEnviar");
  if (btn) btn.disabled = true;
  // a pergunta aparece na hora; a resposta chega com a animacao rodando
  const atual = state.roteiro.chatAtual || { mensagens: [] };
  const otimista = { ...atual, mensagens: [...(atual.mensagens || []), { role: "user", content: mensagem }] };
  rotRenderMsgs(otimista);
  rotPensando(true);
  if (ta && !mensagemForcada) ta.value = "";
  try {
    const r = await api("/api/roteiro/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        brandId: state.roteiro.brandId, id: state.roteiro.chatId,
        mensagem, opcoes: rotOpcoes(),
      }),
    });
    state.roteiro.chatId = r.chat.id;
    state.roteiro.chatAtual = r.chat;
    const lista = await api(`/api/roteiro/chats?brandId=${encodeURIComponent(state.roteiro.brandId || "")}`);
    state.roteiro.chats = lista.chats || [];
    rotRenderLista();
    rotRenderMsgs(r.chat);
  } catch (e) {
    rotRenderMsgs(state.roteiro.chatAtual || null);
    if (ta && !mensagemForcada && !ta.value) ta.value = mensagem;
    toast(e.message || "A IA não respondeu", 6000);
  } finally {
    rotPensando(false);
    state.roteiro.enviando = false;
    if (btn) btn.disabled = false;
  }
}

function wireRoteiro() {
  const view = $("#view-roteiro");
  if (!view || view.dataset.wired) return;
  view.dataset.wired = "1";
  $("#rotNovo")?.addEventListener("click", () => {
    state.roteiro.chatId = null;
    state.roteiro.chatAtual = null;
    rotRenderLista();
    rotRenderMsgs(null);
    $("#rotTexto")?.focus();
  });
  $("#rotEnviar")?.addEventListener("click", () => rotEnviar());
  $("#rotTexto")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); rotEnviar(); }
  });
  ["#rotEstilo", "#rotDuracao", "#rotObjetivo", "#rotTom", "#rotGatilho"].forEach((id) => $(id)?.addEventListener("change", rotGuardarOpcoes));
  $("#rotAtalhos")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-ideia]");
    if (!b) return;
    const ta = $("#rotTexto");
    if (ta) { ta.value = b.dataset.ideia; ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
  });
  $("#rotChats")?.addEventListener("click", async (e) => {
    const x = e.target.closest("[data-apagar]");
    if (x) {
      const id = x.dataset.apagar;
      const ok = await pedirConfirmacao("Apagar este roteiro?", "Some deste computador. Não dá para desfazer.", "Apagar", true);
      if (!ok) return;
      await api("/api/roteiro/apagar", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brandId: state.roteiro.brandId, id }) });
      if (state.roteiro.chatId === id) { state.roteiro.chatId = null; state.roteiro.chatAtual = null; rotRenderMsgs(null); }
      state.roteiro.chats = state.roteiro.chats.filter((c) => c.id !== id);
      rotRenderLista();
      return;
    }
    const a = e.target.closest("[data-id]");
    if (a) rotAbrir(a.dataset.id);
  });
  $("#rotMsgs")?.addEventListener("click", (e) => {
    const msgs = (state.roteiro.chatAtual && state.roteiro.chatAtual.mensagens) || [];
    const c = e.target.closest("[data-copiar]");
    if (c) { rotCopiar(msgs[Number(c.dataset.copiar)]?.content || "", "Roteiro"); return; }
    const g = e.target.closest("[data-copiar-ganchos]");
    if (g) {
      const txt = msgs[Number(g.dataset.copiarGanchos)]?.content || "";
      rotCopiar(rotSecao(txt, "GANCHOS") || txt, "Ganchos");
      return;
    }
    const r = e.target.closest("[data-refazer]");
    if (r) rotEnviar("Me dê outra versão, com ganchos diferentes e a mesma estrutura.");
  });
  $("#rotEmpresaAbrir")?.addEventListener("click", () => setView("presets"));
  // 5.0.1: o formulario mora na tela de Empresas e grava na empresa ATIVA
  $("#rotEmpresaSalvar")?.addEventListener("click", async () => {
    try {
      const bid = (state.brandActive && state.brandActive.id) || state.roteiro.brandId;
      const r = await api("/api/roteiro/empresa", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brandId: bid, perfil: rotLerPerfilForm(),
          texto: $("#rotEmpresaTexto")?.value || "" }) });
      toast(`✓ Perfil de ${r.nome} salvo — a IA passa a usar`);
      if (state.roteiro.pack) state.roteiro.pack.empresa = r;
      rotMarcarFalta(r);
      loadBrandsUi().catch(() => {});
    } catch (e) {
      toast(e.message || "Não salvei o perfil");
    }
  });
  // "Montar com meus videos": a IA le as falas dos ultimos videos desta
  // marca e devolve um RASCUNHO nos campos — nada e gravado ate Salvar.
  $("#rotPerfilDosVideos")?.addEventListener("click", async () => {
    const btn = $("#rotPerfilDosVideos");
    const st = $("#rotPerfilStatus");
    if (btn) btn.disabled = true;
    if (st) { st.hidden = false; st.classList.remove("hidden"); st.textContent = "Lendo as falas dos seus últimos vídeos…"; }
    try {
      const r = await api("/api/roteiro/perfil-dos-videos", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brandId: (state.brandActive && state.brandActive.id) || state.roteiro.brandId }) });
      const atual = rotLerPerfilForm();
      document.querySelectorAll("#rotPerfilGrid [data-perfil]").forEach((ta) => {
        const k = ta.dataset.perfil;
        // o que a pessoa ja escreveu fica; o rascunho preenche so o vazio
        if (!atual[k] && r.perfil[k]) ta.value = r.perfil[k];
      });
      const n = Object.keys(r.perfil || {}).length;
      if (st) st.textContent = `Rascunho a partir de ${r.videos} vídeo(s): ${n} campo(s) preenchidos. Corrija o que quiser e clique em Salvar perfil.`;
      toast("✓ Rascunho pronto — confira e salve");
    } catch (e) {
      if (st) st.textContent = e.message || "Não consegui montar o perfil";
      toast(e.message || "Não consegui montar o perfil", 5000);
    } finally {
      if (btn) btn.disabled = false;
    }
  });
}
