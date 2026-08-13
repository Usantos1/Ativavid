/* Popup — manda o background capturar; mostra status persistido. */
const statusEl = document.getElementById("status");
const persistEl = document.getElementById("persist");

function setStatus(msg, err) {
  statusEl.textContent = msg;
  statusEl.className = err ? "err" : "";
}

async function refreshPersist() {
  try {
    const res = await chrome.runtime.sendMessage({ type: "status" });
    const st = res?.status || {};
    const lines = [];
    for (const id of ["chatgpt-web", "gemini-web", "claude-web", "deepseek-web"]) {
      const row = st[id];
      if (!row) continue;
      const name =
        id === "chatgpt-web" ? "ChatGPT"
          : id === "gemini-web" ? "Gemini"
            : id === "claude-web" ? "Claude" : "DeepSeek";
      if (row.ok) lines.push(`✓ ${name}: ${row.cookieCount || "?"} cookies`);
      else if (row.queued) lines.push(`… ${name}: na fila (abra o ATIVAVID)`);
    }
    if (st.lastError) lines.push(st.lastError);
    persistEl.textContent = lines.length
      ? lines.join("\n")
      : "Ainda sem captura. Abra o ChatGPT/Gemini logado — a extensão sincroniza sozinha.";
  } catch {
    persistEl.textContent = "Recarregue a extensão em chrome://extensions.";
  }
}

document.querySelectorAll("button[data-provider]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const provider = btn.dataset.provider;
    const url = btn.dataset.url;
    setStatus("Capturando…");
    try {
      // Garante aba do site
      if (url) {
        const base = url.replace(/\/$/, "");
        let tabs = [];
        try {
          tabs = await chrome.tabs.query({ url: [`${base}/*`, `${base}`] });
        } catch {
          tabs = [];
        }
        if (tabs.length) {
          try { await chrome.tabs.update(tabs[0].id, { active: true }); } catch { /* ignore */ }
        } else {
          await chrome.tabs.create({ url, active: true });
          setStatus("Abri o site — faça login, espere carregar; a extensão captura sozinha (ou clique de novo).", true);
          await refreshPersist();
          return;
        }
        await new Promise((r) => setTimeout(r, 350));
      }

      const out = await chrome.runtime.sendMessage({ type: "capture", provider });
      if (out?.ok) setStatus(out.message || "OK");
      else setStatus(out?.message || "Falha", true);
      await refreshPersist();
    } catch (e) {
      setStatus(String(e.message || e), true);
    }
  });
});

refreshPersist();
// Tenta descarregar fila se o app estiver aberto
chrome.runtime.sendMessage({ type: "flush" }).catch(() => {});
