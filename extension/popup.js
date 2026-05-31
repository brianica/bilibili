const COOKIE_NAMES = ["SESSDATA", "bili_jct", "buvid3"];
const BILIBILI_ORIGIN = "https://www.bilibili.com";

const serverUrlEl = document.getElementById("server-url");
const openBtn     = document.getElementById("open-btn");
const errorEl     = document.getElementById("error");
const cookieDot   = document.getElementById("cookie-dot");
const cookieMsg   = document.getElementById("cookie-msg");

let cookies = {};
let currentTabUrl = "";

// ── Restore saved server URL ─────────────────────────────────────────────────
chrome.storage.local.get(["serverUrl"], (saved) => {
  if (saved.serverUrl) serverUrlEl.value = saved.serverUrl;
});

serverUrlEl.addEventListener("input", () => {
  chrome.storage.local.set({ serverUrl: serverUrlEl.value.trim() });
});

// ── Read current tab URL + Bilibili cookies ──────────────────────────────────
chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
  const tab = tabs[0];
  if (!tab?.url?.includes("bilibili.com/video")) {
    setCookieStatus(false, "Not a Bilibili video page.");
    return;
  }

  currentTabUrl = tab.url;

  try {
    const results = await Promise.all(
      COOKIE_NAMES.map((name) => chrome.cookies.get({ url: BILIBILI_ORIGIN, name }))
    );

    const missing = [];
    results.forEach((c, i) => {
      if (c?.value) cookies[COOKIE_NAMES[i]] = c.value;
      else missing.push(COOKIE_NAMES[i]);
    });

    if (missing.length === 0) {
      setCookieStatus(true, "Session cookies found ✓");
      openBtn.disabled = false;
    } else {
      setCookieStatus(false, `Missing: ${missing.join(", ")} — are you logged in?`);
    }
  } catch (e) {
    setCookieStatus(false, `Cookie error: ${e.message}`);
  }
});

function setCookieStatus(ok, msg) {
  cookieDot.className = "dot " + (ok ? "ok" : "err");
  cookieMsg.textContent = msg;
}

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.style.display = msg ? "block" : "none";
}

// ── Open web app with prefilled data via URL fragment ────────────────────────
openBtn.addEventListener("click", () => {
  const serverUrl = serverUrlEl.value.trim().replace(/\/$/, "");
  if (!serverUrl) {
    showError("Please enter the web app URL.");
    return;
  }

  const payload = btoa(JSON.stringify({
    url:      currentTabUrl,
    sessdata: cookies["SESSDATA"]  || "",
    bili_jct: cookies["bili_jct"]  || "",
    buvid3:   cookies["buvid3"]    || "",
  }));

  chrome.tabs.create({ url: `${serverUrl}/#prefill=${payload}` });
  window.close();
});
