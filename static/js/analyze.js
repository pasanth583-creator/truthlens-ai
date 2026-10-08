/**
 * TruthLens AI — Analyze Form Logic
 */
document.addEventListener("DOMContentLoaded", () => {
  const textarea = document.getElementById("claim-text");
  const charCounter = document.getElementById("char-counter");
  const clearBtn = document.getElementById("clear-btn");
  const form = document.getElementById("analyze-form");
  const submitBtn = document.getElementById("analyze-submit-btn");
  const loadingOverlay = document.getElementById("loading-overlay");
  const samplePills = document.querySelectorAll(".sample-pill-btn");

  const MAX_CHARS = 10000;
  const MIN_CHARS = 5;

  // Update Character Counter
  function updateCharCount() {
    if (!textarea || !charCounter) return;
    const len = textarea.value.length;
    charCounter.textContent = `${len.toLocaleString()} / ${MAX_CHARS.toLocaleString()} chars`;

    if (len > MAX_CHARS) {
      charCounter.style.color = "var(--color-false)";
    } else if (len >= MIN_CHARS) {
      charCounter.style.color = "var(--text-muted)";
    } else {
      charCounter.style.color = "var(--text-muted)";
    }
  }

  if (textarea) {
    textarea.addEventListener("input", updateCharCount);
    updateCharCount();
  }

  // Clear Button
  if (clearBtn && textarea) {
    clearBtn.addEventListener("click", () => {
      textarea.value = "";
      textarea.focus();
      updateCharCount();
    });
  }

  // Sample Claim Buttons (populate only, do NOT auto-submit)
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

  // Submit Handler with Loading State & Anti-Double Submission
  if (form && submitBtn && loadingOverlay) {
    form.addEventListener("submit", (e) => {
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

      // Show Loading State
      submitBtn.disabled = true;
      submitBtn.innerHTML = `
        <span class="spinner" style="width: 18px; height: 18px; border-width: 2px; display: inline-block; vertical-align: middle;"></span>
        <span>Analyzing...</span>
      `;
      loadingOverlay.style.display = "flex";
    });
  }
});
