const COOKIE_NAMES = ["SESSDATA", "bili_jct", "buvid3"];
const BILIBILI_URL = "https://www.bilibili.com";
const STORAGE_KEYS = ["serverUrl", "geminiKey"];

const urlEl       = document.getElementById("url");
const serverUrlEl = document.getElementById("server-url");
const geminiKeyEl = document.getElementById("gemini-key");
const fetchBtn    = document.getElementById("fetch-btn");
const errorEl     = document.getElementById("error");
const successEl   = document.getElementById("success");
const cookieDot   = document.getElementById("cookie-dot");
const cookieMsg   = document.getElementById("cookie-msg");

let cookies = {};
let currentTabUrl = "";

// ── Restore saved settings ──────────────────────────────────────────────────
chrome.storage.local.get(STORAGE_KEYS, (saved) => {
  if (saved.serverUrl) serverUrlEl.value = saved.serverUrl;
  if (saved.geminiKey) geminiKeyEl.value = saved.geminiKey;
});

[serverUrlEl, geminiKeyEl].forEach((el) => {
  el.addEventListener("input", () => {
    chrome.storage.local.set({
      serverUrl: serverUrlEl.value.trim(),
      geminiKey: geminiKeyEl.value.trim(),
    });
  });
});

// ── Get current tab URL and cookies ─────────────────────────────────────────
chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
  const tab = tabs[0];
  if (!tab?.url?.includes("bilibili.com/video")) {
    setCookieStatus(false, "Not a Bilibili video page.");
    urlEl.value = "";
    return;
  }

  currentTabUrl = tab.url;
  urlEl.value = tab.url;

  try {
    const results = await Promise.all(
      COOKIE_NAMES.map((name) =>
        chrome.cookies.get({ url: BILIBILI_URL, name })
      )
    );

    const missing = [];
    results.forEach((c, i) => {
      if (c?.value) {
        cookies[COOKIE_NAMES[i]] = c.value;
      } else {
        missing.push(COOKIE_NAMES[i]);
      }
    });

    if (missing.length === 0) {
      setCookieStatus(true, "Session cookies found ✓");
      fetchBtn.disabled = false;
    } else {
      setCookieStatus(false, `Missing cookies: ${missing.join(", ")} — are you logged in?`);
    }
  } catch (e) {
    setCookieStatus(false, `Cookie error: ${e.message}`);
  }
});

function setCookieStatus(ok, msg) {
  cookieDot.className = "dot " + (ok ? "ok" : "err");
  cookieMsg.textContent = msg;
}

// ── Fetch button ─────────────────────────────────────────────────────────────
fetchBtn.addEventListener("click", async () => {
  const serverUrl = serverUrlEl.value.trim().replace(/\/$/, "");
  if (!serverUrl) {
    showError("Please enter the server URL.");
    return;
  }

  showError("");
  showSuccess("");
  setLoading(true);

  try {
    const body = {
      url: currentTabUrl,
      sessdata: cookies["SESSDATA"] || "",
      bili_jct: cookies["bili_jct"] || "",
      buvid3:   cookies["buvid3"]   || "",
      gemini_api_key: geminiKeyEl.value.trim(),
    };

    const res = await fetch(`${serverUrl}/subtitles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await res.json();
    if (!res.ok) {
      showError(data.detail || "Server returned an error.");
      return;
    }

    // Store result and open the result page in a new tab
    chrome.storage.local.set({ subtitleResult: data }, () => {
      chrome.tabs.create({ url: chrome.runtime.getURL("result.html") });
      window.close();
    });
  } catch (e) {
    showError("Network error: " + e.message);
  } finally {
    setLoading(false);
  }
});

function setLoading(on) {
  fetchBtn.disabled = on;
  fetchBtn.innerHTML = on
    ? '<span class="spinner"></span>Fetching…'
    : "Fetch Subtitles &amp; Summary";
}

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.style.display = msg ? "block" : "none";
  if (msg) successEl.style.display = "none";
}

function showSuccess(msg) {
  successEl.textContent = msg;
  successEl.style.display = msg ? "block" : "none";
  if (msg) errorEl.style.display = "none";
}
