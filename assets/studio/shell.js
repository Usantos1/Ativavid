/* Shared hub shell wiring for editor pages (preview). */
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

  if (document.documentElement.classList.contains("hub-embed")) return;
  syncCollapse();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      wireCollapse();
      wireNav();
      refreshHint();
    });
  } else {
    wireCollapse();
    wireNav();
    refreshHint();
  }
})();
