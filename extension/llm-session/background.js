/* Service worker — mantém a sessão viva sem precisar clicar no popup. */
importScripts("capture.js");

const A = globalThis.AtivaVidSession;
const ALARM = "ativavid-keepalive";

async function setBadge(ok) {
  try {
    await chrome.action.setBadgeBackgroundColor({ color: ok ? "#00c853" : "#666" });
    await chrome.action.setBadgeText({ text: ok ? "ON" : "" });
  } catch {
    /* ignore */
  }
}

async function tick() {
  try {
    const results = await A.captureAllKnown();
    const flushed = await A.flushPending();
    const anyOk = flushed || Object.values(results).some((r) => r && r.ok);
    const st = (await chrome.storage.local.get("status")).status || {};
    await setBadge(!!(anyOk || st.lastOkAt));
  } catch {
    /* ignore */
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(ALARM, { periodInMinutes: 2 });
  tick();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(ALARM, { periodInMinutes: 2 });
  tick();
});

chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === ALARM) tick();
});

// Ao visitar ChatGPT/Gemini logado, captura sozinho
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status !== "complete") return;
  const provider = A.providerFromUrl(tab.url || "");
  if (!provider) return;
  chrome.storage.local.get("lastAuto").then(async (bag) => {
    const last = bag.lastAuto || {};
    const now = Date.now();
    if (last[provider] && now - last[provider] < 20000) return;
    last[provider] = now;
    await chrome.storage.local.set({ lastAuto: last });
    await A.captureProvider(provider, { requireReady: true });
    await setBadge(true);
  }).catch(() => {});
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    if (msg?.type === "capture") {
      const out = await A.captureProvider(msg.provider, { requireReady: msg.requireReady !== false });
      sendResponse(out);
      return;
    }
    if (msg?.type === "status") {
      const st = (await chrome.storage.local.get(["status", "pending"])).status || {};
      const pending = (await chrome.storage.local.get("pending")).pending || {};
      sendResponse({ status: st, pending });
      return;
    }
    if (msg?.type === "flush") {
      await A.flushPending();
      await tick();
      sendResponse({ ok: true });
      return;
    }
    sendResponse({ ok: false });
  })().catch((e) => sendResponse({ ok: false, message: String(e.message || e) }));
  return true;
});

// Garante alarm após o worker acordar
chrome.alarms.get(ALARM).then((a) => {
  if (!a) chrome.alarms.create(ALARM, { periodInMinutes: 2 });
});
