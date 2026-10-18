/* SE-Tracker overview — charts (Chart.js), sparklines, and the admin student table.
   Colors come from CSS tokens, so light/dark mode is one source of truth. */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const dataEl = $("#overview-data");
  if (!dataEl) return;
  const data = JSON.parse(dataEl.textContent);
  const MAX = data.max_score;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const STATUS = ["active", "risk", "low", "none"];

  function tokens() {
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    return {
      ink: v("--text"),
      ink2: v("--text-2"),
      muted: v("--muted"),
      grid: v("--chart-grid"),
      axis: v("--chart-axis"),
      surface: v("--surface"),
      raised: v("--surface-raised"),
      border: v("--border"),
      s1: v("--series-1"),
      s2: v("--series-2"),
      s1soft: v("--series-1-soft"),
      status: { active: v("--status-active"), risk: v("--status-risk"), low: v("--status-low"), none: v("--status-none") },
      lowBand: v("--status-low-band"),
    };
  }

  /* ---------- shared chart config ---------- */

  function baseOptions(t) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: reduceMotion ? false : { duration: 900, easing: "easeOutQuart" },
      layout: { padding: { top: 4, right: 8 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: t.raised,
          titleColor: t.ink,
          bodyColor: t.ink2,
          borderColor: t.border,
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
          titleFont: { weight: "600" },
          boxPadding: 4,
          usePointStyle: true,
        },
      },
    };
  }

  function axis(t, extra) {
    return Object.assign(
      {
        grid: { color: t.grid, drawTicks: false },
        border: { color: t.axis },
        ticks: { color: t.muted, padding: 6, font: { size: 11 } },
      },
      extra || {}
    );
  }

  // Dashed reference lines (score thresholds, attendance midpoint) with a tiny label.
  const refLines = {
    id: "refLines",
    afterDatasetsDraw(chart, _args, opts) {
      const { ctx, chartArea: a, scales } = chart;
      (opts.lines || []).forEach((line) => {
        const scale = scales[line.axis];
        if (!scale) return;
        const p = scale.getPixelForValue(line.value);
        ctx.save();
        ctx.strokeStyle = line.color;
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        if (line.axis === "x") {
          ctx.moveTo(p, a.top);
          ctx.lineTo(p, a.bottom);
        } else {
          ctx.moveTo(a.left, p);
          ctx.lineTo(a.right, p);
        }
        ctx.stroke();
        if (line.label) {
          ctx.setLineDash([]);
          ctx.fillStyle = line.color;
          ctx.font = "500 10px Inter, system-ui, sans-serif";
          if (line.axis === "x") {
            ctx.textAlign = "center";
            ctx.fillText(line.label, p, a.top - 2 > 8 ? a.top - 2 : a.top + 10);
          } else {
            ctx.textAlign = "right";
            ctx.fillText(line.label, a.right - 2, p - 4);
          }
        }
        ctx.restore();
      });
    },
  };

  // Faint band behind a y-range (the "Low" zone on the scatter).
  const bandPlugin = {
    id: "band",
    beforeDatasetsDraw(chart, _args, opts) {
      if (!opts || opts.to === undefined) return;
      const { ctx, chartArea: a, scales } = chart;
      const top = scales.y.getPixelForValue(opts.to);
      const bottom = scales.y.getPixelForValue(opts.from);
      ctx.save();
      ctx.fillStyle = opts.color;
      ctx.fillRect(a.left, top, a.right - a.left, bottom - top);
      ctx.restore();
    },
  };

  function teamUrl(id) {
    const team = data.teams.find((t) => t.id === id);
    return team && team.url;
  }

  /* ---------- the charts ---------- */

  let charts = [];

  function rankChart(t) {
    const el = $("#c-rank");
    if (!el) return;
    const rows = data.teams.slice().sort((a, b) => (b.avg ?? -1) - (a.avg ?? -1));
    const opts = baseOptions(t);
    opts.indexAxis = "y";
    opts.layout.padding.top = 16;
    opts.scales = {
      x: axis(t, { min: 0, max: MAX, ticks: { color: t.muted, stepSize: 1, font: { size: 11 } } }),
      y: axis(t, { grid: { display: false }, ticks: { color: t.ink2, font: { size: 12, weight: "500" } } }),
    };
    opts.plugins.refLines = {
      lines: [
        { axis: "x", value: 2.5, color: t.status.low, label: "2.5" },
        { axis: "x", value: 4, color: t.status.active, label: "4" },
      ],
    };
    opts.plugins.tooltip.callbacks = {
      title: (items) => {
        const r = rows[items[0].dataIndex];
        return "Team " + r.number + (r.project ? " · " + r.project : "");
      },
      label: (item) => {
        const r = rows[item.dataIndex];
        return [
          "Avg " + (r.avg ?? "—") + " / " + MAX,
          "Attendance " + (r.attendance ?? "—") + "%",
          r.flagged + " flagged · " + r.calls + " calls",
        ];
      },
    };
    opts.onClick = (_e, els) => {
      if (els.length) window.location = rows[els[0].index].url;
    };
    opts.onHover = (e, els) => (e.native.target.style.cursor = els.length ? "pointer" : "default");
    charts.push(
      new Chart(el, {
        type: "bar",
        data: {
          labels: rows.map((r) => "Team " + r.number),
          datasets: [{
            data: rows.map((r) => r.avg ?? 0),
            backgroundColor: t.s1,
            hoverBackgroundColor: t.s1,
            borderRadius: 4,
            borderSkipped: "start",
            barThickness: 16,
          }],
        },
        options: opts,
        plugins: [refLines],
      })
    );
  }

  function statusChart(t) {
    const el = $("#c-status");
    if (!el) return;
    const rows = data.teams;
    const opts = baseOptions(t);
    opts.indexAxis = "y";
    opts.scales = {
      x: axis(t, { stacked: true, ticks: { color: t.muted, precision: 0, font: { size: 11 } } }),
      y: axis(t, { stacked: true, grid: { display: false }, ticks: { color: t.ink2, font: { size: 12, weight: "500" } } }),
    };
    opts.plugins.legend = {
      display: true,
      position: "bottom",
      labels: { color: t.ink2, usePointStyle: true, pointStyle: "rectRounded", boxWidth: 10, boxHeight: 10, padding: 14, font: { size: 12 } },
    };
    opts.plugins.tooltip.mode = "index";
    opts.plugins.tooltip.callbacks = {
      title: (items) => "Team " + rows[items[0].dataIndex].number,
    };
    opts.onClick = (_e, els) => {
      if (els.length) window.location = rows[els[0].index].url;
    };
    charts.push(
      new Chart(el, {
        type: "bar",
        data: {
          labels: rows.map((r) => "Team " + r.number),
          datasets: STATUS.map((key) => ({
            label: data.status_labels[key],
            data: rows.map((r) => r.status_counts[key]),
            backgroundColor: t.status[key],
            borderColor: t.surface,
            borderWidth: { left: 0, right: 2, top: 0, bottom: 0 },
            borderSkipped: false,
            barThickness: 16,
          })),
        },
        options: opts,
      })
    );
  }

  // Deterministic jitter so many "100% attendance" students don't stack into one dot.
  function jitter(id, spread) {
    const x = Math.sin(id * 12.9898) * 43758.5453;
    return (x - Math.floor(x) - 0.5) * spread;
  }

  function scatterChart(t) {
    const el = $("#c-scatter");
    if (!el) return;
    const scored = data.students.filter((s) => s.avg !== null && s.attendance !== null);
    const opts = baseOptions(t);
    opts.layout.padding.top = 14;
    opts.scales = {
      x: axis(t, { min: -4, max: 104, title: { display: true, text: "Attendance %", color: t.muted, font: { size: 11 } },
        ticks: { color: t.muted, stepSize: 25, font: { size: 11 }, callback: (v) => (v >= 0 && v <= 100 && v % 25 === 0 ? v : "") } }),
      y: axis(t, { min: 0, max: MAX, title: { display: true, text: "Avg score", color: t.muted, font: { size: 11 } },
        ticks: { color: t.muted, stepSize: 1, font: { size: 11 } } }),
    };
    opts.plugins.band = { from: 0, to: 2.5, color: t.lowBand };
    opts.plugins.refLines = {
      lines: [
        { axis: "y", value: 4, color: t.status.active, label: "Active ≥ 4" },
        { axis: "y", value: 2.5, color: t.status.low, label: "Low < 2.5" },
        { axis: "x", value: 50, color: t.muted, label: "50%" },
      ],
    };
    opts.plugins.tooltip.callbacks = {
      title: (items) => items[0].raw.s.name,
      label: (item) => {
        const s = item.raw.s;
        return ["Team " + s.team + (s.ta ? " · " + s.ta : ""), "Avg " + s.avg_display + " · Attendance " + s.attendance + "%"];
      },
    };
    opts.onClick = (_e, els) => {
      if (!els.length) return;
      const ds = charts.find((c) => c.canvas === el).data.datasets[els[0].datasetIndex];
      const url = teamUrl(ds.data[els[0].index].s.team_id);
      if (url) window.location = url;
    };
    opts.onHover = (e, els) => (e.native.target.style.cursor = els.length ? "pointer" : "default");
    charts.push(
      new Chart(el, {
        type: "scatter",
        data: {
          datasets: ["active", "risk", "low"].map((key) => ({
            label: data.status_labels[key],
            data: scored
              .filter((s) => s.status === key)
              .map((s) => ({ x: Math.min(100, Math.max(0, s.attendance + jitter(s.id, 4))), y: s.avg, s: s })),
            backgroundColor: t.status[key],
            borderColor: t.surface,
            borderWidth: 2,
            pointRadius: 5.5,
            pointHoverRadius: 7.5,
            pointHitRadius: 8,
          })),
        },
        options: opts,
        plugins: [bandPlugin, refLines],
      })
    );
  }

  function lineChart(el, t, labels, datasets, yMax, suffix) {
    const opts = baseOptions(t);
    opts.interaction = { mode: "index", intersect: false };
    opts.scales = {
      x: axis(t, { grid: { display: false } }),
      y: axis(t, { min: 0, max: yMax, ticks: { color: t.muted, maxTicksLimit: 5, font: { size: 11 } } }),
    };
    opts.plugins.tooltip.callbacks = {
      title: (items) => "Call " + items[0].label,
      label: (item) => " " + item.dataset.label + ": " + (item.raw ?? "—") + suffix,
    };
    charts.push(new Chart(el, { type: "line", data: { labels: labels, datasets: datasets }, options: opts, plugins: [crosshair] }));
  }

  const crosshair = {
    id: "crosshair",
    afterDatasetsDraw(chart) {
      const active = chart.tooltip && chart.tooltip.getActiveElements();
      if (!active || !active.length) return;
      const { ctx, chartArea: a } = chart;
      const x = active[0].element.x;
      ctx.save();
      ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--chart-axis");
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, a.top);
      ctx.lineTo(x, a.bottom);
      ctx.stroke();
      ctx.restore();
    },
  };

  function lineSeries(label, values, color, fill, t) {
    return {
      label: label,
      data: values,
      borderColor: color,
      backgroundColor: fill || color,
      fill: !!fill,
      borderWidth: 2,
      tension: 0.3,
      pointRadius: values.length > 14 ? 0 : 3,
      pointHoverRadius: 5,
      pointBackgroundColor: color,
      pointBorderColor: t.surface,
      pointBorderWidth: 2,
      spanGaps: true,
    };
  }

  function trendCharts(t) {
    const labels = data.trend.map((r) => "#" + r.call);
    const trendEl = $("#c-trend");
    if (trendEl)
      lineChart(trendEl, t, labels, [
        lineSeries("Attendance", data.trend.map((r) => r.attendance), t.s1, null, t),
        lineSeries("Spoke", data.trend.map((r) => r.speaking), t.s2, null, t),
      ], 100, "%");
    const scoreEl = $("#c-score");
    if (scoreEl)
      lineChart(scoreEl, t, labels, [lineSeries("Avg score", data.trend.map((r) => r.avg), t.s1, t.s1soft, t)], MAX, "");
  }

  function weeklyChart(t) {
    const el = $("#c-weekly");
    if (!el || !data.admin) return;
    const rows = data.admin.activity;
    const opts = baseOptions(t);
    opts.scales = {
      x: axis(t, { grid: { display: false }, ticks: { color: t.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: 6, font: { size: 11 } } }),
      y: axis(t, { beginAtZero: true, ticks: { color: t.muted, precision: 0, maxTicksLimit: 5, font: { size: 11 } } }),
    };
    opts.plugins.tooltip.callbacks = {
      title: (items) => "Week of " + items[0].label,
      label: (item) => " " + item.raw + " call" + (item.raw === 1 ? "" : "s"),
    };
    charts.push(
      new Chart(el, {
        type: "bar",
        data: {
          labels: rows.map((r) => r.label),
          datasets: [{ data: rows.map((r) => r.calls), backgroundColor: t.s1, borderRadius: 4, borderSkipped: "start", maxBarThickness: 22 }],
        },
        options: opts,
      })
    );
  }

  function render() {
    if (!window.Chart) return;
    charts.forEach((c) => c.destroy());
    charts = [];
    const t = tokens();
    Chart.defaults.font.family = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif";
    Chart.defaults.color = t.muted;
    rankChart(t);
    statusChart(t);
    scatterChart(t);
    trendCharts(t);
    weeklyChart(t);
  }

  /* ---------- sparklines (per-call totals; gaps = absent) ---------- */

  function sparklines() {
    $$("svg.spark").forEach((svg) => {
      let series;
      try {
        series = JSON.parse(svg.dataset.series || "[]");
      } catch (e) {
        return;
      }
      const max = parseFloat(svg.dataset.max) || 7;
      const n = series.length;
      svg.innerHTML = "";
      if (!n) return;
      const W = 80, H = 22, pad = 3;
      const x = (i) => (n === 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (n - 1));
      const y = (v) => H - pad - (v / max) * (H - 2 * pad);
      const ns = "http://www.w3.org/2000/svg";
      let d = "", pen = false;
      series.forEach((v, i) => {
        if (v === null) { pen = false; return; }
        d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
        pen = true;
      });
      const path = document.createElementNS(ns, "path");
      path.setAttribute("d", d);
      path.setAttribute("class", "spark-line");
      svg.appendChild(path);
      series.forEach((v, i) => {
        if (v !== null && i !== n - 1) return;
        const c = document.createElementNS(ns, "circle");
        c.setAttribute("cx", x(i));
        c.setAttribute("cy", v === null ? H - 2 : y(v));
        c.setAttribute("r", v === null ? 1.6 : 2.2);
        c.setAttribute("class", v === null ? "spark-gap" : "spark-end");
        svg.appendChild(c);
      });
    });
  }

  /* ---------- admin: student table search / filter / sort ---------- */

  function studentTable() {
    const table = $("#student-table");
    if (!table) return;
    const rows = $$("tbody tr", table);
    const search = $("#student-search");
    const empty = $("#student-empty");
    let status = "";

    function apply() {
      const q = (search.value || "").trim().toLowerCase();
      let shown = 0;
      rows.forEach((tr) => {
        const okStatus = !status || (status === "flagged" ? tr.dataset.flagged === "1" : tr.dataset.status === status);
        const okText = !q || tr.textContent.toLowerCase().includes(q);
        tr.hidden = !(okStatus && okText);
        if (!tr.hidden) shown += 1;
      });
      empty.hidden = shown > 0;
    }
    search.addEventListener("input", apply);
    $$("#status-filter [data-status]").forEach((btn) =>
      btn.addEventListener("click", () => {
        status = btn.dataset.status;
        $$("#status-filter [data-status]").forEach((b) => b.classList.toggle("active", b === btn));
        apply();
      })
    );

    $$("th[data-sort]", table).forEach((th, _i) => {
      th.tabIndex = 0;
      const idx = Array.from(th.parentNode.children).indexOf(th);
      const sort = () => {
        const dir = th.dataset.dir === "asc" ? "desc" : "asc";
        $$("th[data-sort]", table).forEach((h) => delete h.dataset.dir);
        th.dataset.dir = dir;
        const num = th.dataset.sort === "num";
        const val = (tr) => tr.children[idx].dataset.v ?? tr.children[idx].textContent;
        const sorted = rows.slice().sort((a, b) => {
          const va = val(a), vb = val(b);
          const cmp = num ? parseFloat(va) - parseFloat(vb) : String(va).localeCompare(String(vb), undefined, { numeric: true });
          return dir === "asc" ? cmp : -cmp;
        });
        const body = $("tbody", table);
        sorted.forEach((tr) => body.appendChild(tr));
      };
      th.addEventListener("click", sort);
      th.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
      });
    });
  }

  function init() {
    sparklines();
    studentTable();
    render();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", render);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
