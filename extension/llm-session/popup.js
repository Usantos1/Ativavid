/* Capture cookies for the user's own LLM web session → ATIVAVID local. */
const HOSTS = {
  "gemini-web": ["gemini.google.com", ".google.com", "google.com", ".gemini.google.com"],
  "chatgpt-web": ["chatgpt.com", ".chatgpt.com", "chat.openai.com", ".openai.com", "openai.com"],
  "claude-web": ["claude.ai", ".claude.ai"],
  "deepseek-web": ["chat.deepseek.com", ".deepseek.com", "deepseek.com"],
};

const URLS = {
  "gemini-web": [
    "https://gemini.google.com/",
    "https://gemini.google.com/app",
    "https://accounts.google.com/",
  ],
  "chatgpt-web": [
    "https://chatgpt.com/",
    "https://chatgpt.com/c",
    "https://chat.openai.com/",
  ],
  "claude-web": ["https://claude.ai/", "https://claude.ai/chats"],
  "deepseek-web": ["https://chat.deepseek.com/"],
};

const statusEl = document.getElementById("status");

function setStatus(msg, err) {
  statusEl.textContent = msg;
  statusEl.className = err ? "err" : "";
}

function pushCookie(out, seen, c) {
  const key = `${c.domain || ""}|${c.path || ""}|${c.name}|${c.partitionKey?.topLevelSite || ""}`;
  if (seen.has(key)) return;
  seen.add(key);
  out.push({
    name: c.name,
    value: c.value,
    domain: c.domain,
    path: c.path,
    secure: c.secure,
    httpOnly: c.httpOnly,
    expirationDate: c.expirationDate,
    sameSite: c.sameSite,
    partitionKey: c.partitionKey || undefined,
  });
}

async function cookieStores() {
  try {
    return await chrome.cookies.getAllCookieStores();
  } catch {
    return [{ id: undefined }];
  }
}

/**
 * Chrome 119+: sem partitionKey={}, getAll por URL/domain NÃO devolve cookies
 * particionados (CHIPS). Por URL + partitionKey ainda filtra mal — use domain.
 */
async function collectCookies(provider) {
  const domains = HOSTS[provider] || [];
  const urls = URLS[provider] || [];
  const seen = new Set();
  const out = [];
  const stores = await cookieStores();

  for (const store of stores) {
    const storeId = store.id;
    for (const domain of domains) {
      const queries = [
        { domain, storeId },
        { domain, storeId, partitionKey: {} },
      ];
      for (const q of queries) {
        try {
          const list = await chrome.cookies.getAll(q);
          for (const c of list) pushCookie(out, seen, c);
        } catch {
          /* ignore */
        }
      }
    }
    // Fallback URL (cookies nao particionados / stores legados)
    for (const url of urls) {
      try {
        const list = await chrome.cookies.getAll({ url, storeId });
        for (const c of list) pushCookie(out, seen, c);
      } catch {
        /* ignore */
      }
    }
  }
  return out;
}

function sessionLooksReady(provider, cookies) {
  const names = new Set(cookies.map((c) => c.name));
  if (provider === "gemini-web") {
    return (
      names.has("__Secure-1PSID") ||
      names.has("__Secure-1PSIDTS") ||
      names.has("__Secure-3PSID") ||
      names.has("__Secure-3PSIDTS") ||
      names.has("SID") ||
      names.has("HSID") ||
      names.has("SAPISID")
    );
  }
  if (provider === "chatgpt-web") {
    if (names.has("__Secure-next-auth.session-token")) return true;
    if ([...names].some((n) => n.startsWith("__Secure-next-auth.session-token."))) return true;
    if (names.has("oai-did") && (names.has("__Secure-next-auth.session-token") || names.has("cf_clearance"))) {
      return true;
    }
    // sessao nova: access token via cookie rotativo
    return [...names].some((n) => /session-token|access.?token|auth/i.test(n) && n.includes("Secure"));
  }
  return cookies.length > 0;
}

function authCookieHint(provider, cookies) {
  const names = cookies.map((c) => c.name);
  const interesting = names.filter((n) =>
    /psid|sid|session|auth|sapisid|token|oai/i.test(n),
  );
  if (!interesting.length) return `${cookies.length} cookies (nenhum de login óbvio)`;
  return `${cookies.length} cookies · ${interesting.slice(0, 6).join(", ")}`;
}

async function sendCapture(provider, cookies) {
  const res = await fetch("http://127.0.0.1:4850/api/llm-proxy/capture", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider,
      cookies,
      meta: {
        source: "ativavid-extension",
        version: "0.1.1",
        at: new Date().toISOString(),
      },
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function ensureLoggedTab(url) {
  if (!url) return true;
  const base = url.replace(/\/$/, "");
  let tabs = [];
  try {
    tabs = await chrome.tabs.query({ url: [`${base}/*`, `${base}`] });
  } catch {
    tabs = [];
  }
  if (tabs.length) {
    // Foca a aba logada — ajuda cookies do store certo
    try {
      await chrome.tabs.update(tabs[0].id, { active: true });
    } catch {
      /* ignore */
    }
    return true;
  }
  await chrome.tabs.create({ url, active: true });
  return false;
}

document.querySelectorAll("button[data-provider]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const provider = btn.dataset.provider;
    const url = btn.dataset.url;
    setStatus("Capturando…");
    try {
      const readyTab = await ensureLoggedTab(url);
      if (!readyTab) {
        setStatus("Abri o site — faça login, espere carregar e clique Capturar de novo.", true);
        return;
      }
      // Pequena pausa: cookies particionados às vezes só aparecem após a aba ativar
      await new Promise((r) => setTimeout(r, 350));

      const cookies = await collectCookies(provider);
      if (!cookies.length) {
        setStatus("Nenhum cookie — abra o site logado no Chrome/Edge desta extensão.", true);
        return;
      }
      if (!sessionLooksReady(provider, cookies)) {
        setStatus(
          `Incompleto: ${authCookieHint(provider, cookies)}. Abra logado e capture de novo.`,
          true,
        );
        await sendCapture(provider, cookies);
        return;
      }
      const saved = await sendCapture(provider, cookies);
      setStatus(`OK · ${saved.cookieCount} cookies → ATIVAVID (${authCookieHint(provider, cookies)})`);
    } catch (e) {
      setStatus(
        String(e.message || e).includes("Failed to fetch")
          ? "ATIVAVID não está aberto em 127.0.0.1:4850 — abra o app primeiro"
          : String(e.message || e),
        true,
      );
    }
  });
});
