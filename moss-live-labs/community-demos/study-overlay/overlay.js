const assistantView = document.getElementById("assistant-view");
const settingsView = document.getElementById("settings-view");
const responseEl = document.getElementById("response");
const loadingEl = document.getElementById("loading");
const contextTag = document.getElementById("context-tag");
const hotkeyLabel = document.getElementById("hotkey-label");
const settingsForm = document.getElementById("settings-form");
const settingsNote = document.getElementById("settings-note");
const promptForm = document.getElementById("prompt-form");
const promptInput = document.getElementById("prompt-input");

const fields = {
  OPENROUTER_API_KEY: document.getElementById("openrouter-key"),
  MOSS_PROJECT_ID: document.getElementById("moss-project-id"),
  MOSS_PROJECT_KEY: document.getElementById("moss-project-key"),
};

function showSettings(settings) {
  assistantView.classList.add("hidden");
  settingsView.classList.remove("hidden");
  if (settings?.values) {
    for (const [key, input] of Object.entries(fields)) {
      input.value = settings.values[key] || "";
    }
  }
  const path = settings?.config_path || "your app data directory";
  settingsNote.textContent = `Saved locally to ${path}. Leave Moss fields blank to run without memory.`;
}

function showAssistant() {
  settingsView.classList.add("hidden");
  assistantView.classList.remove("hidden");
  renderMath();
}

function setLoading(isLoading) {
  loadingEl.classList.toggle("hidden", !isLoading);
}

function renderMath() {
  if (!window.renderMathInElement) return;
  window.renderMathInElement(responseEl, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "$", right: "$", display: false },
      { left: "\\(", right: "\\)", display: false },
      { left: "\\[", right: "\\]", display: true },
    ],
    throwOnError: false,
  });
}

function setMarkdown(markdown) {
  const source = markdown || "";
  const escaped = source.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  if (window.marked) {
    responseEl.innerHTML = window.marked.parse(escaped, { mangle: false, headerIds: false });
  } else {
    responseEl.textContent = source;
  }
  renderMath();
}

async function runAsk(prompt = "") {
  window.StudyOverlay.hotkeyStarted();
  const result = await window.pywebview.api.run_capture(prompt);
  window.StudyOverlay.hotkeyFinished(result);
}

document.getElementById("ask-button").addEventListener("click", () => runAsk(promptInput.value));

promptForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runAsk(promptInput.value);
});

document.getElementById("settings-button").addEventListener("click", async () => {
  const settings = await window.pywebview.api.get_settings();
  showSettings(settings);
});

document.getElementById("back-button").addEventListener("click", () => showAssistant());

document.getElementById("hide-button").addEventListener("click", () => {
  window.pywebview.api.hide_window();
});

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(Object.entries(fields).map(([key, input]) => [key, input.value]));
  const settings = await window.pywebview.api.save_settings(payload);
  settingsNote.textContent = "Saved. Moss memory will be used when both Moss fields are valid.";
  if (!settings.missing.includes("OPENROUTER_API_KEY")) {
    setTimeout(showAssistant, 400);
  }
});

window.StudyOverlay = {
  bootstrap(payload) {
    if (payload?.hotkey) {
      hotkeyLabel.textContent = payload.hotkey.replaceAll("<", "").replaceAll(">", "").replaceAll("+", "+");
    }
    if (payload?.hotkey_enabled === false) {
      hotkeyLabel.textContent = "Enable Accessibility";
    }
    if (payload?.settings?.missing?.length) {
      showSettings(payload.settings);
    } else {
      showAssistant();
    }
    renderMath();
  },

  hotkeyStarted() {
    showAssistant();
    contextTag.classList.add("hidden");
    setLoading(true);
  },

  hotkeyFinished(result) {
    setLoading(false);
    if (result?.settings) {
      window.pywebview.api.get_settings().then(showSettings);
      return;
    }
    if (!result?.ok) {
      setMarkdown(`**Could not complete capture.**\n\n${result?.error || "Unknown error."}`);
      return;
    }
    setMarkdown(result.markdown);
    contextTag.classList.toggle("hidden", !result.used_context);
  },
};

document.addEventListener("DOMContentLoaded", renderMath);
