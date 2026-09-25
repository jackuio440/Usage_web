(function () {
  const { api, toast, esc, fmtDate } = U;

  async function load() {
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
          <td><div class="hbar" title="預約 ${u.booked}／實際 ${u.used} GPU·小時"><i class="b" style="width:${(u.booked / max) * 100}%"></i><i class="u" style="width:${(u.used / max) * 100}%"></i></div></td>
        </tr>`).join("");
      return `<div class="card"><h2>${fmtDate(ws)} – ${fmtDate(we)}</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>使用者</th><th>預約 (GPU·時)</th><th>實際使用 (GPU·時)</th><th>未預約使用</th><th style="width:40%"></th></tr></thead>
          <tbody>${rows || `<tr><td colspan="5" class="muted">這週沒有紀錄</td></tr>`}</tbody>
        </table></div></div>`;
    });
    document.getElementById("weeks-out").innerHTML = out.join("");
  }

  document.getElementById("weeks").onchange = () => load().catch((e) => toast(e.message, true));
  load().catch((e) => toast(e.message, true));
})();
