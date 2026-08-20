/* Shared hub shell wiring for editor pages (preview) + window chrome. */
(function () {
  const $ = (s, el = document) => el.querySelector(s);

  function setCollapsed(on) {
    document.body.classList.toggle("sb-collapsed", !!on);
    try {
      localStorage.setItem("ativavid-sb-collapsed", on ? "1" : "0");
    } catch { /* ignore */ }
  }

  function wireCollapse() {
    const btn = $("#btnSidebar");
    if (btn) {
      btn.addEventListener("click", () => setCollapsed(true));
    }
  }

  function syncCollapse() {
    try {
      setCollapsed(localStorage.getItem("ativavid-sb-collapsed") === "1");
    } catch { /* ignore */ }
  }

  function wireNav() {
    document.querySelectorAll("[data-hub-view]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const view = btn.getAttribute("data-hub-view") || "import";
        const target = view === "import" ? "/" : `/?view=${encodeURIComponent(view)}`;
        (window.top || window).location.href = target;
      });
    });
    const ws = $("#btnWorkspace");
    if (ws) {
      // Na página de edição o card do workspace é um atalho: leva para a
      // tela de Marca no hub, onde ele é interativo de verdade.
      ws.addEventListener("click", (e) => {
        e.preventDefault();
        (window.top || window).location.href = "/?view=marca";
      });
    }
    const home = $("#btnHome");
    if (home) {
      home.addEventListener("click", (e) => {
        e.preventDefault();
        if (document.body.classList.contains("sb-collapsed")) {
          setCollapsed(false);
          return;
        }
        location.href = "/";
      });
    }
  }

  async function refreshHint() {
    const hint = $("#sbHint");
    const label = $("#tbVersionLabel");
    try {
      const res = await fetch("/api/health", { cache: "no-store" });
      const h = await res.json();
      const ver = String(h.version || "?").replace(/^v/i, "");
      if (hint) hint.textContent = `Versão sistema: ${ver}`;
      if (label) label.textContent = `v${ver}`;
    } catch {
      if (hint) hint.textContent = "Versão sistema: —";
    }
  }

  /** Nome do workspace = marca ativa. Mesma leitura do hub, sem estado. */
  async function refreshWorkspace() {
    const nameEl = $("#wsName");
    if (!nameEl) return;
    try {
      const res = await fetch("/api/brands", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const brands = Array.isArray(data.brands) ? data.brands : [];
      const active = brands.find((b) => b.active) || brands[0];
      if (!active) return;
      nameEl.textContent = active.name || "Meu workspace";
      const txt = $("#wsAvatarTxt");
      if (txt) {
        const partes = String(active.name || "AV").trim().split(/[\s._-]+/).filter(Boolean);
        txt.textContent = (partes.length >= 2
          ? partes[0][0] + partes[1][0]
          : String(active.name || "AV").slice(0, 2)).toUpperCase();
      }
      const av = $("#wsAvatar");
      if (av && active.accent) av.style.setProperty("--ws-tint", active.accent);
    } catch { /* sem marca: fica o rótulo padrão */ }
  }

  async function refreshJobCounts() {
    const filaEl = $("#countFila");
    const doneEl = $("#countDone");
    if (!filaEl && !doneEl) return;
    try {
      const res = await fetch("/api/jobs", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const jobs = Array.isArray(data.jobs) ? data.jobs : [];
      const fila = jobs.filter((j) => {
        if (["queued", "processing", "needs_review", "error", "importing"].includes(j.status)) return true;
        const qa = j.quickApply;
        return !!(qa && ["queued", "running", "failed"].includes(qa.status));
      }).length;
      const done = jobs.filter((j) => j.status === "done").length;
      if (filaEl) filaEl.textContent = String(fila);
      if (doneEl) doneEl.textContent = String(done);
      return fila;
    } catch {
      /* ignore — hub poll continues */
    }
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

  async function wireWindowChrome() {
    if (!$("#titlebar") || !$("#btnWinMin")) return;
    document.body.classList.add("desktop-app");

    // Versão: refreshHint() (e o poll do hub) mantém titlebar + sidebar iguais
    await refreshHint();

    const cfg = $("#btnTbConfig");
    if (cfg && !cfg.dataset.wired) {
      cfg.dataset.wired = "1";
      cfg.onclick = () => {
        location.href = "/?view=sistema";
      };
    }

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

  if (document.documentElement.classList.contains("hub-embed")) return;
  syncCollapse();
  const boot = () => {
    wireCollapse();
    wireNav();
    refreshHint();
    refreshWorkspace();
    refreshJobCounts();
    wireWindowChrome();
    // SSE: os contadores acordam por evento; o intervalo vira watchdog e só
    // corre rápido quando há fila ativa (/api/jobs varre o disco no servidor).
    let sseOk = false;
    let lastTick = Date.now();
    let lastFila = 1;
    const tick = () => {
      lastTick = Date.now();
      refreshJobCounts().then((n) => { if (typeof n === "number") lastFila = n; }).catch(() => {});
      refreshHint().catch(() => {});
    };
    try {
      const es = new EventSource("/api/events");
      es.onopen = () => { sseOk = true; };
      es.onerror = () => { sseOk = false; };
      es.addEventListener("tick", () => { if (!document.hidden) tick(); });
    } catch { sseOk = false; }
    setInterval(() => {
      if (document.hidden) return;
      if (sseOk && lastFila === 0 && Date.now() - lastTick < 20000) return;
      tick();
    }, 2500);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) tick();
    });
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
