/* Shared capture logic — used by background + popup */
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

const SITE_URL = {
  "gemini-web": "https://gemini.google.com/app",
  "chatgpt-web": "https://chatgpt.com",
  "claude-web": "https://claude.ai",
  "deepseek-web": "https://chat.deepseek.com",
};

const CAPTURE_URL = "http://127.0.0.1:4850/api/llm-proxy/capture";
const EXT_VERSION = "0.1.3";

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
    if (names.has("oai-did") && names.has("cf_clearance")) return true;
    return [...names].some((n) => /session-token|access.?token|auth/i.test(n) && n.includes("Secure"));
  }
  return cookies.length > 0;
}

function authCookieHint(provider, cookies) {
  const names = cookies.map((c) => c.name);
  const interesting = names.filter((n) => /psid|sid|session|auth|sapisid|token|oai/i.test(n));
  if (!interesting.length) return `${cookies.length} cookies`;
  return `${cookies.length} cookies · ${interesting.slice(0, 6).join(", ")}`;
}

async function sendCapture(provider, cookies) {
  const res = await fetch(CAPTURE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider,
      cookies,
      meta: {
        source: "ativavid-extension",
        version: EXT_VERSION,
        at: new Date().toISOString(),
      },
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function saveLocalStatus(patch) {
  const cur = (await chrome.storage.local.get("status")).status || {};
  const next = { ...cur, ...patch, updatedAt: Date.now() };
  await chrome.storage.local.set({ status: next });
  return next;
}

async function queuePending(provider, cookies) {
  const pending = (await chrome.storage.local.get("pending")).pending || {};
  pending[provider] = {
    cookies,
    at: Date.now(),
    ready: sessionLooksReady(provider, cookies),
  };
  await chrome.storage.local.set({ pending });
}

async function flushPending() {
  const pending = (await chrome.storage.local.get("pending")).pending || {};
  const left = {};
  for (const [provider, pack] of Object.entries(pending)) {
    try {
      const saved = await sendCapture(provider, pack.cookies || []);
      await saveLocalStatus({
        [provider]: {
          ok: true,
          cookieCount: saved.cookieCount,
          at: new Date().toISOString(),
          hint: authCookieHint(provider, pack.cookies || []),
        },
        lastError: null,
      });
    } catch {
      left[provider] = pack;
    }
  }
  await chrome.storage.local.set({ pending: left });
  return Object.keys(left).length === 0;
}

/**
 * Captura um provedor. Se o ATIVAVID estiver fechado, guarda na fila e
 * reenvia quando o app voltar (alarms).
 */
async function captureProvider(provider, { requireReady = true } = {}) {
  const cookies = await collectCookies(provider);
  if (!cookies.length) {
    return { ok: false, error: "sem_cookies", message: "Nenhum cookie — abra o site logado." };
  }
  const ready = sessionLooksReady(provider, cookies);
  if (requireReady && !ready) {
    await queuePending(provider, cookies);
    return {
      ok: false,
      error: "incompleto",
      message: `Sessão incompleta: ${authCookieHint(provider, cookies)}`,
      cookieCount: cookies.length,
    };
  }
  try {
    const saved = await sendCapture(provider, cookies);
    await saveLocalStatus({
      [provider]: {
        ok: true,
        cookieCount: saved.cookieCount,
        at: new Date().toISOString(),
        hint: authCookieHint(provider, cookies),
      },
      lastError: null,
      lastOkAt: Date.now(),
    });
    // limpa fila desse provedor
    const pending = (await chrome.storage.local.get("pending")).pending || {};
    delete pending[provider];
    await chrome.storage.local.set({ pending });
    return {
      ok: true,
      cookieCount: saved.cookieCount,
      message: `OK · ${saved.cookieCount} cookies → ATIVAVID`,
      hint: authCookieHint(provider, cookies),
    };
  } catch (e) {
    await queuePending(provider, cookies);
    const msg = String(e.message || e);
    const offline = /Failed to fetch|NetworkError|fetch/i.test(msg);
    await saveLocalStatus({
      lastError: offline
        ? "ATIVAVID fechado — cookies guardados; reenvio automático ao abrir o app"
        : msg,
      [provider]: {
        ok: false,
        queued: true,
        cookieCount: cookies.length,
        at: new Date().toISOString(),
        hint: authCookieHint(provider, cookies),
      },
    });
    return {
      ok: false,
      queued: true,
      error: offline ? "app_offline" : "send_failed",
      message: offline
        ? "ATIVAVID fechado — guardei a sessão; assim que abrir o app, reenvio sozinho"
        : msg,
      cookieCount: cookies.length,
    };
  }
}

async function captureAllKnown() {
  const results = {};
  for (const provider of Object.keys(HOSTS)) {
    // Só tenta se já houver cookies (usuário visitou o site)
    const cookies = await collectCookies(provider);
    if (!cookies.length || !sessionLooksReady(provider, cookies)) continue;
    results[provider] = await captureProvider(provider, { requireReady: true });
  }
  await flushPending();
  return results;
}

function providerFromUrl(url) {
  if (!url) return null;
  try {
    const h = new URL(url).hostname;
    if (h.includes("chatgpt.com") || h.includes("openai.com")) return "chatgpt-web";
    if (h.includes("gemini.google") || h === "google.com") return "gemini-web";
    if (h.includes("claude.ai")) return "claude-web";
    if (h.includes("deepseek.com")) return "deepseek-web";
  } catch {
    /* ignore */
  }
  return null;
}

// Export for importScripts / ES modules via global in service worker + popup
if (typeof globalThis !== "undefined") {
  globalThis.AtivaVidSession = {
    HOSTS,
    URLS,
    SITE_URL,
    EXT_VERSION,
    collectCookies,
    sessionLooksReady,
    authCookieHint,
    sendCapture,
    captureProvider,
    captureAllKnown,
    flushPending,
    saveLocalStatus,
    providerFromUrl,
  };
}
