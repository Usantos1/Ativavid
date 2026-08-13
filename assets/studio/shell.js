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
        location.href = view === "import" ? "/" : `/?view=${encodeURIComponent(view)}`;
      });
    });
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
    if (!hint) return;
    try {
      const res = await fetch("/api/health");
      const h = await res.json();
      const ver = String(h.version || "?").replace(/^v/i, "");
      hint.textContent = `Versão sistema: ${ver}`;
    } catch {
      hint.textContent = "Versão sistema: —";
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

    const label = $("#tbVersionLabel");
    if (label) {
      try {
        const res = await fetch("/api/health");
        const h = await res.json();
        label.textContent = `v${String(h.version || "?").replace(/^v/i, "")}`;
      } catch {
        label.textContent = "v…";
      }
    }

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
    wireWindowChrome();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
