// Content script — least privilege, active application page only.
//
// HARD RULES (docs/APPLICATION_AUTOMATION.md, docs/SECURITY.md):
//  - Never clicks a final Submit / Apply / Send button.
//  - Never stores account credentials.
//  - Never background-submits; never uploads the full page anywhere.
//  - Only fills fields the backend marked as user-confirmed & deterministic.
//  - Shows the user exactly what it filled; flags everything uncertain.
//
// This skeleton demonstrates the submit-intercept guard and field flagging.

(function () {
  const SUBMIT_PATTERNS = /\b(submit|apply|send application|finish|complete application)\b/i;

  function guardSubmitButtons() {
    const candidates = Array.from(
      document.querySelectorAll('button, input[type="submit"], [role="button"]'),
    );
    for (const el of candidates) {
      const label = (el.innerText || el.value || el.getAttribute("aria-label") || "").trim();
      if (SUBMIT_PATTERNS.test(label) && !el.dataset.jobosGuarded) {
        el.dataset.jobosGuarded = "1";
        el.addEventListener(
          "click",
          (e) => {
            // Block the automatic path. Real submission only proceeds after the
            // user completes the per-job confirmation in the Job OS web app.
            e.preventDefault();
            e.stopImmediatePropagation();
            showConfirmationNotice(label);
          },
          true,
        );
      }
    }
  }

  function showConfirmationNotice(label) {
    let bar = document.getElementById("__jobos_bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "__jobos_bar";
      bar.style.cssText =
        "position:fixed;bottom:0;left:0;right:0;z-index:2147483647;" +
        "background:#111827;color:#e5e7eb;font:14px system-ui;padding:12px 16px;" +
        "border-top:2px solid #3b82f6;display:flex;gap:12px;align-items:center";
      document.body.appendChild(bar);
    }
    bar.textContent =
      `Job OS blocked "${label}". Review every field in the Job OS confirmation ` +
      "page, then confirm this specific job to submit. Nothing was sent.";
  }

  function flagUncertainFields() {
    const inputs = Array.from(document.querySelectorAll("input, textarea, select"));
    let flagged = 0;
    for (const el of inputs) {
      if (!el.value && el.required) {
        el.style.outline = "2px solid #f59e0b";
        flagged++;
      }
    }
    return { fields: inputs.length, flaggedEmptyRequired: flagged };
  }

  const observer = new MutationObserver(() => guardSubmitButtons());
  observer.observe(document.documentElement, { childList: true, subtree: true });
  guardSubmitButtons();

  chrome.runtime.onMessage?.addListener((msg, _sender, sendResponse) => {
    if (msg?.type === "JOBOS_SCAN") {
      sendResponse(flagUncertainFields());
    }
    return true;
  });
})();
