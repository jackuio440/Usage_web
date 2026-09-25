(function () {
  const { api, toast, esc, fmtDate } = U;

  let localLimit = null;

  async function load() {
    if (localLimit === null) localLimit = (await api("GET", "/api/me")).rules.local_gpu_mem_gb || 0;
    const weeks = document.getElementById("weeks").value;
    const d = await api("GET", `/api/stats?weeks=${weeks}`);
    const out = d.weeks.map((w) => {
      const ws = new Date(w.week_start);
      const we = new Date(ws.getTime() + 6 * 864e5);
      const max = Math.max(1, ...w.users.map((u) => Math.max(u.booked, u.used)));
      const rows = w.users.map((u) => `<tr>
          <td><b>${esc(u.username)}</b></td>
          <td class="num">${u.booked}</td>
          <td class="num">${u.used}</td>
          <td class="num">${u.unbooked > 0 ? `<span class="chip warn">⚠ ${u.unbooked}</span>` : "0"}</td>
          <td class="num">${u.used > 0 ? `${u.peak_mem_gb} GB${localLimit && u.peak_mem_gb <= localLimit ? ` <span class="chip" title="${T("stats.local_ok_title", { limit: localLimit })}">${T("stats.local_ok")}</span>` : ""}` : "—"}</td>
          <td><div class="hbar" title="${T("stats.bar_title", { b: u.booked, u: u.used })}"><i class="b" style="width:${(u.booked / max) * 100}%"></i><i class="u" style="width:${(u.used / max) * 100}%"></i></div></td>
        </tr>`).join("");
      return `<div class="card"><h2>${fmtDate(ws)} – ${fmtDate(we)}</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>${T("stats.col_user")}</th><th>${T("stats.col_booked")}</th><th>${T("stats.col_used")}</th><th>${T("stats.col_unbooked")}</th><th>${T("stats.col_peak")}</th><th style="width:34%"></th></tr></thead>
          <tbody>${rows || `<tr><td colspan="6" class="muted">${T("stats.empty")}</td></tr>`}</tbody>
        </table></div></div>`;
    });
    document.getElementById("weeks-out").innerHTML = out.join("");
  }

  document.getElementById("weeks").onchange = () => load().catch((e) => toast(e.message, true));
  load().catch((e) => toast(e.message, true));
})();
