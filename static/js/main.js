/**
 * TruthLens AI — Main Client Interactions & UI Behaviors (Phase 14B)
 */
document.addEventListener("DOMContentLoaded", () => {
  // Mobile Navigation Toggle
  const mobileToggle = document.getElementById("mobile-menu-toggle");
  const navLinks = document.getElementById("nav-links");

  if (mobileToggle && navLinks) {
    mobileToggle.addEventListener("click", () => {
      const isOpen = navLinks.classList.toggle("open");
      mobileToggle.setAttribute("aria-expanded", String(isOpen));
    });

    // Close mobile menu on Escape key
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && navLinks.classList.contains("open")) {
        navLinks.classList.remove("open");
        mobileToggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  // Check if reduced motion is preferred
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Interactive Button & Navigation Shake Feedback (Phase 14B - High Priority)
  document.addEventListener("click", (e) => {
    const target = e.target.closest(
      ".btn, .nav-link, .nav-cta, .brand-container, .sample-pill-btn, .sample-url-pill-btn, .mode-tab, button, a.btn, [role='button']"
    );
    if (!target) return;
    if (target.disabled || target.getAttribute("aria-disabled") === "true") return;

    if (!prefersReducedMotion) {
      // 1. Web Animations API direct execution (works seamlessly on all layout types)
      if (typeof target.animate === "function") {
        target.animate(
          [
            { transform: "translateX(0px)" },
            { transform: "translateX(-4px)" },
            { transform: "translateX(4px)" },
            { transform: "translateX(-2px)" },
            { transform: "translateX(0px)" }
          ],
          {
            duration: 220,
            easing: "ease-in-out"
          }
        );
      }

      // 2. CSS class toggle fallback
      target.classList.remove("shake-feedback", "button-shake");
      void target.offsetWidth; // Force reflow
      target.classList.add("shake-feedback");

      setTimeout(() => {
        target.classList.remove("shake-feedback", "button-shake");
      }, 250);
    }
  });

  // Copy to Clipboard Buttons
  const copyButtons = document.querySelectorAll(".btn-copy");
  copyButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const textToCopy = btn.getAttribute("data-copy-text");
      if (!textToCopy) return;

      try {
        await navigator.clipboard.writeText(textToCopy);
        const originalText = btn.innerHTML;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg><span>Copied</span>`;
        btn.classList.add("btn-copied");
        setTimeout(() => {
          btn.innerHTML = originalText;
          btn.classList.remove("btn-copied");
        }, 2000);
      } catch (err) {
        console.warn("Clipboard write failed:", err);
      }
    });
  });
});
