(function () {
  const { api, toast, esc, fmtDateTime, fmtRange, toInput, fromInput, gpuLabel } = U;
  const rulesForm = document.getElementById("rules-form");

  async function loadRules() {
    const { rules } = await api("GET", "/api/admin/rules");
    for (const [k, v] of Object.entries(rules)) {
      const el = rulesForm.elements[k];
      if (!el) continue;
      if (el.type === "checkbox") el.checked = v; else el.value = v;
    }
  }
  rulesForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const el = rulesForm.elements;
    try {
      await api("PUT", "/api/admin/rules", {
        max_hours_per_booking: Number(el.max_hours_per_booking.value),
        max_gpu_hours_per_week: Number(el.max_gpu_hours_per_week.value),
        max_days_ahead: Number(el.max_days_ahead.value),
        max_gpus_per_booking: Number(el.max_gpus_per_booking.value),
        flag_unbooked_on_free_gpu: el.flag_unbooked_on_free_gpu.checked,
        local_gpu_mem_gb: Number(el.local_gpu_mem_gb.value),
      });
      toast("規則已儲存");
      loadAudit();
    } catch (e) { toast(e.message, true); }
  });

  async function loadAnnouncements() {
    const list = await api("GET", "/api/announcements");
    document.getElementById("ann-list").innerHTML = list.map((a) =>
      `<div class="notice announce">${esc(a.body)}<div class="row muted"><span>${esc(a.created_by)} · ${fmtDateTime(a.created_at)}</span><span class="spacer"></span><button class="link danger" data-ann="${a.id}">刪除</button></div></div>`
    ).join("") || `<span class="muted">沒有公告</span>`;
  }
  document.getElementById("ann-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api("POST", "/api/admin/announcements", { body: ev.target.elements.body.value });
      ev.target.reset();
      toast("已發布");
      loadAnnouncements(); loadAudit();
    } catch (e) { toast(e.message, true); }
  });
  document.getElementById("ann-list").addEventListener("click", async (ev) => {
    const id = ev.target.dataset.ann;
    if (!id || !confirm("刪除這則公告？")) return;
    try { await api("DELETE", `/api/admin/announcements/${id}`); loadAnnouncements(); loadAudit(); }
    catch (e) { toast(e.message, true); }
  });

  async function loadBlackouts() {
    const list = await api("GET", "/api/admin/blackouts");
    document.getElementById("bo-list").innerHTML = list.map((b) =>
      `<div class="notice maint"><b>${fmtRange(b.start, b.end)}</b> ${esc(b.reason)}<div class="row muted"><span>${esc(b.created_by)}</span><span class="spacer"></span><button class="link danger" data-bo="${b.id}">刪除</button></div></div>`
    ).join("") || `<span class="muted">沒有維護時段</span>`;
  }
  const boForm = document.getElementById("bo-form");
  boForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const el = boForm.elements;
    try {
      const r = await api("POST", "/api/admin/blackouts", {
        start: fromInput(el.start.value).toISOString(),
        end: fromInput(el.end.value).toISOString(),
        reason: el.reason.value,
      });
      boForm.reset();
      toast("已新增維護時段");
      showConflicts(r.conflicting_bookings);
      loadBlackouts(); loadAudit();
    } catch (e) { toast(e.message, true); }
  });
  function showConflicts(list) {
    const box = document.getElementById("bo-conflicts");
    if (!list.length) { box.innerHTML = ""; return; }
    box.innerHTML = `<div class="notice error small" style="margin-top:12px">以下預約與維護時段重疊：
      ${list.map((b) => `<div class="row"><span>${esc(b.username)} · ${esc(gpuLabel(b.gpus))} · ${fmtRange(b.start, b.end)}</span><span class="spacer"></span><button class="link danger" data-cancel="${b.id}">取消這筆</button></div>`).join("")}</div>`;
  }
  document.getElementById("bo-conflicts").addEventListener("click", async (ev) => {
    const id = ev.target.dataset.cancel;
    if (!id) return;
    try {
      await api("DELETE", `/api/bookings/${id}`);
      ev.target.closest(".row").remove();
      toast("已取消");
      loadAudit();
    } catch (e) { toast(e.message, true); }
  });
  document.getElementById("bo-list").addEventListener("click", async (ev) => {
    const id = ev.target.dataset.bo;
    if (!id || !confirm("刪除這個維護時段？")) return;
    try { await api("DELETE", `/api/admin/blackouts/${id}`); loadBlackouts(); loadAudit(); }
    catch (e) { toast(e.message, true); }
  });

  const ACTIONS = {
    create_booking: "新增預約", update_booking: "修改預約", delete_booking: "取消預約", end_booking_early: "提前結束",
    update_rules: "修改規則", create_blackout: "新增維護", delete_blackout: "刪除維護",
    create_announcement: "發布公告", delete_announcement: "刪除公告",
  };
  async function loadAudit() {
    const rows = await api("GET", "/api/admin/audit?limit=200");
    document.getElementById("audit-rows").innerHTML = rows.map((r) =>
      `<tr><td class="num" style="white-space:nowrap">${fmtDateTime(r.ts)}</td><td>${esc(r.actor)}</td><td>${esc(ACTIONS[r.action] || r.action)}</td><td class="small">${esc(r.detail)}</td></tr>`
    ).join("");
  }

  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1); tomorrow.setHours(18, 0, 0, 0);
  boForm.elements.start.value = toInput(tomorrow);
  boForm.elements.end.value = toInput(new Date(tomorrow.getTime() + 4 * 36e5));

  Promise.all([loadRules(), loadAnnouncements(), loadBlackouts(), loadAudit()]).catch((e) => toast(e.message, true));
})();
