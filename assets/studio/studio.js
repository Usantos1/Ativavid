/* Hub shell: sidebar + previews + BYOK scaffold */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const state = {
  jobs: [],
  view: "import",
  pendingDeleteId: null,
};

const STATUS_LABEL = {
  queued: "Aguardando",
  processing: "Editando",
  done: "Concluído",
  needs_review: "Revisar",
  error: "Erro",
};

const VIEW_COPY = {
  import: ["Início", "Comece por aqui — arraste verticais 9:16 e edite em 1 clique."],
  fila: ["Fila", "Acompanhe a edição automática — a IA corta, legenda e prepara o final."],
  done: ["Concluídos", "Vídeos prontos para abrir, ajustar ou exportar."],
  estilo: ["Estilos", "Visual padrão da marca — a IA usa isso no corte e na Fase 2."],
  keys: ["Chaves & IA", "Passo a passo da sessão + links para Groq, ElevenLabs e Pexels."],
  licenca: ["Licença", "Status da assinatura, ativação de chave e conta ATIVAVID."],
  sistema: ["Sistema", "Desempenho, pastas, marcas e atualizações."],
  // aliases antigos → redirecionados em setView
  ia: ["Chaves & IA", "Sessão do navegador e chaves de API."],
  doutor: ["Sistema", "Desempenho e pastas."],
};

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast._tm);
  toast._tm = setTimeout(() => t.classList.add("hidden"), 2800);
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function looksTechnical(s) {
  return /cmd failed|traceback|exception|uv run|\\\\|\/helpers\/|render\.py/i.test(s);
}

function jobHeadline(j) {
  if (j.status === "processing") {
    return j.message || j.stageLabel || "Editando com IA…";
  }
  if (j.status === "queued") return j.message || "Aguardando na fila";
  if (j.status === "error") {
    if (/cancel/i.test(j.message || "") || j.reason === "cancelled") {
      return "Edição cancelada — pode reiniciar ou apagar";
    }
    return j.message || "Não foi possível concluir este vídeo";
  }
  if (j.status === "needs_review") return j.message || "Precisa de revisão";
  if (j.status === "done") {
    const sc = j.score && j.score.overall;
    return sc ? `Pronto · análise estrutural ${sc}/100` : (j.message || "Pronto para revisar");
  }
  const msg = (j.message || "").trim();
  if (msg && !looksTechnical(msg)) return msg;
  return STATUS_LABEL[j.status] || "";
}

function jobDetail(j) {
  const d = (j.detail || "").trim();
  const m = (j.message || "").trim();
  if (d && d !== m) return d;
  if (looksTechnical(m)) return m;
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
    const fr = $("#estiloFrame");
    if (fr && !fr.dataset.loaded) {
      fr.dataset.loaded = "1";
      fr.onload = () => {
        const t = document.documentElement.getAttribute("data-theme") || "dark";
        applyThemeToIframes(t);
      };
      fr.src = "/estilo-padrao?embed=1";
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

function filterJobs(kind) {
  if (kind === "fila") {
    return state.jobs.filter((j) => ["queued", "processing", "needs_review", "error"].includes(j.status));
  }
  if (kind === "done") return state.jobs.filter((j) => j.status === "done");
  return state.jobs.slice(0, 6); // recent
}

function cardHtml(j) {
  const canFinal = j.hasFinal || j.status === "done";
  const editor = j.editorUrl || "#";
  const estilo = j.estiloUrl || "#";
  const finalu = j.finalUrl || "#";
  const busy = j.status === "processing" || j.status === "queued";
  const headline = jobHeadline(j);
  const detail = jobDetail(j);
  const progress = (j.status === "processing" && j.progress != null)
    ? `<div class="pc-progress"><span style="width:${Math.max(5, Math.min(100, j.progress))}%"></span></div>`
    : "";
  const detailBlock = detail
    ? `<button type="button" class="pc-detail-btn" data-act="detail" data-id="${j.id}">Ver detalhes</button>`
    : "";
  const thumb = j.thumbUrl || `/api/jobs/${j.id}/thumb`;
  const chipLabel = j.stageLabel || STATUS_LABEL[j.status] || j.status;
  const footLeft = [];
  if (busy) {
    footLeft.push(`<button type="button" class="chip-btn" data-act="cancel" data-id="${j.id}">Cancelar</button>`);
    footLeft.push(`<button type="button" class="chip-btn" data-act="retry" data-id="${j.id}">Reiniciar</button>`);
  } else if (j.status === "needs_review" || j.status === "error") {
    footLeft.push(`<button type="button" class="chip-btn" data-act="retry" data-id="${j.id}">Tentar novamente</button>`);
  }
  return `<article class="project-card ${j.status}">
    <div class="pc-thumb">
      <div class="pc-thumb-fallback">9:16</div>
      <img src="${thumb}?t=${encodeURIComponent(j.updatedAt || j.id)}" alt="" loading="lazy"
        onload="this.previousElementSibling.style.display='none'"
        onerror="this.style.display='none'">
    </div>
    <div class="pc-body">
      <div class="pc-top">
        <div class="pc-name">${escapeHtml(j.name)}</div>
        <span class="chip ${j.status}">${escapeHtml(chipLabel)}</span>
      </div>
      <div class="pc-msg">${escapeHtml(headline)}</div>
      ${progress}
      ${detailBlock}
      <div class="pc-actions">
        <a class="chip-btn primary" href="${editor}">${j.status === "done" ? "Revisar" : "Abrir editor"}</a>
        <div class="pc-links">
          <a class="chip-btn" href="${estilo}">Estilo</a>
          <a class="chip-btn ${canFinal ? "" : "disabled"}" href="${canFinal ? finalu : "#"}">Final</a>
          <button type="button" class="chip-btn ghostish" data-act="folder" data-id="${j.id}">Pasta</button>
        </div>
      </div>
      <div class="pc-foot">
        <div class="pc-foot-left">${footLeft.join("")}</div>
        <button type="button" class="chip-btn danger-outline" data-act="delete" data-id="${j.id}"
          data-name="${escapeHtml(j.name)}" title="Apagar projeto e pasta">Apagar</button>
      </div>
    </div>
  </article>`;
}

function renderInto(boxId, emptyId, jobs) {
  const box = $(`#${boxId}`);
  if (!box) return;
  const empty = emptyId ? $(`#${emptyId}`) : null;
  if (!jobs.length) {
    box.innerHTML = "";
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  box.innerHTML = jobs.map(cardHtml).join("");
}

function renderJobs() {
  const fila = filterJobs("fila");
  const done = filterJobs("done");
  $("#countFila").textContent = String(fila.length);
  $("#countDone").textContent = String(done.length);

  const counts = state.jobs.reduce((a, j) => {
    a[j.status] = (a[j.status] || 0) + 1;
    return a;
  }, {});
  const meta = $("#queueMeta");
  if (meta) {
    const workView = ["import", "fila", "done"].includes(state.view);
    meta.hidden = !workView;
    meta.textContent = state.jobs.length
      ? Object.entries(counts).map(([k, v]) => `${v} ${STATUS_LABEL[k] || k}`).join(" · ")
      : "Nenhum projeto";
  }

  renderInto("jobListRecent", null, filterJobs("recent"));
  renderInto("jobListFila", "emptyFila", fila);
  renderInto("jobListDone", "emptyDone", done);
}

async function refreshJobs() {
  const data = await api("/api/jobs");
  state.jobs = data.jobs || [];
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

function renderLicense(lic) {
  const hint = $("#licenseHint");
  const device = $("#licenseDevice");
  const badge = $("#licenseBadge");
  const card = $("#licenseStatusCard");
  if (!hint) return;
  const mode = lic.mode || "open";
  const upd = lic.update || {};
  let badgeText = "—";
  let tone = "neutral";
  if (mode === "update_required" || upd.force) {
    hint.textContent = upd.message || lic.message || "Atualize o ATIVAVID para continuar.";
    badgeText = "Atualizar";
    tone = "bad";
  } else if (mode === "account") {
    const until = lic.validUntil ? String(lic.validUntil).slice(0, 10) : "—";
    const mail = lic.accountEmail || "";
    hint.textContent = `Conta ativa${mail ? " · " + mail : ""} · válida até ${until}.`;
    badgeText = "Conta";
    tone = "ok";
    if (upd.updateAvailable && !upd.force) {
      hint.textContent += ` · nova versão ${upd.latestVersion || ""} disponível.`;
    }
  } else if (mode === "open" || !lic.configured) {
    hint.textContent = "Modo aberto — configure o Supabase nesta página para ligar trial/licença.";
    badgeText = "Aberto";
    tone = "neutral";
  } else if (mode === "error") {
    hint.textContent = lic.message || lic.error || "Erro ao falar com o Supabase.";
    badgeText = "Erro";
    tone = "bad";
  } else if (mode === "trial") {
    hint.textContent = `Trial ativo · ${lic.trialDaysLeft ?? "?"} dia(s) restante(s) de ${lic.trialDaysTotal || 7}.`;
    badgeText = "Trial";
    tone = "warn";
  } else if (mode === "licensed") {
    const until = lic.validUntil ? String(lic.validUntil).slice(0, 10) : "—";
    hint.textContent = `Licença ativa${lic.licenseKeyHint ? " · " + lic.licenseKeyHint : ""} · válida até ${until}.`;
    badgeText = "Ativa";
    tone = "ok";
    if (upd.updateAvailable && !upd.force) {
      hint.textContent += ` · nova versão ${upd.latestVersion || ""} disponível.`;
    }
  } else {
    hint.textContent = lic.message || "Trial encerrado — ative uma chave ou assine.";
    badgeText = "Bloqueada";
    tone = "bad";
  }
  if (badge) badge.textContent = badgeText;
  if (card) card.dataset.tone = tone;
  if (device && lic.deviceId) {
    device.hidden = false;
    device.textContent = `Device: ${lic.deviceId}`;
  }
  state.license = lic;
  if (state.auth) applyAccountChrome(state.auth);
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

async function uploadFiles(fileList) {
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
  const fd = new FormData();
  for (const f of files) fd.append("files", f, f.name);
  toast(`Importando ${files.length}…`);
  const res = await fetch("/api/jobs", { method: "POST", body: fd });
  const data = await res.json();
  if (res.status === 403 && (data.error === "license_required" || data.error === "update_required")) {
    renderLicense(data.license || {});
    if (data.error === "update_required" || data.license?.update?.force) {
      openUpdateDialog(data.license);
      toast("Atualização obrigatória");
    } else {
      openLicenseDialog(data.license);
      toast("Licença necessária");
    }
    return;
  }
  if (!res.ok) throw new Error(data.error || "falha no upload");
  toast(`${(data.jobs || []).length} na fila — editando com IA`);
  setView("fila");
  await refreshJobs();
}

function wireDrop() {
  const zone = $("#dropZone");
  const input = $("#fileInput");
  $("#btnPick").onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    input.click();
  };
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
    uploadFiles(e.dataTransfer.files).catch((err) => toast(err.message));
  });
  input.addEventListener("change", () => {
    uploadFiles(input.files).catch((err) => toast(err.message));
    input.value = "";
  });
}

function showJobDetail(id) {
  const j = state.jobs.find((x) => x.id === id);
  if (!j) return;
  const text = jobDetail(j) || (j.message || "").trim() || "Sem detalhes técnicos.";
  const title = $("#detailTitle");
  const body = $("#detailBody");
  const dlg = $("#dlgJobDetail");
  if (!dlg || !body) return;
  if (title) title.textContent = j.name || "Detalhes do erro";
  body.textContent = text;
  try {
    dlg.showModal();
  } catch {
    toast(text.slice(0, 120));
  }
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
  toast("Projeto apagado");
  await refreshJobs();
}

function wireList() {
  document.addEventListener("click", async (e) => {
    const nav = e.target.closest("[data-view]");
    if (nav && nav.dataset.view) {
      e.preventDefault();
      setView(nav.dataset.view);
      return;
    }
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const id = btn.dataset.id;
    const act = btn.dataset.act;
    try {
      if (act === "folder") {
        await api("/api/jobs/open-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
      } else if (act === "retry") {
        await api("/api/jobs/retry", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        toast("De volta à fila");
        setView("fila");
        await refreshJobs();
      } else if (act === "cancel") {
        await api("/api/jobs/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        toast("Edição cancelada");
        await refreshJobs();
      } else if (act === "detail") {
        showJobDetail(id);
      } else if (act === "delete") {
        askDelete(id, btn.dataset.name || "");
      }
    } catch (err) {
      toast(err.message);
    }
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
  if (openBtn) openBtn.hidden = true;
  if (logoutBtn) logoutBtn.hidden = !logged;
  const label = $("#authEmailLabel");
  if (label) {
    if (logged) {
      label.textContent = st.isAdmin
        ? `Admin: ${email || "—"}`
        : (email || "—");
    } else {
      label.textContent = "Não logado — use Entrar na barra lateral.";
    }
  }
  const panel = $("#licenseAdminPanel");
  if (panel) {
    const show = !!(logged && st.isAdmin);
    panel.hidden = !show;
    if (show) loadAccessList().catch(() => {});
  }
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
    empty.textContent = "Nenhuma conta liberada ainda — use o formulário acima.";
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
          return `<tr>
            <td title="${email}">${email}</td>
            <td><span class="access-st ${st}">${st}</span></td>
            <td>${until}</td>
            <td>${pcs}</td>
            <td><button type="button" class="ghost-btn access-revoke" data-email="${rawEmail}">Revogar</button></td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
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
  if (empty) {
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
      toast("Perfil salvo");
      loadSistema().catch(() => {});
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
  if (btnLicAct) {
    btnLicAct.onclick = async () => {
      try {
        await activateLicenseKey(($("#licenseKeyInput")?.value || "").trim());
      } catch (e) {
        toast(e.message || "Falha ao ativar");
      }
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
        const patch = {};
        const srv = ($("#supabaseServiceInput")?.value || "").trim();
        if (!srv) {
          toast("Cole a service role (ou ela já está salva)");
          return;
        }
        patch.supabaseServiceRoleKey = srv;
        const res = await api("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        });
        if ($("#supabaseServiceInput")) $("#supabaseServiceInput").value = "";
        const hint = $("#adminServiceHint");
        if (hint) {
          hint.hidden = false;
          hint.textContent = "Service role já salva neste PC (deixe em branco para manter).";
        }
        adminOut(res.settings ? { ok: true, hasServiceRole: !!res.settings.hasServiceRole } : res);
        toast("Service role salva");
      } catch (e) {
        toast(e.message || "Falha ao salvar");
      }
    };
  }
  $$("#adminDayPresets [data-days]").forEach((btn) => {
    btn.onclick = () => {
      if ($("#adminLicDays")) $("#adminLicDays").value = btn.dataset.days || "7";
    };
  });
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
        if (data.ok) await loadAccessList();
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
        if (data.ok) await loadAccessList();
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
  if (state.auth && state.auth.isAdmin) {
    await loadAccessList().catch(() => {});
  }
}

function applySistemaData(data) {
  const hint = $("#sysMachineHint");
  const m = data.machine || {};
  const perf = data.performance || {};
  const s = data.settings || {};
  if (hint) {
    const base =
      `${m.os || "?"} ${m.osRelease || ""} · ${m.cores || "?"} núcleos · RAM ${m.ramGb ?? "?"} GB · `
      + `encoder ${(m.accel && m.accel.preferredEncoder) || "libx264"} · disco ${m.diskFreeGb ?? "?"} GB`;
    hint.textContent = m.error ? `${base} (aviso: ${m.error})` : base;
  }
  if ($("#sysPerfHint")) {
    $("#sysPerfHint").textContent =
      `Perfil ${perf.label || "—"} · jobs=${perf.parallelJobs} · proxy=${perf.proxyEnabled ? perf.proxyHeight + "p" : "off"}`;
  }
  if ($("#sysMetricProfile")) $("#sysMetricProfile").textContent = perf.label || "—";
  if ($("#sysMetricJobs")) $("#sysMetricJobs").textContent = String(perf.parallelJobs ?? "—");
  if ($("#sysMetricProxy")) {
    $("#sysMetricProxy").textContent = perf.proxyEnabled ? `${perf.proxyHeight}p` : "off";
  }
  if ($("#perfProfile") && s.performanceProfile) $("#perfProfile").value = s.performanceProfile || "auto";
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
      srvHint.textContent = "Service role já salva neste PC (deixe em branco para manter).";
    } else {
      srvHint.hidden = true;
    }
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
    $("#brandHint").textContent = active
      ? `Ativa: ${active.name || active.id} · export ${active.exportPreset || "reels"}`
      : "";
  }
  try {
    const lib = await api("/api/library");
    if ($("#libraryHint")) {
      $("#libraryHint").textContent =
        `Biblioteca: ${lib.items?.length || 0} arquivo(s) em ${lib.root || "%USERPROFILE%\\\\ATIVAVID\\\\Biblioteca"}`;
    }
  } catch {
    if ($("#libraryHint")) $("#libraryHint").textContent = "Biblioteca: —";
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
  list.textContent = jobs.map((j) => j.name || j.id).join(", ");
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
      fr.src = "/estilo-padrao?embed=1&t=" + Date.now();
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
  setInterval(() => {
    refreshJobs().catch(() => {});
    refreshHealth().catch(() => {});
  }, 2500);
}

boot();
