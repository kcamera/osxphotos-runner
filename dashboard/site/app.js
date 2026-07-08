/* Read-only dashboard: fetches data/status.json + data/history.jsonl
   (published by the Mini) and renders them. No framework, no service
   worker (plain-HTTP LAN has no secure context); manual refresh +
   refetch-on-focus keep it honest. */

"use strict";

const HISTORY_COLLAPSED = 20;
const $ = (id) => document.getElementById(id);
let showAllHistory = false;

function fmtAge(iso, now) {
  const dt = new Date(iso);
  const s = (now - dt) / 1000;
  if (isNaN(s)) return "?";
  if (s < 3600) return `${Math.max(0, Math.round(s / 60))} min ago`;
  if (s < 36 * 3600) return `${Math.round(s / 3600)} hours ago`;
  return `${Math.round(s / 86400)} days ago`;
}

function fmtWhen(iso) {
  const dt = new Date(iso);
  if (isNaN(dt)) return iso || "?";
  return dt.toLocaleString([], {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

function fmtDuration(s) {
  if (s == null) return "—";
  if (s < 90) return `${s}s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

function renderStatus(st, now) {
  const run = st.last_run || {};
  const badge = $("outcome");
  badge.textContent = run.outcome || "unknown";
  badge.className = `badge ${run.outcome || ""}`;

  $("last-when").textContent = run.started_at
    ? `${fmtAge(run.started_at, now)} — ${fmtWhen(run.started_at)}`
    : "never";
  // "exported" counts files (original + AAE + XMP sidecars), not photos.
  $("last-detail").textContent = run.started_at
    ? `${run.processed ?? "?"} photos processed · ${run.exported ?? "?"} files exported · ` +
      `${run.skipped ?? "?"} skipped · ${fmtDuration(run.duration_s)}`
    : "No runs recorded yet.";

  const failure = $("failure");
  failure.classList.toggle("hidden", !run.failure_reason);
  failure.textContent = run.failure_reason || "";

  const cov = st.coverage || {};
  if (cov.exported_in_library != null && cov.library_total) {
    const pct = (100 * cov.exported_in_library) / cov.library_total;
    $("coverage-fill").style.width = `${pct.toFixed(1)}%`;
    $("coverage-num").textContent =
      `${cov.exported_in_library.toLocaleString()} / ${cov.library_total.toLocaleString()} (${pct.toFixed(1)}%)`;
  } else {
    $("coverage-num").textContent = "unknown";
  }
  const lib = st.library || {};
  $("library-detail").textContent = lib.library_total
    ? `Library: ${lib.library_total.toLocaleString()} photos & videos (shared excluded)` +
      (lib.missing ? ` · ${lib.missing} missing originals` : "")
    : "";

  const sched = st.schedule || {};
  $("next-run").textContent = sched.next_run ? fmtWhen(sched.next_run) : "unscheduled";
  const app = st.app || {};
  $("app-detail").textContent =
    `runner v${app.version ?? "?"} · every ${sched.interval_days ?? 7} days`;

  // Stale = no run started within interval + 1 day.
  const stale = $("stale");
  const intervalDays = sched.interval_days ?? 7;
  if (run.started_at) {
    const ageDays = (now - new Date(run.started_at)) / 86400e3;
    const isStale = ageDays > intervalDays + 1;
    stale.classList.toggle("hidden", !isStale);
    if (isStale) {
      stale.textContent =
        `⚠️ No backup for ${Math.floor(ageDays)} days (expected every ${intervalDays}). ` +
        "Check the Mini's menu bar app.";
    }
  }
}

function renderHistory(entries) {
  const newest = entries.slice().reverse();
  const shown = showAllHistory ? newest : newest.slice(0, HISTORY_COLLAPSED);
  const tbody = $("history").querySelector("tbody");
  tbody.replaceChildren(
    ...shown.map((e) => {
      const tr = document.createElement("tr");
      const cells = [
        [fmtWhen(e.started_at), ""],
        [e.outcome || "?", `outcome-${e.outcome}`],
        [e.outcome === "succeeded" ? String(e.exported ?? "?") : "—", ""],
        [e.outcome === "interrupted" ? "—" : fmtDuration(e.duration_s), ""],
      ];
      for (const [text, cls] of cells) {
        const td = document.createElement("td");
        td.textContent = text;
        if (cls) td.className = cls;
        tr.appendChild(td);
      }
      return tr;
    })
  );
  $("history-count").textContent = `${entries.length} runs`;
  const btn = $("show-all");
  btn.classList.toggle("hidden", showAllHistory || newest.length <= HISTORY_COLLAPSED);
}

async function refresh() {
  const bust = `?t=${Date.now()}`;
  const now = new Date();
  try {
    const [stRes, histRes] = await Promise.all([
      fetch(`data/status.json${bust}`),
      fetch(`data/history.jsonl${bust}`),
    ]);
    if (!stRes.ok) throw new Error(`status.json: HTTP ${stRes.status}`);
    renderStatus(await stRes.json(), now);

    if (histRes.ok) {
      const lines = (await histRes.text()).split("\n").filter((l) => l.trim());
      const entries = [];
      for (const line of lines) {
        try { entries.push(JSON.parse(line)); } catch { /* torn last line */ }
      }
      renderHistory(entries);
    }
    $("error").classList.add("hidden");
    $("refreshed").textContent = `updated ${now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  } catch (err) {
    const box = $("error");
    box.textContent = `Can't load backup data: ${err.message}`;
    box.classList.remove("hidden");
  }
}

$("show-all").addEventListener("click", () => {
  showAllHistory = true;
  refresh();
});
window.addEventListener("focus", refresh);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
refresh();
setInterval(refresh, 5 * 60 * 1000);
