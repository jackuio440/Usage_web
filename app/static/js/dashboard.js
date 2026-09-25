(function () {
  const { api, esc, fmtRange, fmtDateTime, fmtTime } = U;

  function meter(label, value, pct, hot) {
    pct = Math.max(0, Math.min(100, pct || 0));
    return `<div class="meter"><div class="meter-top"><span>${label}</span><span class="num">${value}</span></div>
      <div class="bar${hot ? " hot" : ""}" role="progressbar" aria-valuenow="${Math.round(pct)}" aria-valuemin="0" aria-valuemax="100" aria-label="${label}"><i style="width:${pct}%"></i></div></div>`;
  }

  function flagChip(flag) {
    if (flag === "unbooked") return `<span class="chip warn" title="這張卡目前沒人預約">⚠ 未預約</span>`;
    if (flag === "conflict") return `<span class="chip crit" title="這張卡目前是別人預約的">✕ 佔用</span>`;
    return "";
  }

  function gpuCard(g) {
    const memPct = g.mem_total_mb ? (g.mem_used_mb / g.mem_total_mb) * 100 : 0;
    const flags = g.processes.map((p) => p.flag);
    const cls = flags.includes("conflict") ? "flag-crit" : flags.includes("unbooked") ? "flag-warn" : "";
    const b = g.booking, nb = g.next_booking;
    let status;
    if (b) status = `<span class="chip ${b.username === APP.username ? "good" : ""}">已預約：${esc(b.username)}</span>`;
    else if (g.processes.length) status = `<span class="chip">使用中</span>`;
    else status = `<span class="chip good">● 空閒</span>`;

    const bookingLine = b
      ? `<div class="booking-line"><b>${esc(b.username)}</b> 預約到 ${fmtTime(b.end)}${b.purpose ? `<div class="muted small">${esc(b.purpose)}</div>` : ""}</div>`
      : `<div class="booking-line muted">目前沒有預約</div>`;
    const nextLine = nb ? `<div class="small muted">下一個：${esc(nb.username)}，${fmtRange(nb.start, nb.end)}</div>` : "";
    const procs = g.processes.length
      ? `<div class="procs">${g.processes
          .map((p) => `<div><b>${esc(p.username)}</b><span class="pname">${esc(p.name)} · PID ${p.pid}</span><span class="num">${Math.round(p.mem_mb).toLocaleString()} MB</span>${flagChip(p.flag)}</div>`)
          .join("")}</div>`
      : `<div class="procs muted">沒有程式在跑</div>`;

    return `<div class="card gpu-card ${cls}">
      <div class="gpu-head"><span class="idx">GPU ${g.index}</span><span class="name" title="${esc(g.name)}">${esc(g.name)}</span>${status}</div>
      ${meter("使用率", `${Math.round(g.util)}%`, g.util)}
      ${meter("記憶體", `${(g.mem_used_mb / 1024).toFixed(1)} / ${(g.mem_total_mb / 1024).toFixed(0)} GB`, memPct, memPct > 95)}
      <div class="facts">${g.temperature != null ? `<span>溫度 <span class="num">${Math.round(g.temperature)}°C</span></span>` : ""}${g.power_w != null ? `<span>功耗 <span class="num">${Math.round(g.power_w)} W</span></span>` : ""}</div>
      ${bookingLine}${nextLine}${procs}
      <div style="margin-top:10px"><a class="btn" href="/calendar?gpu=${g.index}">預約這張</a></div>
    </div>`;
  }

  function tile(label, value, sub, pct) {
    return `<div class="card tile"><div class="label">${label}</div><div class="value">${value}</div>${pct != null ? `<div class="bar${pct > 90 ? " hot" : ""}"><i style="width:${pct}%"></i></div>` : ""}${sub ? `<div class="small muted" style="margin-top:4px">${sub}</div>` : ""}</div>`;
  }

  function render(d) {
    const s = d.system;
    const tiles = [
      tile("CPU", `${Math.round(s.cpu_percent)}%`, `${s.cpu_count} 核心 · 負載 ${s.load_avg.join(" / ")}`, s.cpu_percent),
      tile("記憶體 (RAM)", `${s.mem_used_gb} / ${s.mem_total_gb} GB`, null, s.mem_percent),
      ...s.disks.map((k) => tile(`硬碟 ${esc(k.path)}`, `${k.percent}%`, `剩 ${(k.total_gb - k.used_gb).toFixed(0)} GB / 共 ${k.total_gb} GB`, k.percent)),
      tile("SSH 登入中", s.users_logged_in.length, esc(s.users_logged_in.join("、")) || "—"),
    ];
    document.getElementById("sys").innerHTML = tiles.join("");

    const notices = [];
    if (d.gpu_error) notices.push(`<div class="notice error">${esc(d.gpu_error)}</div>`);
    for (const b of d.blackouts) notices.push(`<div class="notice maint">🛠 維護時段：${fmtRange(b.start, b.end)}　${esc(b.reason)}</div>`);
    for (const a of d.announcements) notices.push(`<div class="notice announce">📢 ${esc(a.body)} <span class="muted small">— ${esc(a.created_by)}，${fmtDateTime(a.created_at)}</span></div>`);
    document.getElementById("notices").innerHTML = notices.join("");

    document.getElementById("gpus").innerHTML = d.gpus.length ? d.gpus.map(gpuCard).join("") : `<p class="muted">沒有偵測到 GPU</p>`;
    document.getElementById("updated").textContent = `更新於 ${new Date().toLocaleTimeString("zh-TW")}（每 10 秒）`;
  }

  async function refresh() {
    if (document.hidden) return;
    try { render(await api("GET", "/api/status")); }
    catch (e) { document.getElementById("updated").textContent = "更新失敗：" + e.message; }
  }
  refresh();
  setInterval(refresh, 10000);
  document.addEventListener("visibilitychange", refresh);
})();
