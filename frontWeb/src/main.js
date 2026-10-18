import { interpretShortenResponse, safeHttpUrl } from "./client.js";
import { clearRecent, loadRecent, rememberLink } from "./storage.js";
import { validateLongUrl } from "./validate.js";

const config = window.SHORTLINK_CONFIG || { apiBaseUrl: "" };
const form = document.querySelector("#shorten-form");
const input = document.querySelector("#long-url");
const expiry = document.querySelector("#expiry");
const submitButton = document.querySelector("#submit-button");
const errorEl = document.querySelector("#url-error");
const statusEl = document.querySelector("#status");
const result = document.querySelector("#result");
const resultTitle = document.querySelector("#result-title");
const shortUrlEl = document.querySelector("#short-url");
const openLink = document.querySelector("#open-link");
const destinationEl = document.querySelector("#destination");
const expiryNote = document.querySelector("#expiry-note");
const copyButton = document.querySelector("#copy-button");
const againButton = document.querySelector("#again-button");
const recent = document.querySelector("#recent");
const recentList = document.querySelector("#recent-list");
const clearButton = document.querySelector("#clear-recent");

let inFlight = false;
let copyTimer = 0;

form.addEventListener("submit", onSubmit);
input.addEventListener("blur", onBlur);
input.addEventListener("input", onInput);
copyButton.addEventListener("click", onCopy);
againButton.addEventListener("click", () => {
  input.focus();
  input.select();
});
clearButton.addEventListener("click", () => {
  try {
    clearRecent(localStorage);
    renderRecent();
  } catch {
    recent.hidden = true;
  }
});
try {
  renderRecent();
} catch {
  recent.hidden = true;
}

async function onSubmit(event) {
  event.preventDefault();
  if (inFlight) {
    return;
  }
  const validation = validateLongUrl(input.value);
  if (!validation.ok) {
    showError(validation.message);
    setStatus("");
    input.focus();
    return;
  }
  clearError();
  hideResult();
  const payload = { long_url: validation.url };
  if (expiry.value) {
    payload.expires_in_days = Number(expiry.value);
  }

  inFlight = true;
  submitButton.disabled = true;
  submitButton.textContent = "Shortening";
  form.setAttribute("aria-busy", "true");
  setStatus("Shortening link.");

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(apiUrl("/shorten"), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await readJson(response);
    const interpreted = interpretShortenResponse(response.status, data);
    if (!interpreted.ok) {
      showError(interpreted.message);
      setStatus("");
      input.focus();
      return;
    }
    showSuccess(interpreted);
    try {
      rememberLink(
        {
          shortUrl: interpreted.shortUrl,
          longUrl: interpreted.longUrl,
          createdAt: interpreted.createdAt,
          expiresAt: interpreted.expiresAt,
        },
        localStorage,
      );
      renderRecent();
    } catch {
      // History is optional. A blocked storage API should not fail the shorten action.
    }
  } catch (error) {
    showError(
      error && error.name === "AbortError"
        ? "The request timed out. Try again."
        : "Couldn't reach the shortener. Check your connection and try again.",
    );
    setStatus("");
  } finally {
    window.clearTimeout(timer);
    inFlight = false;
    submitButton.disabled = false;
    submitButton.textContent = "Shorten";
    form.removeAttribute("aria-busy");
  }
}

function onBlur() {
  if (!input.value.trim()) {
    clearError();
    return;
  }
  const validation = validateLongUrl(input.value);
  if (!validation.ok) {
    showError(validation.message);
  } else {
    clearError();
  }
}

function onInput() {
  if (input.getAttribute("aria-invalid") !== "true") {
    return;
  }
  const validation = validateLongUrl(input.value);
  if (validation.ok || !input.value.trim()) {
    clearError();
    return;
  }
  showError(validation.message);
}

async function onCopy() {
  const text = shortUrlEl.textContent || "";
  const copied = await copyText(text);
  if (copied) {
    copyButton.textContent = "Copied";
    setStatus("Copied the short link.");
    window.clearTimeout(copyTimer);
    copyTimer = window.setTimeout(() => {
      copyButton.textContent = "Copy";
    }, 2000);
    return;
  }
  selectContents(shortUrlEl);
  copyButton.textContent = "Copy";
  setStatus("Couldn't copy automatically. The short link is selected.", { visible: true });
}

function showSuccess(interpreted) {
  result.hidden = false;
  shortUrlEl.textContent = interpreted.shortUrl;
  openLink.href = interpreted.shortUrl;
  destinationEl.textContent = interpreted.longUrl;
  expiryNote.textContent = interpreted.expiresAt
    ? `Stops redirecting ${formatWhen(interpreted.expiresAt)}.`
    : "This link does not expire.";
  copyButton.textContent = "Copy";
  setStatus(`Short link created. ${interpreted.shortUrl}`);
  resultTitle.focus();
}

function hideResult() {
  result.hidden = true;
  shortUrlEl.textContent = "";
  openLink.href = "";
  destinationEl.textContent = "";
  expiryNote.textContent = "";
}

function renderRecent() {
  const items = loadRecent(localStorage);
  recent.hidden = items.length === 0;
  recentList.replaceChildren();
  for (const item of items) {
    const href = safeHttpUrl(item.shortUrl);
    const destination = safeHttpUrl(item.longUrl);
    if (!href || !destination) {
      continue;
    }
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.href = href;
    link.textContent = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const detail = document.createElement("p");
    detail.textContent = destination;
    li.append(link, detail);
    recentList.append(li);
  }
  if (!recentList.children.length) {
    recent.hidden = true;
  }
}

function showError(message) {
  errorEl.hidden = false;
  errorEl.textContent = message;
  input.setAttribute("aria-invalid", "true");
}

function clearError() {
  errorEl.hidden = true;
  errorEl.textContent = "";
  input.removeAttribute("aria-invalid");
}

function setStatus(message, { visible = false } = {}) {
  statusEl.textContent = message;
  statusEl.classList.toggle("is-visible", Boolean(visible && message));
}

function apiUrl(path) {
  const base = String(config.apiBaseUrl || "").replace(/\/$/, "");
  return `${base}${path}`;
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function copyText(text) {
  if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
    return false;
  }
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function selectContents(node) {
  const range = document.createRange();
  range.selectNodeContents(node);
  const selection = window.getSelection();
  if (!selection) {
    return;
  }
  selection.removeAllRanges();
  selection.addRange(range);
}

function formatWhen(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
