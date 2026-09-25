(function () {
  const { api, toast, esc, fmtDateTime, hours, gpuLabel } = U;

  function tile(label, value, sub, pct) {
    return `<div class="card tile"><div class="label">${label}</div><div class="value">${value}</div>${pct != null ? `<div class="bar${pct > 90 ? " hot" : ""}"><i style="width:${Math.min(100, pct)}%"></i></div>` : ""}${sub ? `<div class="small muted" style="margin-top:4px">${sub}</div>` : ""}</div>`;
  }

  async function load() {
    const me = await api("GET", "/api/me");
    const r = me.rules;
    document.getElementById("quota-tiles").innerHTML = [
      tile("本週已預約", `${me.week_gpu_hours} GPU·小時`, APP.isAdmin ? "管理員不受配額限制" : `上限 ${r.max_gpu_hours_per_week}`, APP.isAdmin ? null : (me.week_gpu_hours / r.max_gpu_hours_per_week) * 100),
      tile("單次最長", `${r.max_hours_per_booking} 小時`),
      tile("可提前預約", `${r.max_days_ahead} 天`),
      tile("單次最多", r.max_gpus_per_booking ? `${r.max_gpus_per_booking} 張 GPU` : "不限張數"),
    ].join("");

    const now = new Date();
    const rows = me.bookings.map((b) => {
      const s = new Date(b.start), e = new Date(b.end);
      const state = e <= now ? `<span class="chip">已結束</span>` : s <= now ? `<span class="chip good">● 進行中</span>` : `<span class="chip">即將開始</span>`;
      const action = e <= now ? "" : `<button class="danger" data-id="${b.id}" data-running="${s <= now}">${s <= now ? "提前結束" : "取消"}</button>`;
      return `<tr><td>${state}</td><td>${esc(gpuLabel(b.gpus))}</td><td class="num">${fmtDateTime(s)}</td><td class="num">${fmtDateTime(e)}</td><td class="num">${hours(s, e).toFixed(1)}</td><td>${b.mem_gb ? `<span class="muted small">需 ${b.mem_gb} GB${b.local_insufficient ? "（本地跑不動）" : ""}</span><br>` : ""}${esc(b.purpose)}</td><td>${action}</td></tr>`;
    });
    document.getElementById("my-rows").innerHTML = rows.join("") || `<tr><td colspan="7" class="muted">還沒有預約，<a href="/calendar">去預約</a></td></tr>`;
  }

  document.getElementById("my-rows").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-id]");
    if (!btn) return;
    const running = btn.dataset.running === "true";
    if (!confirm(running ? "確定要現在結束這個預約？" : "確定要取消這個預約？")) return;
    try {
      await api("DELETE", `/api/bookings/${btn.dataset.id}`);
      toast(running ? "已提前結束" : "已取消預約");
      load();
    } catch (e) { toast(e.message, true); }
  });

  load().catch((e) => toast(e.message, true));
})();
