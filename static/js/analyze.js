/**
 * TruthLens AI — Analyze Form Logic with Claim / URL Mode Switcher
 */
document.addEventListener("DOMContentLoaded", () => {
  const modeInput = document.getElementById("analysis-mode-input");
  const tabClaim = document.getElementById("mode-tab-claim");
  const tabUrl = document.getElementById("mode-tab-url");
  const panelClaim = document.getElementById("claim-mode-panel");
  const panelUrl = document.getElementById("url-mode-panel");
  const samplesClaim = document.getElementById("samples-claim-section");
  const samplesUrl = document.getElementById("samples-url-section");

  const textarea = document.getElementById("claim-text");
  const urlInput = document.getElementById("news-url-input");
  const charCounter = document.getElementById("char-counter");
  const clearBtn = document.getElementById("clear-btn");
  const form = document.getElementById("analyze-form");
  const submitBtn = document.getElementById("analyze-submit-btn");
  const loadingOverlay = document.getElementById("loading-overlay");
  const samplePills = document.querySelectorAll(".sample-pill-btn");
  const sampleUrlPills = document.querySelectorAll(".sample-url-pill-btn");

  const MAX_CHARS = 10000;
  const MIN_CHARS = 5;

  // Tab Mode Switching
  function setMode(mode) {
    if (modeInput) modeInput.value = mode;

    if (mode === "url") {
      if (tabUrl) {
        tabUrl.classList.remove("btn-secondary");
        tabUrl.classList.add("btn-primary");
      }
      if (tabClaim) {
        tabClaim.classList.remove("btn-primary");
        tabClaim.classList.add("btn-secondary");
      }
      if (panelClaim) panelClaim.style.display = "none";
      if (panelUrl) panelUrl.style.display = "block";
      if (samplesClaim) samplesClaim.style.display = "none";
      if (samplesUrl) samplesUrl.style.display = "block";
      if (textarea) textarea.removeAttribute("required");
      if (urlInput) {
        urlInput.setAttribute("required", "required");
        urlInput.focus();
      }
    } else {
      if (tabClaim) {
        tabClaim.classList.remove("btn-secondary");
        tabClaim.classList.add("btn-primary");
      }
      if (tabUrl) {
        tabUrl.classList.remove("btn-primary");
        tabUrl.classList.add("btn-secondary");
      }
      if (panelClaim) panelClaim.style.display = "block";
      if (panelUrl) panelUrl.style.display = "none";
      if (samplesClaim) samplesClaim.style.display = "block";
      if (samplesUrl) samplesUrl.style.display = "none";
      if (urlInput) urlInput.removeAttribute("required");
      if (textarea) {
        textarea.setAttribute("required", "required");
        textarea.focus();
      }
    }
  }

  if (tabClaim) {
    tabClaim.addEventListener("click", () => setMode("claim"));
  }
  if (tabUrl) {
    tabUrl.addEventListener("click", () => setMode("url"));
  }

  // Update Character Counter
  function updateCharCount() {
    if (!textarea || !charCounter) return;
    const len = textarea.value.length;
    charCounter.textContent = `${len.toLocaleString()} / ${MAX_CHARS.toLocaleString()} chars`;

    if (len > MAX_CHARS) {
      charCounter.style.color = "var(--color-false)";
    } else {
      charCounter.style.color = "var(--text-muted)";
    }
  }

  if (textarea) {
    textarea.addEventListener("input", updateCharCount);
    updateCharCount();
  }

  // Clear Button
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      const currentMode = modeInput ? modeInput.value : "claim";
      if (currentMode === "url" && urlInput) {
        urlInput.value = "";
        urlInput.focus();
      } else if (textarea) {
        textarea.value = "";
        textarea.focus();
        updateCharCount();
      }
    });
  }

  // Sample Claim Buttons
  samplePills.forEach((btn) => {
    btn.addEventListener("click", () => {
      const sampleText = btn.getAttribute("data-sample");
      if (textarea && sampleText) {
        textarea.value = sampleText;
        textarea.focus();
        updateCharCount();
      }
    });
  });

  // Sample URL Buttons
  sampleUrlPills.forEach((btn) => {
    btn.addEventListener("click", () => {
      const sampleUrl = btn.getAttribute("data-sample-url");
      if (urlInput && sampleUrl) {
        urlInput.value = sampleUrl;
        urlInput.focus();
      }
    });
  });

  // Fallback Paste Button Action
  const fallbackPasteBtn = document.getElementById("fallback-paste-btn");
  if (fallbackPasteBtn) {
    fallbackPasteBtn.addEventListener("click", () => {
      setMode("claim");
      const errArea = document.getElementById("validation-error-area");
      if (errArea) {
        errArea.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      if (textarea) {
        textarea.focus();
      }
    });
  }

  // Submit Handler with Loading Overlay and Dynamic Stage Progression
  if (form && submitBtn && loadingOverlay) {
    form.addEventListener("submit", (e) => {
      const currentMode = modeInput ? modeInput.value : "claim";

      if (currentMode === "url") {
        const urlVal = (urlInput ? urlInput.value : "").trim();
        if (!urlVal) {
          e.preventDefault();
          alert("Please enter a valid article URL.");
          return;
        }
        if (!urlVal.startsWith("http://") && !urlVal.startsWith("https://")) {
          e.preventDefault();
          alert("URL must begin with http:// or https://");
          return;
        }
      } else {
        const text = (textarea ? textarea.value : "").trim();
        if (text.length < MIN_CHARS) {
          e.preventDefault();
          alert(`Claim is too short. Please enter at least ${MIN_CHARS} characters.`);
          return;
        }
        if (text.length > MAX_CHARS) {
          e.preventDefault();
          alert(`Claim exceeds maximum length of ${MAX_CHARS} characters.`);
          return;
        }
      }

      // Show Loading State
      submitBtn.disabled = true;
      submitBtn.innerHTML = `
        <span class="spinner" style="width: 18px; height: 18px; border-width: 2px; display: inline-block; vertical-align: middle;"></span>
        <span>Analyzing...</span>
      `;
      loadingOverlay.style.display = "flex";

      // Dynamic Stage Step Animation
      const stages = document.querySelectorAll(".loading-stages .stage-item");
      if (stages && stages.length > 0) {
        let activeIdx = 0;
        const intervalMs = currentMode === "url" ? 1400 : 900;
        setInterval(() => {
          if (activeIdx < stages.length) {
            stages.forEach((s, idx) => {
              if (idx <= activeIdx) {
                s.classList.add("active");
              }
            });
            activeIdx++;
          }
        }, intervalMs);
      }
    });
  }
});
