(function () {
  function parseArgs(raw) {
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [parsed];
    } catch (_) {
      return [];
    }
  }

  function invokeAction(action, args, el, event) {
    if (!action || typeof window[action] !== "function") return;

    if (action === "setGameType" || action === "switchRefTab" || action === "switchDigTab" || action === "switchKpiTab") {
      return window[action](args[0], el);
    }
    if (action === "setAnimToggle") {
      return window.setAnimToggle(!!el.checked);
    }
    if (action === "setBustVoteEnabled") {
      return window.setBustVoteEnabled(!!el.checked);
    }
    if (action === "setGodMode") {
      return window.setGodMode(!!el.checked);
    }
    if (action === "cycleLocalSeat") {
      return window.cycleLocalSeat();
    }
    if (action === "setBustVoteSetupToggle") {
      return window.setBustVoteSetupToggle(!!el.checked);
    }
    if (action === "handleRulesBackdropClick") {
      return window.handleRulesBackdropClick(event);
    }
    return window[action](...args);
  }

  function applyConfiguredText() {
    const text = window.UI_TEXT || {};
    document.querySelectorAll("[data-copy]").forEach((el) => {
      const key = el.dataset.copy;
      if (key && text[key]) el.textContent = text[key];
    });
  }

  window.exportDrinksAndClose = function exportDrinksAndClose() {
    exportDrinkCSV();
    closeSummaryModal();
  };

  document.addEventListener("click", (event) => {
    const stopper = event.target.closest("[data-stop-propagation='true']");
    if (stopper) {
      event.stopPropagation();
    }

    const backdrop = event.target.closest("[data-backdrop-action]");
    if (backdrop && event.target === backdrop) {
      invokeAction(backdrop.dataset.backdropAction, [], backdrop, event);
      return;
    }

    const trigger = event.target.closest("[data-action]");
    if (!trigger) return;
    const args = parseArgs(trigger.dataset.args);
    invokeAction(trigger.dataset.action, args, trigger, event);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const trigger = event.target.closest("[data-enter-action]");
    if (!trigger) return;
    invokeAction(trigger.dataset.enterAction, [], trigger, event);
  });

  document.addEventListener("change", (event) => {
    const trigger = event.target.closest("[data-change-action]");
    if (!trigger) return;
    invokeAction(trigger.dataset.changeAction, [], trigger, event);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyConfiguredText);
  } else {
    applyConfiguredText();
  }
})();
