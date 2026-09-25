(function () {
  const { api, toast, esc, fmtDateTime, hours, gpuLabel } = U;

  function tile(label, value, sub, pct) {
    return `<div class="card tile"><div class="label">${label}</div><div class="value">${value}</div>${pct != null ? `<div class="bar${pct > 90 ? " hot" : ""}"><i style="width:${Math.min(100, pct)}%"></i></div>` : ""}${sub ? `<div class="small muted" style="margin-top:4px">${sub}</div>` : ""}</div>`;
  }

  async function load() {
    const me = await api("GET", "/api/me");
    const r = me.rules;
    document.getElementById("quota-tiles").innerHTML = [
      tile(T("my.week_used"), T("my.gpu_hours", { n: me.week_gpu_hours }), APP.isAdmin ? T("my.admin_no_quota") : T("my.limit", { n: r.max_gpu_hours_per_week }), APP.isAdmin ? null : (me.week_gpu_hours / r.max_gpu_hours_per_week) * 100),
      tile(T("my.per_booking"), T("my.hours_n", { n: r.max_hours_per_booking })),
      tile(T("my.ahead"), T("my.days_n", { n: r.max_days_ahead })),
      tile(T("my.max_gpus"), r.max_gpus_per_booking ? T("my.gpus_n", { n: r.max_gpus_per_booking }) : T("my.gpus_any")),
    ].join("");

    const now = new Date();
    const rows = me.bookings.map((b) => {
      const s = new Date(b.start), e = new Date(b.end);
      const state = e <= now ? `<span class="chip">${T("my.state_ended")}</span>` : s <= now ? `<span class="chip good">${T("my.state_running")}</span>` : `<span class="chip">${T("my.state_upcoming")}</span>`;
      const action = e <= now ? "" : `<button class="danger" data-id="${b.id}" data-running="${s <= now}">${T(s <= now ? "cal.end_now" : "common.cancel")}</button>`;
      return `<tr><td>${state}</td><td>${esc(gpuLabel(b.gpus))}</td><td class="num">${fmtDateTime(s)}</td><td class="num">${fmtDateTime(e)}</td><td class="num">${hours(s, e).toFixed(1)}</td><td>${b.mem_gb ? `<span class="muted small">${T("cal.needs_mem", { gb: b.mem_gb })}</span><br>` : ""}${esc(b.purpose)}</td><td>${action}</td></tr>`;
    });
    document.getElementById("my-rows").innerHTML = rows.join("") || `<tr><td colspan="7" class="muted">${T("my.empty")}<a href="/calendar">${T("my.go_book")}</a></td></tr>`;
  }

  document.getElementById("my-rows").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-id]");
    if (!btn) return;
    const running = btn.dataset.running === "true";
    if (!confirm(T(running ? "cal.confirm_end" : "cal.confirm_cancel"))) return;
    try {
      await api("DELETE", `/api/bookings/${btn.dataset.id}`);
      toast(T(running ? "cal.ended" : "cal.cancelled"));
      load();
    } catch (e) { toast(e.message, true); }
  });

  load().catch((e) => toast(e.message, true));
})();
