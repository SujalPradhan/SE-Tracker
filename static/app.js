/* SE-Tracker — light vanilla JS: toggles, steppers, live totals, drafts, saves. */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const CSRF = ($('meta[name="csrf-token"]') || { content: "" }).content;

  /* ---------- Y/N toggles ---------- */

  function syncYn(group) {
    const value = $("input[type=hidden]", group).value;
    $$(".yn-btn", group).forEach((btn) => {
      const on = btn.dataset.val === value;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", String(on));
    });
  }

  function initToggles() {
    $$(".yn").forEach((group) => {
      const input = $("input[type=hidden]", group);
      $$(".yn-btn", group).forEach((btn) =>
        btn.addEventListener("click", () => {
          input.value = btn.dataset.val;
          syncYn(group);
          input.dispatchEvent(new Event("input", { bubbles: true }));
        })
      );
      syncYn(group);
    });
  }

  /* ---------- score steppers & live totals ---------- */

  // "+" from blank gives 0.5; "−" at 0 clears back to blank (blank = unscored).
  function stepValue(current, delta, max) {
    if (current === "") return delta > 0 ? "0.5" : "";
    const value = parseFloat(current);
    if (Number.isNaN(value)) return "";
    if (delta < 0 && value <= 0) return "";
    const next = Math.min(Math.max(value + delta, 0), max);
    return String(+next.toFixed(1));
  }

  function initSteppers() {
    $$(".stepper").forEach((wrap) => {
      const input = $(".score-input", wrap);
      $$(".step", wrap).forEach((btn) =>
        btn.addEventListener("click", () => {
          input.value = stepValue(input.value, parseFloat(btn.dataset.delta), parseFloat(input.max));
          input.dispatchEvent(new Event("input", { bubbles: true }));
        })
      );
    });
  }

  function refreshCard(card) {
    const totalEl = $(".total-value", card);
    if (!totalEl) return;
    const filled = $$(".score-input", card).filter((i) => i.value !== "");
    totalEl.textContent = filled.length
      ? String(+filled.reduce((sum, i) => sum + (parseFloat(i.value) || 0), 0).toFixed(1))
      : "—";
  }

  function cardLogged(card) {
    return (
      $$(".score-input", card).some((i) => i.value !== "") ||
      ($("textarea[name=progress]", card) || { value: "" }).value.trim() !== ""
    );
  }

  function cardAbsent(card) {
    return $("input[name=present]", card).value === "0";
  }

  // Progress hint, jump-pill states, and absent-card dimming in one pass.
  function refreshProgressHint() {
    const cards = $$(".member-card");
    const hint = $("#log-progress");
    if (!hint || !cards.length) return;
    const pills = $$(".member-pill");
    let logged = 0;
    cards.forEach((card, i) => {
      const done = cardLogged(card);
      const absent = cardAbsent(card);
      if (done) logged += 1;
      card.classList.toggle("absent", absent);
      if (pills[i]) {
        pills[i].classList.toggle("done", done);
        pills[i].classList.toggle("absent", absent);
      }
    });
    hint.textContent = logged + " of " + cards.length + " members logged";
  }

  /* ---------- remark quick-chips ---------- */

  function initChips() {
    $$(".chip[data-text]").forEach((chip) =>
      chip.addEventListener("click", () => {
        const wrap = chip.closest(".remarks-wrap");
        const field = wrap && $("textarea, input", wrap);
        if (!field) return;
        field.value = field.value.trim() ? field.value.trim() + "; " + chip.dataset.text : chip.dataset.text;
        field.dispatchEvent(new Event("input", { bubbles: true }));
        field.focus();
      })
    );
  }

  /* ---------- shared save-with-retry ---------- */

  async function putJson(url, payload, statusEl, retryFn) {
    statusEl.className = "save-status";
    statusEl.textContent = "Saving…";
    try {
      const res = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.ok) throw new Error(body.error || "HTTP " + res.status);
      statusEl.classList.add("ok");
      const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      statusEl.textContent = "Saved ✓ " + time;
      return true;
    } catch (err) {
      // The form keeps its state — nothing the TA typed is lost.
      statusEl.classList.add("err");
      statusEl.textContent = "Couldn't save (" + err.message + "). Your entries are safe. ";
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "link-btn";
      retry.textContent = "Retry";
      retry.addEventListener("click", retryFn);
      statusEl.appendChild(retry);
      return false;
    }
  }

  /* ---------- call form: collect / drafts / save ---------- */

  const TEXT_FIELDS = ["tasks_assigned_prev", "tasks_for_next", "progress", "evidence_link", "remarks"];
  const SCORE_NAMES = ["role_fulfillment", "client_interaction", "initiative"];

  function initCallForm() {
    const form = $("#call-form");
    if (!form) return;
    const draftKey = "se-tracker-draft-call-" + form.dataset.callId;
    const status = $("#save-status");
    let saving = false;

    // Jump-pills in the save bar: one per member, click scrolls to their card.
    const pillBar = $("#member-pills");
    if (pillBar)
      $$(".member-card", form).forEach((card) => {
        const pill = document.createElement("button");
        pill.type = "button";
        pill.className = "member-pill";
        pill.textContent = $("h2", card).textContent.trim().split(" ")[0];
        pill.title = "Jump to " + $("h2", card).textContent.trim();
        pill.addEventListener("click", () =>
          card.scrollIntoView({ behavior: "smooth", block: "start" })
        );
        pillBar.appendChild(pill);
      });

    function markDirty() {
      if (saving) return;
      status.className = "save-status warn";
      status.textContent = "Unsaved changes";
    }

    // "Open ↗" next to each evidence field, kept in sync with the input.
    $$(".evidence-row", form).forEach((row) => {
      const input = $("input", row);
      const link = $(".evidence-open", row);
      const sync = () => {
        const url = input.value.trim();
        link.hidden = !url;
        if (url) link.href = url;
      };
      input.addEventListener("input", sync);
      sync();
    });

    if (form.dataset.readonly === "1") {
      // Demo: show the call as-is — no drafts, no saving.
      $$(".member-card", form).forEach(refreshCard);
      refreshProgressHint();
      return;
    }

    function collect() {
      return {
        week: $("#call-week").value,
        milestone: $("#call-milestone").value,
        date: $("#call-date").value,
        entries: $$(".member-card", form).map((card) => {
          const row = { member_id: parseInt(card.dataset.memberId, 10) };
          row.present = $("input[name=present]", card).value === "1";
          row.spoke = $("input[name=spoke]", card).value === "1";
          TEXT_FIELDS.concat(SCORE_NAMES).forEach((name) => {
            row[name] = $("[name=" + name + "]", card).value;
          });
          return row;
        }),
      };
    }

    function apply(data) {
      $("#call-week").value = data.week || "";
      if (data.milestone) $("#call-milestone").value = data.milestone;
      if (data.date) $("#call-date").value = data.date;
      (data.entries || []).forEach((row) => {
        const card = $('.member-card[data-member-id="' + row.member_id + '"]', form);
        if (!card) return;
        $("input[name=present]", card).value = row.present ? "1" : "0";
        $("input[name=spoke]", card).value = row.spoke ? "1" : "0";
        TEXT_FIELDS.concat(SCORE_NAMES).forEach((name) => {
          const el = $("[name=" + name + "]", card);
          if (el && row[name] !== undefined) el.value = row[name];
        });
        $$(".yn", card).forEach(syncYn);
        refreshCard(card);
      });
      refreshProgressHint();
    }

    let draftTimer = null;
    function scheduleDraft() {
      clearTimeout(draftTimer);
      draftTimer = setTimeout(() => {
        try {
          localStorage.setItem(draftKey, JSON.stringify({ savedAt: Date.now(), data: collect() }));
        } catch (err) {
          /* storage unavailable — server saves still work */
        }
      }, 300);
    }

    function restoreDraft() {
      let draft = null;
      try {
        draft = JSON.parse(localStorage.getItem(draftKey));
      } catch (err) {
        return;
      }
      if (!draft || !draft.data) return;
      apply(draft.data);
      markDirty(); // a restored draft is by definition unsaved
      const banner = $("#draft-banner");
      if (banner) banner.hidden = false;
    }

    async function save() {
      const btn = $("#save-call");
      if (btn.disabled) return; // a save is already in flight (Enter can re-trigger)
      btn.disabled = true;
      saving = true;
      const ok = await putJson("/api/calls/" + form.dataset.callId, collect(), status, save);
      if (ok) {
        clearTimeout(draftTimer); // a pending autosave must not resurrect the draft
        localStorage.removeItem(draftKey);
      }
      saving = false;
      btn.disabled = false;
    }

    form.addEventListener("submit", (e) => {
      e.preventDefault(); // Enter anywhere = save, never a stray submit
      save();
    });
    $("#save-call").addEventListener("click", save);
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        save();
      }
    });

    form.addEventListener("input", (e) => {
      const card = e.target.closest(".member-card");
      if (card) refreshCard(card);
      refreshProgressHint();
      markDirty();
      scheduleDraft();
    });

    const discard = $("#discard-draft");
    if (discard)
      discard.addEventListener("click", () => {
        localStorage.removeItem(draftKey);
        location.reload();
      });

    const del = $("#delete-call");
    if (del)
      del.addEventListener("click", () => {
        if (!confirm("Delete this call and all its member entries?")) return;
        const f = document.createElement("form");
        f.method = "post";
        f.action = del.dataset.url;
        const token = document.createElement("input");
        token.type = "hidden";
        token.name = "csrf_token";
        token.value = CSRF;
        f.appendChild(token);
        document.body.appendChild(f);
        localStorage.removeItem(draftKey);
        f.submit();
      });

    $$(".member-card", form).forEach(refreshCard);
    restoreDraft();
    refreshProgressHint();
  }

  /* ---------- milestone grid ---------- */

  function initGrid() {
    const grid = $("#milestone-grid");
    if (!grid || !$("#save-grid")) return;

    async function save() {
      const rows = $$("tr[data-member-id]", grid).map((tr) => {
        const row = { member_id: parseInt(tr.dataset.memberId, 10) };
        ["report_section", "code", "tests", "demo", "evidence_link", "remarks"].forEach((name) => {
          row[name] = $("[name=" + name + "]", tr).value;
        });
        return row;
      });
      const url = "/api/teams/" + grid.dataset.teamId + "/milestones/" + grid.dataset.milestone;
      await putJson(url, { rows: rows }, $("#grid-status"), save);
    }

    $("#save-grid").addEventListener("click", save);
  }

  /* ---------- flashes & clickable rows ---------- */

  function initFlashes() {
    $$(".flash").forEach((flash) => {
      const delay = flash.classList.contains("flash-error") ? 8000 : 4000;
      setTimeout(() => {
        flash.classList.add("flash-hide");
        setTimeout(() => flash.remove(), 450);
      }, delay);
    });
  }

  function initRowLinks() {
    $$("tr[data-href]").forEach((tr) =>
      tr.addEventListener("click", (e) => {
        if (e.target.closest("a, button, input, select, textarea")) return;
        window.location = tr.dataset.href;
      })
    );
  }

  /* ---------- import page ---------- */

  function initImport() {
    const box = $("#import-json");
    if (!box) return;
    const status = $("#import-status");
    const result = $("#import-result");

    $("#run-import").addEventListener("click", async () => {
      result.hidden = true;
      let payload;
      try {
        payload = JSON.parse(box.value);
      } catch (err) {
        status.className = "save-status err";
        status.textContent = "Not valid JSON: " + err.message;
        return;
      }
      status.className = "save-status";
      status.textContent = "Importing…";
      try {
        const res = await fetch("/api/import", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
          body: JSON.stringify(payload),
        });
        const body = await res.json();
        if (body.ok) {
          const s = body.summary;
          status.className = "save-status ok";
          status.textContent = "Imported ✓";
          result.className = "flash flash-ok";
          result.textContent =
            "Created team(s) " + s.team_numbers.join(", ") + ": " +
            s.members + " members, " + s.calls + " calls, " +
            s.entries + " call entries, " + s.submissions + " milestone submissions. " +
            "Check the sidebar — summaries and exports are ready.";
          result.hidden = false;
        } else {
          status.className = "save-status err";
          status.textContent = "Nothing imported — fix the issues below and retry.";
          result.className = "flash flash-error";
          result.innerHTML = "";
          const list = document.createElement("ul");
          (body.errors || ["Unknown error"]).forEach((message) => {
            const item = document.createElement("li");
            item.textContent = message;
            list.appendChild(item);
          });
          result.appendChild(list);
          result.hidden = false;
        }
      } catch (err) {
        status.className = "save-status err";
        status.textContent = "Couldn't reach the server (" + err.message + "). Your JSON is untouched — retry.";
      }
    });

    const copy = $("#copy-prompt");
    if (copy)
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText($("#claude-prompt").textContent);
          $("#copy-status").textContent = "Copied ✓";
        } catch (err) {
          $("#copy-status").textContent = "Copy failed — select the text manually.";
        }
      });
  }

  /* ---------- team form: add member row ---------- */

  function initTeamForm() {
    const addBtn = $("#add-member-row");
    if (!addBtn) return;
    addBtn.addEventListener("click", () => {
      const tbody = $("#member-rows");
      const row = tbody.lastElementChild.cloneNode(true);
      $$("input", row).forEach((input) => {
        input.value = "";
        input.removeAttribute("required");
      });
      tbody.appendChild(row);
      $("input[name=member_name]", row).focus();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initToggles();
    initSteppers();
    initChips();
    initCallForm();
    initGrid();
    initTeamForm();
    initFlashes();
    initRowLinks();
    initImport();

    // Forms with data-confirm ask first; then disable submit buttons once a
    // plain form is on its way — a double-click on "+ New call" would
    // otherwise create two calls.
    document.addEventListener("submit", (e) => {
      if (e.defaultPrevented) return;
      const message = e.target.dataset.confirm;
      if (message && !confirm(message)) {
        e.preventDefault();
        return;
      }
      $$("button[type=submit]", e.target).forEach((btn) => (btn.disabled = true));
    });
  });
})();
