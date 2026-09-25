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
      toast(T("admin.rules_saved"));
      loadAudit();
    } catch (e) { toast(e.message, true); }
  });

  async function loadAnnouncements() {
    const list = await api("GET", "/api/announcements");
    document.getElementById("ann-list").innerHTML = list.map((a) =>
      `<div class="notice announce">${esc(a.body)}<div class="row muted"><span>${esc(a.created_by)} · ${fmtDateTime(a.created_at)}</span><span class="spacer"></span><button class="link danger" data-ann="${a.id}">${T("common.delete")}</button></div></div>`
    ).join("") || `<span class="muted">${T("admin.ann_empty")}</span>`;
  }
  document.getElementById("ann-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api("POST", "/api/admin/announcements", { body: ev.target.elements.body.value });
      ev.target.reset();
      toast(T("admin.ann_posted"));
      loadAnnouncements(); loadAudit();
    } catch (e) { toast(e.message, true); }
  });
  document.getElementById("ann-list").addEventListener("click", async (ev) => {
    const id = ev.target.dataset.ann;
    if (!id || !confirm(T("admin.ann_confirm"))) return;
    try { await api("DELETE", `/api/admin/announcements/${id}`); loadAnnouncements(); loadAudit(); }
    catch (e) { toast(e.message, true); }
  });

  async function loadBlackouts() {
    const list = await api("GET", "/api/admin/blackouts");
    document.getElementById("bo-list").innerHTML = list.map((b) =>
      `<div class="notice maint"><b>${fmtRange(b.start, b.end)}</b> ${esc(b.reason)}<div class="row muted"><span>${esc(b.created_by)}</span><span class="spacer"></span><button class="link danger" data-bo="${b.id}">${T("common.delete")}</button></div></div>`
    ).join("") || `<span class="muted">${T("admin.maint_empty")}</span>`;
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
      toast(T("admin.maint_added"));
      showConflicts(r.conflicting_bookings);
      loadBlackouts(); loadAudit();
    } catch (e) { toast(e.message, true); }
  });
  function showConflicts(list) {
    const box = document.getElementById("bo-conflicts");
    if (!list.length) { box.innerHTML = ""; return; }
    box.innerHTML = `<div class="notice error small" style="margin-top:12px">${T("admin.maint_conflicts")}
      ${list.map((b) => `<div class="row"><span>${esc(b.username)} · ${esc(gpuLabel(b.gpus))} · ${fmtRange(b.start, b.end)}</span><span class="spacer"></span><button class="link danger" data-cancel="${b.id}">${T("admin.cancel_this")}</button></div>`).join("")}</div>`;
  }
  document.getElementById("bo-conflicts").addEventListener("click", async (ev) => {
    const id = ev.target.dataset.cancel;
    if (!id) return;
    try {
      await api("DELETE", `/api/bookings/${id}`);
      ev.target.closest(".row").remove();
      toast(T("admin.cancelled"));
      loadAudit();
    } catch (e) { toast(e.message, true); }
  });
  document.getElementById("bo-list").addEventListener("click", async (ev) => {
    const id = ev.target.dataset.bo;
    if (!id || !confirm(T("admin.maint_confirm"))) return;
    try { await api("DELETE", `/api/admin/blackouts/${id}`); loadBlackouts(); loadAudit(); }
    catch (e) { toast(e.message, true); }
  });

  async function loadAudit() {
    const rows = await api("GET", "/api/admin/audit?limit=200");
    document.getElementById("audit-rows").innerHTML = rows.map((r) =>
      `<tr><td class="num" style="white-space:nowrap">${fmtDateTime(r.ts)}</td><td>${esc(r.actor)}</td><td>${esc(I18N["audit." + r.action] || r.action)}</td><td class="small">${esc(r.detail)}</td></tr>`
    ).join("");
  }

  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1); tomorrow.setHours(18, 0, 0, 0);
  boForm.elements.start.value = toInput(tomorrow);
  boForm.elements.end.value = toInput(new Date(tomorrow.getTime() + 4 * 36e5));

  Promise.all([loadRules(), loadAnnouncements(), loadBlackouts(), loadAudit()]).catch((e) => toast(e.message, true));
})();
