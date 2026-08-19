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
  pendingDuration: null,
  pendingRecommended: null,
  uploads: {},
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
  estilo: ["Estilos", "Como os vídeos da sua marca normalmente devem parecer."],
  keys: ["Chaves & IA", "Passo a passo da sessão + links para Groq, ElevenLabs e Pexels."],
  licenca: ["Licença", "Status da assinatura e contas."],
  sistema: ["Sistema", "Máquina, pastas, atualizações e diagnóstico."],
  // aliases antigos → redirecionados em setView
  ia: ["Chaves & IA", "Sessão do navegador e chaves de API."],
  doutor: ["Sistema", "Desempenho e pastas."],
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

function applyFailed(j) {
  const qa = j && j.quickApply;
  return !!(qa && qa.status === "failed");
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
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function goHome() {
  setView("import");
}

function setView(name) {
  if (name === "ia") name = "keys";
  if (name === "doutor") name = "sistema";
  state.view = name;
  $$(".sb-item[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$("[data-view-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.viewPanel !== name));
  const [title, sub] = VIEW_COPY[name] || ["ATIVAVID", ""];
  $("#wsTitle").textContent = title;
  $("#wsSub").textContent = sub;
  document.body.classList.toggle("view-estilo-on", name === "estilo");
  if (name === "keys") loadLlm().catch(() => {});
  if (name === "licenca") loadLicenca().catch((e) => toast(e.message));
  if (name === "sistema") {
    loadSistema().catch((e) => toast(e.message));
  }
  if (name === "estilo") {
    loadBrandsUi().catch(() => {});
    const fr = $("#estiloFrame");
    if (fr && !fr.dataset.loaded) {
      fr.dataset.loaded = "1";
      fr.onload = () => {
        const t = document.documentElement.getAttribute("data-theme") || "dark";
        applyThemeToIframes(t);
      };
      fr.src = estiloFrameSrc();
    } else {
      applyThemeToIframes(document.documentElement.getAttribute("data-theme") || "dark");
    }
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

function filterJobs(kind) {
  if (kind === "fila") {
    return state.jobs.filter(jobInFila);
  }
  if (kind === "done") {
    return state.jobs
      .filter((j) => j.status === "done")
      .sort((a, b) => jobRecency(b) - jobRecency(a) || String(b.id).localeCompare(String(a.id)));
  }
  return [...state.jobs]
    .sort((a, b) => jobRecency(b) - jobRecency(a) || String(b.id).localeCompare(String(a.id)))
    .slice(0, 8);
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

function cardSig(j, opts) {
  const links = jobLinks(j);
  const qa = j.quickApply || {};
  return [
    j.id, j.status, j.title || j.name, Math.round(Number(j.progress) || 0), j.hasFinal, j.hasThumb, j.finishedAt, j.finishedAtLabel,
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
  const dur = j.durationLabel || "";
  const metaBits = [dur, fmt].filter(Boolean);
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
  const menu = `<div class="pc-more" data-menu-host="${menuKey}">
      <button type="button" class="chip-btn ghostish pc-more-btn" data-act="menu" data-id="${safeId}" data-menu-key="${menuKey}" aria-label="Mais ações" aria-expanded="false" aria-haspopup="menu">⋯</button>
      <div class="pc-menu hidden" data-menu="${menuKey}" role="menu">
        <button type="button" role="menuitem" data-act="folder" data-id="${safeId}">Abrir pasta</button>
        <a role="menuitem" href="${escapeHtml(links.final)}" ${canFinal ? "" : "class=\"disabled\""}>Ver vídeo final</a>
        <a role="menuitem" href="${escapeHtml(editor)}">Editar</a>
        <a role="menuitem" href="${escapeHtml(estilo)}" data-id="${safeId}">Alterar estilo</a>
        ${(copy.badge === "ERRO" || copy.badge === "REVISAR" || j.detail)
          ? `<button type="button" role="menuitem" data-act="detail" data-id="${safeId}">Ver detalhe</button>`
          : ""}
        <button type="button" role="menuitem" class="danger" data-act="delete" data-id="${safeId}" data-name="${escapeHtml(title)}">Apagar</button>
      </div>
    </div>`;
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
      <div class="pc-top">
        <div class="pc-title-block">
          <button type="button" class="pc-name pc-name-btn" data-act="rename" data-id="${safeId}"
            data-title="${escapeHtml(title)}" title="Clique para renomear">${escapeHtml(title)}</button>
          ${metaBits.length ? `<div class="pc-when">${escapeHtml(metaBits.join(" · "))}</div>` : ""}
        </div>
        <span class="chip ${escapeHtml(tone)}">${escapeHtml(chipLabel)}</span>
      </div>
      ${headline ? `<div class="pc-msg">${escapeHtml(headline)}</div>` : ""}
      ${progress}
      <div class="pc-actions">
        ${primary}
        ${(() => { const s = stuckActionsHtml(j, safeId); return s ? `<span class="pc-stuck" data-stuck-sig="${escapeHtml(s)}">${s}</span>` : ""; })()}
        ${j.status === "done" ? `<button type="button" class="chip-btn ghostish" data-act="folder" data-id="${safeId}" title="Abrir a pasta publicar">Pasta</button>${j.legenda ? `<button type="button" class="chip-btn ghostish" data-act="copylegenda" data-id="${safeId}" title="Copiar a legenda do post">Legenda</button>` : ""}` : ""}
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
  if (copy.text) {
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
  $("#countFila").textContent = String(fila.length);
  $("#countDone").textContent = String(done.length);
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
  const meta = $("#queueMeta");
  if (meta) {
    const workView = ["import", "fila", "done"].includes(state.view);
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
  const locals = state.jobs.filter((j) => j.status === "importing" && String(j.id).startsWith("tmp-"));
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
    if (justOpened) loadAccessList().catch(() => {});
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
  else syncLicenseChrome();
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
  if (!dlg.open) dlg.showModal();
}

async function openUpdateDownload(lic) {
  const L = lic || state.license || {};
  const upd = L.update || {};
  let url = (upd.downloadUrl || "").trim();
  try {
    if (!url) {
      const check = await api("/api/update/check");
      url = (check.downloadUrl || check.releaseUrl || "").trim();
    }
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
  $("#licDlgHint").textContent = L.message || "Assine o plano anual ou cole a chave de ativação.";
  $("#licDlgPrice").textContent = L.priceLabel || "R$ 399 / ano";
  if (!dlg.open) dlg.showModal();
}

async function activateLicenseKey(key) {
  const res = await fetch("/api/license/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  const data = await res.json();
  if (!res.ok || !data.entitled) {
    throw new Error(data.message || data.error || "Chave inválida");
  }
  renderLicense(data);
  toast("Licença ativada");
  const dlg = $("#dlgLicense");
  if (dlg?.open) dlg.close();
  return data;
}

function openCheckout(url) {
  const u = url || state.license?.checkoutUrl;
  if (!u) {
    toast("Configure o Checkout URL em Sistema → Licença");
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

function probeVideoDuration(file) {
  return new Promise((resolve) => {
    try {
      const url = URL.createObjectURL(file);
      const v = document.createElement("video");
      v.preload = "metadata";
      v.onloadedmetadata = () => {
        const d = Number(v.duration);
        URL.revokeObjectURL(url);
        resolve(Number.isFinite(d) ? d : null);
      };
      v.onerror = () => {
        URL.revokeObjectURL(url);
        resolve(null);
      };
      v.src = url;
    } catch {
      resolve(null);
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
    const out = [];
    for (const it of items) {
      const entry = it.webkitGetAsEntry?.();
      if (entry) await collectEntry(entry, "", out);
      else {
        const f = it.getAsFile?.();
        if (f) out.push(f);
      }
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
  $("#btnPick").onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    input.click();
  };
  const btnFolder = $("#btnPickFolder");
  if (btnFolder && folderInput) {
    btnFolder.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      folderInput.click();
    };
  }
  zone.addEventListener("click", (e) => {
    if (e.target.closest("button")) return;
    input.click();
  });
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
  const anywhere = $("#dropAnywhere");
  if (anywhere) {
    let dragDepth = 0;
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
      dragDepth = 0;
      anywhere.classList.add("hidden");
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
      $("#dlgImport")?.close();
      try {
        await uploadFiles(files, collectImportIntent());
      } catch (err) {
        toast(err.message);
      } finally {
        state.pendingFiles = null;
      }
    };
  }
  const btnCancel = $("#btnImportCancel");
  if (btnCancel) {
    btnCancel.onclick = () => {
      state.pendingFiles = null;
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
  await api("/api/jobs/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  toast("Projeto foi para a Lixeira");
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
      if (act === "folder") {
        await api("/api/jobs/open-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
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
        markApplyAck(job && job.quickApply);
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
      try {
        await navigator.clipboard.writeText(text);
        toast("Log copiado");
      } catch {
        toast("Não consegui copiar");
      }
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
          <a class="chip-btn" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">Abrir site</a>
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

function applyAccountChrome(st) {
  const logged = !!st?.loggedIn;
  const email = st?.email || "";
  const name = logged ? displayNameFromEmail(email) : "Entrar";
  const licMeta = licenseSidebarMeta(state.license);
  const btn = $("#btnSbAccount");
  const avatar = $("#sbAccAvatar");
  const nameEl = $("#sbAccName");
  const metaEl = $("#sbAccMeta");
  if (nameEl) nameEl.textContent = logged ? name : "Entrar";
  if (metaEl) {
    metaEl.textContent = logged
      ? (st.isAdmin ? `Admin · ${licMeta.text}` : licMeta.text)
      : "Toque para entrar";
  }
  if (avatar) avatar.textContent = logged ? initialsFromEmail(email) : "?";
  if (btn) {
    btn.dataset.logged = logged ? "1" : "0";
    btn.dataset.tone = logged ? licMeta.tone : "neutral";
    btn.title = logged ? `${email} · ${licMeta.text}` : "Entrar na conta";
  }
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
    empty.hidden = false;
    table.hidden = true;
    empty.textContent = (data && (data.message || data.error)) || "Falha ao listar. Rode supabase/rpc_admin.sql se ainda não rodou.";
    return;
  }
  const rows = Array.isArray(data.access) ? data.access : [];
  if (!rows.length) {
    empty.hidden = false;
    table.hidden = true;
    empty.innerHTML = `Nenhuma conta ainda. <button type="button" class="export-btn export-btn--sm" id="btnLicAccountEmpty">Nova conta</button>`;
    const b = $("#btnLicAccountEmpty");
    if (b) b.onclick = () => openLicAccountDialog("");
    return;
  }
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
          const st = escapeHtml(r.status || "—");
          const until = escapeHtml(fmtAccessUntil(r.valid_until));
          const pcs = escapeHtml(String(r.max_devices ?? "—"));
          const rawEmail = String(r.email || "").replace(/"/g, "&quot;");
          const pending = r.user_id ? "" : " <span class=\"hint\">(sem login ainda)</span>";
          return `<tr class="access-row" data-email="${rawEmail}" title="Abrir para editar">
            <td title="${email}">${email}${pending}</td>
            <td><span class="access-st ${st}">${st}</span></td>
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

async function loadAccessList() {
  const empty = $("#adminAccessEmpty");
  const table = $("#adminAccessTable");
  const hasTable = !!(table && !table.hidden && table.querySelector("table"));
  // Evita piscar: só mostra "Carregando…" na 1ª carga (sem tabela ainda).
  if (empty && !hasTable) {
    empty.hidden = false;
    empty.textContent = "Carregando acessos…";
  }
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
  const btnSbAccount = $("#btnSbAccount");
  if (btnSbAccount) {
    btnSbAccount.onclick = () => {
      const st = state.auth || {};
      if (st.loggedIn) setView("licenca");
      else openLoginDialog();
    };
  }
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
        await api("/api/brands", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...preset,
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
  if ($("#exportPresetSelect") && active) {
    $("#exportPresetSelect").value = active.exportPreset || "reels";
  }
  if ($("#brandHint")) {
    const fmtNames = { reels: "Reels/Shorts", youtube: "YouTube 16:9", square: "Quadrado 1:1", feed: "Feed 4:5" };
    $("#brandHint").textContent = active
      ? `Os vídeos desta marca saem em ${fmtNames[active.exportPreset] || "Reels/Shorts"}. O estilo edita-se abaixo.`
      : "";
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
