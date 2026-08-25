/* Hub shell: sidebar + previews + BYOK scaffold */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const state = {
  jobs: [],
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
  libraryRoot: "",
  presetBrandId: "padrao",
};

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
  marca: ["Marca", "Qual marca está ativa e o que define a identidade dela."],
  biblioteca: ["Biblioteca", "Arquivos reutilizáveis que a IA pode usar nos vídeos."],
  presets: ["Presets", "Combinações salvas de estilo e formato, prontas para reusar."],
  ia: ["IA", "A inteligência que corta, escreve e legenda — sessão do navegador e modelo."],
  integracoes: ["Integrações", "Serviços externos que o pipeline chama: transcrição, voz e b-roll."],
  licenca: ["Licença", "Status da assinatura e contas."],
  sistema: ["Configurações", "Máquina, pastas, atualizações e diagnóstico."],
  // aliases antigos → redirecionados em setView (links salvos continuam abrindo)
  keys: ["IA", "Sessão do navegador e chaves de API."],
  doutor: ["Configurações", "Desempenho e pastas."],
};

function toast(msg, ms) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
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
      return { badge: "REVISAR", text: "Falta o texto da marca em Estilos (card final)" };
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

async function api(path, opts) {
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
  if (name === "doutor") name = "sistema";
  state.view = name;
  $$(".sb-item[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$("[data-view-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.viewPanel !== name));
  const [title, sub] = VIEW_COPY[name] || ["ATIVAVID", ""];
  $("#wsTitle").textContent = title;
  $("#wsSub").textContent = sub;
  document.body.classList.toggle("view-estilo-on", name === "estilo");
  if (name === "ia") loadLlm().catch(() => {});
  if (name === "integracoes") refreshHealth().catch(() => {});
  if (name === "licenca") loadLicenca().catch((e) => toast(e.message));
  if (name === "sistema") {
    loadSistema().catch((e) => toast(e.message));
  }
  if (name === "marca") loadBrandsUi().catch(() => {});
  if (name === "biblioteca") loadLibraryUi().catch(() => {});
  if (name === "presets") loadPresetsUi().catch(() => {});
  if (name === "estilo") {
    loadBrandsUi().catch(() => {});
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

function estiloFrameSrc() {
  const id = ($("#brandSelect") && $("#brandSelect").value) || "";
  const q = new URLSearchParams({ embed: "1" });
  if (id) q.set("brandId", id);
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

function filterJobs(kind) {
  if (kind === "fila") {
    return state.jobs.filter(jobInFila);
  }
  if (kind === "done") {
    return state.jobs.filter((j) => j.status === "done").sort(byRecency);
  }
  if (kind === "projetos") {
    // Projetos é o acervo: TODO trabalho que ainda existe em disco, em
    // qualquer estado. A Fila e os Concluídos são recortes disto.
    const f = state.projFilter || "todos";
    const busca = (state.projBusca || "").trim().toLowerCase();
    return state.jobs
      .filter((j) => {
        if (f === "ativos") return jobInFila(j) && j.status !== "error";
        if (f === "prontos") return j.status === "done";
        if (f === "parados") return j.status === "error" || j.status === "needs_review";
        return true;
      })
      .filter((j) => !busca
        || String(j.name || "").toLowerCase().includes(busca)
        || jobFolderName(j).toLowerCase().includes(busca))
      .sort(byRecency);
  }
  return [...state.jobs].sort(byRecency).slice(0, 8);
}

function jobFolderName(j) {
  const raw = String(j.projectDir || j.editDir || j.name || j.id || "").replace(/[\\/]+$/, "");
  const parts = raw.split(/[/\\]/).filter(Boolean);
  return parts[parts.length - 1] || String(j.id || "");
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
  // Nota (nao erro): o plano veio do Groq porque as sessoes web cairam.
  if (j.iaNota) linhas.push(["IA", j.iaNota]);
  const ini = String(j.startedAtLabel || j.createdAtLabel || "");
  const fin = String(j.finishedAtLabel || "");
  if (ini) linhas.push(["Início", ini]);
  if (fin) linhas.push(["Final", fin]);
  if (!linhas.length) return "";
  return `<dl class="pc-ficha">${linhas.map(([k, v]) =>
    `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`).join("")}</dl>`;
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
  const links = jobLinks(j);
  const qa = j.quickApply || {};
  return [
    j.id, j.status, j.title || j.name, Math.round(Number(j.progress) || 0), j.hasFinal, j.hasThumb, j.finishedAt, j.finishedAtLabel,
    j.startedAtLabel || "", j.durationSec || "", j.sourceDurationSec || "", j.legenda ? "L" : "",
    j.styleLabel || "",
    j.iaAviso || "",
    j.modoLabel || "",
    j.corteResumo || "",
    j.iaNota || "",
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
        ${j.legenda ? `<button type="button" role="menuitem" data-act="copylegenda" data-id="${safeId}">Copiar legenda do post</button>` : ""}
        <a role="menuitem" href="${escapeHtml(links.final)}" ${canFinal ? "" : "class=\"disabled\""}>Ver vídeo final</a>
        <a role="menuitem" href="${escapeHtml(links.editor)}">Editar</a>
        <a role="menuitem" href="${escapeHtml(links.estilo)}" data-id="${safeId}">Alterar estilo</a>
        ${j.status === "done" ? `<button type="button" role="menuitem" data-act="retry" data-id="${safeId}">Tentar novamente</button>` : ""}
        ${(copy.badge === "ERRO" || copy.badge === "REVISAR" || j.detail)
          ? `<button type="button" role="menuitem" data-act="detail" data-id="${safeId}">Ver detalhe</button>`
          : ""}
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
      <div class="pc-thumb-fallback${thumb ? "" : " skeleton"}">9:16</div>
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

function renderInto(boxId, emptyId, jobs, opts) {
  const box = $(`#${boxId}`);
  if (!box) return;
  const empty = emptyId ? $(`#${emptyId}`) : null;
  const sig = jobs.map((j) => cardSig(j, opts)).join("\n");
  if (!jobs.length) {
    if (box.dataset.cardSig === "empty") return;
    closeCardMenus(box);
    box.innerHTML = "";
    box.dataset.cardSig = "empty";
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  if (box.dataset.cardSig === sig) return;
  syncCards(box, jobs, opts);
  box.dataset.cardSig = sig;
}

function syncCards(box, jobs, opts) {
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

function renderJobs() {
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
  }

  const counts = state.jobs.reduce((a, j) => {
    a[j.status] = (a[j.status] || 0) + 1;
    return a;
  }, {});
  setCount("#countProjetos", state.jobs.length);
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
  renderInto("jobListRecent", null, filterJobs("recent"), { compact: true, view: "recent" });
  renderInto("jobListFila", "emptyFila", fila, { view: "fila" });
  renderInto("jobListDone", "emptyDone", done, { view: "done" });
  if (state.view === "projetos") {
    renderInto("jobListProjetos", "emptyProjetos", filterJobs("projetos"), { view: "projetos" });
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
  host.innerHTML = `<div class="home-now-title">Agora</div>` + actives.slice(0, 3).map((j) => `
    <div class="home-now-row" data-id="${escapeHtml(j.id)}">
      <div class="home-now-name">${escapeHtml(displayTitle(j))}</div>
      <div class="home-now-stage">${escapeHtml(j.message || "Processando…")}</div>
      ${cardProgressHtml(j)}
    </div>`).join("") + (actives.length > 3
      ? `<button type="button" class="ghost-btn home-now-more" data-view="fila">+${actives.length - 3} na fila</button>`
      : "");
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
  const showKey = !isAdmin && (needsPay || lic.mode === "trial" || lic.mode === "blocked" || (!lic.entitled && lic.configured));

  const panel = $("#licenseAdminPanel");
  if (panel) {
    const justOpened = isAdmin && panel.hidden;
    panel.hidden = !isAdmin;
    if (justOpened) {
      loadAccessList().catch(() => {});
      loadDeviceList().catch(() => {});
    }
  }
  const pay = $("#licAccountStrip");
  if (pay) pay.hidden = !needsPay;
  const clientKey = $("#licClientKeyCard");
  if (clientKey) clientKey.hidden = !showKey;
  if (needsPay) {
    const title = $("#licPayTitle");
    const hint = $("#licPayHint");
    if (title) title.textContent = lic.priceLabel || "Assinatura anual";
    if (hint) {
      hint.textContent = lic.message || "Assine ou ative uma chave neste PC.";
    }
  }
}

function renderLicense(lic) {
  const hint = $("#licenseHint");
  const device = $("#licenseDevice");
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
  } else if (mode === "open" || !lic.configured) {
    title = "Modo aberto — licença não exigida neste PC.";
    badgeText = "Aberto";
    tone = "neutral";
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
  if (device) {
    device.hidden = true;
    device.textContent = "";
  }
  const advDev = $("#licAdvDeviceHint");
  if (advDev && lic.deviceId) {
    advDev.hidden = false;
    advDev.textContent = `Este PC: ${lic.deviceId}`;
  }
  const deviceInput = $("#adminDeviceId");
  if (deviceInput && lic.deviceId && !deviceInput.value) {
    deviceInput.placeholder = lic.deviceId;
  }
  state.license = lic;
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

function openUpdateDialog(lic) {
  const dlg = $("#dlgUpdate");
  if (!dlg) return;
  const L = lic || state.license || {};
  const upd = L.update || {};
  const title = $("#updDlgTitle");
  const hint = $("#updDlgHint");
  const meta = $("#updDlgMeta");
  if (title) {
    title.textContent = upd.force ? "Atualização obrigatória" : "Nova versão disponível";
  }
  if (hint) {
    hint.textContent = upd.message || L.message || "Baixe o instalador e atualize o ATIVAVID.";
  }
  if (meta) {
    const cur = L.appVersion || upd.appVersion || "";
    const latest = upd.latestVersion || "";
    meta.textContent = [cur && `Atual: v${String(cur).replace(/^v/i, "")}`, latest && `Nova: v${String(latest).replace(/^v/i, "")}`]
      .filter(Boolean)
      .join(" · ") || "";
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
  $("#licDlgTitle").textContent = L.mode === "blocked" ? "Ative o ATIVAVID" : "Licença";
  $("#licDlgHint").textContent = L.message || "Entre com a conta liberada, assine o plano anual ou cole a chave.";
  $("#licDlgPrice").textContent = L.priceLabel || "R$ 399 / ano";
  // Sem checkout configurado, "Assinar agora" so levava a um toast de erro.
  const pay = $("#btnLicDlgPay");
  if (pay) pay.hidden = !L.checkoutUrl;
  // Ja logado nao precisa da saida de login.
  const login = $("#btnLicDlgLogin");
  if (login) login.hidden = !!state.auth?.loggedIn;
  if (!dlg.open) dlg.showModal();
}

async function activateLicenseKey(key) {
  const res = await fetch("/api/license/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  const data = await res.json();
  if (!res.ok || (!data.entitled && !data.activated)) {
    throw new Error(data.message || data.error || "Chave inválida");
  }
  renderLicense(data);
  const dlg = $("#dlgLicense");
  if (dlg?.open) dlg.close();
  if (!data.entitled && data.activated) {
    // Chave aceita, mas a build está abaixo da versão mínima.
    toast(data.message || "Chave ativada neste PC. Atualize o ATIVAVID para usar.");
    openUpdateDialog(data);
    return data;
  }
  toast("Licença ativada");
  return data;
}

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

function collectImportIntent() {
  const mode = document.querySelector(".intent-card.on")?.dataset.intent || "dynamic";
  // "viral" é um pacote da UI: intenção dinâmica + tipo de conteúdo viral
  const realMode = mode === "viral" ? "dynamic" : mode;
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
    brandId: $("#brandSelect")?.value || null,
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
  // o card Viral também define o tipo de conteúdo — um clique, o pacote todo
  if (mode === "viral" && $("#importContentType")) $("#importContentType").value = "viral";
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
      reject(new Error("falha no upload"));
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
  // Arrastar arquivo para QUALQUER lugar da janela abre a importação — o
  // overlay dá o alvo gigante; sem ele o usuário tinha que acertar o card.
  const anywhere = overlayArraste;
  if (anywhere) {
    window.addEventListener("dragenter", (e) => {
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
      if (act === "folder") {
        await api("/api/jobs/open-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
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
  window.addEventListener("resize", closeCardMenus);
  window.addEventListener("scroll", closeCardMenus, true);

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
  const nome = marca.name || "Meu workspace";
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
    menu.classList.toggle("hidden", !abrir);
    btn.setAttribute("aria-expanded", abrir ? "true" : "false");
  });
  menu.addEventListener("click", async (e) => {
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
    if (acao === "empresa") return setView("marca");
    if (acao === "licenca") return setView("licenca");
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
          const pcs = escapeHtml(String(r.max_devices ?? "—"));
          const rawEmail = String(r.email || "").replace(/"/g, "&quot;");
          const pending = r.user_id ? "" : " <span class=\"hint\">(sem login ainda)</span>";
          return `<tr class="access-row" data-email="${rawEmail}" title="Abrir para editar">
            <td title="${email}">${email}${pending}</td>
            <td><span class="access-st ${st}">${stLabel}</span></td>
            <td>${until}</td>
            <td>${pcs}</td>
            <td><button type="button" class="ghost-btn access-revoke" data-email="${rawEmail}">Revogar</button></td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
  table.querySelectorAll(".access-row").forEach((row) => {
    row.onclick = (ev) => {
      if (ev.target.closest(".access-revoke")) return;
      const email = row.getAttribute("data-email") || "";
      openLicAccountDialog(email);
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
          const dono = escapeHtml(r.account_email || r.label || "—");
          const seg = id.replace(/"/g, "&quot;");
          return `<tr class="access-row">
            <td class="mono" title="${escapeHtml(id)}">${escapeHtml(idCurto)}</td>
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
  btn.textContent = tem ? "Baixar atualização" : "Baixar última versão";
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
    const el = ($("#keyEl")?.value || "").trim();
    const px = ($("#keyPx")?.value || "").trim();
    if (g) body.GROQ_API_KEY = g;
    if (el) body.ELEVENLABS_API_KEY = el;
    if (px) body.PEXELS_API_KEY = px;
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
      if (res.keys?.ELEVENLABS_API_KEY) ok.push("ElevenLabs");
      if (res.keys?.PEXELS_API_KEY) ok.push("Pexels");
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
      const el = ($("#keyEl")?.value || "").trim();
      const px = ($("#keyPx")?.value || "").trim();
      if (service === "groq" && g) body.GROQ_API_KEY = g;
      if (service === "elevenlabs" && el) body.ELEVENLABS_API_KEY = el;
      if (service === "pexels" && px) body.PEXELS_API_KEY = px;
      try {
        const res = await api("/api/keys/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        $("#keysStatus").textContent = res.ok ? `${service}: OK` : `${service}: falhou`;
        toast(res.ok ? `${service} OK` : `${service} falhou`);
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
  const btnLicAct = $("#btnLicenseActivate");
  const activateFromInput = async () => {
    try {
      await activateLicenseKey(($("#licenseKeyInput")?.value || "").trim());
    } catch (e) {
      toast(e.message || "Falha ao ativar");
    }
  };
  if (btnLicAct) {
    btnLicAct.onclick = () => {
      const card = $("#licClientKeyCard");
      if (card && !card.hidden) {
        $("#licenseKeyInput")?.focus();
        return activateFromInput();
      }
      return activateFromInput();
    };
  }
  const btnLicActInline = $("#btnLicenseActivateInline");
  if (btnLicActInline) btnLicActInline.onclick = activateFromInput;
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
  const btnLicPay = $("#btnLicenseCheckout");
  if (btnLicPay) {
    btnLicPay.onclick = () => openCheckout();
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
          if ($("#licenseKeyInput")) $("#licenseKeyInput").value = data.licenseKey;
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
  const btnDlgAct = $("#btnLicDlgActivate");
  if (btnDlgAct) {
    btnDlgAct.onclick = async () => {
      try {
        await activateLicenseKey(($("#licDlgKey")?.value || "").trim());
      } catch (e) {
        toast(e.message || "Falha ao ativar");
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
      openLoginDialog("login");
    };
  }
  const btnDlgPay = $("#btnLicDlgPay");
  if (btnDlgPay) btnDlgPay.onclick = () => openCheckout();
  const btnDlgLater = $("#btnLicDlgLater");
  if (btnDlgLater) {
    btnDlgLater.onclick = () => {
      const dlg = $("#dlgLicense");
      if (dlg?.open) dlg.close();
    };
  }
  const btnUpdNow = $("#btnUpdDownload");
  if (btnUpdNow) {
    btnUpdNow.onclick = () => openUpdateDownload(state.license);
  }
  const btnUpdLater = $("#btnUpdLater");
  if (btnUpdLater) {
    btnUpdLater.onclick = () => {
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
  const btnUpdateOpen = $("#btnUpdateOpen");
  if (btnUpdateOpen) {
    btnUpdateOpen.onclick = async () => {
      const check = await api("/api/update/check").catch(() => ({}));
      const url =
        check.downloadUrl ||
        check.releaseUrl ||
        "https://github.com/Usantos1/Ativavid/releases/latest";
      const res = await api("/api/update/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "release", url }),
      });
      toast(res.ok ? "Abrindo download…" : (res.error || "Não abriu"));
    };
  }
  const btnBrandAct = $("#btnBrandActivate");
  if (btnBrandAct) {
    btnBrandAct.onclick = async () => {
      try {
        const id = $("#brandSelect").value;
        if (!id) {
          toast("Escolha uma marca na lista");
          return;
        }
        await api("/api/brands", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "activate", id }),
        });
        toast("Marca ativada");
        await loadBrandsUi();
        const fr = $("#estiloFrame");
        if (fr) {
          fr.dataset.loaded = "1";
          fr.src = estiloFrameSrc();
        }
      } catch (e) {
        toast(e.message || "Falha ao ativar marca");
      }
    };
  }
  const btnBrandSave = $("#btnBrandSave");
  if (btnBrandSave) {
    btnBrandSave.onclick = async () => {
      try {
        const name = ($("#brandNewName").value || "").trim();
        if (!name) {
          toast("Digite o nome da marca");
          $("#brandNewName")?.focus();
          return;
        }
        const exportPreset = $("#exportPresetSelect").value || "reels";
        const preset = await api("/api/preset");
        // `/api/preset` devolve o estilo da marca ATIVA — inclusive o brandId
        // dela. Mandar isso num "criar marca NOVA" fazia o servidor gravar por
        // cima da marca ativa: o nome digitado apenas a renomeava, a antiga
        // sumia e nenhuma nova nascia. Aqui o estilo vai, a identidade nao.
        const { brandId: _bid, id: _id, brandName: _bn, ...estilo } = preset || {};
        await api("/api/brands", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...estilo,
            brandName: name,
            exportPreset,
            activate: true,
          }),
        });
        toast("Marca salva e ativada");
        $("#brandNewName").value = "";
        await loadBrandsUi();
      } catch (e) {
        toast(e.message || "Falha ao salvar marca");
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

async function runDoutor() {
  const out = $("#doutorOut");
  if (!out) return;
  out.innerHTML = "<p class='hint'>Verificando…</p>";
  const data = await api("/api/doutor");
  const itens = data.itens || [];
  out.innerHTML = itens
    .map((it) => {
      const nivel = it.nivel || "ok";
      const mark = nivel === "ok" ? "ok" : nivel === "aviso" ? "aviso" : "bloqueio";
      return `<div class="item ${mark}">
        <div class="t">${escapeHtml(it.titulo || nivel)}</div>
        <div class="d">${escapeHtml(it.detalhe || "")}</div>
        ${it.solucao ? `<div class="s">${escapeHtml(it.solucao)}</div>` : ""}
      </div>`;
    })
    .join("") || "<p class='hint'>Sem itens.</p>";
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
  loadHardwareCard().catch(() => {});
  if ($("#projectsRootHint") && m.projectsRoot) {
    $("#projectsRootHint").textContent = m.projectsRoot || "";
  }
  if ($("#projectsRootInput") && !$("#projectsRootInput").value) {
    $("#projectsRootInput").value = s.projectsRoot || m.projectsRoot || "";
  }
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

async function loadSistema() {
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

async function loadImportPresets() {
  const sel = $("#importPresetSelect");
  const hint = $("#importPresetHint");
  if (!sel) return;
  try {
    const pack = await api("/api/brand-presets");
    const presets = pack.presets || [];
    const activeId = pack.activeId || (pack.active && pack.active.id);
    sel.innerHTML = presets.map((p) =>
      `<option value="${escapeHtml(p.id)}" ${p.id === activeId ? "selected" : ""}>${escapeHtml(p.name || p.id)}</option>`
    ).join("") || `<option value="">Padrão</option>`;
    const cur = presets.find((p) => p.id === sel.value) || pack.active || presets[0];
    if (hint) hint.textContent = cur ? `Usar: ${cur.name}` : "Usar: padrão da marca";
    if (cur && cur.contentType && $("#importContentType")) {
      $("#importContentType").value = cur.contentType;
    }
    sel.onchange = () => {
      const p = presets.find((x) => x.id === sel.value);
      if (hint) hint.textContent = p ? `Usar: ${p.name}` : "Usar: padrão da marca";
      if (p && p.contentType && $("#importContentType")) {
        $("#importContentType").value = p.contentType;
      }
    };
  } catch {
    if (hint) hint.textContent = "Usar: padrão da marca";
  }
}

async function loadBrandsUi() {
  const data = await api("/api/brands");
  const sel = $("#brandSelect");
  if (!sel) return;
  const brands = data.brands || [];
  sel.innerHTML = brands.map((b) =>
    `<option value="${escapeHtml(b.id)}" ${b.active ? "selected" : ""}>${escapeHtml(b.name || b.id)}</option>`
  ).join("") || `<option value="padrao">Padrão</option>`;
  const active = brands.find((b) => b.active) || brands[0];
  state.brandActive = active || null;
  renderWorkspaceCard();
  if ($("#exportPresetSelect") && active) {
    $("#exportPresetSelect").value = active.exportPreset || "reels";
  }
  const fmtNames = { reels: "Reels/Shorts", youtube: "YouTube 16:9", square: "Quadrado 1:1", feed: "Feed 4:5" };
  const formato = fmtNames[active && active.exportPreset] || "Reels/Shorts";
  if ($("#brandHint")) {
    $("#brandHint").textContent = active ? `Sai em ${formato}.` : "";
  }
  if ($("#brandHintMarca")) {
    $("#brandHintMarca").textContent = active
      ? `Os vídeos desta marca saem em ${formato}. O estilo edita-se em Estilos.`
      : "";
  }
  if ($("#estiloBrandName")) $("#estiloBrandName").textContent = (active && active.name) || "Padrão";
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

/**
 * Biblioteca. O acervo já existia (/api/library alimenta o b-roll da IA),
 * mas só aparecia como um botão "abrir pasta" perdido dentro de Estilos —
 * aqui ele ganha tela própria. Nada de backend novo.
 */
async function loadLibraryUi() {
  const grid = $("#libraryGrid");
  if (!grid) return;
  let lib = { items: [], root: "" };
  try {
    lib = await api("/api/library");
  } catch {
    grid.innerHTML = "";
    $("#libraryHint").textContent = "A biblioteca não respondeu.";
    falhaDaTela("libraryEmpty",
      "Não deu para ler a biblioteca — o ATIVAVID pode estar iniciando ou ter sido fechado.",
      loadLibraryUi);
    return;
  }
  state.libraryRoot = lib.root || "";
  const itens = lib.items || [];
  const empty = $("#libraryEmpty");
  if (empty) empty.classList.toggle("hidden", itens.length > 0);
  const hint = $("#libraryHint");
  if (hint) {
    const imgs = itens.filter((i) => i.kind === "image").length;
    const clips = itens.length - imgs;
    hint.textContent = itens.length
      ? `${imgs} imagem(ns)${clips ? ` e ${clips} clipe(s)` : ""} · a IA usa como b-roll`
      : "Coloque fotos dos seus produtos aqui para a IA usar como b-roll.";
  }
  grid.innerHTML = itens.map((it) => {
    const src = `/api/library/file?rel=${encodeURIComponent(it.rel)}`;
    const kb = it.bytes > 1048576
      ? `${(it.bytes / 1048576).toFixed(1)} MB`
      : `${Math.max(1, Math.round(it.bytes / 1024))} KB`;
    const midia = it.kind === "clip"
      ? `<video class="lib-thumb" src="${src}" muted preload="metadata"></video>`
      : `<img class="lib-thumb" src="${src}" alt="" loading="lazy">`;
    return `<figure class="lib-item" title="${escapeHtml(it.name)}">
      ${midia}
      <figcaption><span class="lib-name">${escapeHtml(it.name)}</span><span class="lib-size">${kb}</span></figcaption>
    </figure>`;
  }).join("");
}

/**
 * Presets. O backend (/api/brand-presets) já fazia criar/renomear/duplicar/
 * apagar/definir padrão — só era alcançável pelo seletor da tela de importar.
 */
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
    const marca = pack.brandName || (state.brandActive && state.brandActive.name) || "Padrão";
    hint.textContent = presets.length
      ? `${presets.length} preset(s) da marca ${marca}. O marcado como padrão é o que a importação usa.`
      : `Nenhum preset salvo para a marca ${marca}. Crie um a partir de um estilo aberto.`;
  }
  lista.innerHTML = presets.map((p) => {
    const on = p.id === activeId;
    const tipo = p.contentType ? escapeHtml(p.contentType) : "—";
    return `<article class="preset-row${on ? " on" : ""}" data-preset="${escapeHtml(p.id)}">
      <div class="preset-main">
        <strong class="preset-name">${escapeHtml(p.name || p.id)}</strong>
        <span class="preset-meta">${tipo}${on ? " · padrão da marca" : ""}</span>
      </div>
      <div class="preset-acts">
        ${on ? "" : `<button type="button" class="ghost-btn ghost-btn--sm" data-preset-act="default">Usar como padrão</button>`}
        <button type="button" class="ghost-btn ghost-btn--sm" data-preset-act="duplicate">Duplicar</button>
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

function wirePresets() {
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
          if (!confirm("Apagar este preset?")) return;
          await presetAction("delete", { id });
          toast("Preset apagado");
        } else if (act === "rename") {
          const atual = row.querySelector(".preset-name")?.textContent || "";
          const nome = prompt("Novo nome do preset:", atual);
          if (!nome || !nome.trim()) return;
          await presetAction("rename", { id, name: nome.trim() });
          toast("Preset renomeado");
        } else if (act === "duplicate") {
          const atual = row.querySelector(".preset-name")?.textContent || "Preset";
          await presetAction("duplicate", { id, name: `${atual} (cópia)` });
          toast("Preset duplicado");
        } else if (act === "default") {
          await presetAction("default", { id });
          toast("Preset virou o padrão da marca");
        }
      } catch (err) {
        toast(err.message || "Não deu para aplicar");
      }
    });
  }
}

function wireBiblioteca() {
  const btn = $("#btnLibraryUpload");
  const input = $("#libraryFileInput");
  if (!btn || !input || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.onclick = () => input.click();
  input.onchange = async () => {
    const files = [...(input.files || [])];
    if (!files.length) return;
    let ok = 0;
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f, f.name);
      try {
        const res = await fetch("/api/library/upload", { method: "POST", body: fd });
        if (res.ok) ok += 1;
      } catch { /* segue para o próximo */ }
    }
    input.value = "";
    toast(ok ? `${ok} arquivo(s) na biblioteca` : "Nada foi enviado");
    await loadLibraryUi().catch(() => {});
  };
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
          try {
            await fetch("/api/update/open", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ url: up.downloadUrl || up.releaseUrl || "" }),
            });
          } catch { /* ignore */ }
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
  wireBiblioteca();
  wireTheme();
  await wireTitlebar();
  window.addEventListener("message", (e) => {
    if (!e.data || e.data.type !== "ativavid-house-style-saved") return;
    toast("Estilo padrão salvo");
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
