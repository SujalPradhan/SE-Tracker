/* SE-Tracker — motion and chrome: nav drawer, reveals, count-ups, tab indicator.
   Purely presentational; everything still works with this file absent. */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- mobile nav drawer ---------- */

  function initDrawer() {
    const toggle = $("#nav-toggle");
    const scrim = $("#nav-scrim");
    if (!toggle) return;
    const set = (open) => {
      document.body.classList.toggle("nav-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      if (scrim) scrim.hidden = !open;
    };
    toggle.addEventListener("click", () => set(!document.body.classList.contains("nav-open")));
    if (scrim) scrim.addEventListener("click", () => set(false));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") set(false);
    });
  }

  /* ---------- scroll reveals (staggered) ---------- */

  function initReveals() {
    const targets = $$(".reveal, .reveal-group");
    $$(".reveal-group").forEach((group) =>
      Array.from(group.children).forEach((child, i) => child.style.setProperty("--i", i))
    );
    if (reduceMotion || !("IntersectionObserver" in window)) {
      targets.forEach((el) => el.classList.add("in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("in");
          io.unobserve(entry.target);
          $$("[data-count]", entry.target).forEach(countUp);
        }),
      { rootMargin: "0px 0px -6% 0px", threshold: 0.08 }
    );
    targets.forEach((el) => io.observe(el));
  }

  /* ---------- KPI count-up ---------- */

  function countUp(el) {
    if (el.dataset.counted) return;
    el.dataset.counted = "1";
    const target = parseFloat(el.dataset.count);
    const decimals = parseInt(el.dataset.decimals || "0", 10);
    if (Number.isNaN(target) || reduceMotion) return;
    const start = performance.now();
    const duration = 900;
    const step = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = (target * eased).toFixed(decimals);
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = decimals ? String(+target.toFixed(decimals)) : String(target);
    };
    requestAnimationFrame(step);
  }

  /* ---------- sliding tab indicator ---------- */

  function initTabs() {
    const tabs = $(".tabs");
    const bar = tabs && $(".tab-indicator", tabs);
    const active = tabs && $(".tab.active", tabs);
    if (!bar || !active) return;
    const key = "se-tracker-tab-indicator";
    const place = (left, width) => {
      bar.style.transform = "translateX(" + left + "px)";
      bar.style.width = width + "px";
    };
    let prev = null;
    try {
      prev = JSON.parse(sessionStorage.getItem(key));
    } catch (e) {
      prev = null;
    }
    const target = { left: active.offsetLeft, width: active.offsetWidth, path: location.pathname };
    if (prev && prev.path === target.path && !reduceMotion) {
      bar.style.transition = "none";
      place(prev.left, prev.width);
      bar.getBoundingClientRect(); // commit the start position
      bar.style.transition = "";
    }
    requestAnimationFrame(() => place(target.left, target.width));
    try {
      sessionStorage.setItem(key, JSON.stringify(target));
    } catch (e) {
      /* storage unavailable — indicator just doesn't slide */
    }
    window.addEventListener("resize", () => place(active.offsetLeft, active.offsetWidth));
  }

  /* ---------- light / dark / system switch ---------- */

  function initThemeSwitch() {
    const buttons = $$("[data-theme-choice]");
    const sync = () => {
      const current = document.documentElement.dataset.themeChoice || "system";
      buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === current)));
    };
    buttons.forEach((b) =>
      b.addEventListener("click", () => {
        try {
          localStorage.setItem("se-theme", b.dataset.themeChoice);
        } catch (e) {
          /* storage blocked — the choice just won't stick */
        }
        if (window.applyTheme) window.applyTheme();
        sync();
      })
    );
    sync();
  }

  /* ---------- Y/N/blank selects tint by value ---------- */

  function initYnd() {
    $$("select.ynd").forEach((sel) =>
      sel.addEventListener("change", () => {
        sel.classList.remove("ynd-Y", "ynd-N", "ynd-blank");
        sel.classList.add("ynd-" + (sel.value || "blank"));
      })
    );
  }

  /* ---------- present toggle pulses the card ---------- */

  function initCardPulse() {
    $$(".member-card .yn-btn").forEach((btn) =>
      btn.addEventListener("click", () => {
        if (reduceMotion) return;
        btn.classList.remove("pop");
        void btn.offsetWidth;
        btn.classList.add("pop");
      })
    );
  }

  function init() {
    document.documentElement.classList.add("js");
    initDrawer();
    initThemeSwitch();
    initReveals();
    initTabs();
    initYnd();
    initCardPulse();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
